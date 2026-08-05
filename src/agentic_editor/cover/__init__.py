"""Cover / timeline JSON — dual-source + fake multicam framing + Remotion."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_SCALES = {"wide": 1.0, "medium": 1.1, "close": 1.18}

RESET_NOTE_RE = re.compile(
    r"\b(reset|lesson|howto|how-to|outro|thanks)\b",
    re.I,
)
EMPHASIS_NOTE_RE = re.compile(
    r"\b(hook|scandal|fallout|reveal|admit|cta|throttle)\b",
    re.I,
)


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


def build_timeline_from_edl_and_cover(
    edl: dict[str, Any],
    cover: dict[str, Any] | None,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Merge radio-edit EDL with cover + camera_play into a Remotion timeline."""
    cover = cover or {}
    camera_play = cover.get("camera_play") or {}
    scales = _scales(camera_play)
    cover_events = list(cover.get("events") or [])
    clips: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = list(cover.get("captions") or [])
    snap = bool(camera_play.get("snap_on_cuts", True))
    max_hold = float(camera_play.get("max_hold_sec", 16.0))

    out_t = 0.0
    global_clip_i = 0
    for i, r in enumerate(edl["ranges"]):
        src = r["source"]
        note = str(r.get("note") or "")
        range_start = float(r["start"])
        range_end = float(r["end"])
        dur_total = range_end - range_start

        visual_src = src
        layout = "full"
        pip_ev = None
        for ev in _events_overlapping(cover_events, range_start, range_end):
            kind = (ev.get("type") or "").lower()
            if kind in ("screen", "screen_full"):
                visual_src = ev.get("source") or "screen"
                layout = "full"
            elif kind in ("pip", "screen_pip"):
                pip_ev = ev

        # Emphasis punches / punch-outs (output timeline coords)
        for ev in _events_overlapping(cover_events, range_start, range_end):
            kind = (ev.get("type") or "").lower()
            if kind not in ("punch_in", "punch", "punch_out"):
                continue
            local = max(0.0, float(ev["start"]) - range_start)
            effects.append(
                {
                    "type": "punch_out" if kind == "punch_out" else "punch_in",
                    "fromSec": out_t + local,
                    "durationSec": float(
                        ev.get("duration", max(0.1, float(ev["end"]) - float(ev["start"])))
                    ),
                    "scale": float(ev.get("scale", scales["close"])),
                }
            )

        segments = (
            _subdivide_range(range_start, range_end, max_hold=max_hold)
            if snap and layout == "full"
            else [(range_start, range_end)]
        )

        for seg_i, (seg_start, seg_end) in enumerate(segments):
            seg_dur = seg_end - seg_start
            framing, motion = _pick_base_framing(
                range_index=global_clip_i, note=note, camera_play=camera_play
            )
            scale = _framing_scale(framing, scales)

            # Explicit framing events win for this sub-segment
            for ev in _events_overlapping(cover_events, seg_start, seg_end):
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
                    "sourceIn": seg_start,
                    "sourceOut": seg_end,
                    "fromSec": out_t,
                    "durationSec": seg_dur,
                    "layout": layout,
                    "framing": framing,
                    "scale": scale,
                    "motion": motion,
                }
            )
            out_t += seg_dur
            global_clip_i += 1

        if pip_ev is not None:
            local = max(0.0, float(pip_ev.get("start", range_start)) - range_start)
            pip_dur = min(
                dur_total - local,
                float(pip_ev.get("end", range_end)) - float(pip_ev.get("start", range_start)),
            )
            # pip sits on the parent range start; output time already advanced — place relative to range
            pip_from = out_t - dur_total + local
            clips.append(
                {
                    "id": f"pip-{len(clips)}",
                    "track": "overlay",
                    "source": pip_ev.get("source") or "screen",
                    "sourceIn": float(pip_ev.get("start", range_start)),
                    "sourceOut": float(pip_ev.get("end", range_end)),
                    "fromSec": max(0.0, pip_from),
                    "durationSec": max(0.05, pip_dur),
                    "layout": "pip_corner",
                    "framing": "medium",
                    "scale": 1.0,
                    "motion": "hold",
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
        "camera_play": {
            "snap_on_cuts": snap,
            "home": camera_play.get("home", "medium"),
            "alt": camera_play.get("alt", "close"),
            "max_hold_sec": max_hold,
            "scales": scales,
        },
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
            "scales": {"wide": 1.0, "medium": 1.1, "close": 1.18},
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
                "duration": 3.0,
                "scale": 1.12,
                "note": "emphasize key line",
            },
        ],
        "captions": [],
    }
