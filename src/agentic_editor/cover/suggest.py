"""Suggest screen_with_cam cover ranges from transcript deixis + screen activity."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from agentic_editor.paths import framework_home
from agentic_editor.project import load_project, resolve_source

DEFAULT_KEYWORDS = [
    "look at",
    "look here",
    "here",
    "this",
    "click",
    "klik",
    "lihat",
    "di sini",
    "disini",
    "ui",
    "dashboard",
    "screen",
    "menu",
    "button",
    "form",
    "field",
    "error",
    "cursor",
    "code",
    "terminal",
]

DEFAULT_COVER_CFG: dict[str, Any] = {
    "prefer_screen_when": DEFAULT_KEYWORDS,
    # balanced = deixis needs activity when bins exist
    # prefer_screen = show screen whenever deixis OR activity; fill gaps; off_hold
    "mode": "prefer_screen",
    "screen_bias": 0.35,  # 0..1 — lowers activity gates, widens pads/merge
    "require_activity_for_deixis": False,  # prefer_screen default
    "min_hold_sec": 2.0,
    "min_active_sec": 1.0,
    "activity_fps": 2,
    "activity_threshold": 0.028,
    "merge_gap_sec": 1.2,
    "off_hold_sec": 1.5,
    "pad_before_sec": 0.5,
    "pad_after_sec": 1.5,
}

DEFAULT_CAMERA_PLAY: dict[str, Any] = {
    "snap_on_cuts": True,
    "home": "medium",
    "alt": "close",
    "wide_on_resets": True,
    "max_hold_sec": 7,
    "scales": {"wide": 1.0, "medium": 1.22, "close": 1.42},
}


def load_style_cover_config(style_name: str = "tutorial") -> dict[str, Any]:
    """Load cover.* defaults from styles/<style>/style.md YAML fence."""
    cfg = dict(DEFAULT_COVER_CFG)
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
    cover = parsed.get("cover") or {}
    if isinstance(cover, dict):
        for k, v in cover.items():
            if v is not None:
                cfg[k] = v
    # Mode shortcuts
    mode = str(cfg.get("mode") or "balanced").lower()
    if mode == "prefer_screen" and "require_activity_for_deixis" not in (
        cover if isinstance(cover, dict) else {}
    ):
        cfg["require_activity_for_deixis"] = False
    elif mode == "balanced" and "require_activity_for_deixis" not in (
        cover if isinstance(cover, dict) else {}
    ):
        cfg["require_activity_for_deixis"] = True
    return cfg


def load_style_camera_play(style_name: str = "tutorial") -> dict[str, Any]:
    """Load camera_play.* from style YAML; fall back to punchy defaults."""
    cfg = dict(DEFAULT_CAMERA_PLAY)
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
    cam = parsed.get("camera_play") or {}
    if isinstance(cam, dict):
        for k, v in cam.items():
            if v is not None:
                if k == "scales" and isinstance(v, dict):
                    scales = dict(cfg.get("scales") or {})
                    scales.update({sk: float(sv) for sk, sv in v.items()})
                    cfg["scales"] = scales
                else:
                    cfg[k] = v
    return cfg


def apply_screen_bias(cover_cfg: dict[str, Any], bias: float | None = None) -> dict[str, Any]:
    """Return cover cfg with thresholds relaxed by screen_bias (0..1)."""
    out = dict(cover_cfg)
    b = float(out.get("screen_bias", 0) if bias is None else bias)
    b = max(0.0, min(1.0, b))
    out["screen_bias"] = b
    if b <= 0:
        return out
    out["activity_threshold"] = float(out.get("activity_threshold", 0.035)) * (1.0 - 0.5 * b)
    out["min_active_sec"] = float(out.get("min_active_sec", 1.5)) * (1.0 - 0.4 * b)
    out["min_hold_sec"] = max(1.2, float(out.get("min_hold_sec", 2.5)) * (1.0 - 0.25 * b))
    out["merge_gap_sec"] = float(out.get("merge_gap_sec", 0.8)) * (1.0 + 0.75 * b)
    out["pad_before_sec"] = float(out.get("pad_before_sec", 0.4)) * (1.0 + 0.35 * b)
    out["pad_after_sec"] = float(out.get("pad_after_sec", 1.2)) * (1.0 + 0.35 * b)
    out["off_hold_sec"] = float(out.get("off_hold_sec", 1.0)) * (1.0 + 0.5 * b)
    return out


def _word_text(w: dict[str, Any]) -> str:
    return str(w.get("word") or w.get("text") or "").strip()


def load_cam_words(edit: Path) -> list[dict[str, Any]]:
    path = edit / "transcripts" / "cam.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    words = data.get("words") or []
    out: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        text = _word_text(w)
        if not text:
            continue
        out.append(
            {
                "text": text,
                "start": float(w["start"]),
                "end": float(w["end"]),
                "score": float(w["score"]) if w.get("score") is not None else 1.0,
            }
        )
    return out


def find_deixis_windows(
    words: list[dict[str, Any]],
    keywords: list[str],
    *,
    pad_before: float,
    pad_after: float,
) -> list[dict[str, Any]]:
    """Return padded windows where transcript matches prefer_screen_when phrases."""
    if not words or not keywords:
        return []
    # Build lowercase stream with char→word index for multi-word phrases
    parts: list[str] = []
    spans: list[tuple[int, int, int]] = []  # char_start, char_end, word_i
    cursor = 0
    for i, w in enumerate(words):
        token = w["text"].lower()
        if parts:
            parts.append(" ")
            cursor += 1
        start_c = cursor
        parts.append(token)
        cursor += len(token)
        spans.append((start_c, cursor, i))
    hay = "".join(parts)

    keyed = sorted((k.strip().lower() for k in keywords if k and str(k).strip()), key=len, reverse=True)
    hits: list[dict[str, Any]] = []
    for kw in keyed:
        if not kw:
            continue
        start = 0
        while True:
            idx = hay.find(kw, start)
            if idx < 0:
                break
            end = idx + len(kw)
            # map to word indices
            wi_start = next((i for cs, ce, i in spans if cs <= idx < ce), None)
            wi_end = next((i for cs, ce, i in spans if cs < end <= ce or (cs <= idx and end <= ce)), None)
            if wi_start is None:
                # fallback: any overlapping span
                overlapping = [i for cs, ce, i in spans if not (ce <= idx or cs >= end)]
                if not overlapping:
                    start = end
                    continue
                wi_start = overlapping[0]
                wi_end = overlapping[-1]
            if wi_end is None:
                wi_end = wi_start
            w0, w1 = words[wi_start], words[wi_end]
            hits.append(
                {
                    "start": max(0.0, float(w0["start"]) - pad_before),
                    "end": float(w1["end"]) + pad_after,
                    "keyword": kw,
                    "confidence": min(float(w0.get("score", 1.0)), float(w1.get("score", 1.0))),
                }
            )
            start = end
    return _merge_windows(hits, gap=0.15)


def snap_window_to_words(
    start: float,
    end: float,
    words: list[dict[str, Any]],
) -> tuple[float, float]:
    if not words:
        return start, end
    # expand to covering word boundaries
    covering = [w for w in words if w["end"] > start and w["start"] < end]
    if not covering:
        return start, end
    return float(covering[0]["start"]), float(covering[-1]["end"])


def probe_screen_activity(
    screen_path: Path,
    *,
    fps: float = 2.0,
    threshold: float = 0.035,
) -> list[dict[str, Any]]:
    """
    Return 1s activity bins: {start, end, activity, active}.
    activity is mean abs pixel diff normalized ~0..1 between consecutive samples.
    """
    if not screen_path.is_file():
        return []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return []

    with tempfile.TemporaryDirectory(prefix="ae-screen-act-") as tmp:
        tmp_path = Path(tmp)
        pattern = tmp_path / "f_%05d.png"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(screen_path),
            "-vf",
            f"fps={fps},scale=160:-1",
            "-start_number",
            "0",
            str(pattern),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return []
        frames = sorted(tmp_path.glob("f_*.png"))
        if len(frames) < 2:
            return []

        prev = None
        # map sample index → activity vs previous
        sample_acts: list[tuple[float, float]] = []  # (time_sec, activity)
        for i, fp in enumerate(frames):
            arr = np.asarray(Image.open(fp).convert("L"), dtype=np.float32) / 255.0
            t = i / max(fps, 0.01)
            if prev is None:
                sample_acts.append((t, 0.0))
            else:
                diff = float(np.mean(np.abs(arr - prev)))
                sample_acts.append((t, diff))
            prev = arr

        if not sample_acts:
            return []
        duration = sample_acts[-1][0] + (1.0 / max(fps, 0.01))
        bins: list[dict[str, Any]] = []
        sec = 0
        while sec < duration:
            s0, s1 = float(sec), float(sec + 1)
            vals = [a for t, a in sample_acts if s0 <= t < s1]
            if not vals:
                # carry nearest
                nearest = min(sample_acts, key=lambda x: abs(x[0] - (s0 + 0.5)))
                vals = [nearest[1]]
            act = float(sum(vals) / len(vals))
            bins.append(
                {
                    "start": s0,
                    "end": s1,
                    "activity": act,
                    "active": act >= threshold,
                }
            )
            sec += 1
        return bins


def activity_in_window(
    bins: list[dict[str, Any]],
    start: float,
    end: float,
) -> tuple[float, float]:
    """Return (mean_activity, active_seconds) for [start, end)."""
    overlapping = [b for b in bins if b["end"] > start and b["start"] < end]
    if not overlapping:
        return 0.0, 0.0
    mean = float(sum(float(b["activity"]) for b in overlapping) / len(overlapping))
    active_sec = float(sum(1.0 for b in overlapping if b.get("active")))
    return mean, active_sec


def _merge_windows(windows: list[dict[str, Any]], *, gap: float) -> list[dict[str, Any]]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: float(w["start"]))
    merged: list[dict[str, Any]] = [dict(ordered[0])]
    for w in ordered[1:]:
        cur = merged[-1]
        if float(w["start"]) <= float(cur["end"]) + gap:
            cur["end"] = max(float(cur["end"]), float(w["end"]))
            notes = [cur.get("note"), w.get("note"), w.get("keyword")]
            parts = [str(n) for n in notes if n]
            if parts:
                cur["note"] = "+".join(dict.fromkeys(parts))
            if w.get("keyword") and not cur.get("keyword"):
                cur["keyword"] = w["keyword"]
            cur["confidence"] = max(float(cur.get("confidence", 0)), float(w.get("confidence", 0)))
            if w.get("mean_activity") is not None:
                cur["mean_activity"] = max(
                    float(cur.get("mean_activity") or 0),
                    float(w["mean_activity"]),
                )
        else:
            merged.append(dict(w))
    return merged


def decide_screen_pip_windows(
    *,
    deixis: list[dict[str, Any]],
    activity_bins: list[dict[str, Any]],
    edl_ranges: list[dict[str, Any]] | None = None,
    min_hold_sec: float = 2.5,
    min_active_sec: float = 1.5,
    merge_gap_sec: float = 0.8,
    activity_threshold: float = 0.035,
    words: list[dict[str, Any]] | None = None,
    mode: str = "balanced",
    require_activity_for_deixis: bool | None = None,
    off_hold_sec: float = 1.0,
) -> list[dict[str, Any]]:
    """
    use_screen_pip iff duration >= min_hold
      AND (deixis_hit OR sustained_activity >= min_active_sec)
      AND (balanced: activity in window when bins exist;
           prefer_screen: deixis may skip activity gate)

    ``off_hold_sec`` extends activity-derived runs past the last active bin
    so UI holds stay on screen briefly after motion stops.
    """
    mode_l = str(mode or "balanced").lower()
    if require_activity_for_deixis is None:
        require_activity_for_deixis = mode_l != "prefer_screen"

    candidates: list[dict[str, Any]] = []

    # From deixis
    for hit in deixis:
        mean_act, active_sec = activity_in_window(activity_bins, hit["start"], hit["end"])
        if activity_bins and require_activity_for_deixis:
            has_activity = active_sec > 0 or mean_act >= activity_threshold
            if not has_activity:
                continue
        end = float(hit["end"])
        if activity_bins and off_hold_sec > 0:
            end = end + float(off_hold_sec)
        candidates.append(
            {
                "start": float(hit["start"]),
                "end": end,
                "keyword": hit.get("keyword"),
                "mean_activity": mean_act,
                "note": f"deixis:{hit.get('keyword', '?')}",
                "confidence": float(hit.get("confidence", 1.0)),
            }
        )

    # Sustained activity without deixis (+ off_hold tail)
    if activity_bins:
        run_start: float | None = None
        for b in activity_bins:
            if b.get("active"):
                if run_start is None:
                    run_start = float(b["start"])
            else:
                if run_start is not None:
                    run_end = float(b["start"]) + float(off_hold_sec)
                    if run_end - run_start >= min_active_sec:
                        mean_act, _ = activity_in_window(
                            activity_bins, run_start, float(b["start"])
                        )
                        candidates.append(
                            {
                                "start": run_start,
                                "end": run_end,
                                "mean_activity": mean_act,
                                "note": f"activity:{mean_act:.2f}",
                                "confidence": min(1.0, mean_act / max(activity_threshold, 1e-6)),
                            }
                        )
                    run_start = None
        if run_start is not None:
            run_end = float(activity_bins[-1]["end"]) + float(off_hold_sec)
            if run_end - run_start >= min_active_sec:
                mean_act, _ = activity_in_window(activity_bins, run_start, float(activity_bins[-1]["end"]))
                candidates.append(
                    {
                        "start": run_start,
                        "end": run_end,
                        "mean_activity": mean_act,
                        "note": f"activity:{mean_act:.2f}",
                        "confidence": min(1.0, mean_act / max(activity_threshold, 1e-6)),
                    }
                )

    # Source-first: merge intent in continuous source time BEFORE the keep mask.
    # Clipping to EDL early shatters one demo into per-keep shards.
    effective_merge = merge_gap_sec
    if mode_l == "prefer_screen":
        effective_merge = max(merge_gap_sec, merge_gap_sec * 1.25)

    merged = _merge_windows(candidates, gap=effective_merge)

    # Project through EDL keep mask, but stitch shards that belong to the same
    # source-time intent (demo continuity across radio-edit holes).
    if edl_ranges:
        projected: list[dict[str, Any]] = []
        keeps = sorted(
            (
                (float(r["start"]), float(r["end"]))
                for r in edl_ranges
                if str(r.get("source") or "cam") == "cam"
            ),
            key=lambda x: x[0],
        )
        for c in merged:
            cs, ce = float(c["start"]), float(c["end"])
            slices: list[tuple[float, float]] = []
            for rs, re in keeps:
                s = max(cs, rs)
                e = min(ce, re)
                if e - s >= 0.2:
                    slices.append((s, e))
            if not slices:
                continue
            # Stitch: one screen event per intent, spanning keep slices
            # (source start/end = first/last overlapping keep inside intent)
            projected.append(
                {
                    **c,
                    "start": slices[0][0],
                    "end": slices[-1][1],
                    "_slices": slices,
                }
            )
        merged = projected

    # Enforce min hold + snap to words
    out: list[dict[str, Any]] = []
    for w in merged:
        start, end = float(w["start"]), float(w["end"])
        if words:
            start, end = snap_window_to_words(start, end, words)
        if end - start < min_hold_sec:
            mid = (start + end) / 2
            start = mid - min_hold_sec / 2
            end = mid + min_hold_sec / 2
            if words:
                start, end = snap_window_to_words(start, end, words)
            if end - start < min_hold_sec * 0.9:
                continue
        # Re-check activity only in balanced mode (prefer_screen keeps deixis holds)
        if activity_bins and require_activity_for_deixis:
            mean_act, active_sec = activity_in_window(activity_bins, start, end)
            if active_sec <= 0 and mean_act < activity_threshold:
                continue
            w["mean_activity"] = mean_act
        elif activity_bins:
            mean_act, _ = activity_in_window(activity_bins, start, end)
            w["mean_activity"] = mean_act
        reason = w.get("note") or "screen"
        if w.get("mean_activity") is not None and "activity:" not in str(reason):
            reason = f"{reason}+activity:{float(w['mean_activity']):.2f}"
        out.append(
            {
                "type": "screen_with_cam",
                "start": round(start, 3),
                "end": round(end, 3),
                "note": reason,
            }
        )
    return _merge_windows(out, gap=effective_merge)


def suggest_cover(
    episode: Path,
    *,
    activity_bins: list[dict[str, Any]] | None = None,
    skip_activity_probe: bool = False,
    mode: str | None = None,
    screen_bias: float | None = None,
    activity_threshold: float | None = None,
    min_hold_sec: float | None = None,
    min_active_sec: float | None = None,
    merge_gap_sec: float | None = None,
) -> dict[str, Any]:
    """Build a draft cover.json suggestion for an episode."""
    cfg = load_project(episode)
    style = str(cfg.get("style") or "tutorial")
    cover_cfg = load_style_cover_config(style)
    if mode is not None:
        cover_cfg["mode"] = mode
        if str(mode).lower() == "prefer_screen":
            cover_cfg["require_activity_for_deixis"] = False
        elif str(mode).lower() == "balanced":
            cover_cfg["require_activity_for_deixis"] = True
    if screen_bias is not None:
        cover_cfg["screen_bias"] = float(screen_bias)
    if activity_threshold is not None:
        cover_cfg["activity_threshold"] = float(activity_threshold)
    if min_hold_sec is not None:
        cover_cfg["min_hold_sec"] = float(min_hold_sec)
    if min_active_sec is not None:
        cover_cfg["min_active_sec"] = float(min_active_sec)
    if merge_gap_sec is not None:
        cover_cfg["merge_gap_sec"] = float(merge_gap_sec)

    cover_cfg = apply_screen_bias(cover_cfg)
    camera_play = load_style_camera_play(style)
    edit = episode / "edit"

    words = load_cam_words(edit)
    deixis = find_deixis_windows(
        words,
        list(cover_cfg.get("prefer_screen_when") or DEFAULT_KEYWORDS),
        pad_before=float(cover_cfg.get("pad_before_sec", 0.4)),
        pad_after=float(cover_cfg.get("pad_after_sec", 1.2)),
    )

    sources = cfg.get("sources") or {}
    has_screen = "screen" in sources
    bins: list[dict[str, Any]] = list(activity_bins or [])
    if has_screen and activity_bins is None and not skip_activity_probe:
        screen_path = resolve_source(episode, sources["screen"])
        bins = probe_screen_activity(
            screen_path,
            fps=float(cover_cfg.get("activity_fps", 2)),
            threshold=float(cover_cfg.get("activity_threshold", 0.035)),
        )
        # Persist for gap-class wait detection (ae edl-suggest)
        try:
            (edit / "screen_activity.json").write_text(
                json.dumps(
                    {
                        "fps": float(cover_cfg.get("activity_fps", 2)),
                        "threshold": float(cover_cfg.get("activity_threshold", 0.035)),
                        "bins": bins,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    edl_ranges: list[dict[str, Any]] | None = None
    edl_path = edit / "edl.json"
    if edl_path.is_file():
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
        edl_ranges = list(edl.get("ranges") or [])

    events: list[dict[str, Any]] = []
    if has_screen:
        events = decide_screen_pip_windows(
            deixis=deixis,
            activity_bins=bins,
            edl_ranges=edl_ranges,
            min_hold_sec=float(cover_cfg.get("min_hold_sec", 2.5)),
            min_active_sec=float(cover_cfg.get("min_active_sec", 1.5)),
            merge_gap_sec=float(cover_cfg.get("merge_gap_sec", 0.8)),
            activity_threshold=float(cover_cfg.get("activity_threshold", 0.035)),
            words=words,
            mode=str(cover_cfg.get("mode") or "balanced"),
            require_activity_for_deixis=bool(
                cover_cfg.get("require_activity_for_deixis", True)
            ),
            off_hold_sec=float(cover_cfg.get("off_hold_sec", 1.0)),
        )

    return {
        "camera_play": camera_play,
        "events": events,
        "captions": [],
        "_meta": {
            "has_screen": has_screen,
            "deixis_hits": len(deixis),
            "activity_bins": len(bins),
            "suggested_events": len(events),
            "style": style,
            "mode": cover_cfg.get("mode"),
            "screen_bias": cover_cfg.get("screen_bias"),
            "cover_config": {
                k: cover_cfg[k]
                for k in (
                    "mode",
                    "screen_bias",
                    "require_activity_for_deixis",
                    "min_hold_sec",
                    "min_active_sec",
                    "activity_threshold",
                    "merge_gap_sec",
                    "off_hold_sec",
                    "prefer_screen_when",
                )
                if k in cover_cfg
            },
        },
    }


def write_cover_suggest(episode: Path, suggestion: dict[str, Any]) -> Path:
    edit = episode / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    out = edit / "cover.suggest.json"
    # Strip private meta from events file but keep meta for agents
    out.write_text(json.dumps(suggestion, indent=2) + "\n", encoding="utf-8")
    return out
