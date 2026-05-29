from pathlib import Path

from PIL import Image
from PIL.ExifTags import IFD, TAGS


def read_exif(image: Image.Image) -> dict[str, str]:
    try:
        raw_exif = image.getexif()
    except Exception:
        return {}

    exif: dict[str, str] = {}
    items = list(raw_exif.items())
    try:
        items.extend(raw_exif.get_ifd(IFD.Exif).items())
    except Exception:
        pass

    for tag_id, value in items:
        name = TAGS.get(tag_id, str(tag_id))
        text = normalise_exif_value(value)
        if text:
            exif[name] = text
    return exif


def normalise_exif_value(value) -> str:
    if isinstance(value, bytes):
        encodings = (
            ("utf-16-le", "utf-8", "latin-1")
            if b"\x00" in value
            else ("utf-8", "latin-1")
        )
        for encoding in encodings:
            try:
                return value.decode(encoding).strip("\x00 ")
            except UnicodeDecodeError:
                continue
        return ""
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def suggest_caption(path: Path, exif: dict[str, str]) -> str:
    for key in ("ImageDescription", "XPTitle", "DocumentName"):
        value = exif.get(key, "").strip()
        if value:
            return value

    captured = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if captured:
        return captured.replace(":", "-", 2)

    return path.stem.replace("_", " ").replace("-", " ").strip()
