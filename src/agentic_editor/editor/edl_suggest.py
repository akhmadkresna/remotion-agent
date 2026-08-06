"""Smart radio-edit EDL suggest (clause + gap-class + AV wait compression).

Architecture:
  1. Build **clauses** from ASR segments (fallback: word phrases)
  2. Classify each inter-clause gap: breath / think / ai_wait / retake
  3. breath → stay inside the keep (short natural pause only)
  4. think → **hard cut** (no hold beat) — tighter pacing
  5. ai_wait → compress to a short beat with a **hold tail** (survives snap)
  6. retake → drop the inferior duplicate clause

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
from agentic_editor.editor.gap_class import (
    DEFAULT_GAP_POLICY,
    GapClass,
    GapPolicy,
    activity_in_gap,
    classify_gap,
)
from agentic_editor.editor.pack import group_into_phrases
from agentic_editor.paths import framework_home
from agentic_editor.project import load_project

DEFAULT_RADIO_CFG: dict[str, Any] = {
    # Gap-class policy (primary)
    "breath_max_sec": 0.6,
    "wait_min_sec": 5.0,
    "hold_sec": 0.4,
    "activity_wait_min_sec": 3.5,
    # Hygiene
    "min_keep_sec": 0.90,
    "pad_before_sec": 0.08,
    "pad_after_sec": 0.12,
    "cut_repeats": True,
    "repeat_similarity": 0.75,
    "repeat_window_sec": 90.0,
    "cut_wait_speech": True,
    "wait_speech_max_sec": 0.9,
    # Legacy aliases (mapped → gap-class)
    "silence_gap_sec": 0.60,  # fallback pack only
    "gap_cut_sec": 5.0,  # treated as wait_min if wait_min unset
    "hold_if_gap_sec": 5.0,
}

WAIT_SPEECH_RE = re.compile(
    r"(?i)^(?=.{0,48}$).*\b("
    r"tunggu(\s+(sebentar|dulu|ya|loading))?|"
    r"sebentar|bentar|please\s+wait|loading|"
    r"masih\s+(proses|loading|nunggu)|satu\s+detik|moment"
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
    # Legacy → gap-class
    if "wait_min_sec" not in (parsed.get("radio_edit") or {}):
        if radio.get("hold_if_gap_sec") is not None:
            cfg["wait_min_sec"] = float(radio["hold_if_gap_sec"])
        elif radio.get("gap_cut_sec") is not None and float(radio["gap_cut_sec"]) >= 3.0:
            cfg["wait_min_sec"] = float(radio["gap_cut_sec"])
    return cfg


def policy_from_radio(radio: dict[str, Any]) -> GapPolicy:
    return GapPolicy(
        breath_max=float(radio.get("breath_max_sec", DEFAULT_GAP_POLICY.breath_max)),
        wait_min=float(radio.get("wait_min_sec", DEFAULT_GAP_POLICY.wait_min)),
        hold_sec=float(radio.get("hold_sec", DEFAULT_GAP_POLICY.hold_sec)),
        activity_wait_min=float(
            radio.get("activity_wait_min_sec", DEFAULT_GAP_POLICY.activity_wait_min)
        ),
    )


def normalize_phrase(text: str) -> str:
    tokens = [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _FILLER and len(t) > 1
    ]
    return " ".join(tokens)


def phrase_similarity(a: str, b: str) -> float:
    ta = set(normalize_phrase(a).split())
    tb = set(normalize_phrase(b).split())
    if not ta or not tb:
        na, nb = normalize_phrase(a), normalize_phrase(b)
        return 1.0 if na and na == nb else 0.0
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    containment = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(jaccard, containment)


def is_wait_speech(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or not WAIT_SPEECH_RE.search(raw):
        return False
    tokens = [t for t in _TOKEN_RE.findall(raw) if t.lower() not in _FILLER]
    return len(tokens) <= 8


def load_cam_segments(edit: Path) -> list[dict[str, Any]]:
    path = edit / "transcripts" / "cam.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    segs = data.get("segments") or []
    out: list[dict[str, Any]] = []
    for s in segs:
        if not isinstance(s, dict):
            continue
        try:
            start, end = float(s["start"]), float(s["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(s.get("text") or "").strip()
        if end <= start:
            continue
        out.append({"start": start, "end": end, "text": text})
    return out


def clauses_from_segments(
    segments: list[dict[str, Any]],
    *,
    source_start: float | None = None,
    source_end: float | None = None,
) -> list[dict[str, Any]]:
    """ASR segments are discourse units — better than silence packing when healthy."""
    clauses: list[dict[str, Any]] = []
    for seg in segments:
        s, e = float(seg["start"]), float(seg["end"])
        if source_start is not None:
            s = max(s, float(source_start))
        if source_end is not None:
            e = min(e, float(source_end))
        if e - s < 0.12:
            continue
        text = str(seg.get("text") or "").strip()
        if not text and not normalize_phrase(text):
            # allow through; filter later
            pass
        clauses.append({"start": s, "end": e, "text": text, "note": "speech"})
    return clauses


# Whisper sometimes emits multi-minute segments with almost no speech inside.
_MAX_TRUSTED_SEGMENT_SEC = 12.0
_MIN_SEGMENT_SPEECH_COVERAGE = 0.30
_MAX_INTERNAL_WORD_GAP_SEC = 1.5


def _normalize_word_rows(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in words:
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e <= s:
            continue
        text = str(w.get("text") or w.get("word") or "").strip()
        out.append(
            {
                "type": "word",
                "text": text,
                "word": text,
                "start": s,
                "end": e,
            }
        )
    out.sort(key=lambda w: float(w["start"]))
    return out


def _words_in_window(
    words: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if float(w["end"]) > start + 1e-4 and float(w["start"]) < end - 1e-4
    ]


def _segment_needs_word_split(
    start: float,
    end: float,
    words_in: list[dict[str, Any]],
) -> bool:
    span = end - start
    if span <= 0.12:
        return False
    if not words_in:
        # Empty speech inside a long segment → drop via split producing nothing
        return span > _MAX_TRUSTED_SEGMENT_SEC
    spoken = sum(float(w["end"]) - float(w["start"]) for w in words_in)
    coverage = spoken / span
    max_gap = 0.0
    for a, b in zip(words_in, words_in[1:]):
        max_gap = max(max_gap, float(b["start"]) - float(a["end"]))
    if span > _MAX_TRUSTED_SEGMENT_SEC and coverage < _MIN_SEGMENT_SPEECH_COVERAGE:
        return True
    if max_gap >= _MAX_INTERNAL_WORD_GAP_SEC:
        return True
    if coverage < _MIN_SEGMENT_SPEECH_COVERAGE and span > 4.0:
        return True
    return False


def clauses_from_segments_refined(
    segments: list[dict[str, Any]],
    words: list[dict[str, Any]],
    *,
    silence_gap_sec: float = 0.6,
    source_start: float | None = None,
    source_end: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Use ASR segments when healthy; split pathological ones on word gaps.

    Faster-whisper sometimes stamps one short phrase across minutes of silence
    (AI wait). Gap-class only sees *inter*-clause silence, so those holes must
    be split before classify.
    """
    word_rows = _normalize_word_rows(words)
    stats = {"segments_kept": 0, "segments_split": 0, "segments_empty": 0}
    if not word_rows:
        return (
            clauses_from_segments(
                segments, source_start=source_start, source_end=source_end
            ),
            stats,
        )

    clauses: list[dict[str, Any]] = []
    for seg in segments:
        s, e = float(seg["start"]), float(seg["end"])
        if source_start is not None:
            s = max(s, float(source_start))
        if source_end is not None:
            e = min(e, float(source_end))
        if e - s < 0.12:
            continue
        text = str(seg.get("text") or "").strip()
        win = _words_in_window(word_rows, s, e)
        if _segment_needs_word_split(s, e, win):
            stats["segments_split"] += 1
            if not win:
                stats["segments_empty"] += 1
                continue
            split = clauses_from_words(
                win,
                silence_gap_sec=silence_gap_sec,
                source_start=source_start,
                source_end=source_end,
            )
            clauses.extend(split)
            continue
        # Healthy: snap clause to spoken word bounds (drop trailing quiet)
        if win:
            s = float(win[0]["start"])
            e = float(win[-1]["end"])
            if not text:
                text = " ".join(
                    str(w.get("text") or w.get("word") or "").strip()
                    for w in win
                    if str(w.get("text") or w.get("word") or "").strip()
                )
        if e - s < 0.12:
            continue
        stats["segments_kept"] += 1
        clauses.append({"start": s, "end": e, "text": text, "note": "speech"})

    # Deduplicate / merge tiny overlaps from adjacent splits
    clauses.sort(key=lambda c: float(c["start"]))
    return clauses, stats


def clauses_from_words(
    words: list[dict[str, Any]],
    *,
    silence_gap_sec: float = 0.6,
    source_start: float | None = None,
    source_end: float | None = None,
) -> list[dict[str, Any]]:
    pack_words = _normalize_word_rows(words)
    phrases = group_into_phrases(pack_words, silence_threshold=silence_gap_sec)
    if source_start is not None or source_end is not None:
        s0 = float(source_start if source_start is not None else 0.0)
        s1 = float(source_end) if source_end is not None else float("inf")
        phrases = [
            {**p, "start": max(float(p["start"]), s0), "end": min(float(p["end"]), s1)}
            for p in phrases
            if min(float(p["end"]), s1) - max(float(p["start"]), s0) > 0.05
        ]
    return [
        {
            "start": float(p["start"]),
            "end": float(p["end"]),
            "text": str(p.get("text") or ""),
            "note": "speech",
        }
        for p in phrases
    ]


def _filter_clauses(
    clauses: list[dict[str, Any]],
    *,
    cut_repeats: bool,
    repeat_similarity: float,
    repeat_window_sec: float,
    cut_wait_speech: bool,
    wait_speech_max_sec: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept: list[dict[str, Any]] = []
    stats = {"dropped_repeat": 0, "clamped_wait": 0, "dropped_wait": 0, "dropped_filler": 0}
    for c in clauses:
        text = str(c.get("text") or "")
        start, end = float(c["start"]), float(c["end"])
        if not normalize_phrase(text):
            # filler-only segment
            if end - start < 2.0:
                stats["dropped_filler"] += 1
                continue
        if cut_wait_speech and is_wait_speech(text):
            if end - start <= wait_speech_max_sec * 0.5:
                stats["dropped_wait"] += 1
                continue
            end = start + wait_speech_max_sec
            c = {**c, "end": end, "note": "wait-clamp"}
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
                if cur_dur > prev_dur * 1.25:
                    kept.pop(i)
                    stats["dropped_repeat"] += 1
                    break
                stats["dropped_repeat"] += 1
                drop = True
                break
            if drop:
                continue
        kept.append({**c, "start": start, "end": end})
    return kept, stats


def suggest_edl_from_words(
    words: list[dict[str, Any]],
    *,
    source: str = "cam",
    sources: dict[str, str] | None = None,
    segments: list[dict[str, Any]] | None = None,
    activity_bins: list[dict[str, Any]] | None = None,
    # Gap-class policy
    breath_max_sec: float = 0.6,
    wait_min_sec: float = 5.0,
    hold_sec: float = 0.4,
    activity_wait_min_sec: float = 3.5,
    # Hygiene
    min_keep_sec: float = 0.90,
    pad_before_sec: float = 0.08,
    pad_after_sec: float = 0.12,
    source_start: float | None = None,
    source_end: float | None = None,
    snap: bool = True,
    cut_repeats: bool = True,
    repeat_similarity: float = 0.75,
    repeat_window_sec: float = 90.0,
    cut_wait_speech: bool = True,
    wait_speech_max_sec: float = 0.9,
    silence_gap_sec: float = 0.60,
    # Legacy kwargs (ignored for cut logic; accepted for API compat)
    gap_cut_sec: float | None = None,
    hold_if_gap_sec: float | None = None,
    bridge_gap_sec: float | None = None,
    bridge_similarity: float | None = None,
) -> dict[str, Any]:
    """
    Build keep ranges with gap-class logic.

    Invariants:
      - Breath pauses stay inside the keep
      - Think gaps hard-cut (no hold) for tight pacing
      - AI waits compress to ``hold_sec`` with hold_tail (visible beat)
      - Retakes / near-duplicates dropped
    """
    if hold_if_gap_sec is not None and wait_min_sec == 5.0:
        wait_min_sec = float(hold_if_gap_sec)
    if gap_cut_sec is not None and float(gap_cut_sec) >= 3.0 and wait_min_sec == 5.0:
        wait_min_sec = float(gap_cut_sec)

    policy = GapPolicy(
        breath_max=breath_max_sec,
        wait_min=wait_min_sec,
        hold_sec=hold_sec,
        activity_wait_min=activity_wait_min_sec,
    )

    refine_stats: dict[str, int] = {}
    if segments and words:
        clauses, refine_stats = clauses_from_segments_refined(
            segments,
            words,
            silence_gap_sec=silence_gap_sec,
            source_start=source_start,
            source_end=source_end,
        )
        unit = "segment+word"
    elif segments:
        clauses = clauses_from_segments(
            segments, source_start=source_start, source_end=source_end
        )
        unit = "segment"
    else:
        clauses = clauses_from_words(
            words,
            silence_gap_sec=silence_gap_sec,
            source_start=source_start,
            source_end=source_end,
        )
        unit = "phrase"

    clauses, filter_stats = _filter_clauses(
        clauses,
        cut_repeats=cut_repeats,
        repeat_similarity=repeat_similarity,
        repeat_window_sec=repeat_window_sec,
        cut_wait_speech=cut_wait_speech,
        wait_speech_max_sec=wait_speech_max_sec,
    )
    filter_stats = {**refine_stats, **filter_stats}

    class_counts = {c.value: 0 for c in GapClass}
    if not clauses:
        return {
            "sources": sources or {source: f"../raw/{source}.mp4"},
            "ranges": [],
            "_meta": {
                "keep_sec": 0.0,
                "strategy": "gap-class+clause",
                "empty": True,
                "unit": unit,
                "gap_classes": class_counts,
                **filter_stats,
            },
        }

    ranges: list[dict[str, Any]] = []
    cur_start = float(clauses[0]["start"])
    cur_end = float(clauses[0]["end"])
    cur_note = str(clauses[0].get("note") or "speech")
    cur_hold_tail = False

    for nxt in clauses[1:]:
        nxt_start, nxt_end = float(nxt["start"]), float(nxt["end"])
        gap = nxt_start - cur_end
        screen_active = activity_in_gap(activity_bins, cur_end, nxt_start)
        gclass = classify_gap(
            gap, policy=policy, screen_active=screen_active, is_retake=False
        )
        class_counts[gclass.value] += 1

        if gclass == GapClass.BREATH:
            # Keep short natural pause inside the keep
            cur_end = max(cur_end, nxt_end)
            continue

        if gclass == GapClass.RETAKE:
            continue

        if gclass == GapClass.THINK:
            # Hard cut — jump to next clause with no hold beat
            ranges.append(
                {
                    "source": source,
                    "start": cur_start,
                    "end": cur_end,
                    "note": cur_note,
                    "_hold_tail": cur_hold_tail,
                }
            )
            cur_start, cur_end = nxt_start, nxt_end
            cur_note = str(nxt.get("note") or "speech")
            cur_hold_tail = False
            continue

        # AI_WAIT → compress: keep short beat after last speech, then jump
        hold_end = min(nxt_start, cur_end + policy.hold_sec)
        if hold_end > cur_end + 0.05:
            cur_end = hold_end
            cur_note = "speech+wait-beat"
            cur_hold_tail = True
        ranges.append(
            {
                "source": source,
                "start": cur_start,
                "end": cur_end,
                "note": cur_note,
                "_hold_tail": cur_hold_tail,
            }
        )
        cur_start, cur_end = nxt_start, nxt_end
        cur_note = str(nxt.get("note") or "speech")
        cur_hold_tail = False

    ranges.append(
        {
            "source": source,
            "start": cur_start,
            "end": cur_end,
            "note": cur_note,
            "_hold_tail": cur_hold_tail,
        }
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
        hold_tail = bool(r.pop("_hold_tail", False))
        desired_end = e
        if snap and word_dicts:
            s, e = snap_range_to_words(
                s,
                e,
                word_dicts,
                pad_before=pad_before_sec,
                pad_after=pad_after_sec,
                hold_tail=hold_tail,
            )
            if hold_tail:
                # Guarantee visible beat even if snap pulled speech end back
                e = max(e, min(desired_end, s + min_keep_sec), desired_end)
        if source_start is not None:
            s = max(s, float(source_start))
        if source_end is not None:
            e = min(e, float(source_end))
        if e - s < min_keep_sec:
            continue
        cleaned.append(
            {
                "source": source,
                "start": round(s, 3),
                "end": round(e, 3),
                "note": r.get("note") or "speech",
            }
        )

    keep = sum(float(r["end"]) - float(r["start"]) for r in cleaned)
    return {
        "sources": sources or {source: f"../raw/{source}.mp4"},
        "ranges": cleaned,
        "grade": None,
        "_meta": {
            "strategy": "gap-class+clause",
            "unit": unit,
            "breath_max_sec": policy.breath_max,
            "wait_min_sec": policy.wait_min,
            "hold_sec": policy.hold_sec,
            # Compat fields for CLI printouts
            "gap_cut_sec": policy.wait_min,
            "hold_if_gap_sec": policy.wait_min,
            "min_keep_sec": min_keep_sec,
            "source_start": source_start,
            "source_end": source_end,
            "keep_sec": round(keep, 3),
            "range_count": len(cleaned),
            "cut_repeats": cut_repeats,
            "cut_wait_speech": cut_wait_speech,
            "gap_classes": class_counts,
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
    if hold_if_gap_sec is not None:
        radio["wait_min_sec"] = float(hold_if_gap_sec)
    if gap_cut_sec is not None and float(gap_cut_sec) >= 3.0:
        radio["wait_min_sec"] = float(gap_cut_sec)
    if hold_sec is not None:
        radio["hold_sec"] = float(hold_sec)
    if min_keep_sec is not None:
        radio["min_keep_sec"] = float(min_keep_sec)

    edit = episode / "edit"
    words = load_cam_words(edit)
    segments = load_cam_segments(edit)

    # Optional activity bins for smarter wait detection
    activity_bins = None
    act_path = edit / "screen_activity.json"
    if act_path.is_file():
        try:
            activity_bins = json.loads(act_path.read_text(encoding="utf-8")).get("bins")
        except (OSError, json.JSONDecodeError):
            activity_bins = None

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
        segments=segments or None,
        activity_bins=activity_bins,
        breath_max_sec=float(radio.get("breath_max_sec", 0.6)),
        wait_min_sec=float(radio.get("wait_min_sec", 5.0)),
        hold_sec=float(radio["hold_sec"]),
        activity_wait_min_sec=float(radio.get("activity_wait_min_sec", 3.5)),
        min_keep_sec=float(radio["min_keep_sec"]),
        pad_before_sec=float(radio["pad_before_sec"]),
        pad_after_sec=float(radio["pad_after_sec"]),
        source_start=source_start,
        source_end=source_end,
        silence_gap_sec=float(radio.get("silence_gap_sec", 0.6)),
        cut_repeats=bool(radio.get("cut_repeats", True)),
        repeat_similarity=float(radio.get("repeat_similarity", 0.75)),
        repeat_window_sec=float(radio.get("repeat_window_sec", 90.0)),
        cut_wait_speech=bool(radio.get("cut_wait_speech", True)),
        wait_speech_max_sec=float(radio.get("wait_speech_max_sec", radio["hold_sec"])),
    )
    meta = suggestion.setdefault("_meta", {})
    meta["style"] = style
    meta["radio_config"] = {
        k: radio[k]
        for k in (
            "breath_max_sec",
            "wait_min_sec",
            "hold_sec",
            "activity_wait_min_sec",
            "min_keep_sec",
            "cut_repeats",
            "cut_wait_speech",
        )
        if k in radio
    }
    meta["word_count"] = len(words)
    meta["segment_count"] = len(segments)
    return suggestion


def write_edl_suggest(episode: Path, suggestion: dict[str, Any]) -> Path:
    edit = episode / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    out = edit / "edl.suggest.json"
    out.write_text(json.dumps(suggestion, indent=2) + "\n", encoding="utf-8")
    return out
