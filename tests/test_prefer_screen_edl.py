"""Tests for prefer_screen cover suggest + silence-cut EDL suggest."""

from __future__ import annotations

from agentic_editor.cover.suggest import (
    apply_screen_bias,
    decide_screen_pip_windows,
)
from agentic_editor.editor.edl_suggest import suggest_edl_from_words


def test_prefer_screen_keeps_deixis_without_activity():
    """prefer_screen: deixis on idle screen still becomes screen_with_cam."""
    deixis = [{"start": 10.0, "end": 14.0, "keyword": "lihat", "confidence": 1.0}]
    bins = [
        {"start": float(i), "end": float(i + 1), "activity": 0.001, "active": False}
        for i in range(0, 20)
    ]
    events = decide_screen_pip_windows(
        deixis=deixis,
        activity_bins=bins,
        mode="prefer_screen",
        require_activity_for_deixis=False,
        min_hold_sec=2.0,
        activity_threshold=0.035,
        off_hold_sec=1.0,
    )
    assert len(events) >= 1
    assert events[0]["type"] == "screen_with_cam"
    assert events[0]["end"] - events[0]["start"] >= 2.0


def test_balanced_still_drops_idle_deixis():
    deixis = [{"start": 10.0, "end": 14.0, "keyword": "lihat", "confidence": 1.0}]
    bins = [
        {"start": float(i), "end": float(i + 1), "activity": 0.001, "active": False}
        for i in range(0, 20)
    ]
    events = decide_screen_pip_windows(
        deixis=deixis,
        activity_bins=bins,
        mode="balanced",
        require_activity_for_deixis=True,
        min_hold_sec=2.5,
        activity_threshold=0.035,
    )
    assert events == []


def test_off_hold_extends_activity_run():
    bins = []
    for i in range(0, 20):
        active = 5 <= i < 10
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
        mode="prefer_screen",
        min_active_sec=1.0,
        min_hold_sec=2.0,
        off_hold_sec=1.5,
        activity_threshold=0.035,
    )
    assert events
    # activity 5..10 + off_hold 1.5 → end around 11.5
    assert events[0]["end"] >= 11.0


def test_screen_bias_lowers_threshold():
    cfg = {
        "activity_threshold": 0.040,
        "min_active_sec": 2.0,
        "min_hold_sec": 2.5,
        "merge_gap_sec": 0.8,
        "pad_before_sec": 0.4,
        "pad_after_sec": 1.2,
        "off_hold_sec": 1.0,
        "screen_bias": 0.5,
    }
    out = apply_screen_bias(cfg)
    assert out["activity_threshold"] < 0.040
    assert out["min_active_sec"] < 2.0
    assert out["merge_gap_sec"] > 0.8


def test_edl_suggest_cuts_medium_silence():
    # speech 0-2, silence 2-3.5 (1.5s), speech 3.5-5
    words = [
        {"text": "halo", "start": 0.0, "end": 0.4},
        {"text": "dunia", "start": 0.5, "end": 1.2},
        {"text": "oke", "start": 1.3, "end": 2.0},
        {"text": "lanjut", "start": 3.5, "end": 4.2},
        {"text": "ya", "start": 4.3, "end": 5.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=0.5,
        hold_if_gap_sec=5.0,
        hold_sec=1.5,
        min_keep_sec=0.3,
        snap=False,
    )
    ranges = edl["ranges"]
    assert len(ranges) == 2
    assert ranges[0]["end"] <= 2.1
    assert ranges[1]["start"] >= 3.4
    assert edl["_meta"]["keep_sec"] < 5.0


def test_edl_suggest_holds_long_ai_wait():
    # speech, then 10s gap, then speech — should keep hold_sec of the wait
    words = [
        {"text": "tunggu", "start": 0.0, "end": 1.0},
        {"text": "selesai", "start": 12.0, "end": 13.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=0.5,
        hold_if_gap_sec=5.0,
        hold_sec=1.5,
        min_keep_sec=0.3,
        snap=False,
    )
    ranges = edl["ranges"]
    assert len(ranges) == 2
    # first range should extend into the wait (~1.5s hold)
    assert ranges[0]["end"] >= 2.4
    assert ranges[0]["end"] < 12.0
    keep = edl["_meta"]["keep_sec"]
    assert keep < 14.0
    assert keep >= 2.5  # ~1s + 1.5 hold + 1s


def test_edl_suggest_respects_source_window():
    words = [
        {"text": "a", "start": 0.0, "end": 1.0},
        {"text": "b", "start": 10.0, "end": 11.0},
        {"text": "c", "start": 20.0, "end": 21.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=0.5,
        hold_if_gap_sec=8.0,
        hold_sec=2.0,
        source_start=5.0,
        source_end=15.0,
        snap=False,
        min_keep_sec=0.3,
    )
    ranges = edl["ranges"]
    assert all(r["start"] >= 5.0 - 0.01 for r in ranges)
    assert all(r["end"] <= 15.0 + 0.01 for r in ranges)
    assert not any(r["start"] < 1.0 for r in ranges)
