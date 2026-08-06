"""Invariant tests for gap-class radio-edit (tight pacing: think hard-cut)."""

from __future__ import annotations

from agentic_editor.editor.edl import snap_range_to_words
from agentic_editor.editor.edl_suggest import suggest_edl_from_words
from agentic_editor.editor.gap_class import GapClass, GapPolicy, classify_gap


def test_classify_breath_think_ai_wait():
    p = GapPolicy(breath_max=0.6, wait_min=5.0, hold_sec=0.4)
    assert classify_gap(0.4, policy=p) == GapClass.BREATH
    assert classify_gap(2.5, policy=p) == GapClass.THINK
    assert classify_gap(4.8, policy=p) == GapClass.THINK
    assert classify_gap(6.0, policy=p) == GapClass.AI_WAIT


def test_pathological_long_segment_split_on_words():
    """Whisper mega-segment with tiny speech must not keep minutes of silence."""
    segments = [
        {"start": 0.0, "end": 2.0, "text": "halo guys"},
        # 10 minutes stamped on a 2-word phrase
        {"start": 10.0, "end": 610.0, "text": "sudah selesai lagi ya"},
        {"start": 620.0, "end": 622.0, "text": "lanjut"},
    ]
    words = [
        {"text": "halo", "start": 0.0, "end": 0.5},
        {"text": "guys", "start": 0.6, "end": 1.2},
        {"text": "sudah", "start": 10.0, "end": 10.4},
        {"text": "selesai", "start": 10.5, "end": 11.0},
        {"text": "lagi", "start": 11.1, "end": 11.4},
        {"text": "ya", "start": 11.5, "end": 11.8},
        {"text": "lanjut", "start": 620.0, "end": 621.5},
    ]
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        breath_max_sec=0.6,
        wait_min_sec=5.0,
        hold_sec=0.4,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    assert edl["_meta"]["unit"] == "segment+word"
    assert edl["_meta"].get("segments_split", 0) >= 1
    keep = sum(float(r["end"]) - float(r["start"]) for r in edl["ranges"])
    assert keep < 30.0  # not ~612s of silence
    # No keep should swallow the empty AI wait
    assert all(float(r["end"]) - float(r["start"]) < 20 for r in edl["ranges"])


def test_breath_still_merges():
    """Sub-breath_max pause stays inside one keep."""
    segments = [
        {"start": 0.0, "end": 1.0, "text": "satu"},
        {"start": 1.4, "end": 2.5, "text": "dua"},
    ]
    words = [{"text": "x", "start": s["start"], "end": s["end"]} for s in segments]
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        breath_max_sec=0.6,
        wait_min_sec=5.0,
        hold_sec=0.4,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    assert len(edl["ranges"]) == 1
    assert edl["ranges"][0]["end"] == 2.5
    assert edl["_meta"]["gap_classes"]["breath"] >= 1


def test_wait_hold_tail_survives_snap():
    words = [
        {"text": "klik", "start": 0.0, "end": 1.0, "type": "word"},
        {"text": "selesai", "start": 12.0, "end": 13.0, "type": "word"},
    ]
    # Speech-only snap would pull 2.0 → 1.08; hold_tail must keep the beat
    s, e = snap_range_to_words(0.0, 2.0, words, hold_tail=True)
    assert e >= 1.95

    segments = [
        {"start": 0.0, "end": 1.0, "text": "klik tombolnya"},
        {"start": 12.0, "end": 13.0, "text": "selesai"},
    ]
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        wait_min_sec=5.0,
        hold_sec=0.4,
        snap=True,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    assert len(edl["ranges"]) == 2
    # First range must extend into the wait (~0.4s beat), not snap away
    assert edl["ranges"][0]["end"] >= 1.35


def test_retake_dropped():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "kemudian ke cloud code"},
        {"start": 3.0, "end": 6.0, "text": "kemudian ke cloud code hasil kerjaan"},
        {"start": 10.0, "end": 11.0, "text": "lanjut"},
    ]
    words = [{"text": "x", "start": s["start"], "end": s["end"]} for s in segments]
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        wait_min_sec=5.0,
        snap=False,
        cut_repeats=True,
        repeat_similarity=0.72,
        cut_wait_speech=False,
    )
    assert edl["_meta"]["dropped_repeat"] >= 1
