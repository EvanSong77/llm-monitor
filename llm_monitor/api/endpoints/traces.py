"""Trace API endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class TraceCreate(BaseModel):
    """Trace creation schema."""

    request_id: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    status: str = "success"
    metadata: dict = Field(default_factory=dict)


class TraceResponse(TraceCreate):
    """Trace response schema."""

    id: str
    created_at: datetime


@router.post("/", response_model=TraceResponse)
async def create_trace(trace: TraceCreate):
    """Create a new trace record."""
    # TODO: Implement actual storage
    return TraceResponse(
        id=trace.request_id,
        **trace.model_dump(),
        created_at=datetime.utcnow(),
    )


@router.get("/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str):
    """Get trace by ID."""
    # TODO: Implement actual retrieval
    raise HTTPException(status_code=404, detail="Trace not found")
