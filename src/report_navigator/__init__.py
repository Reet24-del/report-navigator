"""Public API: load_report, Navigator, Settings and the frontend data contracts."""

from .config import Settings
from .schemas import AnswerResult, BackendError, Chunk, Citation, ReportInfo
from .service import Navigator, load_report

__all__ = [
    "load_report",
    "Navigator",
    "Settings",
    "AnswerResult",
    "ReportInfo",
    "Chunk",
    "Citation",
    "BackendError",
]
