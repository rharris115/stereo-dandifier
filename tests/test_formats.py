import pytest

from stereo_dandifier.formats import CARD_FORMATS, format_particulars, mm_to_px


def test_mm_to_px_uses_300_dpi():
    assert mm_to_px(25.4) == 300


@pytest.mark.parametrize("name", CARD_FORMATS)
def test_all_formats_have_particulars(name):
    particulars = format_particulars(name)

    assert "mm card" in particulars
    assert "caption area" in particulars
