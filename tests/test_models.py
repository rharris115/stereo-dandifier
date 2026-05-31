from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    RenderSettings,
    ToneMode,
    WindowShape,
    plain_caption_html,
)


def test_plain_caption_html_escapes_text_and_sets_defaults():
    html = plain_caption_html("First <wicket>")

    assert "First &lt;wicket&gt;" in html
    assert "font-family:Arial" in html
    assert "font-size:14pt" in html


def test_plain_caption_html_returns_empty_for_blank_caption():
    assert plain_caption_html("") == ""


def test_render_settings_normalises_categorical_strings_to_enums():
    settings = RenderSettings(
        layout_template="holmes_standard",
        tone_mode="Sepia",
        caption_position="Left image",
        window_shape="Circle",
    )

    assert settings.layout_template is CardLayoutName.HOLMES_STANDARD
    assert settings.tone_mode is ToneMode.SEPIA
    assert settings.caption_position is CaptionPosition.LEFT_IMAGE
    assert settings.window_shape is WindowShape.CIRCLE
