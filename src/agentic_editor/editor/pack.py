"""Pack word-level transcripts into takes_packed.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def format_time(seconds: float) -> str:
    return f"{seconds:06.2f}"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}m {s:04.1f}s"


def group_into_phrases(
    words: list[dict[str, Any]],
    silence_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    phrases: list[dict[str, Any]] = []
    current_words: list[dict[str, Any]] = []
    current_start: float | None = None
    current_speaker: str | None = None
    prev_end: float | None = None

    def flush() -> None:
        nonlocal current_words, current_start, current_speaker
        if not current_words:
            return
        text_parts: list[str] = []
        for w in current_words:
            t = w.get("type", "word")
            raw = (w.get("text") or w.get("word") or "").strip()
            if not raw:
                continue
            if t == "audio_event" and not raw.startswith("("):
                raw = f"({raw})"
            text_parts.append(raw)
        if not text_parts:
            current_words = []
            current_start = None
            current_speaker = None
            return
        text = " ".join(text_parts)
        text = (
            text.replace(" ,", ",")
            .replace(" .", ".")
            .replace(" ?", "?")
            .replace(" !", "!")
        )
        end_time = current_words[-1].get(
            "end", current_words[-1].get("start", current_start or 0.0)
        )
        phrases.append(
            {
                "start": current_start,
                "end": end_time,
                "text": text,
                "speaker_id": current_speaker,
            }
        )
        current_words = []
        current_start = None
        current_speaker = None

    for w in words:
        t = w.get("type", "word")
        if t == "spacing":
            start = w.get("start")
            end = w.get("end")
            if start is not None and end is not None and (end - start) >= silence_threshold:
                flush()
            continue

        start = w.get("start")
        if start is None:
            continue
        speaker = w.get("speaker_id") or w.get("speaker")

        if (
            current_speaker is not None
            and speaker is not None
            and speaker != current_speaker
        ):
            flush()
        if prev_end is not None and start - prev_end >= silence_threshold:
            flush()

        if current_start is None:
            current_start = float(start)
            current_speaker = speaker
        current_words.append(w)
        prev_end = float(w.get("end", start))

    flush()
    return phrases


def pack_one_file(
    json_path: Path, silence_threshold: float
) -> tuple[str, float, list[dict[str, Any]]]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    words = data.get("words") or []
    # If only segments exist, synthesize crude words
    if not words and data.get("segments"):
        for seg in data["segments"]:
            parts = (seg.get("text") or "").split()
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start))
            if not parts:
                continue
            step = (end - start) / max(len(parts), 1)
            for i, p in enumerate(parts):
                words.append(
                    {
                        "type": "word",
                        "word": p,
                        "text": p,
                        "start": start + i * step,
                        "end": start + (i + 1) * step,
                    }
                )
    phrases = group_into_phrases(words, silence_threshold)
    if phrases:
        duration = float(phrases[-1]["end"]) - float(phrases[0]["start"])
    else:
        duration = 0.0
    return json_path.stem, duration, phrases


def render_markdown(
    entries: list[tuple[str, float, list[dict[str, Any]]]],
    silence_threshold: float,
) -> str:
    lines = [
        "# Packed transcripts",
        "",
        f"Phrase-level, grouped on silences ≥ {silence_threshold:.1f}s or speaker change.",
        "Use `[start-end]` ranges to address cuts in the EDL.",
        "",
    ]
    for name, duration, phrases in entries:
        lines.append(
            f"## {name}  (duration: {format_duration(duration)}, {len(phrases)} phrases)"
        )
        if not phrases:
            lines.append("  _no speech detected_")
            lines.append("")
            continue
        for p in phrases:
            spk = p.get("speaker_id")
            if spk is not None:
                spk_str = str(spk)
                if spk_str.startswith("speaker_"):
                    spk_str = spk_str[len("speaker_") :]
                spk_tag = f" S{spk_str}"
            else:
                spk_tag = ""
            lines.append(
                f"  [{format_time(float(p['start']))}-{format_time(float(p['end']))}]"
                f"{spk_tag} {p['text']}"
            )
        lines.append("")
    return "\n".join(lines)


def pack_edit_dir(edit_dir: Path, silence_threshold: float = 0.5) -> Path:
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    json_files = sorted(transcripts_dir.glob("*.json"))
    entries = [pack_one_file(p, silence_threshold) for p in json_files]
    markdown = render_markdown(entries, silence_threshold)
    out_path = edit_dir / "takes_packed.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path
