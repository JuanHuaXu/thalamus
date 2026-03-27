import json
import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API & Database
    host: str = "0.0.0.0"
    port: int = 8080
    api_key: Optional[str] = None
    cognee_api_url: str = "http://localhost:8000"
    cognee_api_key: Optional[str] = None
    cognee_dataset_name: Optional[str] = None
    
    # RDBMS Stubbing
    enable_rdbms: bool = False
    database_url: Optional[str] = None
    sessions_dir: Optional[str] = None
    
    # Middleware Logic
    cognify_debounce_ms: int = 5000
    cache_ttl_seconds: int = 300
    webhook_urls: List[str] = []
    webhook_secret: Optional[str] = None

    # Scaling & Mitigation Parameters
    verified_dispute_threshold: int = 5
    unverified_dispute_threshold: int = 2
    initial_dynamic_threshold: int = 5
    ingestion_queue_max_size: int = 1000
    crawler_timeout: float = 15.0
    crawler_user_agent: str = "Thalamus/0.1.0"
    llm_provider_url: Optional[str] = None
    llm_model_name: str = "llama3:8b"
    llm_auto_pull: bool = True
    
    # Ingestion & Sanitization
    max_message_size: int = 1000000 # 1MB limit for single message content
    consolidation_cluster_size: int = 5
    db_path: str = "thalamus.db"
    
    # LSA & Pressure thresholds
    pressure_threshold_high: float = 0.8
    pressure_threshold_critical: float = 0.95

    # Pulse Goal Lifecycle
    pulse_goal_ttl_seconds: int = 86400        # 24h — pending goals older than this are evicted
    pulse_completed_ttl_seconds: int = 604800  # 7 days — completed/failed goals older than this are purged
    pulse_dedup_enabled: bool = True

    @classmethod
    def load(cls):
        # Look for config.json in the project root (3 levels up from this file)
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        config_path = os.getenv("THALAMUS_CONFIG_PATH") or (project_root / "config.json")
        
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config_data = json.load(f)
                return cls(**config_data)
        return cls()

settings = Settings.load()
print(f"[Thalamus] Loaded config from Cognee URL: {settings.cognee_api_url}")
