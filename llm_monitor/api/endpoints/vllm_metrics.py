"""vLLM metrics query endpoints with instant cache response."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from llm_monitor.services.metrics_query import query_service
from llm_monitor.services.vllm_collector import collector

router = APIRouter()


async def check_instance_status(inst):
    """Check if an instance is online with timeout."""
    try:
        # First check cache for instant response
        cached_status = collector.cache.get_instance_status(inst.id)
        if collector.cache.get_latest_metrics(inst.id):
            metrics = collector.cache.get_latest_metrics(inst.id)
            return {
                "id": inst.id,
                "name": inst.name,
                "host": inst.host,
                "port": inst.port,
                "online": True,
                "model_name": metrics.model_name if metrics else None,
                "engine": inst.engine
            }
        
        # Fallback: actual HTTP check
        metrics = await asyncio.wait_for(
            collector.collect_metrics_from_instance(inst),
            timeout=2.0
        )
        is_online = metrics is not None
        model_name = metrics.model_name if metrics else None
    except asyncio.TimeoutError:
        is_online = False
        model_name = None
    except Exception:
        is_online = False
        model_name = None

    return {
        "id": inst.id,
        "name": inst.name,
        "host": inst.host,
        "port": inst.port,
        "online": is_online,
        "model_name": model_name,
        "engine": inst.engine
    }


@router.get("/instances-with-status")
async def get_instances_with_status():
    """Get list of all enabled instances with their online status - optimized with cache."""
    instances = collector.get_instances()
    enabled_instances = [inst for inst in instances if inst.enabled]
    
    # Check all instances concurrently
    tasks = [check_instance_status(inst) for inst in enabled_instances]
    instances_status = await asyncio.gather(*tasks, return_exceptions=True)
    
    instances_status = [
        result for result in instances_status
        if isinstance(result, dict)
    ]

    return {"instances": instances_status}


@router.get("/models")
async def get_models():
    """Get list of all monitored models - from cache for instant response."""
    models = await query_service.get_models_list()
    return {"models": models}


@router.get("/models/{model_name}/metrics")
async def get_model_metrics(
    model_name: str,
    minutes: int = Query(default=60, description="Time window in minutes"),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """Get raw metrics for a specific model - from cache for instant response."""
    if not end_time:
        end_time = datetime.utcnow()
    if not start_time:
        start_time = end_time - timedelta(minutes=minutes)

    metrics = await query_service.get_model_metrics(model_name, start_time, end_time)
    return {
        "model_name": model_name,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
        "count": len(metrics),
        "metrics": metrics,
    }


@router.get("/models/{model_name}/aggregated")
async def get_model_aggregated(
    model_name: str,
    minutes: int = Query(default=5, description="Time window in minutes"),
):
    """Get aggregated metrics for a specific model - from cache for instant response."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)
    
    agg = await query_service.get_aggregated_metrics(model_name, start_time, end_time)
    if not agg:
        return {"error": "No metrics found for this model"}
    
    # Custom serialization to add 'Z' suffix for UTC timestamps
    result = agg.model_dump()
    if 'timestamp' in result and result['timestamp']:
        # Convert datetime to ISO string with 'Z' suffix
        result['timestamp'] = agg.timestamp.isoformat() + "Z"
    return result


@router.get("/aggregated")
async def get_all_aggregated(
    minutes: int = Query(default=5, description="Time window in minutes"),
):
    """Get aggregated metrics for all models - from cache for instant response."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)
    
    # Get all aggregations from cache (instant)
    all_aggs = await query_service.get_all_models_aggregated()
    
    result = {}
    for model_name, agg in all_aggs.items():
        model_data = agg.model_dump()
        # Add 'Z' suffix for UTC timestamps
        if 'timestamp' in model_data and model_data['timestamp']:
            model_data['timestamp'] = agg.timestamp.isoformat() + "Z"
        result[model_name] = model_data
    
    return {
        "timestamp": end_time.isoformat() + "Z",
        "time_window_minutes": minutes,
        "models": result,
    }


@router.get("/cache-status")
async def get_cache_status():
    """Get cache status for debugging."""
    return {
        "models": collector.cache.get_model_list(),
        "model_count": len(collector.cache.get_model_list()),
        "aggregations": len(collector.cache.get_all_aggregations()),
    }
