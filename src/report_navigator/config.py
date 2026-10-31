"""Configuration loaded explicitly, without creating clients at import time."""

import os
import tempfile
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)

from .schemas import BackendError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    model: Literal["gemma-4-26b-a4b-it", "gemma-4-31b-it"] = "gemma-4-26b-a4b-it"
    cache_dir: Path = Path(tempfile.gettempdir()) / "report-navigator-cache"
    cache_enabled: bool = True
    answer_mode: Literal["offline", "hosted"] = "offline"
    ocr_enabled: bool = True
    tessdata_dir: Path = PROJECT_ROOT / "models" / "tessdata"
    ocr_dpi: int = Field(default=300, ge=100, le=400)
    ocr_page_seconds: float = Field(default=25, ge=1, le=60)
    runtime_seconds: float = Field(default=1100, ge=1, le=1150)
    candidate_count: int = Field(default=40, ge=6, le=100)
    chunk_words: int = Field(default=400, ge=50, le=800)
    overlap_words: int = Field(default=50, ge=0)
    min_native_chars: int = Field(default=30, ge=1)
    max_pdf_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_pages: int = Field(default=1000, ge=1)
    max_question_chars: int = Field(default=2000, ge=1)
    timeout_seconds: float = Field(default=30, ge=1, le=120)
    request_deadline_seconds: float = Field(default=45, ge=1, le=120)
    max_attempts: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def validate_overlap(self) -> "Settings":
        if self.overlap_words >= self.chunk_words:
            raise ValueError("overlap_words must be smaller than chunk_words")
        return self

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        try:
            return cls(
                api_key=os.getenv("GEMINI_API_KEY") or None,
                model=os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it"),
                cache_dir=Path(
                    os.getenv(
                        "REPORT_CACHE_DIR",
                        str(Path(tempfile.gettempdir()) / "report-navigator-cache"),
                    )
                ),
                tessdata_dir=Path(
                    os.getenv(
                        "TESSDATA_PREFIX", str(PROJECT_ROOT / "models" / "tessdata")
                    )
                ),
                answer_mode=os.getenv("ANSWER_MODE", "offline"),
                timeout_seconds=os.getenv("GEMMA_TIMEOUT_SECONDS", "30"),
                request_deadline_seconds=os.getenv("GEMMA_DEADLINE_SECONDS", "45"),
                max_attempts=os.getenv("GEMMA_MAX_ATTEMPTS", "2"),
            )
        except ValidationError:
            raise BackendError(
                "configuration_error", "Check the backend environment settings."
            ) from None
