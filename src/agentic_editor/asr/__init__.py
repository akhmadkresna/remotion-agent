"""ASR package: auto backend, cache, normalize."""

from agentic_editor.asr.backends import resolve_backend, BackendName
from agentic_editor.asr.ingest import ingest_episode

__all__ = ["resolve_backend", "BackendName", "ingest_episode"]
