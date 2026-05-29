from io import BytesIO
from pathlib import Path

from PIL import Image, ImageSequence

from stereo_dandifier.exif import read_exif, suggest_caption
from stereo_dandifier.models import ProjectImage, RenderSettings


def load_project_images(path: Path) -> list[ProjectImage]:
    if path.suffix.lower() == ".dng":
        raw_images = load_raw_project_images(path)
        if raw_images:
            return raw_images

    return load_pillow_project_images(path)


def load_pillow_project_images(path: Path) -> list[ProjectImage]:
    with Image.open(path) as image:
        exif = read_exif(image)
        frame_count = getattr(image, "n_frames", 1)
        frames = []

        for frame_index, frame in enumerate(ImageSequence.Iterator(image)):
            frame.load()
            source = frame.convert("RGB")
            caption = suggest_caption(path, exif)
            if frame_count > 1:
                caption = f"{caption} ({frame_index + 1})"
            frames.append(
                ProjectImage(
                    path=path,
                    source=source,
                    frame_index=frame_index,
                    frame_count=frame_count,
                    exif=exif,
                    settings=RenderSettings(caption=caption),
                )
            )

    return frames


def load_raw_project_images(path: Path) -> list[ProjectImage]:
    try:
        import rawpy
    except ImportError:
        return []

    with rawpy.imread(str(path)) as raw:
        variants = []
        exif = read_pillow_exif_fallback(path)
        caption = suggest_caption(path, exif)

        preview = extract_raw_preview(raw)
        if preview is not None:
            variants.append(
                ProjectImage(
                    path=path,
                    source=preview,
                    frame_index=0,
                    frame_count=2,
                    variant_name="Preview",
                    selected_for_export=False,
                    exif=exif,
                    settings=RenderSettings(caption=caption),
                )
            )

        raw_render = Image.fromarray(raw.postprocess()).convert("RGB")
        variants.append(
            ProjectImage(
                path=path,
                source=raw_render,
                frame_index=len(variants),
                frame_count=len(variants) + 1,
                variant_name="RAW render",
                selected_for_export=True,
                exif=exif,
                settings=RenderSettings(caption=caption),
            )
        )

    frame_count = len(variants)
    for index, variant in enumerate(variants):
        variant.frame_index = index
        variant.frame_count = frame_count
    return variants


def extract_raw_preview(raw) -> Image.Image | None:
    try:
        import rawpy

        thumbnail = raw.extract_thumb()
    except Exception:
        return None

    if thumbnail.format == rawpy.ThumbFormat.JPEG:
        return Image.open(BytesIO(thumbnail.data)).convert("RGB")
    if thumbnail.format == rawpy.ThumbFormat.BITMAP:
        return Image.fromarray(thumbnail.data).convert("RGB")
    return None


def read_pillow_exif_fallback(path: Path) -> dict[str, str]:
    try:
        with Image.open(path) as image:
            return read_exif(image)
    except Exception:
        return {}
