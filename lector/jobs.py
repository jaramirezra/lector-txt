"""Gestión de trabajos temporales (documento, bloques y contraseña en memoria)."""

from __future__ import annotations

import re
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .models import Block, Page


class JobNotFound(Exception):
    pass


class TooLargeError(Exception):
    def __init__(self, limit_mb: int):
        super().__init__(f"El archivo supera el límite de {limit_mb} MB.")
        self.message = str(self)
        self.limit_mb = limit_mb


@dataclass
class Job:
    id: str
    filename: str
    kind: str
    path: Path
    directory: Path
    created_at: float
    last_access: float
    attempts_left: int = 5
    status: str = "pending"
    page_count: int = 0
    pages: list[Page] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    encryption: dict | None = None
    preview_html: str | None = None
    password: str | None = None

    def touch(self) -> None:
        self.last_access = time.time()

    def clear_password(self) -> None:
        self.password = None


def _safe_filename(filename: str) -> str:
    name = Path(filename or "documento").name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:180] or "documento"


class JobStore:
    def __init__(
        self,
        base_dir: str | Path | None,
        ttl_seconds: int = 3600,
        max_file_mb: int = 30,
        max_attempts: int = 5,
    ):
        self.base_dir = Path(base_dir) if base_dir else Path("/tmp/lector-txt-jobs")
        self.base_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ttl_seconds = ttl_seconds
        self.max_file_mb = max_file_mb
        self.max_attempts = max_attempts
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def create(self, filename: str, data: bytes, kind: str) -> Job:
        if len(data) > self.max_file_mb * 1024 * 1024:
            raise TooLargeError(self.max_file_mb)

        self.purge_expired()
        job_id = secrets.token_urlsafe(18)
        directory = self.base_dir / job_id
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        suffix = ".pdf" if kind == "pdf" else ".docx"
        path = directory / f"original{suffix}"
        path.write_bytes(data)
        try:
            path.chmod(0o600)
        except OSError:
            pass

        now = time.time()
        job = Job(
            id=job_id,
            filename=_safe_filename(filename),
            kind=kind,
            path=path,
            directory=directory,
            created_at=now,
            last_access=now,
            attempts_left=self.max_attempts,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job:
        self.purge_expired()
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        job.touch()
        return job

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        job.clear_password()
        shutil.rmtree(job.directory, ignore_errors=True)
        return True

    def purge_expired(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if now - job.last_access > self.ttl_seconds
            ]
        for job_id in expired:
            self.delete(job_id)

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)
