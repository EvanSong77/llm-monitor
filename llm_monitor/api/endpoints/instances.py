"""vLLM instances management endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from llm_monitor.models.vllm import VLLMInstanceConfig
from llm_monitor.services.vllm_collector import collector

router = APIRouter()


@router.get("/", response_model=list[VLLMInstanceConfig])
async def list_instances():
    """List all configured vLLM instances."""
    return collector.get_instances()


@router.post("/", response_model=VLLMInstanceConfig)
async def add_instance(instance: VLLMInstanceConfig):
    """Add a new vLLM instance to monitor."""
    collector.add_instance(instance)
    return instance


@router.post("/reload")
async def reload_instances():
    """Reload instances from config file."""
    collector._load_instances()
    instances = collector.get_instances()
    return {
        "message": "Configuration reloaded",
        "instances_count": len(instances),
        "instances": [{"id": inst.id, "name": inst.name} for inst in instances]
    }


@router.get("/{instance_id}", response_model=VLLMInstanceConfig)
async def get_instance(instance_id: str):
    """Get a specific vLLM instance configuration."""
    instances = collector.get_instances()
    for inst in instances:
        if inst.id == instance_id:
            return inst
    raise HTTPException(status_code=404, detail="Instance not found")


@router.put("/{instance_id}", response_model=VLLMInstanceConfig)
async def update_instance(instance_id: str, instance: VLLMInstanceConfig):
    """Update a vLLM instance configuration."""
    instance.id = instance_id
    collector.add_instance(instance)
    return instance


@router.delete("/{instance_id}")
async def delete_instance(instance_id: str):
    """Remove a vLLM instance from monitoring."""
    if not collector.remove_instance(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")
    return {"message": "Instance removed"}


@router.post("/{instance_id}/toggle")
async def toggle_instance(instance_id: str, enabled: Optional[bool] = None):
    """Enable or disable monitoring for an instance."""
    instances = collector.get_instances()
    for inst in instances:
        if inst.id == instance_id:
            inst.enabled = enabled if enabled is not None else not inst.enabled
            return {"message": f"Instance {'enabled' if inst.enabled else 'disabled'}"}
    raise HTTPException(status_code=404, detail="Instance not found")


@router.post("/test-collect")
async def test_collect():
    """Manually trigger metrics collection for testing."""
    try:
        metrics_list = await collector.collect_all_metrics()
        results = []
        for metrics in metrics_list:
            success = await collector.store_metrics(metrics)
            results.append({
                "instance_id": metrics.instance_id,
                "model_name": metrics.model_name,
                "stored": success
            })
        return {
            "collected": len(metrics_list),
            "results": results
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
