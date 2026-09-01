from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    google_vision_api_key: str = os.getenv("GOOGLE_VISION_API_KEY", "")
    chain_api_url: str = os.getenv("CHAIN_API_URL", "http://127.0.0.1:8546")
    public_api_url: str = os.getenv("PUBLIC_API_URL", "http://localhost:8000")
    require_face_confirmation: bool = os.getenv("REQUIRE_FACE_CONFIRMATION", "false").lower() == "true"
    vision_timeout_seconds: int = int(os.getenv("VISION_TIMEOUT_SECONDS", "45"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    data_dir: Path = ROOT / "data"
    model_dir: Path = ROOT / "backend" / "models"


settings = Settings()
