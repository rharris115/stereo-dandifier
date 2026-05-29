from pathlib import Path

from stereo_dandifier.exif import normalise_exif_value, suggest_caption


def test_normalise_utf16_exif_bytes():
    assert normalise_exif_value("First wicket".encode("utf-16-le")) == "First wicket"


def test_suggest_caption_prefers_description():
    caption = suggest_caption(
        Path("IMG_0001.jpg"), {"ImageDescription": "Village cricket"}
    )

    assert caption == "Village cricket"


def test_suggest_caption_falls_back_to_clean_filename():
    caption = suggest_caption(Path("IMG_0001-first-wicket.jpg"), {})

    assert caption == "IMG 0001 first wicket"
