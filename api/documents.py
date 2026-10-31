"""Single-worker, temporary document registry with bounded admission and idle TTL."""

import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock, Semaphore
from typing import Callable

from backend import BackendError, Navigator


@dataclass
class Entry:
    navigator: Navigator
    mode: str
    size: int
    touched: float


class DocumentStore:
    def __init__(
        self,
        *,
        max_documents=2,
        max_bytes=40 * 1024 * 1024,
        ttl_seconds=1800,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_documents = max_documents
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.entries: dict[str, Entry] = {}
        self.lock = RLock()
        # PyMuPDF work is serialized, and duplicate uploads cannot race admission.
        self.busy = Semaphore(1)
        self.hosted_requests = 0

    @contextmanager
    def operation(self):
        if not self.busy.acquire(blocking=False):
            raise BackendError(
                "service_busy",
                "Another document operation is running. Retry shortly.",
                http_status=429,
            )
        try:
            yield
        finally:
            self.busy.release()

    def prune(self):
        with self.lock:
            now = self.clock()
            for token, entry in list(self.entries.items()):
                if now - entry.touched >= self.ttl_seconds:
                    del self.entries[token]

    def check_capacity(self, size):
        with self.lock:
            self.prune()
            if (
                len(self.entries) >= self.max_documents
                or sum(e.size for e in self.entries.values()) + size > self.max_bytes
            ):
                raise BackendError(
                    "capacity_reached",
                    "Demo capacity reached. Delete an uploaded document or wait for expiry.",
                    http_status=503,
                )

    def add(self, navigator, mode, size):
        with self.lock:
            self.check_capacity(size)
            token = secrets.token_urlsafe(32)
            self.entries[token] = Entry(navigator, mode, size, self.clock())
            return token

    def get(self, token):
        with self.lock:
            self.prune()
            entry = self.entries.get(token)
            if entry is None:
                raise BackendError(
                    "document_not_found",
                    "Document not found or expired. Upload it again.",
                    http_status=404,
                )
            entry.touched = self.clock()
            return entry

    def delete(self, token):
        with self.lock:
            self.get(token)
            del self.entries[token]

    def consume_hosted_request(self):
        with self.lock:
            if self.hosted_requests >= 60:
                raise BackendError(
                    "demo_quota_reached",
                    "The hosted demo request budget is exhausted. Offline mode is still available.",
                    http_status=429,
                )
            self.hosted_requests += 1

    def clear(self):
        with self.lock:
            self.entries.clear()
