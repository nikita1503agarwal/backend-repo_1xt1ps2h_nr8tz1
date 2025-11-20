"""
Database Schemas for GDSS (Software Engineer Selection)

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""

from pydantic import BaseModel, Field
from typing import Optional

class Candidate(BaseModel):
    id: str = Field(..., description="Candidate id (string)")
    name: str
    position: str
    photo_url: Optional[str] = None

class Criterion(BaseModel):
    id: str = Field(..., description="Criterion id (string)")
    name: str
    weight: float = Field(..., ge=0, le=1, description="Relative weight (0-1)")
    type: str = Field(..., pattern="^(Benefit|Cost)$", description="Benefit or Cost")

class Vote(BaseModel):
    userId: str
    candidateId: str
    criteriaId: str
    scoreValue: int = Field(..., ge=1, le=100)

class User(BaseModel):
    id: str
    role: str = Field(..., pattern="^(staff|chief)$")
    name: str
