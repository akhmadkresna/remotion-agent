"""Tests for framing-aware + density/relevance overlay suggest."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_editor.cover.overlay_suggest import (
    caps_for_duration,
    companion_framing_event,
    ensure_overlay_dwell,
    find_payoff_hits,
    get_dwell_holds,
    is_mostly_screen,
    merge_framing_into_events,
    min_gap_ok,
    score_emphasis,
    screen_windows,
    short_label,
    suggest_overlays,
)


def test_caps_scale_and_reserve_structure():
    short = caps_for_duration(300)
    long = caps_for_duration(1560)
    assert long["target_total"] > short["target_total"]
    assert long["structure_reserve"] >= short["structure_reserve"]
    assert long["target_total"] >= long["structure_reserve"]
    # Denser defaults (~1 / 40s): ~21m keep should ask for many stings
    mid = caps_for_duration(1275)
    assert mid["target_total"] >= 30
    assert mid["emphasis"] >= 8


def test_short_label_rejects_generic_speech_notes():
    assert short_label("speech", fallback="Demo") == "Demo"
    assert short_label("speech+wait-beat", fallback="Roadmap") == "Roadmap"
    assert short_label("roadmap walkthrough") == "Roadmap"


def test_punch_and_roadmap_boost_emphasis_score():
    hit = {"text": "Roadmap", "start": 40.0, "end": 41.0, "phrase": "roadmap"}
    base = score_emphasis(hit, screen_wins=[], punch_wins=[])
    punched = score_emphasis(hit, screen_wins=[], punch_wins=[(39.0, 41.0)])
    assert punched > base
    other = score_emphasis(
        {"text": "Status", "start": 40.0, "end": 41.0, "phrase": "status"},
        screen_wins=[],
        punch_wins=[],
    )
    assert base > other  # roadmap ranked / boosted over late singles


def test_dwell_holds_from_style_are_readable():
    holds = get_dwell_holds("tutorial")
    assert holds["chip"] >= 3.5
    assert holds["chapter"] >= 4.5
    assert holds["diagram"] >= 6.0
    assert holds["emphasis"] >= 2.0
    assert holds["min"] >= 1.5
    s, e = ensure_overlay_dwell(10.0, 10.8, kind="chip")
    assert e - s >= holds["chip"] - 0.01
    s2, e2 = ensure_overlay_dwell(20.0, 20.5, kind="emphasis")
    assert e2 - s2 >= holds["emphasis"] - 0.01


def test_dwell_moves_to_keep_that_fits():
    """Short overlapping keep → place chip in nearby keep that fits min_hold."""
    ranges = [
        {"source": "cam", "start": 10.0, "end": 11.0},
        {"source": "cam", "start": 12.0, "end": 20.0},
    ]
    s, e = ensure_overlay_dwell(
        10.2,
        10.5,
        kind="chip",
        edl_ranges=ranges,
        holds={"chip": 4.0, "min": 1.8},
    )
    assert s >= 12.0 - 1e-6
    assert e - s >= 4.0 - 0.01
    assert e <= 20.0 + 1e-6


def test_short_label_curates_notes():
    assert short_label("hook + plan: continue toko material, roadmap") == "Roadmap"
    assert "Master Data" == short_label("phase 1 done: menus, res.partner, UDU check")
    assert short_label("purchase demo + status buttons + stock bug → diterima") == "Pembelian"
    assert short_label("not only toko material + phase 2 summary") == "Bukan Cuma Toko Material"


def test_screen_windows_and_majority():
    wins = screen_windows(
        [
            {"type": "screen_with_cam", "start": 10, "end": 40},
            {"type": "framing", "start": 0, "end": 5, "framing": "close"},
        ]
    )
    assert wins == [(10.0, 40.0)]
    assert is_mostly_screen(12, 20, wins) is True
    assert is_mostly_screen(0, 8, wins) is False


def test_companion_framing_rules():
    assert companion_framing_event(
        kind="chapter", start=1, end=4, on_screen=True, ov_id="c1"
    ) is None
    ch = companion_framing_event(
        kind="chapter", start=1, end=4, on_screen=False, ov_id="c1"
    )
    assert ch is not None
    assert ch["type"] == "framing"
    assert ch["framing"] == "medium"
    diag = companion_framing_event(
        kind="diagram", start=10, end=16, on_screen=False, ov_id="d1"
    )
    assert diag is not None and diag["framing"] == "wide"
    assert (
        companion_framing_event(
            kind="emphasis", start=2, end=3, on_screen=False, ov_id="e1"
        )
        is None
    )


def test_min_gap_ok():
    spans = [(10.0, 13.0), (200.0, 203.0)]
    assert min_gap_ok(12.0, spans, min_gap=90.0) is False
    assert min_gap_ok(300.0, spans, min_gap=90.0) is True


def test_payoff_hits_and_screen_enter_score():
    words = [
        {"text": "kita", "start": 10.0, "end": 10.2},
        {"text": "cek", "start": 10.3, "end": 10.5},
        {"text": "stok", "start": 10.6, "end": 11.0},
        {"text": "otomatis", "start": 50.0, "end": 50.5},
        {"text": "diterima", "start": 12.0, "end": 12.5},
    ]
    hits = find_payoff_hits(words)
    labels = {h["text"] for h in hits}
    assert "Stok" in labels
    assert "Diterima" in labels
    assert "Otomatis" in labels
    wins = [(10.0, 40.0)]
    near = next(h for h in hits if h["text"] == "Stok")
    far = next(h for h in hits if h["text"] == "Otomatis")
    assert score_emphasis(near, screen_wins=wins) > score_emphasis(far, screen_wins=wins)


def test_merge_framing_replaces_overlay_notes_only():
    existing = [
        {"type": "screen_with_cam", "start": 10, "end": 40},
        {"type": "framing", "start": 1, "end": 3, "framing": "close", "note": "overlay:old"},
        {"type": "framing", "start": 50, "end": 55, "framing": "close", "note": "manual"},
    ]
    new = [
        {
            "type": "framing",
            "start": 1,
            "end": 4,
            "framing": "medium",
            "note": "overlay:chip-open",
        }
    ]
    merged = merge_framing_into_events(existing, new)
    notes = [str(e.get("note") or "") for e in merged if e.get("type") == "framing"]
    assert "overlay:old" not in notes
    assert "manual" in notes
    assert "overlay:chip-open" in notes


def _write_words(edit: Path, pairs: list[tuple[str, float, float]]) -> None:
    (edit / "transcripts").mkdir(exist_ok=True)
    words = [
        {"type": "word", "word": t, "text": t, "start": s, "end": e} for t, s, e in pairs
    ]
    (edit / "transcripts" / "cam.json").write_text(
        json.dumps({"language": "id", "backend": "test", "model": "small", "words": words}),
        encoding="utf-8",
    )


def test_suggest_emits_framing_for_cam_chapter(tmp_path: Path):
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: demo\nsources:\n  cam: raw/cam.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4"},
                "ranges": [
                    {"source": "cam", "start": 0.0, "end": 20.0, "note": "hook intro"},
                    {
                        "source": "cam",
                        "start": 30.0,
                        "end": 80.0,
                        "note": "phase build flow steps",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    _write_words(
        edit,
        [
            ("hook", 0.1, 0.5),
            ("intro", 0.5, 1.0),
            ("phase", 30.5, 30.9),
            ("build", 31.0, 31.4),
            ("flow", 31.5, 31.9),
            ("stok", 32.0, 32.4),
            ("otomatis", 40.0, 40.5),
            ("studio", 41.0, 41.4),
        ],
    )

    out = suggest_overlays(episode)
    assert out["overlays"]
    face_heavy = [o for o in out["overlays"] if o["kind"] in {"chapter", "diagram", "chip"}]
    assert face_heavy
    assert all(o.get("cover_mode") == "full_cam" for o in face_heavy)
    assert out["framing_events"]


def test_suggest_skips_framing_on_screen_cover(tmp_path: Path):
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: demo\nsources:\n  cam: raw/cam.mp4\n  screen: raw/screen.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4", "screen": "../raw/screen.mp4"},
                "ranges": [
                    {
                        "source": "cam",
                        "start": 10.0,
                        "end": 100.0,
                        "note": "phase master data flow",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (edit / "cover.json").write_text(
        json.dumps(
            {
                "camera_play": {"snap_on_cuts": True, "home": "medium", "alt": "close"},
                "events": [
                    {"type": "screen_with_cam", "start": 10.0, "end": 100.0, "note": "ui"}
                ],
                "captions": [],
            }
        ),
        encoding="utf-8",
    )
    _write_words(
        edit,
        [
            ("phase", 10.1, 10.5),
            ("flow", 11.0, 11.4),
            ("stok", 12.0, 12.4),
            ("diterima", 20.0, 20.5),
        ],
    )

    out = suggest_overlays(episode)
    assert out["_meta"]["has_cover"] is True
    on_screen = [o for o in out["overlays"] if o.get("cover_mode") == "screen_with_cam"]
    assert on_screen
    for o in on_screen:
        if o["kind"] in {"chapter", "diagram"}:
            assert o.get("requires_framing") is None


def test_structure_before_emphasis_and_curated_copy(tmp_path: Path):
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: odoo-studio-video-2\nsources:\n  cam: raw/cam.mp4\n  screen: raw/screen.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4", "screen": "../raw/screen.mp4"},
                "ranges": [
                    {"source": "cam", "start": 0.0, "end": 30.0, "note": "hook plan"},
                    {
                        "source": "cam",
                        "start": 40.0,
                        "end": 200.0,
                        "note": "phase 1 master data flow",
                    },
                    {
                        "source": "cam",
                        "start": 210.0,
                        "end": 400.0,
                        "note": "purchase demo bug diterima",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (edit / "cover.json").write_text(
        json.dumps(
            {
                "events": [
                    {"type": "screen_with_cam", "start": 40.0, "end": 200.0},
                    {"type": "screen_with_cam", "start": 210.0, "end": 400.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    pairs: list[tuple[str, float, float]] = [("lanjut", 1.0, 1.4), ("toko", 1.5, 1.9)]
    # many weak words that old logic loved
    t = 45.0
    for w in ["model", "penting", "custom", "field", "model", "penting"]:
        pairs.append((w, t, t + 0.3))
        t += 1.0
    # real payoffs near screen enters
    pairs.extend(
        [
            ("stok", 42.0, 42.5),
            ("otomatis", 43.0, 43.5),
            ("diterima", 215.0, 215.6),
            ("chatter", 300.0, 300.5),
        ]
    )
    _write_words(edit, pairs)

    out = suggest_overlays(episode)
    kinds = [o["kind"] for o in out["overlays"]]
    assert kinds.count("chapter") + kinds.count("chip") + kinds.count("diagram") >= 2
    emph = [o for o in out["overlays"] if o["kind"] == "emphasis"]
    texts = {o["text"] for o in emph}
    # curated payoffs preferred over raw model/penting
    assert "penting" not in {t.lower() for t in texts}
    assert texts & {"Stok", "Otomatis", "Diterima", "Chatter"}
    # chapter labels curated
    chapters = [o for o in out["overlays"] if o["kind"] == "chapter"]
    assert chapters
    assert all("res.partner" not in o["text"] or o["text"] == "Master Data" or len(o["text"]) < 40 for o in chapters)
    assert any(o["text"] in {"Lanjut Toko Material", "Master Data", "Pembelian"} for o in chapters)


def test_punch_guarantee_places_mg_on_bare_punch(tmp_path: Path):
    """Punch-in with no nearby payoff candidate still gets an emphasis sting."""
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: demo\nsources:\n  cam: raw/cam.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4"},
                "ranges": [
                    {"source": "cam", "start": 0.0, "end": 30.0, "note": "hook"},
                    {
                        "source": "cam",
                        "start": 1600.0,
                        "end": 1720.0,
                        "note": "mid restrict talk",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (edit / "cover.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "type": "punch_in",
                        "start": 1660.0,
                        "end": 1661.5,
                        "note": "restrict",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pairs: list[tuple[str, float, float]] = [
        ("hook", 0.2, 0.6),
        ("intro", 1.0, 1.4),
        ("restrict", 1658.0, 1658.5),
        ("akses", 1659.0, 1659.4),
        ("user", 1659.5, 1659.9),
    ]
    _write_words(edit, pairs)

    out = suggest_overlays(episode)
    near = [
        o
        for o in out["overlays"]
        if abs(float(o["start"]) - 1660.0) < 10.0
    ]
    assert near, "bare punch_in must get MG"
    assert any(o["kind"] == "emphasis" for o in near)
