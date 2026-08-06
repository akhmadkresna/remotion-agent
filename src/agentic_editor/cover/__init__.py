"""Cover / timeline JSON — dual-source + fake multicam framing + Remotion."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_SCALES = {"wide": 1.0, "medium": 1.22, "close": 1.42}

RESET_NOTE_RE = re.compile(
    r"\b(reset|lesson|howto|how-to|outro|thanks)\b",
    re.I,
)
EMPHASIS_NOTE_RE = re.compile(
    r"\b(hook|scandal|fallout|reveal|admit|cta|throttle)\b",
    re.I,
)

SCREEN_WITH_CAM_TYPES = frozenset({"screen_with_cam", "cam_pip"})
SCREEN_FULL_TYPES = frozenset({"screen", "screen_full"})
PIP_TYPES = frozenset({"pip", "screen_pip"})


def _scales(camera_play: dict[str, Any]) -> dict[str, float]:
    raw = camera_play.get("scales") or {}
    return {
        "wide": float(raw.get("wide", DEFAULT_SCALES["wide"])),
        "medium": float(raw.get("medium", DEFAULT_SCALES["medium"])),
        "close": float(raw.get("close", DEFAULT_SCALES["close"])),
    }


def _framing_scale(name: str, scales: dict[str, float], explicit: float | None = None) -> float:
    if explicit is not None:
        return float(explicit)
    return float(scales.get(name, DEFAULT_SCALES.get(name, 1.0)))


def _pick_base_framing(
    *,
    range_index: int,
    note: str,
    camera_play: dict[str, Any],
) -> tuple[str, str]:
    """Return (framing, motion) for an EDL range before event overrides."""
    home = str(camera_play.get("home") or "medium")
    alt = str(camera_play.get("alt") or "close")
    snap = bool(camera_play.get("snap_on_cuts", True))
    wide_resets = bool(camera_play.get("wide_on_resets", True))

    if wide_resets and RESET_NOTE_RE.search(note or ""):
        return "wide", "snap" if snap else "hold"
    if EMPHASIS_NOTE_RE.search(note or ""):
        return "close", "ease" if range_index == 0 else "snap"
    if not snap:
        return home, "hold"
    # Alternate home/alt on joins → fake cam A / cam B
    return (home if range_index % 2 == 0 else alt), "snap"


def _events_overlapping(
    events: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        ev_start = float(ev.get("start", 0))
        ev_end = float(ev.get("end", 0))
        if ev_end <= start or ev_start >= end:
            continue
        out.append(ev)
    return out


def _subdivide_range(
    start: float,
    end: float,
    *,
    max_hold: float,
) -> list[tuple[float, float]]:
    """Split long source ranges so fake-cam framing can change mid-beat."""
    dur = end - start
    if dur <= max_hold + 0.05:
        return [(start, end)]
    parts: list[tuple[float, float]] = []
    t = start
    while t < end - 0.05:
        nxt = min(end, t + max_hold)
        # avoid a tiny tail; absorb into previous
        if end - nxt < 4.0 and nxt < end:
            nxt = end
        parts.append((t, nxt))
        t = nxt
    return parts


def _clip_muted(source: str) -> bool:
    """Audio always from cam; every other source is visual-only."""
    return str(source) != "cam"


def _screen_intervals_in_range(
    cover_events: list[dict[str, Any]],
    range_start: float,
    range_end: float,
) -> list[tuple[float, float, str]]:
    """Merged screen-intent intervals clipped to ``[range_start, range_end]``.

    Returns list of (start, end, mode) where mode is ``screen_with_cam`` or ``screen``.
    """
    raw: list[tuple[float, float, str]] = []
    for ev in cover_events:
        kind = str(ev.get("type") or "").lower()
        if kind in SCREEN_WITH_CAM_TYPES:
            mode = "screen_with_cam"
        elif kind in SCREEN_FULL_TYPES:
            mode = "screen"
        else:
            continue
        s = max(float(ev.get("start", 0)), range_start)
        e = min(float(ev.get("end", 0)), range_end)
        if e - s >= 0.15:
            raw.append((s, e, mode))
    if not raw:
        return []
    raw.sort(key=lambda x: x[0])
    merged: list[tuple[float, float, str]] = [raw[0]]
    for s, e, mode in raw[1:]:
        ps, pe, pm = merged[-1]
        if s <= pe + 0.05:
            # Prefer screen_with_cam when either side wants PIP
            m = "screen_with_cam" if "with_cam" in (pm + mode) or pm == "screen_with_cam" or mode == "screen_with_cam" else mode
            if pm == "screen_with_cam" or mode == "screen_with_cam":
                m = "screen_with_cam"
            merged[-1] = (ps, max(pe, e), m)
        else:
            merged.append((s, e, mode))
    return merged


def partition_range_by_cover(
    range_start: float,
    range_end: float,
    cover_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split one EDL keep into full-cam vs screen(+PIP) subclips.

    Critical: a short screen event must NOT force the whole keep to float.
    PIP (cam audio + face) must cover the entire screen subclip, not just the
    original short event window.
    """
    screens = _screen_intervals_in_range(cover_events, range_start, range_end)
    if not screens:
        return [{"start": range_start, "end": range_end, "mode": "full_cam"}]

    parts: list[dict[str, Any]] = []
    cursor = range_start
    for s, e, mode in screens:
        if s > cursor + 0.05:
            parts.append({"start": cursor, "end": s, "mode": "full_cam"})
        parts.append(
            {
                "start": s,
                "end": e,
                "mode": "screen_with_cam" if mode == "screen_with_cam" else "screen",
            }
        )
        cursor = e
    if range_end > cursor + 0.05:
        parts.append({"start": cursor, "end": range_end, "mode": "full_cam"})
    return parts


def build_timeline_from_edl_and_cover(
    edl: dict[str, Any],
    cover: dict[str, Any] | None,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    screen_explainer: dict[str, Any] | None = None,
    overlays: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge radio-edit EDL with cover + camera_play into a Remotion timeline."""
    from agentic_editor.cover.style_load import (
        DEFAULT_OVERLAYS,
        DEFAULT_SCREEN_EXPLAINER,
    )

    cover = cover or {}
    camera_play = cover.get("camera_play") or {}
    scales = _scales(camera_play)
    cover_events = list(cover.get("events") or [])
    clips: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = list(cover.get("captions") or [])
    snap = bool(camera_play.get("snap_on_cuts", True))
    max_hold = float(camera_play.get("max_hold_sec", 16.0))
    se = screen_explainer or DEFAULT_SCREEN_EXPLAINER
    ov_style = overlays or DEFAULT_OVERLAYS
    float_presentation = str(
        (se.get("screen") or {}).get("presentation") or "float_centered"
    )

    from agentic_editor.cover.remap import build_timeline_overlays

    timeline_overlays = build_timeline_overlays(edl, cover)

    out_t = 0.0
    global_clip_i = 0
    for i, r in enumerate(edl["ranges"]):
        note = str(r.get("note") or "")
        range_start = float(r["start"])
        range_end = float(r["end"])
        range_out_start = out_t

        # Emphasis punches / punch-outs (output timeline coords)
        for ev in _events_overlapping(cover_events, range_start, range_end):
            kind = (ev.get("type") or "").lower()
            if kind not in ("punch_in", "punch", "punch_out"):
                continue
            local = max(0.0, float(ev["start"]) - range_start)
            effects.append(
                {
                    "type": "punch_out" if kind == "punch_out" else "punch_in",
                    "fromSec": range_out_start + local,
                    "durationSec": float(
                        ev.get("duration", max(0.1, float(ev["end"]) - float(ev["start"])))
                    ),
                    "scale": float(ev.get("scale", scales["close"])),
                }
            )

        parts = partition_range_by_cover(range_start, range_end, cover_events)
        for part in parts:
            seg_start = float(part["start"])
            seg_end = float(part["end"])
            mode = str(part["mode"])
            screen_visual = mode in ("screen_with_cam", "screen")
            visual_src = "screen" if screen_visual else str(r["source"])
            layout = float_presentation if screen_visual else "full"

            if screen_visual:
                segments = [(seg_start, seg_end)]
            else:
                do_snap = snap and layout == "full"
                segments = (
                    _subdivide_range(seg_start, seg_end, max_hold=max_hold)
                    if do_snap
                    else [(seg_start, seg_end)]
                )

            part_out_start = out_t
            for seg_s, seg_e in segments:
                seg_dur = seg_e - seg_s
                if screen_visual:
                    framing, motion, scale = "wide", "hold", 1.0
                else:
                    framing, motion = _pick_base_framing(
                        range_index=global_clip_i, note=note, camera_play=camera_play
                    )
                    scale = _framing_scale(framing, scales)
                    for ev in _events_overlapping(cover_events, seg_s, seg_e):
                        kind = (ev.get("type") or "").lower()
                        if kind != "framing":
                            continue
                        framing = str(ev.get("framing") or framing)
                        motion = str(ev.get("motion") or motion)
                        scale = _framing_scale(framing, scales, ev.get("scale"))
                    if motion == "hold" and seg_dur >= 12:
                        motion = "drift"
                    if motion == "snap" and seg_dur >= 14 and framing != "wide":
                        motion = "drift"

                clips.append(
                    {
                        "id": f"a-{len(clips)}",
                        "track": "a_roll",
                        "source": visual_src,
                        "sourceIn": seg_s,
                        "sourceOut": seg_e,
                        "fromSec": out_t,
                        "durationSec": seg_dur,
                        "layout": layout,
                        "framing": framing,
                        "scale": scale,
                        "motion": motion,
                        "muted": _clip_muted(visual_src),
                    }
                )
                out_t += seg_dur
                global_clip_i += 1

            # PIP covers the entire screen subclip (face + cam audio)
            if screen_visual:
                part_dur = seg_end - seg_start
                clips.append(
                    {
                        "id": f"pip-{len(clips)}",
                        "track": "overlay",
                        "source": "cam",
                        "sourceIn": seg_start,
                        "sourceOut": seg_end,
                        "fromSec": part_out_start,
                        "durationSec": max(0.05, part_dur),
                        "layout": "pip_corner",
                        "framing": "medium",
                        "scale": 1.0,
                        "motion": "hold",
                        "muted": False,
                    }
                )

    sources = dict(edl.get("sources") or {})
    return {
        "fps": fps,
        "width": width,
        "height": height,
        "durationInFrames": max(1, int(round(out_t * fps))),
        "durationSec": out_t,
        "sources": sources,
        "clips": clips,
        "effects": effects,
        "captions": captions,
        "overlays": timeline_overlays,
        "camera_play": {
            "snap_on_cuts": snap,
            "home": camera_play.get("home", "medium"),
            "alt": camera_play.get("alt", "close"),
            "max_hold_sec": max_hold,
            "scales": scales,
        },
        "presentation": {"screenExplainer": se, "overlays": ov_style},
    }


def write_timeline(path: Path, timeline: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")


def example_cover() -> dict[str, Any]:
    return {
        "camera_play": {
            "snap_on_cuts": True,
            "home": "medium",
            "alt": "close",
            "wide_on_resets": True,
            "max_hold_sec": 7,
            "scales": {"wide": 1.0, "medium": 1.22, "close": 1.42},
        },
        "events": [
            {
                "type": "framing",
                "start": 0.0,
                "end": 5.0,
                "framing": "close",
                "motion": "ease",
                "note": "open tight",
            },
            {
                "type": "punch_in",
                "start": 12.0,
                "end": 15.0,
                "duration": 1.35,
                "scale": 1.28,
                "note": "emphasize key line",
            },
            {
                "type": "screen_with_cam",
                "start": 20.0,
                "end": 35.0,
                "note": "demo UI with soft-float cam PIP",
            },
        ],
        "captions": [],
        "overlays": [],
    }
