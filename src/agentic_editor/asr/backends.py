"""Choose ASR backend by OS / config."""

from __future__ import annotations

import shutil
import sys
from typing import Literal

BackendName = Literal["whisper.cpp", "faster-whisper"]


def resolve_backend(requested: str = "auto") -> BackendName:
    req = (requested or "auto").strip().lower()
    if req in ("whisper.cpp", "whispercpp", "whisper-cpp"):
        return "whisper.cpp"
    if req in ("faster-whisper", "faster_whisper", "fw"):
        return "faster-whisper"
    if req != "auto":
        raise ValueError(f"Unknown ASR backend: {requested!r}")
    # auto: prefer whisper.cpp on macOS when CLI is present; else faster-whisper
    if sys.platform == "darwin" and whisper_cpp_binary():
        return "whisper.cpp"
    if sys.platform == "darwin":
        # Metal whisper.cpp not installed — fall back so ingest still works
        return "faster-whisper"
    return "faster-whisper"


def whisper_cpp_binary() -> str | None:
    from pathlib import Path

    for name in ("whisper-cli", "whisper-cpp"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        "/opt/homebrew/bin/whisper-cli",
        "/usr/local/bin/whisper-cli",
        "/opt/homebrew/bin/whisper-cpp",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


MODEL_MAP = {
    "tiny": {"whisper.cpp": "ggml-tiny.bin", "faster-whisper": "tiny"},
    "base": {"whisper.cpp": "ggml-base.bin", "faster-whisper": "base"},
    "small": {"whisper.cpp": "ggml-small.bin", "faster-whisper": "small"},
    "medium": {"whisper.cpp": "ggml-medium.bin", "faster-whisper": "medium"},
    "large": {"whisper.cpp": "ggml-large-v3.bin", "faster-whisper": "large-v3"},
}


def mapped_model(tier: str, backend: BackendName) -> str:
    tier = (tier or "small").lower()
    if tier not in MODEL_MAP:
        # allow raw model names
        return tier
    return MODEL_MAP[tier][backend]
