"""vLLM monitoring models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VLLMInstanceConfig(BaseModel):
    """vLLM instance configuration."""

    id: Optional[str] = None
    name: str = Field(..., description="Instance name")
    host: str = Field(..., description="Host IP")
    port: int = Field(default=8000, description="Port number")
    enabled: bool = Field(default=True, description="Whether to monitor this instance")
    engine: str = Field(default="vllm", description="Engine type: vllm or sglang")
    model_name: Optional[str] = Field(default=None, description="Model name override")


class VLLMMetrics(BaseModel):
    """vLLM metrics data."""

    timestamp: datetime
    instance_id: str
    instance_name: str
    model_name: str
    model_status: str = Field(description="on / off")
    
    # Throughput metrics
    avg_prompt_throughput: float = Field(default=0.0, description="Tokens/s")
    avg_generation_throughput: float = Field(default=0.0, description="Tokens/s")
    
    # Request queue metrics
    running_requests: int = Field(default=0)
    waiting_requests: int = Field(default=0)
    
    # Cache metrics
    gpu_kv_cache_usage: float = Field(default=0.0, description="0-1 ratio")
    prefix_cache_hit_rate: float = Field(default=0.0, description="0-1 ratio")
    external_prefix_cache_hit_rate: float = Field(default=0.0, description="0-1 ratio")
    mm_cache_hit_rate: float = Field(default=0.0, description="0-1 ratio")
    
    # Latency metrics
    ttft: Optional[float] = Field(default=None, description="Time to First Token (ms)")
    tpot: Optional[float] = Field(default=None, description="Time Per Output Token (ms)")


class VLLMMetricsAggregation(BaseModel):
    """Aggregated vLLM metrics by model."""

    model_name: str
    instances: list[str] = Field(default_factory=list)
    total_running_requests: int = 0
    total_waiting_requests: int = 0
    avg_prompt_throughput: float = 0.0
    avg_generation_throughput: float = 0.0
    avg_gpu_kv_cache_usage: float = 0.0
    avg_prefix_cache_hit_rate: float = 0.0
    avg_external_prefix_cache_hit_rate: float = 0.0
    avg_mm_cache_hit_rate: float = 0.0
    avg_ttft: Optional[float] = None
    avg_tpot: Optional[float] = None
    timestamp: datetime
