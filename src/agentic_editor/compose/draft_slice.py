"""Slice a Remotion timeline to the first N seconds for draft review.

Overlays / effects / clips all use output-time ``fromSec`` + ``durationSec``
after ``ae cover``. Hand-rolled trims that look for ``start``/``end`` silently
drop OverlayLayer (the open chip bug). Always use this helper.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _item_span(item: dict[str, Any]) -> tuple[float, float]:
    """Return (start, end) in output timeline seconds."""
    if "fromSec" in item:
        start = float(item.get("fromSec") or 0)
        if "durationSec" in item:
            end = start + float(item.get("durationSec") or 0)
        elif "end" in item:
            end = float(item["end"])
        else:
            end = start
        return start, end
    start = float(item.get("start") or 0)
    end = float(item.get("end") or start)
    return start, end


def _trim_item(item: dict[str, Any], limit_sec: float) -> dict[str, Any] | None:
    start, end = _item_span(item)
    if end <= 0 or start >= limit_sec:
        return None
    clipped_end = min(end, limit_sec)
    out = deepcopy(item)
    if "fromSec" in item or "durationSec" in item:
        out["fromSec"] = start
        out["durationSec"] = max(0.05, clipped_end - start)
    if "start" in item:
        out["start"] = start
    if "end" in item:
        out["end"] = clipped_end
    return out


def slice_timeline(timeline: dict[str, Any], limit_sec: float) -> dict[str, Any]:
    """Return a deep-copied timeline truncated to ``[0, limit_sec)``."""
    if limit_sec <= 0:
        raise ValueError("limit_sec must be > 0")
    fps = int(timeline.get("fps") or 30)
    out = deepcopy(timeline)
    out["durationSec"] = float(limit_sec)
    out["durationInFrames"] = max(1, int(round(limit_sec * fps)))

    for key in ("clips", "effects", "overlays", "captions"):
        trimmed: list[dict[str, Any]] = []
        for item in timeline.get(key) or []:
            if not isinstance(item, dict):
                continue
            kept = _trim_item(item, limit_sec)
            if kept is not None:
                trimmed.append(kept)
        out[key] = trimmed
    return out
