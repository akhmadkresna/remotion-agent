from agentic_editor.cover.style_load import (
    DEFAULT_OVERLAYS,
    load_overlays,
    load_screen_explainer,
)


def test_overlays_locked_bold_cool_mist():
    ov = load_overlays("tutorial")
    assert ov["preset"] == "bold_mist"
    assert ov["treatment"] == "bold"
    assert ov["accent"] == "#7dd3fc"
    assert ov["accentName"] == "cool_mist_sky"
    assert ov["fonts"]["display"] == "Syne"
    assert ov["dwell"]["chip_sec"] >= 3.5
    assert ov["dwell"]["emphasis_sec"] >= 2.0


def test_overlays_defaults_match_constant():
    assert load_overlays("missing-style-pack")["accent"] == DEFAULT_OVERLAYS["accent"]
    assert "dwell" in DEFAULT_OVERLAYS


def test_screen_explainer_cool_mist_canvas():
    se = load_screen_explainer("tutorial")
    assert se["canvas"]["background"] == "#d9e2ec"
    assert se["preset"] == "cozy"
