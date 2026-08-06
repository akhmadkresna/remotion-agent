"""Tests for prefer_screen cover suggest + gap-class EDL suggest."""

from __future__ import annotations

from agentic_editor.cover.suggest import (
    apply_screen_bias,
    decide_screen_pip_windows,
)
from agentic_editor.editor.edl_suggest import (
    is_wait_speech,
    load_style_radio_config,
    phrase_similarity,
    suggest_edl_from_words,
)


def test_prefer_screen_keeps_deixis_without_activity():
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


def test_cover_stitches_intent_across_edl_holes():
    """One source-time demo must not shatter into many screen events."""
    deixis = [{"start": 10.0, "end": 40.0, "keyword": "lihat", "confidence": 1.0}]
    bins = [
        {
            "start": float(i),
            "end": float(i + 1),
            "activity": 0.09 if 12 <= i < 38 else 0.001,
            "active": 12 <= i < 38,
        }
        for i in range(0, 50)
    ]
    edl = [
        {"source": "cam", "start": 10.0, "end": 18.0},
        {"source": "cam", "start": 22.0, "end": 30.0},
        {"source": "cam", "start": 34.0, "end": 42.0},
    ]
    events = decide_screen_pip_windows(
        deixis=deixis,
        activity_bins=bins,
        edl_ranges=edl,
        mode="prefer_screen",
        require_activity_for_deixis=False,
        min_hold_sec=2.0,
        merge_gap_sec=1.2,
        activity_threshold=0.035,
        off_hold_sec=1.0,
    )
    # Stitched: one (or few) continuous screen intents, not 3 shards
    assert len(events) <= 2
    assert max(e["end"] - e["start"] for e in events) >= 20.0


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


def test_style_radio_config_is_gap_class():
    cfg = load_style_radio_config("tutorial")
    assert cfg.get("wait_min_sec", cfg.get("hold_if_gap_sec")) >= 4.0
    assert cfg["hold_sec"] <= 0.5
    assert cfg.get("breath_max_sec", 0.6) <= 0.7
    assert cfg["cut_repeats"] is True


def test_wait_speech_only_short_prompts():
    assert is_wait_speech("tunggu sebentar")
    assert is_wait_speech("loading")
    assert not is_wait_speech(
        "kita tunggu proses pembelian sampai status diterima di gudang"
    )


def test_phrase_similarity_containment():
    assert (
        phrase_similarity(
            "kemudian ke cloud code", "kemudian ke cloud code hasil kerjaan"
        )
        >= 0.72
    )


def test_edl_suggest_respects_source_window():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "alpha words here"},
        {"start": 10.0, "end": 11.0, "text": "bravo words here"},
        {"start": 20.0, "end": 21.0, "text": "charlie words here"},
    ]
    words = [{"text": "x", "start": s["start"], "end": s["end"]} for s in segments]
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        wait_min_sec=5.0,
        hold_sec=1.0,
        source_start=5.0,
        source_end=15.0,
        snap=False,
        min_keep_sec=0.5,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    ranges = edl["ranges"]
    assert all(r["start"] >= 5.0 - 0.01 for r in ranges)
    assert all(r["end"] <= 15.0 + 0.01 for r in ranges)
    assert not any(r["start"] < 1.0 for r in ranges)
