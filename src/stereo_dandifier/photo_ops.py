import numpy as np
from PIL import Image, ImageEnhance

from stereo_dandifier.models import RenderSettings, ToneMode


def apply_style(image: Image.Image, settings: RenderSettings) -> Image.Image:
    styled = image.convert("RGB")

    if settings.brightness:
        factor = 1 + (settings.brightness / 100)
        styled = ImageEnhance.Brightness(styled).enhance(factor)

    if settings.contrast:
        factor = 1 + (settings.contrast / 100)
        styled = ImageEnhance.Contrast(styled).enhance(factor)

    if settings.tone_mode == ToneMode.BLACK_AND_WHITE:
        return styled.convert("L").convert("RGB")

    if settings.tone_mode == ToneMode.SEPIA:
        grey = styled.convert("L").convert("RGB")
        sepia = Image.new("RGB", styled.size, (118, 88, 55))
        toned = Image.blend(grey, sepia, 0.36)
        return Image.blend(grey, toned, settings.sepia_strength / 100)

    if settings.saturation:
        factor = 1 + (settings.saturation / 100)
        styled = ImageEnhance.Color(styled).enhance(factor)

    return styled


def compute_shared_levels(
    left: Image.Image,
    right: Image.Image,
    cutoff: float = 0.005,
) -> tuple[np.ndarray, np.ndarray]:
    cutoff = max(0.0, min(0.49, cutoff))
    left_pixels = np.asarray(left.convert("RGB"), dtype=np.float32).reshape(-1, 3)
    right_pixels = np.asarray(right.convert("RGB"), dtype=np.float32).reshape(-1, 3)
    combined = np.concatenate((left_pixels, right_pixels), axis=0)

    low, high = np.quantile(
        combined,
        (cutoff, 1.0 - cutoff),
        axis=0,
    )
    return low.astype(np.float32), high.astype(np.float32)


def apply_shared_levels(
    image: Image.Image,
    low: np.ndarray,
    high: np.ndarray,
) -> Image.Image:
    source = np.asarray(image.convert("RGB"), dtype=np.float32)
    low = np.asarray(low, dtype=np.float32).reshape(1, 1, 3)
    high = np.asarray(high, dtype=np.float32).reshape(1, 1, 3)
    scale = high - low
    valid_channels = scale > 1e-6
    safe_scale = np.where(valid_channels, scale, 1.0)

    adjusted = np.where(valid_channels, (source - low) * (255.0 / safe_scale), source)
    adjusted = np.clip(adjusted, 0, 255).astype(np.uint8)
    return Image.fromarray(adjusted, mode="RGB")


def auto_improve_stereo_pair(
    left: Image.Image,
    right: Image.Image,
    cutoff: float = 0.005,
) -> tuple[Image.Image, Image.Image]:
    low, high = compute_shared_levels(left, right, cutoff=cutoff)
    return apply_shared_levels(left, low, high), apply_shared_levels(right, low, high)
