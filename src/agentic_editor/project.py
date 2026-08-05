"""Load and validate episode project.yaml."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "id": None,
    "sources": {"cam": "raw/cam.mp4"},
    "style": "tutorial",
    "asr": {
        "backend": "auto",
        "model": "small",
        "language": "id",
        "word_timestamps": True,
        "diarize": False,
    },
    "fps": 30,
    "aspect": "16:9",
    "width": 1920,
    "height": 1080,
}


def load_project(episode: Path) -> dict[str, Any]:
    path = episode / "project.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"No project.yaml in {episode}. Run: ae new {episode}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = deepcopy(DEFAULTS)
    _deep_merge(cfg, raw)
    if not cfg.get("id"):
        cfg["id"] = episode.name
    return cfg


def save_project(episode: Path, cfg: dict[str, Any]) -> None:
    path = episode / "project.yaml"
    path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def resolve_source(episode: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return (episode / p).resolve()
