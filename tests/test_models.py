from stereo_dandifier.models import plain_caption_html


def test_plain_caption_html_escapes_text_and_sets_defaults():
    html = plain_caption_html("First <wicket>")

    assert "First &lt;wicket&gt;" in html
    assert "font-family:Arial" in html
    assert "font-size:14pt" in html


def test_plain_caption_html_returns_empty_for_blank_caption():
    assert plain_caption_html("") == ""
