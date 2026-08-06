"""Timeline quality audit — catch silent “boring / broken” compose failures.

Past misses this gates against:
1. Draft / slice dropping overlays (looked for start/end instead of fromSec)
2. Timid camera_play scales that read as no multicam
3. Soft punch_in effects
4. Float screen without windowCrop when smart_window_detect is on
5. cover.json overlays that never land on the output timeline
"""

from __future__ import annotations

from typing import Any

from agentic_editor.cover.remap import collect_overlay_defs


# Tutorial look: close must read as a second camera, not a 2% nudge.
MIN_CLOSE_SCALE = 1.32
MIN_MEDIUM_SCALE = 1.16
MIN_PUNCH_SCALE = 1.22
MAX_HOLD_WARN_SEC = 12.0
# Cozy float is ~0.78 of frame; wider usually means desktop chrome leaked in.
MAX_FLOAT_CROP_WIDTH = 0.82


def _crop_mode(timeline: dict[str, Any]) -> str:
    se = (timeline.get("presentation") or {}).get("screenExplainer") or {}
    crop = (se.get("screen") or {}).get("crop") or {}
    return str(crop.get("mode") or "none").strip().lower()


def audit_timeline_quality(
    timeline: dict[str, Any],
    *,
    cover: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for a compose/draft timeline."""
    errors: list[str] = []
    warnings: list[str] = []

    clips = [c for c in (timeline.get("clips") or []) if isinstance(c, dict)]
    effects = [e for e in (timeline.get("effects") or []) if isinstance(e, dict)]
    overlays = [o for o in (timeline.get("overlays") or []) if isinstance(o, dict)]
    camera_play = timeline.get("camera_play") or {}
    if cover and isinstance(cover.get("camera_play"), dict):
        # Prefer explicit cover scales when timeline omitted them.
        camera_play = {**camera_play, **(cover.get("camera_play") or {})}

    scales = camera_play.get("scales") or {}
    try:
        close = float(scales.get("close", 0) or 0)
        medium = float(scales.get("medium", 0) or 0)
    except (TypeError, ValueError):
        close, medium = 0.0, 0.0
    if close and close < MIN_CLOSE_SCALE:
        warnings.append(
            f"camera_play.scales.close={close} is timid "
            f"(want ≥ {MIN_CLOSE_SCALE}) — multicam will feel flat"
        )
    if medium and medium < MIN_MEDIUM_SCALE:
        warnings.append(
            f"camera_play.scales.medium={medium} is timid "
            f"(want ≥ {MIN_MEDIUM_SCALE})"
        )

    try:
        max_hold = float(camera_play.get("max_hold_sec") or 0)
    except (TypeError, ValueError):
        max_hold = 0.0
    if max_hold > MAX_HOLD_WARN_SEC:
        warnings.append(
            f"camera_play.max_hold_sec={max_hold} is long "
            f"(>{MAX_HOLD_WARN_SEC}) — face-cam holds will feel static"
        )

    soft_punches = [
        e
        for e in effects
        if str(e.get("type") or "") in ("punch_in", "punch")
        and float(e.get("scale") or 0) < MIN_PUNCH_SCALE
    ]
    if soft_punches:
        warnings.append(
            f"{len(soft_punches)} punch_in effect(s) with scale < {MIN_PUNCH_SCALE} "
            "(barely visible)"
        )

    crop_mode = _crop_mode(timeline)
    floats = [c for c in clips if c.get("layout") == "float_centered"]
    if crop_mode == "smart_window_detect":
        missing_crop = [c for c in floats if not isinstance(c.get("windowCrop"), dict)]
        if floats and missing_crop:
            errors.append(
                f"{len(missing_crop)}/{len(floats)} float_centered clip(s) missing "
                "windowCrop — run ae compose (prefers edit/window_crop.json stable)"
            )
        over_wide = []
        for c in floats:
            crop = c.get("windowCrop") or {}
            try:
                w = float(crop.get("w") or 0)
            except (TypeError, ValueError):
                w = 0.0
            if w > MAX_FLOAT_CROP_WIDTH:
                over_wide.append(c.get("id") or "?")
        if over_wide:
            warnings.append(
                f"{len(over_wide)} float crop(s) wider than {MAX_FLOAT_CROP_WIDTH} "
                f"(e.g. {over_wide[0]}) — likely desktop chrome; prefer stable "
                "edit/window_crop.json"
            )

    cover_overlays = list((cover or {}).get("overlays") or [])
    if cover_overlays and not overlays:
        errors.append(
            f"cover.json has {len(cover_overlays)} overlay(s) but timeline.overlays "
            "is empty — remap failed or draft slice dropped fromSec items"
        )
    elif cover_overlays:
        defs = collect_overlay_defs(cover)
        tl_ids = {str(o.get("id") or "") for o in overlays}
        dropped = [d for d in defs if d["id"] not in tl_ids]
        if dropped:
            sample = ", ".join(d["id"] for d in dropped[:3])
            errors.append(
                f"{len(dropped)} cover overlay(s) missing from timeline after remap "
                f"(e.g. {sample}) — outside EDL keeps or zero intersection"
            )
        # Opening chip / early MG should usually appear in the first few seconds
        early = [
            o
            for o in overlays
            if float(o.get("fromSec") or 0) < 5.0
        ]
        cover_early = [
            o
            for o in cover_overlays
            if float(o.get("start") or 0) < 30.0
        ]
        if cover_early and not early and float(timeline.get("durationSec") or 0) >= 5:
            warnings.append(
                "cover has early overlays but none land in first 5s of timeline — "
                "check remap / chip-open framing"
            )

    full_cam = [
        c for c in clips if c.get("layout") == "full" and c.get("source") == "cam"
    ]
    if full_cam:
        full_scales = {float(c.get("scale") or 1) for c in full_cam}
        if full_scales and max(full_scales) < MIN_CLOSE_SCALE:
            warnings.append(
                "full-cam clips never reach close scale — framing events may be "
                "missing or camera_play scales too soft"
            )

    return errors, warnings


def format_audit(errors: list[str], warnings: list[str]) -> str:
    lines: list[str] = []
    for e in errors:
        lines.append(f"ERROR: {e}")
    for w in warnings:
        lines.append(f"WARN:  {w}")
    return "\n".join(lines)
