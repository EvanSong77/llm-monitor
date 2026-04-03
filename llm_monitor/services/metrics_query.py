"""Metrics query service - reads from in-memory cache for instant response."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from elasticsearch import Elasticsearch

from llm_monitor.core.config import settings
from llm_monitor.models.vllm import VLLMMetricsAggregation

logger = logging.getLogger(__name__)


class MetricsQueryService:
    """Query metrics from cache (instant) or Elasticsearch (fallback)."""

    def __init__(self) -> None:
        self.es_client: Optional[Elasticsearch] = None
        # Reference to collector's cache (set during initialization)
        self._cache = None

    async def initialize(self) -> None:
        """Initialize ES client (for historical queries)."""
        self.es_client = Elasticsearch(
            settings.elasticsearch_url,
            verify_certs=False,
        )

    def set_cache(self, cache) -> None:
        """Set reference to metrics cache."""
        self._cache = cache

    async def get_models_list(self) -> list[str]:
        """Get list of unique model names - from cache for instant response."""
        if self._cache:
            cached = self._cache.get_model_list()
            if cached:  # Only return cache if it has data
                return cached
        
        # Fallback to ES (when cache is empty or unavailable)
        return await self._get_models_from_es()

    async def _get_models_from_es(self) -> list[str]:
        """Fallback: get models from Elasticsearch."""
        if not self.es_client:
            return []

        try:
            result = self.es_client.search(
                index="vllm-metrics",
                body={
                    "size": 0,
                    "aggs": {
                        "models": {
                            "terms": {"field": "model_name", "size": 100}
                        }
                    }
                }
            )
            buckets = result.get("aggregations", {}).get("models", {}).get("buckets", [])
            return [b["key"] for b in buckets]
        except Exception as e:
            logger.error(f"Failed to get models list: {e}")
            return []

    async def get_model_metrics(
        self,
        model_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[dict]:
        """Get metrics for a specific model - from cache for instant response."""
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        
        minutes = int((end_time - start_time).total_seconds() / 60)
        
        # Get from cache (instant)
        if self._cache:
            cached = self._cache.get_model_series(model_name, minutes=minutes)
            if cached:
                return cached
        
        # Fallback to ES
        return await self._get_metrics_from_es(model_name, start_time, end_time)

    async def _get_metrics_from_es(
        self,
        model_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Fallback: get metrics from Elasticsearch."""
        if not self.es_client:
            return []

        try:
            result = self.es_client.search(
                index="vllm-metrics",
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"model_name": model_name}},
                                {
                                    "range": {
                                        "timestamp": {
                                            "gte": start_time.isoformat() + "Z",
                                            "lte": end_time.isoformat() + "Z"
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    "size": 500,
                    "sort": [{"timestamp": {"order": "asc"}}],
                    "_source": [
                        "timestamp",
                        "avg_prompt_throughput",
                        "avg_generation_throughput",
                        "running_requests",
                        "waiting_requests",
                        "gpu_kv_cache_usage",
                        "prefix_cache_hit_rate",
                        "external_prefix_cache_hit_rate"
                    ]
                }
            )
            
            hits = result.get("hits", {}).get("hits", [])
            return [hit["_source"] for hit in hits]
        except Exception as e:
            logger.error(f"Failed to get model metrics: {e}")
            return []

    async def get_aggregated_metrics(
        self,
        model_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Optional[VLLMMetricsAggregation]:
        """Get aggregated metrics for a model - from cache for instant response."""
        # Get from cache (instant)
        if self._cache:
            cached = self._cache.get_model_aggregation(model_name)
            if cached:
                return cached
        
        # Fallback to ES
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(minutes=5)
        
        return await self._get_aggregated_from_es(model_name, start_time, end_time)

    async def _get_aggregated_from_es(
        self,
        model_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[VLLMMetricsAggregation]:
        """Fallback: get aggregated metrics from Elasticsearch."""
        if not self.es_client:
            return None

        try:
            result = self.es_client.search(
                index="vllm-metrics",
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"model_name": model_name}},
                                {
                                    "range": {
                                        "timestamp": {
                                            "gte": start_time.isoformat() + "Z",
                                            "lte": end_time.isoformat() + "Z"
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    "size": 0,
                    "aggs": {
                        "instances": {
                            "terms": {"field": "instance_id", "size": 100},
                            "aggs": {
                                "latest_doc": {
                                    "top_hits": {
                                        "sort": [{"timestamp": {"order": "desc"}}],
                                        "size": 1,
                                        "_source": ["running_requests", "waiting_requests"]
                                    }
                                }
                            }
                        },
                        "avg_prompt_throughput": {"avg": {"field": "avg_prompt_throughput"}},
                        "avg_generation_throughput": {"avg": {"field": "avg_generation_throughput"}},
                        "avg_gpu_kv_cache_usage": {"avg": {"field": "gpu_kv_cache_usage"}},
                        "avg_prefix_cache_hit_rate": {"avg": {"field": "prefix_cache_hit_rate"}},
                        "avg_external_prefix_cache_hit_rate": {"avg": {"field": "external_prefix_cache_hit_rate"}},
                        "avg_mm_cache_hit_rate": {"avg": {"field": "mm_cache_hit_rate"}},
                        "avg_ttft": {"avg": {"field": "ttft"}},
                        "avg_tpot": {"avg": {"field": "tpot"}},
                        "latest_timestamp": {"max": {"field": "timestamp"}}
                    }
                }
            )
            
            aggs = result.get("aggregations", {})
            if not aggs:
                return None
            
            total_running = 0
            total_waiting = 0
            instances = []
            
            for bucket in aggs.get("instances", {}).get("buckets", []):
                instances.append(bucket["key"])
                latest_docs = bucket.get("latest_doc", {}).get("hits", {}).get("hits", [])
                if latest_docs:
                    source = latest_docs[0].get("_source", {})
                    total_running += source.get("running_requests", 0)
                    total_waiting += source.get("waiting_requests", 0)

            return VLLMMetricsAggregation(
                model_name=model_name,
                instances=instances,
                total_running_requests=total_running,
                total_waiting_requests=total_waiting,
                avg_prompt_throughput=aggs.get("avg_prompt_throughput", {}).get("value") or 0.0,
                avg_generation_throughput=aggs.get("avg_generation_throughput", {}).get("value") or 0.0,
                avg_gpu_kv_cache_usage=aggs.get("avg_gpu_kv_cache_usage", {}).get("value") or 0.0,
                avg_prefix_cache_hit_rate=aggs.get("avg_prefix_cache_hit_rate", {}).get("value") or 0.0,
                avg_external_prefix_cache_hit_rate=aggs.get("avg_external_prefix_cache_hit_rate", {}).get("value") or 0.0,
                avg_mm_cache_hit_rate=aggs.get("avg_mm_cache_hit_rate", {}).get("value") or 0.0,
                avg_ttft=aggs.get("avg_ttft", {}).get("value"),
                avg_tpot=aggs.get("avg_tpot", {}).get("value"),
                timestamp=datetime.fromisoformat(
                    aggs.get("latest_timestamp", {}).get("value_as_string", datetime.utcnow().isoformat())
                ),
            )
        except Exception as e:
            logger.error(f"Failed to get aggregated metrics: {e}")
            return None

    async def get_all_models_aggregated(self) -> dict[str, VLLMMetricsAggregation]:
        """Get aggregated metrics for all models - from cache for instant response."""
        if self._cache:
            cached = self._cache.get_all_aggregations()
            if cached:  # Only return cache if it has data
                return cached
        
        # Fallback: query each model from ES (when cache is empty or unavailable)
        models = await self.get_models_list()
        result = {}
        for model in models:
            agg = await self.get_aggregated_metrics(model)
            if agg:
                result[model] = agg
        return result


# Global query service instance
query_service = MetricsQueryService()
