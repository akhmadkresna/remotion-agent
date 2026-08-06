"""Tests for prefer_screen cover suggest + silence-cut EDL suggest."""

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


def test_style_radio_config_keeps_sentences():
    cfg = load_style_radio_config("tutorial")
    assert cfg["gap_cut_sec"] >= 1.2
    assert cfg["hold_sec"] <= 1.5
    assert cfg["min_keep_sec"] >= 0.8
    assert cfg["cut_repeats"] is True
    assert cfg["bridge_gap_sec"] >= 2.0


def test_edl_suggest_keeps_short_breath_inside_sentence():
    # ~1.2s breath mid-thought must NOT become a hard cut
    words = [
        {"text": "halo", "start": 0.0, "end": 0.4},
        {"text": "dunia", "start": 0.5, "end": 1.2},
        {"text": "oke", "start": 1.3, "end": 2.0},
        {"text": "lanjut", "start": 3.2, "end": 3.8},
        {"text": "ya", "start": 3.9, "end": 4.3},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=5.0,
        hold_sec=1.0,
        min_keep_sec=0.5,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
        silence_gap_sec=0.60,
        bridge_gap_sec=2.2,
    )
    ranges = edl["ranges"]
    assert len(ranges) == 1
    assert ranges[0]["end"] >= 4.2


def test_edl_suggest_cuts_medium_silence():
    words = [
        {"text": "halo", "start": 0.0, "end": 0.4},
        {"text": "dunia", "start": 0.5, "end": 1.2},
        {"text": "oke", "start": 1.3, "end": 2.0},
        {"text": "lanjut", "start": 4.5, "end": 5.2},
        {"text": "ya", "start": 5.3, "end": 6.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=5.0,
        hold_sec=1.0,
        min_keep_sec=0.5,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
        bridge_gap_sec=2.2,
    )
    # gap 2.5s: above gap_cut, above bridge → hard cut
    ranges = edl["ranges"]
    assert len(ranges) == 2
    assert ranges[0]["end"] <= 2.1
    assert ranges[1]["start"] >= 4.4


def test_edl_suggest_holds_short_beat_on_long_ai_wait():
    words = [
        {"text": "klik", "start": 0.0, "end": 1.0},
        {"text": "selesai", "start": 12.0, "end": 13.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=5.0,
        hold_sec=1.0,
        min_keep_sec=0.5,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    ranges = edl["ranges"]
    assert len(ranges) == 2
    assert ranges[0]["end"] >= 1.9
    assert ranges[0]["end"] <= 2.2
    assert ranges[0]["end"] < 12.0


def test_wait_speech_only_short_prompts():
    assert is_wait_speech("tunggu sebentar")
    assert is_wait_speech("loading")
    assert not is_wait_speech(
        "kita tunggu proses pembelian sampai status diterima di gudang"
    )


def test_edl_suggest_bridges_asr_overlap_repeat():
    # Same line transcribed twice with a short gap (classic whisper overlap)
    words = [
        {"text": "kemudian", "start": 0.0, "end": 0.4},
        {"text": "ke", "start": 0.5, "end": 0.7},
        {"text": "cloud", "start": 0.8, "end": 1.1},
        {"text": "code", "start": 1.2, "end": 1.6},
        {"text": "kemudian", "start": 3.0, "end": 3.4},
        {"text": "ke", "start": 3.5, "end": 3.7},
        {"text": "cloud", "start": 3.8, "end": 4.1},
        {"text": "code", "start": 4.2, "end": 4.6},
        {"text": "hasil", "start": 4.7, "end": 5.1},
        {"text": "kerjaan", "start": 5.2, "end": 5.8},
    ]
    assert phrase_similarity(
        "kemudian ke cloud code", "kemudian ke cloud code hasil kerjaan"
    ) >= 0.72
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=8.0,
        hold_sec=1.0,
        min_keep_sec=0.5,
        snap=False,
        cut_repeats=True,
        repeat_similarity=0.72,
        bridge_gap_sec=2.2,
        bridge_similarity=0.55,
        cut_wait_speech=False,
        silence_gap_sec=0.60,
    )
    assert len(edl["ranges"]) <= 2
    assert edl["_meta"]["dropped_repeat"] + edl["_meta"].get("bridged_ranges", 0) >= 1


def test_edl_suggest_stitches_mid_thought_breath():
    """1.9s pause between clause fragments must stay one keep."""
    words = [
        {"text": "Kemudian", "start": 26.7, "end": 27.2},
        {"text": "kayak", "start": 27.4, "end": 28.0},
        {"text": "kita", "start": 29.9, "end": 30.2},
        {"text": "ke", "start": 30.3, "end": 30.5},
        {"text": "cloud", "start": 30.7, "end": 31.1},
        {"text": "code", "start": 31.3, "end": 31.8},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=5.0,
        hold_sec=1.0,
        min_keep_sec=0.5,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
        bridge_gap_sec=2.2,
        silence_gap_sec=0.60,
    )
    assert len(edl["ranges"]) == 1
    assert edl["ranges"][0]["end"] - edl["ranges"][0]["start"] >= 4.5


def test_edl_suggest_respects_source_window():
    words = [
        {"text": "alpha", "start": 0.0, "end": 1.0},
        {"text": "bravo", "start": 10.0, "end": 11.0},
        {"text": "charlie", "start": 20.0, "end": 21.0},
    ]
    edl = suggest_edl_from_words(
        words,
        gap_cut_sec=1.50,
        hold_if_gap_sec=8.0,
        hold_sec=1.0,
        source_start=5.0,
        source_end=15.0,
        snap=False,
        min_keep_sec=0.5,
        cut_repeats=False,
        cut_wait_speech=False,
        bridge_gap_sec=2.2,
    )
    ranges = edl["ranges"]
    assert all(r["start"] >= 5.0 - 0.01 for r in ranges)
    assert all(r["end"] <= 15.0 + 0.01 for r in ranges)
    assert not any(r["start"] < 1.0 for r in ranges)
