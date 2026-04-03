"""vLLM metrics collector service with in-memory cache for instant model switching."""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from llm_monitor.core.config import settings
from llm_monitor.models.vllm import VLLMInstanceConfig, VLLMMetrics, VLLMMetricsAggregation

logger = logging.getLogger(__name__)

# Configuration file path
CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / "instances.json"


class MetricsCache:
    """In-memory cache for instant model switching.
    
    Maintains:
    - Latest metrics per instance
    - Aggregated metrics per model
    - Time-series data per model (limited window)
    """
    
    def __init__(self, max_points_per_model: int = 2000):
        """Initialize cache with configurable max points.
        
        Default 2000 points supports ~3.3 hours of data at 10s collection interval.
        This covers the max UI time range of 3 hours with some buffer.
        """
        self.max_points = max_points_per_model
        
        # Latest metrics per instance (for real-time display)
        self._latest_metrics: dict[str, VLLMMetrics] = {}
        
        # Time-series data per model (for charts)
        self._model_series: dict[str, list[dict]] = defaultdict(list)
        
        # Model aggregation cache (updated on each collection)
        self._model_aggregations: dict[str, VLLMMetricsAggregation] = {}
        
        # Model to instances mapping
        self._model_instances: dict[str, set[str]] = defaultdict(set)
        
        # Instance status cache
        self._instance_status: dict[str, bool] = {}
    
    def update(self, metrics: VLLMMetrics) -> None:
        """Update cache with new metrics."""
        instance_id = metrics.instance_id
        model_name = metrics.model_name
        
        # Update latest metrics
        self._latest_metrics[instance_id] = metrics
        self._instance_status[instance_id] = True
        
        # Update model-instance mapping
        self._model_instances[model_name].add(instance_id)
        
        # Update time series
        # Add 'Z' suffix to indicate UTC time for proper JavaScript parsing
        series_data = {
            "timestamp": metrics.timestamp.isoformat() + "Z",
            "avg_prompt_throughput": metrics.avg_prompt_throughput,
            "avg_generation_throughput": metrics.avg_generation_throughput,
            "running_requests": metrics.running_requests,
            "waiting_requests": metrics.waiting_requests,
            "gpu_kv_cache_usage": metrics.gpu_kv_cache_usage,
            "prefix_cache_hit_rate": metrics.prefix_cache_hit_rate,
            "external_prefix_cache_hit_rate": metrics.external_prefix_cache_hit_rate,
            "ttft": metrics.ttft,
            "tpot": metrics.tpot,
        }
        self._model_series[model_name].append(series_data)
        
        # Trim old data
        if len(self._model_series[model_name]) > self.max_points:
            self._model_series[model_name] = self._model_series[model_name][-self.max_points:]
        
        # Update aggregation
        self._update_aggregation(model_name)
    
    def _update_aggregation(self, model_name: str) -> None:
        """Calculate and cache model aggregation."""
        instance_ids = self._model_instances.get(model_name, set())
        
        if not instance_ids:
            return
        
        # Get all latest metrics for this model
        model_metrics = [
            self._latest_metrics[iid] 
            for iid in instance_ids 
            if iid in self._latest_metrics
        ]
        
        if not model_metrics:
            return
        
        # Calculate aggregations
        total_running = sum(m.running_requests for m in model_metrics)
        total_waiting = sum(m.waiting_requests for m in model_metrics)
        
        # Average throughput and cache metrics (exclude zeros for more accurate average)
        prompt_throughputs = [m.avg_prompt_throughput for m in model_metrics if m.avg_prompt_throughput > 0]
        gen_throughputs = [m.avg_generation_throughput for m in model_metrics if m.avg_generation_throughput > 0]
        gpu_cache_usages = [m.gpu_kv_cache_usage for m in model_metrics]
        prefix_hits = [m.prefix_cache_hit_rate for m in model_metrics]
        ext_prefix_hits = [m.external_prefix_cache_hit_rate for m in model_metrics]
        mm_hits = [m.mm_cache_hit_rate for m in model_metrics]
        ttfts = [m.ttft for m in model_metrics if m.ttft is not None]
        tpots = [m.tpot for m in model_metrics if m.tpot is not None]
        
        def safe_avg(vals: list) -> float:
            return sum(vals) / len(vals) if vals else 0.0
        
        self._model_aggregations[model_name] = VLLMMetricsAggregation(
            model_name=model_name,
            instances=list(instance_ids),
            total_running_requests=total_running,
            total_waiting_requests=total_waiting,
            avg_prompt_throughput=safe_avg(prompt_throughputs) if prompt_throughputs else safe_avg([m.avg_prompt_throughput for m in model_metrics]),
            avg_generation_throughput=safe_avg(gen_throughputs) if gen_throughputs else safe_avg([m.avg_generation_throughput for m in model_metrics]),
            avg_gpu_kv_cache_usage=safe_avg(gpu_cache_usages),
            avg_prefix_cache_hit_rate=safe_avg(prefix_hits),
            avg_external_prefix_cache_hit_rate=safe_avg(ext_prefix_hits),
            avg_mm_cache_hit_rate=safe_avg(mm_hits),
            avg_ttft=safe_avg(ttfts) if ttfts else None,
            avg_tpot=safe_avg(tpots) if tpots else None,
            timestamp=datetime.utcnow(),
        )
    
    def mark_offline(self, instance_id: str) -> None:
        """Mark an instance as offline."""
        self._instance_status[instance_id] = False
    
    def get_model_list(self) -> list[str]:
        """Get list of models with data."""
        return list(self._model_instances.keys())
    
    def get_model_aggregation(self, model_name: str) -> Optional[VLLMMetricsAggregation]:
        """Get cached aggregation for a model."""
        return self._model_aggregations.get(model_name)
    
    def get_all_aggregations(self) -> dict[str, VLLMMetricsAggregation]:
        """Get all cached aggregations."""
        return dict(self._model_aggregations)
    
    def get_model_series(self, model_name: str, minutes: int = 60) -> list[dict]:
        """Get time series for a model within time window."""
        series = self._model_series.get(model_name, [])
        if not series:
            return []
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        cutoff_str = cutoff.isoformat() + "Z"
        
        return [s for s in series if s["timestamp"] >= cutoff_str]
    
    def get_instance_status(self, instance_id: str) -> bool:
        """Get instance online status."""
        return self._instance_status.get(instance_id, False)
    
    def get_latest_metrics(self, instance_id: str) -> Optional[VLLMMetrics]:
        """Get latest metrics for an instance."""
        return self._latest_metrics.get(instance_id)
    
    def get_all_instance_metrics(self) -> dict[str, VLLMMetrics]:
        """Get all latest instance metrics."""
        return dict(self._latest_metrics)
    
    def clear_instance(self, instance_id: str) -> None:
        """Clear data for a removed instance."""
        if instance_id in self._latest_metrics:
            del self._latest_metrics[instance_id]
        if instance_id in self._instance_status:
            del self._instance_status[instance_id]


class VLLMMetricsCollector:
    """Collects metrics from vLLM instances with in-memory caching."""

    def __init__(self) -> None:
        self.instances: dict[str, VLLMInstanceConfig] = {}
        self.es_client: Optional[Elasticsearch] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Shared HTTP client for connection reuse
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Previous metrics for delta calculation
        self._prev_metrics: dict[str, dict[str, float]] = {}
        
        # In-memory cache for instant access
        self.cache = MetricsCache()
        
        # Metrics buffer for bulk ES write
        self._metrics_buffer: list[dict] = []
        self._buffer_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the collector."""
        try:
            logger.info(f"Connecting to Elasticsearch at {settings.elasticsearch_url}")
            self.es_client = Elasticsearch(
                settings.elasticsearch_url,
                verify_certs=False,
            )
            
            if self.es_client.ping():
                logger.info("Successfully connected to Elasticsearch")
            else:
                logger.warning("Failed to ping Elasticsearch, will retry later")
            
            # Initialize shared HTTP client with connection pool
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
            
            # Setup index template
            self._setup_index_template()
            
            # Load saved instances
            self._load_instances()
            
            # Preload cache from ES historical data
            await self._preload_cache_from_es()
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}", exc_info=True)
            self.es_client = None

    def _load_instances(self) -> None:
        """Load instances from config file."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for inst_data in data.get('instances', []):
                        inst = VLLMInstanceConfig(**inst_data)
                        self.instances[inst.id] = inst
                logger.info(f"Loaded {len(self.instances)} instances from config")
        except Exception as e:
            logger.error(f"Failed to load instances: {e}")

    def _save_instances(self) -> None:
        """Save instances to config file."""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {'instances': [inst.model_dump() for inst in self.instances.values()]}
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.instances)} instances to config")
        except Exception as e:
            logger.error(f"Failed to save instances: {e}")

    async def _preload_cache_from_es(self) -> None:
        """Preload cache with historical data from Elasticsearch on startup."""
        if not self.es_client:
            logger.warning("ES client not available, skipping cache preload")
            return
        
        try:
            # Get data from last 3 hours (matches max UI time range)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=3)
            
            # Query all metrics in time range
            result = self.es_client.search(
                index="vllm-metrics",
                body={
                    "query": {
                        "range": {
                            "timestamp": {
                                "gte": start_time.isoformat() + "Z",
                                "lte": end_time.isoformat() + "Z"
                            }
                        }
                    },
                    "size": 10000,  # Max points per model is 2000, so 10k should be enough
                    "sort": [{"timestamp": {"order": "asc"}}],
                    "_source": [
                        "timestamp", "instance_id", "instance_name", "model_name",
                        "avg_prompt_throughput", "avg_generation_throughput",
                        "running_requests", "waiting_requests", "gpu_kv_cache_usage",
                        "prefix_cache_hit_rate", "external_prefix_cache_hit_rate",
                        "mm_cache_hit_rate", "ttft", "tpot"
                    ]
                }
            )
            
            hits = result.get("hits", {}).get("hits", [])
            if not hits:
                logger.info("No historical data found in ES for cache preload")
                return
            
            # Process and cache each document
            for hit in hits:
                source = hit["_source"]
                try:
                    metrics = VLLMMetrics(
                        timestamp=datetime.fromisoformat(source["timestamp"].rstrip("Z")),
                        instance_id=source["instance_id"],
                        instance_name=source.get("instance_name", ""),
                        model_name=source.get("model_name", "unknown"),
                        model_status="on",
                        avg_prompt_throughput=source.get("avg_prompt_throughput", 0.0),
                        avg_generation_throughput=source.get("avg_generation_throughput", 0.0),
                        running_requests=source.get("running_requests", 0),
                        waiting_requests=source.get("waiting_requests", 0),
                        gpu_kv_cache_usage=source.get("gpu_kv_cache_usage", 0.0),
                        prefix_cache_hit_rate=source.get("prefix_cache_hit_rate", 0.0),
                        external_prefix_cache_hit_rate=source.get("external_prefix_cache_hit_rate", 0.0),
                        mm_cache_hit_rate=source.get("mm_cache_hit_rate", 0.0),
                        ttft=source.get("ttft"),
                        tpot=source.get("tpot"),
                    )
                    self.cache.update(metrics)
                except Exception as e:
                    logger.debug(f"Failed to process historical metric: {e}")
                    continue
            
            model_count = len(self.cache.get_model_list())
            logger.info(f"Preloaded cache with {len(hits)} metrics for {model_count} models from ES")
            
        except Exception as e:
            logger.error(f"Failed to preload cache from ES: {e}", exc_info=True)

    def _setup_index_template(self) -> None:
        """Setup ES index template with ILM policy."""
        if not self.es_client:
            return

        try:
            ilm_policy = {
                "policy": {
                    "phases": {
                        "hot": {
                            "min_age": "0ms",
                            "actions": {
                                "rollover": {"max_size": "50GB", "max_age": "7d"},
                                "set_priority": {"priority": 100}
                            }
                        },
                        "delete": {
                            "min_age": "30d",
                            "actions": {"delete": {}}
                        }
                    }
                }
            }
            self.es_client.ilm.put_lifecycle(name="vllm_metrics_policy", body=ilm_policy)
        except Exception as e:
            logger.warning(f"Failed to create ILM policy: {e}")

        try:
            template = {
                "index_patterns": ["vllm-metrics-*"],
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "index.lifecycle.name": "vllm_metrics_policy",
                    "index.lifecycle.rollover_alias": "vllm-metrics"
                },
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "instance_id": {"type": "keyword"},
                        "instance_name": {"type": "keyword"},
                        "model_name": {"type": "keyword"},
                        "model_status": {"type": "keyword"},
                        "avg_prompt_throughput": {"type": "float"},
                        "avg_generation_throughput": {"type": "float"},
                        "running_requests": {"type": "integer"},
                        "waiting_requests": {"type": "integer"},
                        "gpu_kv_cache_usage": {"type": "float"},
                        "prefix_cache_hit_rate": {"type": "float"},
                        "external_prefix_cache_hit_rate": {"type": "float"},
                        "mm_cache_hit_rate": {"type": "float"},
                        "ttft": {"type": "float"},
                        "tpot": {"type": "float"}
                    }
                }
            }
            self.es_client.indices.put_template(name="vllm_metrics_template", body=template)
            
            if not self.es_client.indices.exists(index="vllm-metrics-000001"):
                self.es_client.indices.create(
                    index="vllm-metrics-000001",
                    body={"aliases": {"vllm-metrics": {"is_write_index": True}}}
                )
        except Exception as e:
            logger.warning(f"Failed to setup index template: {e}")

    def add_instance(self, instance: VLLMInstanceConfig) -> None:
        """Add a vLLM instance to monitor."""
        if not instance.id:
            instance.id = f"{instance.host}:{instance.port}"
        self.instances[instance.id] = instance
        self._save_instances()
        logger.info(f"Added instance: {instance.id}")

    def remove_instance(self, instance_id: str) -> bool:
        """Remove a vLLM instance."""
        if instance_id in self.instances:
            del self.instances[instance_id]
            self.cache.clear_instance(instance_id)
            self._save_instances()
            logger.info(f"Removed instance: {instance_id}")
            return True
        return False

    def get_instances(self) -> list[VLLMInstanceConfig]:
        """Get all configured instances."""
        return list(self.instances.values())

    async def collect_metrics_from_instance(
        self, instance: VLLMInstanceConfig
    ) -> Optional[VLLMMetrics]:
        """Collect metrics from a single vLLM instance using shared HTTP client."""
        url = f"http://{instance.host}:{instance.port}/metrics"
        
        try:
            response = await self._http_client.get(url)
            if response.status_code != 200:
                logger.warning(f"Failed to get metrics from {instance.id}: status {response.status_code}")
                self.cache.mark_offline(instance.id)
                return None

            # Parse metrics based on engine type
            engine = getattr(instance, 'engine', 'vllm')
            if engine == 'sglang':
                metrics_data = self._parse_sglang_metrics(response.text)
            else:
                metrics_data = self._parse_prometheus_metrics(response.text)
            
            # Use configured model_name if provided
            if instance.model_name:
                metrics_data["model_name"] = instance.model_name
            
            # Calculate throughput from deltas
            current_prompt_tokens = metrics_data.get("prompt_tokens_total", 0)
            current_generation_tokens = metrics_data.get("generation_tokens_total", 0)
            
            prev = self._prev_metrics.get(instance.id, {})
            prev_prompt = prev.get("prompt_tokens_total", 0)
            prev_generation = prev.get("generation_tokens_total", 0)
            prev_time = prev.get("timestamp", datetime.utcnow())
            
            now = datetime.utcnow()
            time_delta = (now - prev_time).total_seconds()
            
            prompt_delta = current_prompt_tokens - prev_prompt
            generation_delta = current_generation_tokens - prev_generation
            
            prompt_throughput = prompt_delta / time_delta if time_delta > 0 and prompt_delta >= 0 else 0.0
            generation_throughput = generation_delta / time_delta if time_delta > 0 and generation_delta >= 0 else 0.0
            
            self._prev_metrics[instance.id] = {
                "prompt_tokens_total": current_prompt_tokens,
                "generation_tokens_total": current_generation_tokens,
                "timestamp": now
            }
            
            metrics = VLLMMetrics(
                timestamp=now,
                instance_id=instance.id,
                instance_name=instance.name,
                model_name=metrics_data.get("model_name", "unknown"),
                model_status="on",
                avg_prompt_throughput=prompt_throughput,
                avg_generation_throughput=generation_throughput,
                running_requests=int(metrics_data.get("num_requests_running", 0)),
                waiting_requests=int(metrics_data.get("num_requests_waiting", 0)),
                gpu_kv_cache_usage=metrics_data.get("gpu_cache_usage_perc", 0.0),
                prefix_cache_hit_rate=metrics_data.get("prefix_cache_hit_rate", 0.0),
                external_prefix_cache_hit_rate=metrics_data.get("external_prefix_cache_hit_rate", 0.0),
                mm_cache_hit_rate=metrics_data.get("mm_cache_hit_rate", 0.0),
                ttft=metrics_data.get("avg_ttft_ms"),
                tpot=metrics_data.get("avg_tpot_ms"),
            )
            
            # Update in-memory cache (instant access)
            self.cache.update(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting metrics from {instance.id}: {e}")
            self.cache.mark_offline(instance.id)
            return None

    def _parse_prometheus_metrics(self, content: str) -> dict[str, float]:
        """Parse Prometheus format metrics."""
        metrics = {}
        
        for line in content.split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            
            try:
                if "{" in line:
                    parts = line.rsplit(None, 1)
                    if len(parts) >= 2:
                        metric_part = parts[0]
                        value = float(parts[1])
                        metric_name = metric_part.split("{")[0] if "{" in metric_part else metric_part
                        metrics[metric_name] = value
                        
                        if 'model_name="' in line:
                            start = line.find('model_name="') + len('model_name="')
                            end = line.find('"', start)
                            metrics["model_name"] = line[start:end]
                else:
                    parts = line.split()
                    if len(parts) >= 2:
                        metrics[parts[0]] = float(parts[1])
            except (ValueError, IndexError):
                continue

        # Map to internal format
        result = {
            "num_requests_running": metrics.get("vllm:num_requests_running", 0),
            "num_requests_waiting": metrics.get("vllm:num_requests_waiting", 0),
            "gpu_cache_usage_perc": metrics.get("vllm:kv_cache_usage_perc", 0.0),
            "prompt_tokens_total": metrics.get("vllm:prompt_tokens_total", 0),
            "generation_tokens_total": metrics.get("vllm:generation_tokens_total", 0),
        }
        
        # Cache hit rates
        for name, q_key, h_key in [
            ("prefix_cache_hit_rate", "vllm:prefix_cache_queries_total", "vllm:prefix_cache_hits_total"),
            ("external_prefix_cache_hit_rate", "vllm:external_prefix_cache_queries_total", "vllm:external_prefix_cache_hits_total"),
            ("mm_cache_hit_rate", "vllm:mm_cache_queries_total", "vllm:mm_cache_hits_total"),
        ]:
            queries = metrics.get(q_key, 0)
            hits = metrics.get(h_key, 0)
            result[name] = hits / queries if queries > 0 else 0.0
        
        if "model_name" in metrics:
            result["model_name"] = metrics["model_name"]
        
        # TTFT and TPOT from histograms
        if "vllm:time_to_first_token_seconds_sum" in metrics and "vllm:time_to_first_token_seconds_count" in metrics:
            count = metrics["vllm:time_to_first_token_seconds_count"]
            if count > 0:
                result["avg_ttft_ms"] = (metrics["vllm:time_to_first_token_seconds_sum"] / count) * 1000
        
        if "vllm:request_time_per_output_token_seconds_sum" in metrics and "vllm:request_time_per_output_token_seconds_count" in metrics:
            count = metrics["vllm:request_time_per_output_token_seconds_count"]
            if count > 0:
                result["avg_tpot_ms"] = (metrics["vllm:request_time_per_output_token_seconds_sum"] / count) * 1000
        
        return result

    def _parse_sglang_metrics(self, content: str) -> dict[str, float]:
        """Parse SGLang Prometheus format metrics.
        
        SGLang uses different metric names than vLLM:
        - sglang:num_running_reqs (running requests)
        - sglang:num_queue_reqs (waiting requests in queue)
        - sglang:token_usage (kv cache usage ratio, 0-1)
        - sglang:prompt_tokens_total
        - sglang:generation_tokens_total
        - sglang:cache_hit_rate (prefix cache hit rate)
        - sglang:time_to_first_token_seconds_sum/_bucket{le="+Inf"} for TTFT
        - sglang:inter_token_latency_seconds_sum/_bucket{le="+Inf"} for TPOT
        """
        metrics = {}
        
        for line in content.split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            
            try:
                if "{" in line:
                    parts = line.rsplit(None, 1)
                    if len(parts) >= 2:
                        metric_part = parts[0]
                        value = float(parts[1])
                        metric_name = metric_part.split("{")[0] if "{" in metric_part else metric_part
                        metrics[metric_name] = value
                        
                        # Extract model_name from labels
                        if 'model_name="' in line:
                            start = line.find('model_name="') + len('model_name="')
                            end = line.find('"', start)
                            if end > start:
                                metrics["model_name"] = line[start:end]
                else:
                    parts = line.split()
                    if len(parts) >= 2:
                        metrics[parts[0]] = float(parts[1])
            except (ValueError, IndexError):
                continue

        # Map sglang metrics to internal format
        result = {
            "num_requests_running": metrics.get("sglang:num_running_reqs", 0),
            "num_requests_waiting": metrics.get("sglang:num_queue_reqs", 0),
            "gpu_cache_usage_perc": metrics.get("sglang:token_usage", 0.0) * 100,
            "prompt_tokens_total": metrics.get("sglang:prompt_tokens_total", 0),
            "generation_tokens_total": metrics.get("sglang:generation_tokens_total", 0),
        }
        
        # Cache hit rate - sglang provides this directly
        result["prefix_cache_hit_rate"] = metrics.get("sglang:cache_hit_rate", 0.0)
        
        # Model name
        if "model_name" in metrics:
            result["model_name"] = metrics["model_name"]
        
        # TTFT from histogram
        ttft_sum = metrics.get("sglang:time_to_first_token_seconds_sum")
        ttft_count = metrics.get("sglang:time_to_first_token_seconds_count")
        if ttft_sum is not None and ttft_count and ttft_count > 0:
            result["avg_ttft_ms"] = (ttft_sum / ttft_count) * 1000
        
        # TPOT from inter_token_latency histogram
        tpot_sum = metrics.get("sglang:inter_token_latency_seconds_sum")
        tpot_count = metrics.get("sglang:inter_token_latency_seconds_count")
        if tpot_sum is not None and tpot_count and tpot_count > 0:
            result["avg_tpot_ms"] = (tpot_sum / tpot_count) * 1000
        
        return result

    async def _store_bulk(self) -> None:
        """Bulk store buffered metrics to Elasticsearch."""
        if not self.es_client or not self._metrics_buffer:
            return
        
        async with self._buffer_lock:
            if not self._metrics_buffer:
                return
            
            buffer = self._metrics_buffer.copy()
            self._metrics_buffer.clear()
        
        try:
            actions = [
                {"_index": "vllm-metrics", "_source": doc}
                for doc in buffer
            ]
            success, _ = bulk(self.es_client, actions)
            logger.debug(f"Bulk stored {success} metrics to ES")
        except Exception as e:
            logger.error(f"Failed to bulk store metrics: {e}")

    async def collect_all_metrics(self) -> list[VLLMMetrics]:
        """Collect metrics from all enabled instances in parallel."""
        tasks = [
            self.collect_metrics_from_instance(inst)
            for inst in self.instances.values()
            if inst.enabled
        ]
        
        results = await asyncio.gather(*tasks)
        return [m for m in results if m is not None]

    async def _collection_loop(self) -> None:
        """Background collection loop with bulk ES storage."""
        while self._running:
            try:
                metrics_list = await self.collect_all_metrics()
                
                if metrics_list:
                    # Buffer for bulk write
                    for metrics in metrics_list:
                        doc = metrics.model_dump()
                        # Add 'Z' suffix to indicate UTC time
                        doc["timestamp"] = metrics.timestamp.isoformat() + "Z"
                        self._metrics_buffer.append(doc)
                        logger.info(f"Collected: {metrics.instance_id} - {metrics.model_name}")
                    
                    # Bulk store to ES
                    await self._store_bulk()
                    
                    logger.info(f"Collected metrics from {len(metrics_list)} instances")
                else:
                    logger.warning("No metrics collected")
                    
            except Exception as e:
                logger.error(f"Error in collection loop: {e}", exc_info=True)
            
            await asyncio.sleep(settings.collection_interval)

    def start(self) -> None:
        """Start the collection background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._collection_loop())
        logger.info("Started metrics collection")

    def stop(self) -> None:
        """Stop the collection background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Stopped metrics collection")

    async def close(self) -> None:
        """Cleanup resources."""
        self.stop()
        if self._http_client:
            await self._http_client.aclose()


# Global collector instance
collector = VLLMMetricsCollector()
