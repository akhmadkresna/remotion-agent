"""Map cam (source) time windows onto the radio-edit output timeline."""

from __future__ import annotations

from typing import Any


def remap_source_window(
    edl: dict[str, Any],
    start: float,
    end: float,
    *,
    source: str = "cam",
) -> list[dict[str, float]]:
    """
    Return kept slices of [start, end) as output-timeline segments:
      [{fromSec, durationSec}, ...]
    Only EDL ranges whose source matches `source` contribute.
    """
    if end <= start:
        return []
    out: list[dict[str, float]] = []
    out_t = 0.0
    for r in edl.get("ranges") or []:
        rs = float(r["start"])
        re = float(r["end"])
        dur = max(0.0, re - rs)
        if str(r.get("source") or "cam") != source:
            out_t += dur
            continue
        ov_s = max(start, rs)
        ov_e = min(end, re)
        if ov_e > ov_s + 1e-4:
            local = ov_s - rs
            out.append(
                {
                    "fromSec": out_t + local,
                    "durationSec": ov_e - ov_s,
                }
            )
        out_t += dur
    return out


def collect_overlay_defs(cover: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Overlay creatives live on cover.overlays[] (preferred)."""
    if not cover:
        return []
    raw = cover.get("overlays") or []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or item.get("type") or "").lower().strip()
        if kind not in ("chapter", "emphasis", "diagram", "chip"):
            continue
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        entry = {
            "id": str(item.get("id") or f"ov-{kind}-{i}"),
            "kind": kind,
            "start": start,
            "end": end,
            "source": str(item.get("source") or "cam"),
            "text": str(item.get("text") or "").strip(),
            "kicker": str(item.get("kicker") or "").strip() or None,
            "title": str(item.get("title") or "").strip() or None,
            "note": str(item.get("note") or "").strip() or None,
        }
        steps = item.get("steps")
        if isinstance(steps, list):
            entry["steps"] = [str(s).strip() for s in steps if str(s).strip()]
        out.append(entry)
    return out


def build_timeline_overlays(
    edl: dict[str, Any],
    cover: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Expand cover.overlays (source time) into timeline.overlays (output time)."""
    instances: list[dict[str, Any]] = []
    for i, ov in enumerate(collect_overlay_defs(cover)):
        slices = remap_source_window(
            edl,
            float(ov["start"]),
            float(ov["end"]),
            source=str(ov.get("source") or "cam"),
        )
        for j, sl in enumerate(slices):
            if sl["durationSec"] < 0.12:
                continue
            inst = {
                "id": f"{ov['id']}-{j}" if len(slices) > 1 else ov["id"],
                "kind": ov["kind"],
                "fromSec": sl["fromSec"],
                "durationSec": sl["durationSec"],
                "text": ov.get("text") or "",
            }
            if ov.get("kicker"):
                inst["kicker"] = ov["kicker"]
            if ov.get("title"):
                inst["title"] = ov["title"]
            if ov.get("steps"):
                inst["steps"] = ov["steps"]
            if ov.get("note"):
                inst["note"] = ov["note"]
            instances.append(inst)
    return instances
