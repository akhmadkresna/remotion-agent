"""Invariant tests for gap-class radio-edit (not threshold geometry)."""

from __future__ import annotations

from agentic_editor.editor.edl import snap_range_to_words
from agentic_editor.editor.edl_suggest import suggest_edl_from_words
from agentic_editor.editor.gap_class import GapClass, GapPolicy, classify_gap


def test_classify_think_not_cut():
    p = GapPolicy(breath_max=1.2, wait_min=5.0, hold_sec=1.0)
    assert classify_gap(0.4, policy=p) == GapClass.BREATH
    assert classify_gap(2.5, policy=p) == GapClass.THINK
    assert classify_gap(4.8, policy=p) == GapClass.THINK
    assert classify_gap(6.0, policy=p) == GapClass.AI_WAIT


def test_mid_thought_pause_stays_one_keep():
    """~2.5–4.8s think pauses must not shred a sentence across keeps."""
    segments = [
        {"start": 0.0, "end": 2.0, "text": "kita akalin itu juga ya"},
        {"start": 4.5, "end": 8.0, "text": "kita tidak akan menggunakan app standard"},
        {"start": 20.0, "end": 22.0, "text": "selesai"},
    ]
    words = []
    for seg in segments:
        words.append({"text": "x", "start": seg["start"], "end": seg["end"]})
    edl = suggest_edl_from_words(
        words,
        segments=segments,
        wait_min_sec=5.0,
        hold_sec=1.0,
        snap=False,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    # First two clauses bridged by think pause; long gap before selesai compresses
    assert len(edl["ranges"]) == 2
    assert edl["ranges"][0]["end"] >= 8.0
    assert edl["_meta"]["gap_classes"]["think"] >= 1
    assert edl["_meta"]["gap_classes"]["ai_wait"] >= 1


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
        hold_sec=1.0,
        snap=True,
        cut_repeats=False,
        cut_wait_speech=False,
    )
    assert len(edl["ranges"]) == 2
    # First range must extend into the wait (~1s beat), not snap away
    assert edl["ranges"][0]["end"] >= 1.9


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
