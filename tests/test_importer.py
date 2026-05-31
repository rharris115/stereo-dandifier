import sys
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from stereo_dandifier.card_json import save_card_json
from stereo_dandifier.importer import load_project_images, load_raw_project_images
from stereo_dandifier.models import ProjectImage, RenderSettings


def test_single_frame_file_imports_one_project_image(tmp_path):
    path = tmp_path / "single.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path, dpi=(720, 720))

    images = load_project_images(path)

    assert len(images) == 1
    assert images[0].frame_index == 0
    assert images[0].frame_count == 1
    assert images[0].display_name == "single.png"
    assert "single" in images[0].settings.caption_html
    assert round(images[0].source.info["dpi"][0]) == 720
    assert round(images[0].source.info["dpi"][1]) == 720


def test_multi_frame_file_imports_selectable_project_images(tmp_path):
    path = tmp_path / "multi.tiff"
    first = Image.new("RGB", (8, 4), (255, 0, 0))
    second = Image.new("RGB", (8, 4), (0, 0, 255))
    first.save(path, save_all=True, append_images=[second])

    images = load_project_images(path)

    assert len(images) == 2
    assert images[0].display_name == "multi.tiff [1/2]"
    assert images[1].display_name == "multi.tiff [2/2]"
    red, green, blue = images[0].source.getpixel((0, 0))
    assert red > 240
    assert green < 10
    assert blue < 10
    assert images[1].source.getpixel((0, 0)) == (0, 0, 255)


def test_card_json_imports_embedded_card_data(tmp_path):
    path = tmp_path / "0006_20260528_200109-frame-1-preview-stereocard.json"
    save_card_json(
        ProjectImage(
            path=tmp_path / "source.png",
            source=Image.new("RGB", (8, 4), (25, 50, 75)),
            exif={"Camera": "Kandao"},
            settings=RenderSettings(brightness=120),
        ),
        path,
    )

    images = load_project_images(path)

    assert len(images) == 1
    assert images[0].path == path
    assert images[0].source.size == (8, 4)
    assert images[0].source.getpixel((0, 0)) == (25, 50, 75)
    assert images[0].exif == {"Camera": "Kandao"}
    assert images[0].settings.brightness == 120


def test_dng_import_uses_raw_preview_and_raw_render_when_rawpy_is_available(
    tmp_path, monkeypatch
):
    path = tmp_path / "image.dng"
    path.write_bytes(b"not a real dng")

    fake_raw = FakeRaw(make_jpeg_bytes(Image.new("RGB", (4, 2), (255, 0, 0))))
    fake_rawpy = SimpleNamespace(
        ThumbFormat=SimpleNamespace(JPEG="jpeg", BITMAP="bitmap"),
        imread=lambda _path: fake_raw,
    )
    monkeypatch.setitem(sys.modules, "rawpy", fake_rawpy)
    monkeypatch.setattr(
        "stereo_dandifier.importer.Image.fromarray",
        lambda _array: Image.new("RGB", (4, 2), (0, 0, 255)),
    )

    images = load_raw_project_images(path)

    assert [image.variant_name for image in images] == ["Preview", "RAW render"]
    assert images[0].display_name == "image.dng [Preview]"
    assert images[1].display_name == "image.dng [RAW render]"
    assert images[0].thumbnail_name == "Preview"
    assert images[1].thumbnail_name == "RAW render"
    red, green, blue = images[0].source.getpixel((0, 0))
    assert red > 240
    assert green < 10
    assert blue < 10
    assert images[1].source.getpixel((0, 0)) == (0, 0, 255)


class FakeRaw:
    def __init__(self, jpeg_preview: bytes):
        self.jpeg_preview = jpeg_preview

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_thumb(self):
        return SimpleNamespace(format="jpeg", data=self.jpeg_preview)

    def postprocess(self):
        return object()


def make_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()
