"""Suggest radio-edit EDL from transcript silence gaps.

Cuts gaps ≥ ``gap_cut_sec``; long intentional pauses (≥ ``hold_if_gap_sec``)
are collapsed to ``hold_sec`` instead of removed entirely (AI wait / think time).

Always writes ``edit/edl.suggest.json`` — agent must confirm before ``--apply``
or ``ae cut``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agentic_editor.cover.suggest import load_cam_words
from agentic_editor.editor.edl import snap_range_to_words
from agentic_editor.paths import framework_home
from agentic_editor.project import load_project

DEFAULT_RADIO_CFG: dict[str, Any] = {
    "silence_gap_sec": 0.5,  # pack phrases
    "gap_cut_sec": 0.5,  # cut silences ≥ this
    "hold_if_gap_sec": 5.0,  # longer gaps → keep a short hold
    "hold_sec": 1.5,
    "min_keep_sec": 0.4,
    "pad_before_sec": 0.05,
    "pad_after_sec": 0.08,
}


def load_style_radio_config(style_name: str = "tutorial") -> dict[str, Any]:
    cfg = dict(DEFAULT_RADIO_CFG)
    path = framework_home() / "styles" / style_name / "style.md"
    if not path.is_file():
        return cfg
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S | re.I)
    if not m:
        return cfg
    try:
        parsed = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return cfg
    radio = parsed.get("radio_edit") or {}
    if isinstance(radio, dict):
        for k, v in radio.items():
            if v is not None:
                cfg[k] = v
    return cfg


def _speech_intervals(words: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Merge contiguous word spans (ignore tiny gaps < 50ms)."""
    tokens = []
    for w in words:
        try:
            s = float(w["start"])
            e = float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e <= s:
            continue
        tokens.append((s, e))
    if not tokens:
        return []
    tokens.sort()
    merged: list[tuple[float, float]] = [tokens[0]]
    for s, e in tokens[1:]:
        ps, pe = merged[-1]
        if s <= pe + 0.05:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def suggest_edl_from_words(
    words: list[dict[str, Any]],
    *,
    source: str = "cam",
    sources: dict[str, str] | None = None,
    gap_cut_sec: float = 0.5,
    hold_if_gap_sec: float = 5.0,
    hold_sec: float = 1.5,
    min_keep_sec: float = 0.4,
    pad_before_sec: float = 0.05,
    pad_after_sec: float = 0.08,
    source_start: float | None = None,
    source_end: float | None = None,
    snap: bool = True,
) -> dict[str, Any]:
    """
    Build keep ranges from speech, cutting silence gaps.

    - Gaps in ``[gap_cut_sec, hold_if_gap_sec)`` → hard cut
    - Gaps ≥ ``hold_if_gap_sec`` → insert ``hold_sec`` of source (AI wait)
    """
    intervals = _speech_intervals(words)
    if source_start is not None or source_end is not None:
        s0 = float(source_start if source_start is not None else 0.0)
        s1 = float(source_end) if source_end is not None else float("inf")
        intervals = [(max(a, s0), min(b, s1)) for a, b in intervals if min(b, s1) - max(a, s0) > 0.05]

    ranges: list[dict[str, Any]] = []
    if not intervals:
        return {
            "sources": sources or {source: f"../raw/{source}.mp4"},
            "ranges": [],
            "_meta": {"keep_sec": 0.0, "strategy": "silence-cut", "empty": True},
        }

    # Walk speech intervals; cut or hold gaps between them
    cur_start, cur_end = intervals[0]
    for nxt_start, nxt_end in intervals[1:]:
        gap = nxt_start - cur_end
        if gap < gap_cut_sec:
            # tiny gap — glue
            cur_end = max(cur_end, nxt_end)
            continue
        if gap >= hold_if_gap_sec:
            # keep speech, then a short hold into the wait, then next speech
            hold_end = min(nxt_start, cur_end + hold_sec)
            if hold_end > cur_end + 0.05:
                cur_end = hold_end
            ranges.append(
                {
                    "source": source,
                    "start": cur_start,
                    "end": cur_end,
                    "note": "speech+hold",
                }
            )
            cur_start, cur_end = nxt_start, nxt_end
            continue
        # medium silence — hard cut
        ranges.append(
            {
                "source": source,
                "start": cur_start,
                "end": cur_end,
                "note": "speech",
            }
        )
        cur_start, cur_end = nxt_start, nxt_end
    ranges.append({"source": source, "start": cur_start, "end": cur_end, "note": "speech"})

    # Snap + min keep
    word_dicts = [
        {
            "type": "word",
            "start": float(w["start"]),
            "end": float(w["end"]),
            "word": w.get("text") or w.get("word") or "",
        }
        for w in words
        if w.get("start") is not None and w.get("end") is not None
    ]
    cleaned: list[dict[str, Any]] = []
    for r in ranges:
        s, e = float(r["start"]), float(r["end"])
        if snap and word_dicts:
            s, e = snap_range_to_words(
                s, e, word_dicts, pad_before=pad_before_sec, pad_after=pad_after_sec
            )
        if source_start is not None:
            s = max(s, float(source_start))
        if source_end is not None:
            e = min(e, float(source_end))
        if e - s < min_keep_sec:
            continue
        cleaned.append({**r, "start": round(s, 3), "end": round(e, 3)})

    keep = sum(float(r["end"]) - float(r["start"]) for r in cleaned)
    return {
        "sources": sources or {source: f"../raw/{source}.mp4"},
        "ranges": cleaned,
        "grade": None,
        "_meta": {
            "strategy": "silence-cut",
            "gap_cut_sec": gap_cut_sec,
            "hold_if_gap_sec": hold_if_gap_sec,
            "hold_sec": hold_sec,
            "min_keep_sec": min_keep_sec,
            "source_start": source_start,
            "source_end": source_end,
            "keep_sec": round(keep, 3),
            "range_count": len(cleaned),
        },
    }


def suggest_edl(
    episode: Path,
    *,
    gap_cut_sec: float | None = None,
    hold_if_gap_sec: float | None = None,
    hold_sec: float | None = None,
    min_keep_sec: float | None = None,
    source_start: float | None = None,
    source_end: float | None = None,
) -> dict[str, Any]:
    """Suggest EDL for episode from cam transcript + style radio_edit knobs."""
    cfg = load_project(episode)
    style = str(cfg.get("style") or "tutorial")
    radio = load_style_radio_config(style)
    if gap_cut_sec is not None:
        radio["gap_cut_sec"] = float(gap_cut_sec)
    if hold_if_gap_sec is not None:
        radio["hold_if_gap_sec"] = float(hold_if_gap_sec)
    if hold_sec is not None:
        radio["hold_sec"] = float(hold_sec)
    if min_keep_sec is not None:
        radio["min_keep_sec"] = float(min_keep_sec)

    edit = episode / "edit"
    words = load_cam_words(edit)
    sources_cfg = cfg.get("sources") or {}
    # EDL paths are relative to edit/
    edl_sources: dict[str, str] = {}
    for name, rel in sources_cfg.items():
        p = Path(str(rel))
        if p.is_absolute():
            edl_sources[name] = str(p)
        else:
            # project paths are episode-relative; EDL expects edit-relative
            edl_sources[name] = str(Path("..") / p).replace("\\", "/")

    source = "cam" if "cam" in edl_sources else next(iter(edl_sources), "cam")
    suggestion = suggest_edl_from_words(
        words,
        source=source,
        sources=edl_sources or {"cam": "../raw/cam.mp4"},
        gap_cut_sec=float(radio["gap_cut_sec"]),
        hold_if_gap_sec=float(radio["hold_if_gap_sec"]),
        hold_sec=float(radio["hold_sec"]),
        min_keep_sec=float(radio["min_keep_sec"]),
        pad_before_sec=float(radio["pad_before_sec"]),
        pad_after_sec=float(radio["pad_after_sec"]),
        source_start=source_start,
        source_end=source_end,
    )
    meta = suggestion.setdefault("_meta", {})
    meta["style"] = style
    meta["radio_config"] = {
        k: radio[k]
        for k in (
            "gap_cut_sec",
            "hold_if_gap_sec",
            "hold_sec",
            "min_keep_sec",
            "silence_gap_sec",
        )
        if k in radio
    }
    meta["word_count"] = len(words)
    return suggestion


def write_edl_suggest(episode: Path, suggestion: dict[str, Any]) -> Path:
    edit = episode / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    out = edit / "edl.suggest.json"
    out.write_text(json.dumps(suggestion, indent=2) + "\n", encoding="utf-8")
    return out
