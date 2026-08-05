"""faster-whisper backend (preferred on Windows / NVIDIA)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_editor.asr.normalize import finalize_transcript, normalize_word


def transcribe_faster_whisper(
    audio_wav: Path,
    *,
    model_name: str,
    language: str,
    verbose: bool = True,
) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper not installed. Run: uv sync\n"
            "On Windows GPU, install a CUDA build of ctranslate2 if available."
        ) from e

    import sys

    device = "cuda"
    compute_type = "float16"
    if sys.platform == "darwin":
        device = "cpu"
        compute_type = "int8"
    else:
        # probe cuda
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() == 0:
                device = "cpu"
                compute_type = "int8"
        except Exception:
            device = "cpu"
            compute_type = "int8"

    if verbose:
        print(
            f"  faster-whisper: model={model_name} device={device} compute={compute_type}",
            flush=True,
        )

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        str(audio_wav),
        language=language or None,
        word_timestamps=True,
        vad_filter=True,
    )

    words: list[dict[str, Any]] = []
    segments_out: list[dict[str, Any]] = []
    for seg in segments_iter:
        segments_out.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": (seg.text or "").strip(),
            }
        )
        if seg.words:
            for w in seg.words:
                text = (w.word or "").strip()
                if not text:
                    continue
                words.append(
                    normalize_word(
                        text,
                        float(w.start),
                        float(w.end),
                        score=float(w.probability) if w.probability is not None else None,
                    )
                )

    lang = language or getattr(info, "language", None) or "id"
    return finalize_transcript(
        language=lang,
        backend="faster-whisper",
        model=model_name,
        words=words,
        segments=segments_out,
    )
