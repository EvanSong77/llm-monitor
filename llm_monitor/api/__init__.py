"""API module."""

from fastapi import APIRouter

from llm_monitor.api.endpoints import instances, metrics, traces, vllm_metrics

router = APIRouter()
router.include_router(traces.router, prefix="/traces", tags=["traces"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(instances.router, prefix="/instances", tags=["instances"])
router.include_router(vllm_metrics.router, prefix="/vllm", tags=["vllm"])
