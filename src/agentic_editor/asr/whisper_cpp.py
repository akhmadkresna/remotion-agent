"""whisper.cpp backend (preferred on macOS / Metal)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agentic_editor.asr.backends import whisper_cpp_binary
from agentic_editor.asr.normalize import finalize_transcript, normalize_word
from agentic_editor.paths import framework_home


def find_model(model_file: str) -> Path | None:
    env = os.environ.get("WHISPER_CPP_MODEL", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
        # if env is a directory
        if p.is_dir():
            cand = p / model_file
            if cand.is_file():
                return cand
    home = framework_home()
    candidates = [
        home / "models" / model_file,
        Path.home() / ".cache" / "whisper.cpp" / model_file,
        Path.home() / "models" / "whisper" / model_file,
        Path("/opt/homebrew/share/whisper-cpp") / model_file,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def transcribe_whisper_cpp(
    audio_wav: Path,
    *,
    model_file: str,
    language: str,
    verbose: bool = True,
) -> dict[str, Any]:
    binary = whisper_cpp_binary()
    if not binary:
        raise RuntimeError(
            "whisper.cpp CLI not found. Install with: brew install whisper-cpp\n"
            "Or set PATH to whisper-cli."
        )
    model_path = find_model(model_file)
    if not model_path:
        raise RuntimeError(
            f"whisper.cpp model not found: {model_file}\n"
            f"Download into {framework_home() / 'models'}/ or set WHISPER_CPP_MODEL.\n"
            "Example:\n"
            "  mkdir -p \"$AGENTIC_EDITOR_HOME/models\"\n"
            "  curl -L -o \"$AGENTIC_EDITOR_HOME/models/ggml-small.bin\" \\\n"
            "    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
        )

    with tempfile.TemporaryDirectory(prefix="ae-wcpp-") as td:
        out_base = Path(td) / "out"
        # whisper-cli: -oj for json, -owts for word timestamps (varies by version)
        cmd = [
            binary,
            "-m",
            str(model_path),
            "-f",
            str(audio_wav),
            "-l",
            language or "id",
            "-oj",
            "-of",
            str(out_base),
        ]
        # word timestamps flag names differ across versions
        for flag in ("-ml", "1"):
            pass
        # Try --word-timestamps / -sow if available; ignore failures via probing help
        help_txt = subprocess.run(
            [binary, "-h"], capture_output=True, text=True
        ).stderr + subprocess.run(
            [binary, "-h"], capture_output=True, text=True
        ).stdout
        if "--max-len" in help_txt or "-ml" in help_txt:
            cmd.extend(["-ml", "1"])
        if verbose:
            print(f"  whisper.cpp: {' '.join(cmd[:6])} …", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"whisper.cpp failed ({proc.returncode}):\n{proc.stderr or proc.stdout}"
            )
        json_path = Path(str(out_base) + ".json")
        if not json_path.is_file():
            # some builds write out.json differently
            alts = list(Path(td).glob("*.json"))
            if not alts:
                raise RuntimeError("whisper.cpp produced no JSON output")
            json_path = alts[0]
        raw = json.loads(json_path.read_text(encoding="utf-8"))

    return _parse_whisper_cpp_json(raw, language=language, model=model_file)


def _parse_whisper_cpp_json(
    raw: dict[str, Any], *, language: str, model: str
) -> dict[str, Any]:
    words: list[dict[str, Any]] = []
    segments_out: list[dict[str, Any]] = []

    transcription = raw.get("transcription") or raw.get("segments") or []
    if isinstance(transcription, list):
        for seg in transcription:
            text = (seg.get("text") or "").strip()
            start = float(seg.get("offsets", {}).get("from", 0)) / 1000.0 if "offsets" in seg else float(seg.get("start", 0) or 0)
            end = float(seg.get("offsets", {}).get("to", 0)) / 1000.0 if "offsets" in seg else float(seg.get("end", 0) or 0)
            # newer format: timestamps.from/to as strings "00:00:01,000"
            if "timestamps" in seg and isinstance(seg["timestamps"], dict):
                start = _ts_to_sec(seg["timestamps"].get("from", start))
                end = _ts_to_sec(seg["timestamps"].get("to", end))
            tokens = seg.get("tokens") or []
            if tokens:
                for tok in tokens:
                    tw = (tok.get("text") or "").strip()
                    if not tw or tw.startswith("["):
                        continue
                    t_start = float(tok.get("offsets", {}).get("from", 0)) / 1000.0 if "offsets" in tok else float(tok.get("start", start) or start)
                    t_end = float(tok.get("offsets", {}).get("to", 0)) / 1000.0 if "offsets" in tok else float(tok.get("end", end) or end)
                    if "timestamps" in tok:
                        t_start = _ts_to_sec(tok["timestamps"].get("from", t_start))
                        t_end = _ts_to_sec(tok["timestamps"].get("to", t_end))
                    words.append(normalize_word(tw, t_start, t_end))
            elif text:
                # fall back: split segment into approximate words
                parts = text.split()
                if parts and end > start:
                    step = (end - start) / len(parts)
                    for i, p in enumerate(parts):
                        words.append(
                            normalize_word(p, start + i * step, start + (i + 1) * step)
                        )
            if text:
                segments_out.append({"start": start, "end": end, "text": text})

    return finalize_transcript(
        language=language or raw.get("result", {}).get("language", "id"),
        backend="whisper.cpp",
        model=model,
        words=words,
        segments=segments_out or None,
    )


def _ts_to_sec(value: Any) -> float:
    if isinstance(value, (int, float)):
        # whisper.cpp sometimes uses milliseconds in offsets already handled
        return float(value)
    if not isinstance(value, str):
        return 0.0
    # "00:00:01,230" or "00:00:01.230"
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) != 3:
        try:
            return float(value)
        except ValueError:
            return 0.0
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)
