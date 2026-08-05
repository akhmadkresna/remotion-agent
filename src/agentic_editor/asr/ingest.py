"""Ingest episode: probe, extract audio, ASR, pack transcripts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from agentic_editor.asr.backends import mapped_model, resolve_backend
from agentic_editor.asr.cache import cache_key, load_cached, write_transcript
from agentic_editor.asr.faster_whisper_backend import transcribe_faster_whisper
from agentic_editor.asr.whisper_cpp import transcribe_whisper_cpp
from agentic_editor.editor.pack import pack_edit_dir
from agentic_editor.paths import ensure_edit_dirs
from agentic_editor.project import load_project, resolve_source


def extract_audio(video_path: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ffprobe_summary(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def ingest_episode(episode: Path, *, force: bool = False, verbose: bool = True) -> dict[str, Any]:
    cfg = load_project(episode)
    edit = ensure_edit_dirs(episode)
    asr_cfg = cfg.get("asr") or {}
    backend = resolve_backend(str(asr_cfg.get("backend", "auto")))
    model_tier = str(asr_cfg.get("model", "small"))
    model = mapped_model(model_tier, backend)
    language = str(asr_cfg.get("language", "id"))

    sources: dict[str, str] = cfg.get("sources") or {}
    if not sources:
        raise ValueError("project.yaml sources is empty")

    results: dict[str, Any] = {"backend": backend, "model": model, "transcripts": {}}
    probe_path = edit / "probe.json"
    probes: dict[str, Any] = {}

    for name, rel in sources.items():
        src = resolve_source(episode, rel)
        if not src.is_file():
            raise FileNotFoundError(f"Source '{name}' not found: {src}")
        probes[name] = ffprobe_summary(src)
        if verbose:
            dur = float((probes[name].get("format") or {}).get("duration") or 0)
            print(f"• {name}: {src.name} ({dur:.1f}s)")

        # Prefer ASR on cam (A-roll). Still allow screen if it's the only source.
        if name != "cam" and "cam" in sources:
            if verbose:
                print(f"  skip ASR for '{name}' (cover source; using cam transcript)")
            continue

        out_json = edit / "transcripts" / f"{name}.json"
        key = cache_key(src, backend=backend, model=model, language=language)
        if not force:
            cached = load_cached(out_json, key)
            if cached is not None:
                if verbose:
                    print(f"  cache hit → {out_json.relative_to(episode)}")
                results["transcripts"][name] = str(out_json)
                continue

        wav = edit / "audio" / f"{name}.wav"
        if verbose:
            print(f"  extracting audio → {wav.relative_to(episode)}")
        extract_audio(src, wav)

        if backend == "whisper.cpp":
            data = transcribe_whisper_cpp(
                wav, model_file=model, language=language, verbose=verbose
            )
        else:
            data = transcribe_faster_whisper(
                wav, model_name=model, language=language, verbose=verbose
            )

        write_transcript(out_json, data, key)
        if verbose:
            print(
                f"  wrote {out_json.relative_to(episode)} "
                f"({len(data.get('words', []))} words, backend={backend})"
            )
        results["transcripts"][name] = str(out_json)

    probe_path.write_text(json.dumps(probes, indent=2) + "\n", encoding="utf-8")
    packed = pack_edit_dir(edit)
    results["packed"] = str(packed)
    if verbose:
        print(f"• packed → {packed.relative_to(episode)}")
    return results
