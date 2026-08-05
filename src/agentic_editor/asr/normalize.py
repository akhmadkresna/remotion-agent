"""Normalize backend outputs to the shared transcript contract."""

from __future__ import annotations

from typing import Any


def empty_transcript(
    *,
    language: str,
    backend: str,
    model: str,
) -> dict[str, Any]:
    return {
        "language": language,
        "backend": backend,
        "model": model,
        "words": [],
        "segments": [],
    }


def normalize_word(
    word: str,
    start: float,
    end: float,
    *,
    score: float | None = None,
    speaker: str | None = None,
) -> dict[str, Any]:
    w: dict[str, Any] = {
        "type": "word",
        "word": word.strip(),
        "text": word.strip(),  # packer / SRT compat
        "start": float(start),
        "end": float(end),
    }
    if score is not None:
        w["score"] = float(score)
    if speaker is not None:
        w["speaker_id"] = speaker
    return w


def words_to_segments(words: list[dict[str, Any]], gap: float = 0.5) -> list[dict[str, Any]]:
    if not words:
        return []
    segments: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"]) >= gap:
            segments.append(_flush_segment(cur))
            cur = []
        cur.append(w)
    if cur:
        segments.append(_flush_segment(cur))
    return segments


def _flush_segment(words: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(w.get("word") or w.get("text") or "" for w in words)
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": text.strip(),
    }


def finalize_transcript(
    *,
    language: str,
    backend: str,
    model: str,
    words: list[dict[str, Any]],
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    segs = segments if segments is not None else words_to_segments(words)
    return {
        "language": language,
        "backend": backend,
        "model": model,
        "words": words,
        "segments": segs,
    }
