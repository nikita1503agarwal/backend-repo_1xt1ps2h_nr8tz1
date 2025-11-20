import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
import random

from database import db, create_document, get_documents

app = FastAPI(title="GDSS for Software Engineer Selection")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Models
# -----------------------------

class LoginRequest(BaseModel):
    role: str = Field(..., pattern=r"^(staff|chief)$")
    name: str | None = None

class LoginResponse(BaseModel):
    id: str
    role: str
    name: str

class ScoreInput(BaseModel):
    criteriaId: str
    scoreValue: int = Field(..., ge=1, le=100)

class RateRequest(BaseModel):
    userId: str
    candidateId: str
    scores: List[ScoreInput]

# -----------------------------
# Mock/In-Memory Storage Fallback
# -----------------------------

MOCK_MODE = os.getenv("MOCK_MODE", "0") == "1" or db is None

MEM: Dict[str, Any] = {
    "candidates": [],
    "criteria": [],
    "votes": [],
    "users": [],
}

# -----------------------------
# Helpers & Bootstrapping
# -----------------------------

DEFAULT_CANDIDATES = [
    {
        "id": "cand-1",
        "name": "Alice Engineer",
        "position": "Software Engineer",
        "photo_url": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&auto=format&fit=crop&q=60",
    },
    {
        "id": "cand-2",
        "name": "Bob Developer",
        "position": "Backend Developer",
        "photo_url": "https://images.unsplash.com/photo-1552374196-c4e7ffc6e126?w=400&auto=format&fit=crop&q=60",
    },
    {
        "id": "cand-3",
        "name": "Carla Coder",
        "position": "Frontend Engineer",
        "photo_url": "https://images.unsplash.com/photo-1607746882042-944635dfe10e?w=400&auto=format&fit=crop&q=60",
    },
    {
        "id": "cand-4",
        "name": "Diego Architect",
        "position": "Full‑stack Engineer",
        "photo_url": "https://images.unsplash.com/photo-1547425260-76bcadfb4f2c?w=400&auto=format&fit=crop&q=60",
    },
    {
        "id": "cand-5",
        "name": "Eva Programmer",
        "position": "Mobile Engineer",
        "photo_url": "https://images.unsplash.com/photo-1502685104226-ee32379fefbe?w=400&auto=format&fit=crop&q=60",
    },
]

DEFAULT_CRITERIA = [
    {"id": "coding", "name": "Coding Skill", "weight": 0.4, "type": "Benefit"},
    {"id": "comm", "name": "Communication", "weight": 0.3, "type": "Benefit"},
    {"id": "exp", "name": "Experience", "weight": 0.3, "type": "Benefit"},
]

def _seed_mock_if_needed():
    # Seed candidates and criteria
    if not MEM["candidates"]:
        MEM["candidates"] = [c.copy() for c in DEFAULT_CANDIDATES]
    if not MEM["criteria"]:
        MEM["criteria"] = [c.copy() for c in DEFAULT_CRITERIA]

    # Seed demo votes from 3 decision makers so Chief dashboard shows results
    if not MEM["votes"]:
        dm_users = [
            {"id": "dm-1", "role": "staff", "name": "Decision Maker 1"},
            {"id": "dm-2", "role": "staff", "name": "Decision Maker 2"},
            {"id": "dm-3", "role": "staff", "name": "Decision Maker 3"},
        ]
        MEM["users"].extend(dm_users)
        rng = random.Random(42)
        now = datetime.utcnow()
        for u in dm_users:
            for cand in MEM["candidates"]:
                # generate deterministic but varied scores per criterion
                scores = {}
                for crit in MEM["criteria"]:
                    base = 60 + rng.randint(-20, 20)
                    # slight bias so rankings differentiate
                    adjust = (hash(cand["id"] + crit["id"] + u["id"]) % 15) - 7
                    val = max(1, min(100, base + adjust))
                    scores[crit["id"]] = val
                for crit_id, score in scores.items():
                    MEM["votes"].append({
                        "userId": u["id"],
                        "candidateId": cand["id"],
                        "criteriaId": crit_id,
                        "scoreValue": score,
                        "created_at": now,
                        "updated_at": now,
                    })


def ensure_seed_data() -> None:
    """Ensure default candidates and criteria exist in DB or in-memory. If DB ops fail, fallback to mock mode."""
    global MOCK_MODE
    if MOCK_MODE:
        _seed_mock_if_needed()
        return

    try:
        # Criteria
        criteria_count = db["criterion"].count_documents({}) if db else 0
        if criteria_count == 0:
            for c in DEFAULT_CRITERIA:
                create_document("criterion", c)

        # Candidates
        candidate_count = db["candidate"].count_documents({}) if db else 0
        if candidate_count == 0:
            for p in DEFAULT_CANDIDATES:
                create_document("candidate", p)
    except Exception:
        # Any DB issue -> switch to mock immediately
        MOCK_MODE = True
        _seed_mock_if_needed()


def get_all_candidates() -> List[Dict[str, Any]]:
    ensure_seed_data()
    if MOCK_MODE:
        return MEM["candidates"]
    return get_documents("candidate")


def get_all_criteria() -> List[Dict[str, Any]]:
    ensure_seed_data()
    if MOCK_MODE:
        return MEM["criteria"]
    return get_documents("criterion")

# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def root():
    return {"message": "GDSS Backend Running", "mode": "mock" if MOCK_MODE else "db"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "mode": "mock" if MOCK_MODE else "db",
        "database": "❌ Not Available" if db is None else "✅ Connected",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": os.getenv("DATABASE_NAME") or None,
        "collections": []
    }
    try:
        if db is not None:
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response


@app.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    name = payload.name or ("Chief Manager" if payload.role == "chief" else f"Decision Maker #{str(uuid4())[:6]}")
    user_id = f"{payload.role}-{str(uuid4())[:8]}"
    user_doc = {"id": user_id, "role": payload.role, "name": name}

    if MOCK_MODE:
        MEM["users"].append(user_doc)
        return LoginResponse(**user_doc)

    create_document("user", user_doc)
    return LoginResponse(**user_doc)


@app.get("/candidates")
def list_candidates():
    return {"data": get_all_candidates()}


@app.get("/criteria")
def list_criteria():
    return {"data": get_all_criteria()}


@app.get("/rated")
def rated_candidates(userId: str = Query(...)):
    # list candidateIds already rated by this user
    if MOCK_MODE:
        cand_ids = list({v["candidateId"] for v in MEM["votes"] if v["userId"] == userId})
        return {"data": cand_ids}

    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    cand_ids = db["vote"].distinct("candidateId", {"userId": userId})
    return {"data": cand_ids}


@app.post("/rate")
def rate_candidate(payload: RateRequest):
    """Save ratings for a candidate by a specific user. Prevent duplicate ratings per candidate per user."""
    # Validate criteria ids exist
    criteria = {c["id"]: c for c in get_all_criteria()}
    for s in payload.scores:
        if s.criteriaId not in criteria:
            raise HTTPException(status_code=400, detail=f"Invalid criteria: {s.criteriaId}")

    if MOCK_MODE:
        # Prevent duplicate
        has = any(v for v in MEM["votes"] if v["userId"] == payload.userId and v["candidateId"] == payload.candidateId)
        if has:
            raise HTTPException(status_code=400, detail="You have already rated this candidate.")
        now = datetime.utcnow()
        for s in payload.scores:
            MEM["votes"].append({
                "userId": payload.userId,
                "candidateId": payload.candidateId,
                "criteriaId": s.criteriaId,
                "scoreValue": s.scoreValue,
                "created_at": now,
                "updated_at": now,
            })
        return {"status": "ok", "inserted": len(payload.scores)}

    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    existing = db["vote"].find_one({"userId": payload.userId, "candidateId": payload.candidateId})
    if existing:
        raise HTTPException(status_code=400, detail="You have already rated this candidate.")

    docs = []
    now = datetime.utcnow()
    for s in payload.scores:
        docs.append({
            "userId": payload.userId,
            "candidateId": payload.candidateId,
            "criteriaId": s.criteriaId,
            "scoreValue": s.scoreValue,
            "created_at": now,
            "updated_at": now,
        })
    if docs:
        db["vote"].insert_many(docs)

    return {"status": "ok", "inserted": len(docs)}


@app.get("/stats")
def stats():
    if MOCK_MODE:
        total_candidates = len(MEM["candidates"]) if MEM["candidates"] else 0
        total_dms = len({v["userId"] for v in MEM["votes"]})
        return {"totalCandidates": total_candidates, "totalDecisionMakers": total_dms}

    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    total_candidates = db["candidate"].count_documents({})
    total_dms = len(db["vote"].distinct("userId"))
    return {"totalCandidates": total_candidates, "totalDecisionMakers": total_dms}


@app.get("/results")
def results():
    """Calculate Group Decision using WP (per user) + Borda aggregation"""
    candidates = get_all_candidates()
    criteria = get_all_criteria()

    if MOCK_MODE:
        votes = list(MEM["votes"])  # copy
    else:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not available")
        votes = list(db["vote"].find({}))

    if not candidates:
        return {"data": []}

    # Organize votes: user -> candidate -> criteriaId -> score
    user_groups: Dict[str, Dict[str, Dict[str, int]]] = {}
    for v in votes:
        user = v["userId"]
        cand = v["candidateId"]
        crit = v["criteriaId"]
        score = v["scoreValue"]
        user_groups.setdefault(user, {}).setdefault(cand, {})[crit] = score

    candidate_ids = [c["id"] for c in candidates]
    crit_defs = {c["id"]: c for c in criteria}

    # Step A: For each user, compute WP vector S for every candidate
    user_rankings: Dict[str, List[str]] = {}  # userId -> list of candidateIds ranked best->worst

    for user_id, cand_scores in user_groups.items():
        S: Dict[str, float] = {cid: 0.0 for cid in candidate_ids}
        for cid in candidate_ids:
            product = 1.0
            scores_for_candidate = cand_scores.get(cid, {})
            for crit_id, crit in crit_defs.items():
                # Normalize to 0..1 (avoid zero by setting a tiny epsilon)
                score = scores_for_candidate.get(crit_id, 1)  # if missing, minimal 1
                x = max(1, min(100, score)) / 100.0
                w = float(crit.get("weight", 0))
                if crit.get("type") == "Cost":
                    # Standard WP handling for cost: negative weight exponent
                    product *= pow(x, -w if w != 0 else 0)
                else:
                    product *= pow(x, w)
            S[cid] = product
        # Rank candidates by S desc
        ranked = sorted(candidate_ids, key=lambda k: S[k], reverse=True)
        user_rankings[user_id] = ranked

    # Step B: Borda Count Aggregation
    N = len(candidate_ids)
    total_points: Dict[str, int] = {cid: 0 for cid in candidate_ids}

    for ranking in user_rankings.values():
        for idx, cid in enumerate(ranking):
            points = N - idx  # top gets N, next N-1, ...
            total_points[cid] += points

    # Build final table
    enriched = []
    cand_map = {c["id"]: c for c in candidates}
    for cid in candidate_ids:
        enriched.append({
            "candidateId": cid,
            "name": cand_map[cid]["name"],
            "position": cand_map[cid].get("position"),
            "photo_url": cand_map[cid].get("photo_url"),
            "totalBordaPoints": total_points.get(cid, 0),
        })

    enriched.sort(key=lambda x: x["totalBordaPoints"], reverse=True)

    # Assign ranks, handle ties with same points -> same rank numbers compacted style
    rank = 0
    last_points = None
    for idx, item in enumerate(enriched, start=1):
        if item["totalBordaPoints"] != last_points:
            rank = idx
            last_points = item["totalBordaPoints"]
        item["rank"] = rank

    return {"data": enriched}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
