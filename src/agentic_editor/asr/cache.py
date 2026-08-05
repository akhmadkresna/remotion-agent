"""Transcript cache keyed by source fingerprint + ASR settings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def source_fingerprint(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_key(
    path: Path,
    *,
    backend: str,
    model: str,
    language: str,
) -> str:
    parts = f"{source_fingerprint(path)}|{backend}|{model}|{language}"
    return hashlib.sha256(parts.encode()).hexdigest()[:20]


def load_cached(transcript_path: Path, expected_key: str) -> dict[str, Any] | None:
    if not transcript_path.is_file():
        return None
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    meta = data.get("_cache") or {}
    if meta.get("key") == expected_key:
        return data
    return None


def write_transcript(transcript_path: Path, data: dict[str, Any], key: str) -> None:
    payload = dict(data)
    payload["_cache"] = {"key": key}
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
