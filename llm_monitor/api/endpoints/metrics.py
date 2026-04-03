"""Metrics API endpoints."""

from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def get_metrics_summary():
    """Get overall metrics summary."""
    # TODO: Implement actual metrics calculation
    return {
        "total_requests": 0,
        "total_tokens": 0,
        "avg_latency_ms": 0.0,
        "success_rate": 100.0,
        "period_start": datetime.utcnow().isoformat(),
        "period_end": datetime.utcnow().isoformat(),
    }


@router.get("/by-model")
async def get_metrics_by_model():
    """Get metrics grouped by model."""
    # TODO: Implement actual metrics calculation
    return {
        "models": [],
    }
