"""Load presentation tokens from styles/<name>/style.md YAML fence."""

from __future__ import annotations

import re
from typing import Any

import yaml

from agentic_editor.paths import framework_home

# Locked A-roll MG = bold type + cool mist sky accent
DEFAULT_OVERLAYS: dict[str, Any] = {
    "preset": "bold_mist",
    "treatment": "bold",
    "accent": "#7dd3fc",
    "accentName": "cool_mist_sky",
    "ink": "#ffffff",
    "dim": "rgba(255,255,255,0.55)",
    "fonts": {
        "display": "Syne",
        "ui": "Instrument Sans",
    },
    "chapter": {
        "kickerSizeCqh": 2.4,
        "titleSizeCqh": 9,
        "leftCqw": 4.5,
        "topCqh": 14,
        "maxWidthCqw": 42,
    },
    "emphasis": {
        "sizeCqh": 16,
        "leftCqw": 4.5,
        "bottomCqh": 16,
        "underline": True,
    },
    "diagram": {
        "leftCqw": 4.5,
        "topCqh": 12,
        "maxWidthCqw": 40,
        "stepSizeCqh": 3.6,
    },
    "chip": {
        "leftCqw": 4.5,
        "topCqh": 12,
        "sizeCqh": 3.4,
    },
    "safe": {
        "faceClear": True,
        "zones": ["left_third", "lower_third"],
    },
}

# Locked defaults = cozy + cool mist + smart window detect
DEFAULT_SCREEN_EXPLAINER: dict[str, Any] = {
    "preset": "cozy",
    "canvas": {
        "background": "#d9e2ec",
        "backgroundDeep": "#c4d0dc",
        "gradient": "radial",
    },
    "screen": {
        "presentation": "float_centered",
        "widthRatio": 0.78,
        "maxHeightRatio": 0.82,
        "borderRadiusPx": 12,
        "shadow": "soft_float",
        "objectFit": "fill",
        "crop": {
            "mode": "smart_window_detect",
            "analysisMaxWidth": 480,
            "chromeSideInsetFracMax": 0.12,
            "windowRelativePad": 0.003,
        },
    },
    "pip": {
        "anchor": "stage_lower_right",
        "widthRatio": 0.18,
        "aspectRatio": "4:5",
        "insetRightRatio": 0.035,
        "insetBottomRatio": 0.045,
        "borderRadiusPx": 14,
        "border": "none",
        "objectFit": "cover",
        "objectPosition": "center 28%",
    },
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def _load_style_yaml(style_name: str) -> dict[str, Any]:
    path = framework_home() / "styles" / style_name / "style.md"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S | re.I)
    if not m:
        return {}
    try:
        parsed = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def load_overlays(style_name: str = "tutorial") -> dict[str, Any]:
    """Return A-roll overlay tokens (bold + cool mist accent — locked)."""
    cfg = _deep_merge({}, DEFAULT_OVERLAYS)
    parsed = _load_style_yaml(style_name)
    ov = parsed.get("overlays")
    if isinstance(ov, dict):
        cfg = _deep_merge(cfg, ov)
    return cfg


def load_screen_explainer(style_name: str = "tutorial") -> dict[str, Any]:
    """Return screen_explainer tokens (cozy / cool mist locked by style pack)."""
    cfg = _deep_merge({}, DEFAULT_SCREEN_EXPLAINER)
    parsed = _load_style_yaml(style_name)
    se = parsed.get("screen_explainer")
    if isinstance(se, dict):
        cfg = _deep_merge(cfg, se)
    return cfg
