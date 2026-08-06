"""EDL load / validate / snap helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_edl(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_edl(data)
    return data


def validate_edl(edl: dict[str, Any]) -> None:
    if "sources" not in edl or not isinstance(edl["sources"], dict):
        raise ValueError("EDL missing sources map")
    if "ranges" not in edl or not isinstance(edl["ranges"], list) or not edl["ranges"]:
        raise ValueError("EDL missing non-empty ranges list")
    for i, r in enumerate(edl["ranges"]):
        if "source" not in r or "start" not in r or "end" not in r:
            raise ValueError(f"EDL ranges[{i}] needs source, start, end")
        if float(r["end"]) <= float(r["start"]):
            raise ValueError(f"EDL ranges[{i}] end must be > start")
        if r["source"] not in edl["sources"]:
            raise ValueError(f"EDL ranges[{i}] unknown source {r['source']!r}")


def snap_range_to_words(
    start: float,
    end: float,
    words: list[dict[str, Any]],
    *,
    pad_before: float = 0.05,
    pad_after: float = 0.08,
    hold_tail: bool = False,
) -> tuple[float, float]:
    """Snap cut edges to nearest word boundaries and apply padding.

    ``hold_tail=True`` preserves an intentional non-speech end (AI wait beat).
    Only the start is speech-snapped; ``end`` is kept so the beat survives.
    """
    word_tokens = [
        w
        for w in words
        if w.get("type", "word") == "word" and w.get("start") is not None
    ]
    if not word_tokens:
        return max(0.0, start - pad_before), end + (0.0 if hold_tail else pad_after)

    # find first word overlapping/after start
    first = None
    for w in word_tokens:
        if float(w["end"]) > start:
            first = w
            break
    last = None
    for w in reversed(word_tokens):
        if float(w["start"]) < end:
            last = w
            break
    if first is None or last is None:
        return max(0.0, start - pad_before), end + (0.0 if hold_tail else pad_after)

    snapped_start = max(0.0, float(first["start"]) - pad_before)
    if hold_tail:
        # Keep requested end (wait beat); never pull it back to last word
        snapped_end = max(float(end), snapped_start + 0.05)
    else:
        snapped_end = float(last["end"]) + pad_after
        if snapped_end <= snapped_start:
            snapped_end = snapped_start + 0.05
    return snapped_start, snapped_end


def example_edl(episode_rel_cam: str = "../raw/cam.mp4") -> dict[str, Any]:
    return {
        "sources": {"cam": episode_rel_cam},
        "ranges": [
            {
                "source": "cam",
                "start": 0.0,
                "end": 5.0,
                "note": "example — replace after radio-edit",
            }
        ],
        "grade": None,
    }
