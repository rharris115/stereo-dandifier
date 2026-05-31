from dataclasses import dataclass

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise RuntimeError(
        "OpenCV is required for StereoDandifier stereo image operations. "
        "Run `uv sync` or reinstall the project dependencies."
    ) from exc

from PIL import Image

from stereo_dandifier.models import RenderSettings

RECTIFICATION_WARNING_OFFSET_PX = 2.0
RECTIFICATION_BORDERLINE_OFFSET_PX = 0.8
RECTIFICATION_MIN_CONFIDENCE = 0.35


@dataclass(frozen=True)
class StereoAlignmentReport:
    vertical_offset_px: float | None
    confidence: float
    method: str


def split_stereo_pair(
    image: Image.Image, settings: RenderSettings
) -> tuple[Image.Image, Image.Image]:
    width, height = image.size
    midpoint = width // 2
    left = image.crop((0, 0, midpoint, height))
    right = image.crop((midpoint, 0, width, height))

    if settings.right_eye_transform:
        right = apply_rectification_transform(right, settings.right_eye_transform)

    return left, right


def apply_rectification_transform(
    image: Image.Image, transform: tuple[float, ...]
) -> Image.Image:
    source = np.asarray(image.convert("RGB"))
    border_colour = (245, 241, 232)

    if len(transform) == 6:
        matrix = np.asarray(transform, dtype=np.float32).reshape(2, 3)
        rectified = cv2.warpAffine(
            source,
            matrix,
            image.size,
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_colour,
        )
        return Image.fromarray(rectified)

    if len(transform) == 8:
        matrix = np.asarray((*transform, 1.0), dtype=np.float32).reshape(3, 3)
        rectified = cv2.warpPerspective(
            source,
            matrix,
            image.size,
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_colour,
        )
        return Image.fromarray(rectified)

    if len(transform) == 9:
        matrix = np.asarray(transform, dtype=np.float32).reshape(3, 3)
        rectified = cv2.warpPerspective(
            source,
            matrix,
            image.size,
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_colour,
        )
        return Image.fromarray(rectified)

    raise ValueError(f"Unsupported rectification transform length: {len(transform)}")


def score_comfort(image: Image.Image, settings: RenderSettings) -> str:
    alignment = stereo_alignment_report(image, settings)
    if (
        alignment.vertical_offset_px is not None
        and alignment.confidence >= RECTIFICATION_MIN_CONFIDENCE
    ):
        offset = abs(alignment.vertical_offset_px)
        warning_offset = rectification_warning_offset_px(image.height)
        borderline_offset = rectification_borderline_offset_px(image.height)
        if offset >= warning_offset:
            return f"Poor - vertical alignment off by {offset:.1f}px"
        if offset >= borderline_offset:
            return f"Borderline - vertical alignment off by {offset:.1f}px"

    width, height = image.size
    if width < height:
        return "Borderline - portrait source"
    if width / max(height, 1) < 1.7:
        return "Good - check stereo split"
    return "Excellent"


def rectification_warning_offset_px(eye_height: int) -> float:
    return max(RECTIFICATION_WARNING_OFFSET_PX, eye_height * 0.003)


def rectification_borderline_offset_px(eye_height: int) -> float:
    return max(RECTIFICATION_BORDERLINE_OFFSET_PX, eye_height * 0.001)


def stereo_alignment_report(
    image: Image.Image, settings: RenderSettings
) -> StereoAlignmentReport:
    left, right = split_stereo_pair(image, settings)
    report = opencv_stereo_alignment_report(left, right)
    if report is not None:
        return report
    return StereoAlignmentReport(None, 0.0, "opencv")


def suggested_right_eye_transform(image: Image.Image) -> tuple[float, ...] | None:
    left, right = split_stereo_pair(image, RenderSettings())
    return opencv_right_eye_rectification_transform(left, right)


def opencv_right_eye_rectification_transform(
    left: Image.Image, right: Image.Image
) -> tuple[float, ...] | None:
    left_gray, scale = cv2_grayscale(left)
    right_gray, _right_scale = cv2_grayscale(right)
    left_points, right_points = matched_feature_points(left_gray, right_gray)
    if left_points is None or right_points is None or len(left_points) < 8:
        return None

    affine, inliers = cv2.estimateAffinePartial2D(
        right_points,
        left_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=2.5,
        maxIters=3000,
        confidence=0.995,
    )
    if affine is not None and ransac_inlier_count(inliers) >= 8:
        return cv2_affine_to_transform(affine, scale)

    homography, inliers = cv2.findHomography(
        right_points,
        left_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=3.0,
        maxIters=3000,
        confidence=0.995,
    )
    if homography is not None and ransac_inlier_count(inliers) >= 10:
        return cv2_homography_to_transform(homography, scale)

    return None


def matched_feature_points(left_gray, right_gray):
    if hasattr(cv2, "SIFT_create"):
        detector = cv2.SIFT_create(nfeatures=1600)
        norm = cv2.NORM_L2
    else:
        detector = cv2.ORB_create(nfeatures=1600)
        norm = cv2.NORM_HAMMING

    left_keypoints, left_descriptors = detector.detectAndCompute(left_gray, None)
    right_keypoints, right_descriptors = detector.detectAndCompute(right_gray, None)
    if left_descriptors is None or right_descriptors is None:
        return None, None
    if len(left_keypoints) < 12 or len(right_keypoints) < 12:
        return None, None

    matcher = cv2.BFMatcher(norm)
    matches = matcher.knnMatch(right_descriptors, left_descriptors, k=2)
    left_points = []
    right_points = []
    for pair in matches:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance >= second.distance * 0.75:
            continue
        right_point = right_keypoints[best.queryIdx].pt
        left_point = left_keypoints[best.trainIdx].pt
        right_points.append(right_point)
        left_points.append(left_point)

    if len(left_points) < 8:
        return None, None
    return (
        np.asarray(left_points, dtype=np.float32),
        np.asarray(right_points, dtype=np.float32),
    )


def ransac_inlier_count(inliers) -> int:
    if inliers is None:
        return 0
    return int(inliers.sum())


def cv2_affine_to_transform(affine, scale: float) -> tuple[float, ...]:
    source_to_dest = np.vstack([affine, [0.0, 0.0, 1.0]])
    source_to_dest = unscale_transform(source_to_dest, scale)
    return tuple(float(value) for value in source_to_dest[:2, :].reshape(6))


def cv2_homography_to_transform(homography, scale: float) -> tuple[float, ...]:
    source_to_dest = unscale_transform(homography, scale)
    source_to_dest = source_to_dest / source_to_dest[2, 2]
    return tuple(float(value) for value in source_to_dest.reshape(9))


def unscale_transform(transform, scale: float):
    if scale == 1.0:
        return transform
    scaled_to_source = np.diag([scale, scale, 1.0])
    source_to_scaled = np.diag([1 / scale, 1 / scale, 1.0])
    return source_to_scaled @ transform @ scaled_to_source


def opencv_stereo_alignment_report(
    left: Image.Image, right: Image.Image
) -> StereoAlignmentReport | None:
    left_gray, scale = cv2_grayscale(left)
    right_gray, _right_scale = cv2_grayscale(right)
    orb = cv2.ORB_create(nfeatures=1200)
    left_keypoints, left_descriptors = orb.detectAndCompute(left_gray, None)
    right_keypoints, right_descriptors = orb.detectAndCompute(right_gray, None)
    if left_descriptors is None or right_descriptors is None:
        return None
    if len(left_keypoints) < 12 or len(right_keypoints) < 12:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(left_descriptors, right_descriptors, k=2)
    vertical_offsets = []
    for pair in matches:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance >= second.distance * 0.75:
            continue
        left_point = left_keypoints[best.queryIdx].pt
        right_point = right_keypoints[best.trainIdx].pt
        vertical_offsets.append(right_point[1] - left_point[1])

    if len(vertical_offsets) < 8:
        return None

    offsets = np.asarray(vertical_offsets, dtype=np.float32)
    median = float(np.median(offsets))
    deviations = np.abs(offsets - median)
    inliers = offsets[deviations <= 2.5]
    if len(inliers) < 6:
        return None

    refined = float(np.median(inliers)) / scale
    confidence = min(1.0, len(inliers) / 30) * max(
        0.0, 1.0 - float(np.std(inliers)) / 3
    )
    return StereoAlignmentReport(refined, confidence, "opencv-orb")


def cv2_grayscale(image: Image.Image, max_width: int = 800):
    source = image.convert("RGB")
    scale = 1.0
    if source.width > max_width:
        scale = max_width / source.width
        height = max(1, round(source.height * scale))
        source = source.resize((max_width, height), Image.Resampling.BILINEAR)
    array = np.asarray(source)
    return cv2.cvtColor(array, cv2.COLOR_RGB2GRAY), scale
