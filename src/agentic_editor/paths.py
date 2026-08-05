"""Resolve AGENTIC_EDITOR_HOME and episode paths."""

from __future__ import annotations

import os
from pathlib import Path


def framework_home() -> Path:
    env = os.environ.get("AGENTIC_EDITOR_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # src/agentic_editor/paths.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def resolve_episode(path: str | Path | None) -> Path:
    if path is None or str(path) in (".", ""):
        return Path.cwd().resolve()
    return Path(path).expanduser().resolve()


def ensure_edit_dirs(episode: Path) -> Path:
    edit = episode / "edit"
    (edit / "transcripts").mkdir(parents=True, exist_ok=True)
    (edit / "verify").mkdir(parents=True, exist_ok=True)
    (edit / "audio").mkdir(parents=True, exist_ok=True)
    return edit
