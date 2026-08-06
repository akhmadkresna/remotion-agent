"""Tests for cover timeline builder + screen_with_cam suggest formula."""

from __future__ import annotations

from agentic_editor.cover import build_timeline_from_edl_and_cover
from agentic_editor.cover.suggest import (
    decide_screen_pip_windows,
    find_deixis_windows,
)


def _edl(ranges: list[dict], sources: dict | None = None) -> dict:
    return {
        "sources": sources
        or {
            "cam": "/tmp/cam.mp4",
            "screen": "/tmp/screen.mp4",
        },
        "ranges": ranges,
    }


def test_screen_with_cam_mutes_screen_keeps_cam_audio():
    edl = _edl([{"source": "cam", "start": 10.0, "end": 20.0, "note": "demo"}])
    cover = {
        "camera_play": {"snap_on_cuts": True, "max_hold_sec": 16},
        "events": [{"type": "screen_with_cam", "start": 10.0, "end": 20.0}],
    }
    tl = build_timeline_from_edl_and_cover(edl, cover, fps=30)
    full = [c for c in tl["clips"] if c["layout"] in ("full", "float_centered")]
    pip = [c for c in tl["clips"] if c["layout"] == "pip_corner"]
    assert len(full) == 1
    assert len(pip) == 1
    assert full[0]["source"] == "screen"
    assert full[0]["layout"] == "float_centered"
    assert full[0]["muted"] is True
    assert full[0]["scale"] == 1.0
    assert full[0]["motion"] == "hold"
    assert pip[0]["source"] == "cam"
    assert pip[0]["muted"] is False
    assert tl["presentation"]["screenExplainer"]["preset"] == "cozy"
    assert (
        tl["presentation"]["screenExplainer"]["canvas"]["background"] == "#d9e2ec"
    )


def test_screen_with_cam_skips_snap_subdivision():
    edl = _edl([{"source": "cam", "start": 0.0, "end": 40.0}])
    cover = {
        "camera_play": {"snap_on_cuts": True, "max_hold_sec": 16},
        "events": [{"type": "screen_with_cam", "start": 0.0, "end": 40.0}],
    }
    tl = build_timeline_from_edl_and_cover(edl, cover)
    full = [c for c in tl["clips"] if c["layout"] in ("full", "float_centered")]
    # Without screen mode, 40s with max_hold 16 would subdivide; with screen → one clip
    assert len(full) == 1
    assert full[0]["durationSec"] == 40.0
    assert full[0]["layout"] == "float_centered"


def test_plain_screen_auto_adds_cam_pip():
    edl = _edl([{"source": "cam", "start": 5.0, "end": 12.0}])
    cover = {
        "camera_play": {"snap_on_cuts": False},
        "events": [{"type": "screen", "start": 5.0, "end": 12.0}],
    }
    tl = build_timeline_from_edl_and_cover(edl, cover)
    pip = [c for c in tl["clips"] if c["layout"] == "pip_corner"]
    assert len(pip) == 1
    assert pip[0]["source"] == "cam"
    assert pip[0]["muted"] is False


def test_full_cam_not_muted():
    edl = _edl([{"source": "cam", "start": 0.0, "end": 5.0, "note": "hook"}])
    cover = {"camera_play": {"snap_on_cuts": False}, "events": []}
    tl = build_timeline_from_edl_and_cover(edl, cover)
    assert len(tl["clips"]) == 1
    assert tl["clips"][0]["source"] == "cam"
    assert tl["clips"][0]["muted"] is False


def test_short_screen_does_not_swallow_whole_keep():
    """A 5s screen event inside a 40s keep must leave full-cam on both sides."""
    edl = _edl([{"source": "cam", "start": 0.0, "end": 40.0, "note": "talk"}])
    cover = {
        "camera_play": {"snap_on_cuts": False, "max_hold_sec": 60},
        "events": [{"type": "screen_with_cam", "start": 10.0, "end": 15.0}],
    }
    tl = build_timeline_from_edl_and_cover(edl, cover, fps=30)
    main = [c for c in tl["clips"] if c["layout"] in ("full", "float_centered")]
    pip = [c for c in tl["clips"] if c["layout"] == "pip_corner"]
    layouts = [c["layout"] for c in main]
    assert layouts.count("float_centered") == 1
    assert layouts.count("full") >= 2
    float_c = next(c for c in main if c["layout"] == "float_centered")
    assert abs(float_c["durationSec"] - 5.0) < 0.05
    assert len(pip) == 1
    assert abs(pip[0]["durationSec"] - 5.0) < 0.05
    assert abs(pip[0]["fromSec"] - float_c["fromSec"]) < 0.05
    # Full-cam duration still dominates
    full_dur = sum(c["durationSec"] for c in main if c["layout"] == "full")
    assert full_dur >= 34.0
    assert tl["clips"][0]["layout"] == "full"


def test_deixis_finds_lihat():
    words = [
        {"text": "oke", "start": 1.0, "end": 1.3, "score": 0.9},
        {"text": "lihat", "start": 1.4, "end": 1.8, "score": 0.95},
        {"text": "dashboard", "start": 1.9, "end": 2.5, "score": 0.9},
        {"text": "ini", "start": 2.6, "end": 2.9, "score": 0.8},
    ]
    hits = find_deixis_windows(
        words,
        ["lihat", "dashboard", "klik"],
        pad_before=0.4,
        pad_after=1.2,
    )
    assert hits
    assert any(h.get("keyword") == "lihat" for h in hits) or any(
        "lihat" in str(h.get("note", "")) or h.get("keyword") == "dashboard" for h in hits
    )


def test_decide_requires_activity_when_bins_present():
    deixis = [{"start": 10.0, "end": 14.0, "keyword": "lihat", "confidence": 1.0}]
    # Idle screen — all inactive
    bins = [
        {"start": float(i), "end": float(i + 1), "activity": 0.001, "active": False}
        for i in range(0, 20)
    ]
    events = decide_screen_pip_windows(
        deixis=deixis,
        activity_bins=bins,
        min_hold_sec=2.5,
        activity_threshold=0.035,
    )
    assert events == []


def test_decide_accepts_deixis_with_activity():
    deixis = [{"start": 10.0, "end": 14.0, "keyword": "lihat", "confidence": 1.0}]
    bins = []
    for i in range(0, 20):
        active = 10 <= i < 15
        bins.append(
            {
                "start": float(i),
                "end": float(i + 1),
                "activity": 0.08 if active else 0.001,
                "active": active,
            }
        )
    events = decide_screen_pip_windows(
        deixis=deixis,
        activity_bins=bins,
        min_hold_sec=2.5,
        activity_threshold=0.035,
    )
    assert len(events) >= 1
    assert events[0]["type"] == "screen_with_cam"
    assert events[0]["end"] > events[0]["start"]


def test_decide_sustained_activity_without_deixis():
    bins = []
    for i in range(0, 30):
        active = 5 <= i < 12
        bins.append(
            {
                "start": float(i),
                "end": float(i + 1),
                "activity": 0.09 if active else 0.001,
                "active": active,
            }
        )
    events = decide_screen_pip_windows(
        deixis=[],
        activity_bins=bins,
        min_hold_sec=2.5,
        min_active_sec=1.5,
        activity_threshold=0.035,
    )
    assert len(events) >= 1
    assert events[0]["type"] == "screen_with_cam"
