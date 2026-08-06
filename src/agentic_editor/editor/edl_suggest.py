"""Suggest radio-edit EDL from transcript silence gaps + wait/repeat cuts.

Tutorial defaults balance clean speech with wait trimming:
  - Cut silences ≥ ``gap_cut_sec`` (~0.7s) — keep breath pauses inside sentences
  - AI / screen waits ≥ ``hold_if_gap_sec`` collapse to a short beat (``hold_sec``)
  - Drop near-duplicate / ASR-overlap phrases (Jaccard + containment)
  - Clamp short wait-filler prompts only (not every word like "proses")

Always writes ``edit/edl.suggest.json`` — confirm before ``--apply`` / ``ae cut``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agentic_editor.cover.suggest import load_cam_words
from agentic_editor.editor.edl import snap_range_to_words
from agentic_editor.editor.pack import group_into_phrases
from agentic_editor.paths import framework_home
from agentic_editor.project import load_project

DEFAULT_RADIO_CFG: dict[str, Any] = {
    # Pack into sentence-ish phrases (don't split on every breath)
    "silence_gap_sec": 0.55,
    # Cut only clear pauses — 0.35 shredded Indonesian speech
    "gap_cut_sec": 0.70,
    # Long idle / AI spinner → short beat only
    "hold_if_gap_sec": 5.0,
    "hold_sec": 1.0,
    "min_keep_sec": 0.90,
    "pad_before_sec": 0.08,
    "pad_after_sec": 0.12,
    "cut_repeats": True,
    "repeat_similarity": 0.72,
    "repeat_window_sec": 60.0,
    # Merge near keeps that are ASR overlaps / same thought
    "bridge_gap_sec": 2.5,
    "bridge_similarity": 0.55,
    "cut_wait_speech": True,
    "wait_speech_max_sec": 0.9,
}

# Must look like a wait prompt — avoid matching normal sentences
WAIT_SPEECH_RE = re.compile(
    r"(?i)^(?=.{0,48}$).*\b("
    r"tunggu(\s+(sebentar|dulu|ya|loading))?|"
    r"sebentar|"
    r"bentar|"
    r"please\s+wait|"
    r"loading|"
    r"masih\s+(proses|loading|nunggu)|"
    r"satu\s+detik|"
    r"moment"
    r")\b"
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_FILLER = frozenset(
    {
        "ya",
        "yah",
        "oke",
        "ok",
        "nah",
        "dan",
        "atau",
        "yang",
        "di",
        "ke",
        "dari",
        "juga",
        "sih",
        "dong",
        "lah",
        "nih",
        "ini",
        "itu",
        "the",
        "a",
        "an",
        "of",
        "to",
        "for",
        "guys",
    }
)


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


def normalize_phrase(text: str) -> str:
    tokens = [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _FILLER and len(t) > 1
    ]
    return " ".join(tokens)


def phrase_similarity(a: str, b: str) -> float:
    """Jaccard + containment — catches ASR overlap fragments repeating the same line."""
    ta = set(normalize_phrase(a).split())
    tb = set(normalize_phrase(b).split())
    if not ta or not tb:
        na, nb = normalize_phrase(a), normalize_phrase(b)
        return 1.0 if na and na == nb else 0.0
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    containment = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(jaccard, containment)


def is_wait_speech(text: str) -> bool:
    """True only for short wait-prompt lines, not normal sentences that mention waiting."""
    raw = (text or "").strip()
    if not raw or not WAIT_SPEECH_RE.search(raw):
        return False
    tokens = [t for t in _TOKEN_RE.findall(raw) if t.lower() not in _FILLER]
    # Long explanatory sentences that happen to include "sebentar" stay intact
    if len(tokens) > 8:
        return False
    return True


def _range_text(words: list[dict[str, Any]], start: float, end: float) -> str:
    parts: list[str] = []
    for w in words:
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e <= start or s >= end:
            continue
        t = (w.get("text") or w.get("word") or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts)


def _filter_phrases(
    phrases: list[dict[str, Any]],
    *,
    cut_repeats: bool,
    repeat_similarity: float,
    repeat_window_sec: float,
    cut_wait_speech: bool,
    wait_speech_max_sec: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Drop repeats / clamp wait-filler phrases. Returns (kept, stats)."""
    kept: list[dict[str, Any]] = []
    stats = {"dropped_repeat": 0, "clamped_wait": 0, "dropped_wait": 0}
    for p in phrases:
        text = str(p.get("text") or "")
        start = float(p["start"])
        end = float(p["end"])
        dur = end - start

        if cut_wait_speech and is_wait_speech(text):
            if dur <= wait_speech_max_sec * 0.5:
                stats["dropped_wait"] += 1
                continue
            end = start + wait_speech_max_sec
            p = {**p, "end": end, "note": "wait-clamp"}
            stats["clamped_wait"] += 1

        if cut_repeats and kept:
            drop = False
            for i in range(len(kept) - 1, -1, -1):
                prev = kept[i]
                if start - float(prev["end"]) > repeat_window_sec:
                    break
                sim = phrase_similarity(text, str(prev.get("text") or ""))
                if sim < repeat_similarity:
                    continue
                prev_dur = float(prev["end"]) - float(prev["start"])
                cur_dur = end - start
                # Prefer keeping the longer take when ASR overlaps
                if cur_dur > prev_dur * 1.25:
                    kept.pop(i)
                    stats["dropped_repeat"] += 1
                    break
                stats["dropped_repeat"] += 1
                drop = True
                break
            if drop:
                continue

        kept.append(p)
    return kept, stats


def _coalesce_ranges(
    ranges: list[dict[str, Any]],
    words: list[dict[str, Any]],
    *,
    bridge_gap_sec: float,
    bridge_similarity: float,
    min_keep_sec: float,
) -> tuple[list[dict[str, Any]], int]:
    """Merge neighboring keeps that are the same thought / ASR overlap."""
    if not ranges:
        return [], 0
    merged = 0
    out: list[dict[str, Any]] = []
    cur = dict(ranges[0])
    cur_text = _range_text(words, float(cur["start"]), float(cur["end"]))

    for nxt in ranges[1:]:
        gap = float(nxt["start"]) - float(cur["end"])
        nxt_text = _range_text(words, float(nxt["start"]), float(nxt["end"]))
        sim = phrase_similarity(cur_text, nxt_text)
        # Overlapping / touching windows → always merge
        if gap <= 0.05 or (
            gap <= bridge_gap_sec and sim >= bridge_similarity
        ):
            cur["end"] = max(float(cur["end"]), float(nxt["end"]))
            if "wait" in str(nxt.get("note") or "") and "wait" not in str(
                cur.get("note") or ""
            ):
                cur["note"] = "speech+wait-beat"
            cur_text = _range_text(words, float(cur["start"]), float(cur["end"]))
            merged += 1
            continue
        # Later keep almost repeats earlier → drop later
        if gap <= bridge_gap_sec * 2 and sim >= max(bridge_similarity, 0.72):
            merged += 1
            continue
        out.append(cur)
        cur = dict(nxt)
        cur_text = nxt_text
    out.append(cur)

    cleaned = [
        {**r, "start": round(float(r["start"]), 3), "end": round(float(r["end"]), 3)}
        for r in out
        if float(r["end"]) - float(r["start"]) >= min_keep_sec
    ]
    return cleaned, merged


def suggest_edl_from_words(
    words: list[dict[str, Any]],
    *,
    source: str = "cam",
    sources: dict[str, str] | None = None,
    gap_cut_sec: float = 0.70,
    hold_if_gap_sec: float = 5.0,
    hold_sec: float = 1.0,
    min_keep_sec: float = 0.90,
    pad_before_sec: float = 0.08,
    pad_after_sec: float = 0.12,
    source_start: float | None = None,
    source_end: float | None = None,
    snap: bool = True,
    silence_gap_sec: float | None = None,
    cut_repeats: bool = True,
    repeat_similarity: float = 0.72,
    repeat_window_sec: float = 60.0,
    bridge_gap_sec: float = 2.5,
    bridge_similarity: float = 0.55,
    cut_wait_speech: bool = True,
    wait_speech_max_sec: float = 0.9,
) -> dict[str, Any]:
    """
    Build keep ranges from speech phrases.

    - Gaps in ``[gap_cut_sec, hold_if_gap_sec)`` → hard cut
    - Gaps ≥ ``hold_if_gap_sec`` → keep only ``hold_sec`` beat (not full wait UI)
    - Near-duplicate / ASR-overlap phrases → dropped or coalesced
    - Short wait-prompt speech → clamped / dropped
    """
    phrase_gap = float(silence_gap_sec if silence_gap_sec is not None else gap_cut_sec)
    pack_words: list[dict[str, Any]] = []
    for w in words:
        try:
            s = float(w["start"])
            e = float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        pack_words.append(
            {
                "type": "word",
                "text": w.get("text") or w.get("word") or "",
                "word": w.get("text") or w.get("word") or "",
                "start": s,
                "end": e,
            }
        )

    phrases = group_into_phrases(pack_words, silence_threshold=phrase_gap)
    if source_start is not None or source_end is not None:
        s0 = float(source_start if source_start is not None else 0.0)
        s1 = float(source_end) if source_end is not None else float("inf")
        phrases = [
            {**p, "start": max(float(p["start"]), s0), "end": min(float(p["end"]), s1)}
            for p in phrases
            if min(float(p["end"]), s1) - max(float(p["start"]), s0) > 0.05
        ]

    phrases, filter_stats = _filter_phrases(
        phrases,
        cut_repeats=cut_repeats,
        repeat_similarity=repeat_similarity,
        repeat_window_sec=repeat_window_sec,
        cut_wait_speech=cut_wait_speech,
        wait_speech_max_sec=wait_speech_max_sec,
    )

    if not phrases:
        return {
            "sources": sources or {source: f"../raw/{source}.mp4"},
            "ranges": [],
            "_meta": {
                "keep_sec": 0.0,
                "strategy": "silence-cut+repeat+wait",
                "empty": True,
                **filter_stats,
            },
        }

    ranges: list[dict[str, Any]] = []
    cur_start = float(phrases[0]["start"])
    cur_end = float(phrases[0]["end"])
    cur_note = str(phrases[0].get("note") or "speech")

    for p in phrases[1:]:
        nxt_start = float(p["start"])
        nxt_end = float(p["end"])
        gap = nxt_start - cur_end
        if gap < gap_cut_sec:
            cur_end = max(cur_end, nxt_end)
            continue
        if gap >= hold_if_gap_sec:
            hold_end = min(nxt_start, cur_end + hold_sec)
            if hold_end > cur_end + 0.05:
                cur_end = hold_end
                cur_note = "speech+wait-beat"
            ranges.append(
                {
                    "source": source,
                    "start": cur_start,
                    "end": cur_end,
                    "note": cur_note,
                }
            )
            cur_start, cur_end = nxt_start, nxt_end
            cur_note = str(p.get("note") or "speech")
            continue
        ranges.append(
            {
                "source": source,
                "start": cur_start,
                "end": cur_end,
                "note": cur_note,
            }
        )
        cur_start, cur_end = nxt_start, nxt_end
        cur_note = str(p.get("note") or "speech")
    ranges.append(
        {"source": source, "start": cur_start, "end": cur_end, "note": cur_note}
    )

    word_dicts = [
        {
            "type": "word",
            "start": float(w["start"]),
            "end": float(w["end"]),
            "word": w.get("text") or w.get("word") or "",
            "text": w.get("text") or w.get("word") or "",
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

    cleaned, bridged = _coalesce_ranges(
        cleaned,
        word_dicts,
        bridge_gap_sec=bridge_gap_sec,
        bridge_similarity=bridge_similarity,
        min_keep_sec=min_keep_sec,
    )

    keep = sum(float(r["end"]) - float(r["start"]) for r in cleaned)
    return {
        "sources": sources or {source: f"../raw/{source}.mp4"},
        "ranges": cleaned,
        "grade": None,
        "_meta": {
            "strategy": "silence-cut+repeat+wait",
            "gap_cut_sec": gap_cut_sec,
            "hold_if_gap_sec": hold_if_gap_sec,
            "hold_sec": hold_sec,
            "min_keep_sec": min_keep_sec,
            "source_start": source_start,
            "source_end": source_end,
            "keep_sec": round(keep, 3),
            "range_count": len(cleaned),
            "cut_repeats": cut_repeats,
            "cut_wait_speech": cut_wait_speech,
            "bridged_ranges": bridged,
            **filter_stats,
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
    edl_sources: dict[str, str] = {}
    for name, rel in sources_cfg.items():
        p = Path(str(rel))
        if p.is_absolute():
            edl_sources[name] = str(p)
        else:
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
        silence_gap_sec=float(radio.get("silence_gap_sec", radio["gap_cut_sec"])),
        cut_repeats=bool(radio.get("cut_repeats", True)),
        repeat_similarity=float(radio.get("repeat_similarity", 0.72)),
        repeat_window_sec=float(radio.get("repeat_window_sec", 60.0)),
        bridge_gap_sec=float(radio.get("bridge_gap_sec", 2.5)),
        bridge_similarity=float(radio.get("bridge_similarity", 0.55)),
        cut_wait_speech=bool(radio.get("cut_wait_speech", True)),
        wait_speech_max_sec=float(radio.get("wait_speech_max_sec", radio["hold_sec"])),
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
            "cut_repeats",
            "cut_wait_speech",
            "wait_speech_max_sec",
            "bridge_gap_sec",
            "bridge_similarity",
            "repeat_similarity",
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
