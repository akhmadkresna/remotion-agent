"""Map cam (source) time windows onto the radio-edit output timeline."""

from __future__ import annotations

from typing import Any

# Prefer slices at least this long; sole short slices are still kept.
_MIN_PREFERRED_SLICE = 0.5


def edl_keep_duration_sec(edl: dict[str, Any]) -> float:
    """Total output duration of all EDL keep ranges."""
    total = 0.0
    for r in edl.get("ranges") or []:
        total += max(0.0, float(r["end"]) - float(r["start"]))
    return total


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


def _dwell_floor(kind: str) -> float:
    return {
        "chip": 4.0,
        "chapter": 5.0,
        "diagram": 7.5,
        "emphasis": 2.4,
    }.get(kind, 1.8)


def _pick_best_slice(slices: list[dict[str, float]]) -> dict[str, float] | None:
    """One instance per overlay: longest preferred slice; sole short slice kept."""
    if not slices:
        return None
    preferred = [s for s in slices if float(s["durationSec"]) >= _MIN_PREFERRED_SLICE]
    pool = preferred if preferred else slices
    return max(pool, key=lambda s: float(s["durationSec"]))


def build_timeline_overlays(
    edl: dict[str, Any],
    cover: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Expand cover.overlays (source time) into timeline.overlays (output time)."""
    timeline_dur = edl_keep_duration_sec(edl)
    instances: list[dict[str, Any]] = []
    for ov in collect_overlay_defs(cover):
        slices = remap_source_window(
            edl,
            float(ov["start"]),
            float(ov["end"]),
            source=str(ov.get("source") or "cam"),
        )
        sl = _pick_best_slice(slices)
        if sl is None:
            continue
        kind = str(ov.get("kind") or "")
        floor = _dwell_floor(kind)
        remaining = max(0.05, timeline_dur - float(sl["fromSec"]))
        dur = min(max(float(sl["durationSec"]), floor), remaining)
        inst: dict[str, Any] = {
            "id": ov["id"],
            "kind": ov["kind"],
            "fromSec": sl["fromSec"],
            "durationSec": dur,
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
