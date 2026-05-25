"""
pipeline.py — Full enrollment image processing pipeline.

Stages:
  1. Decode uploaded bytes → BGR NumPy array
  2. YuNet face detection (must find exactly one face)
  3. Face alignment using eye landmarks (affine transform)
  4. CLAHE contrast normalization (handles sunlight/shadow in outdoor booths)
  5. Crop to 112×112 MobileFaceNet standard input
  6. MobileFaceNet → 128-D L2-normalized embedding

Returns:
  EnrollmentResult with embedding + metadata, or raises EnrollmentError.
"""
import logging
from dataclasses import dataclass

import cv2
import numpy as np

from app.onnx_runner import detect_face_yunet, extract_embedding_mobilefacenet
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EnrollmentError(Exception):
    """Raised when the enrollment pipeline rejects an image."""
    pass


@dataclass
class EnrollmentResult:
    embedding: list[float]           # 128-D L2-normalized float vector
    face_confidence: float           # YuNet detection confidence
    face_bbox: dict                  # {"x","y","w","h"}
    image_shape: tuple               # (H, W) of original upload


# ── Main pipeline entry point ─────────────────────────────────────────────────

def run_enrollment_pipeline(image_bytes: bytes) -> EnrollmentResult:
    """
    Full enrollment pipeline: raw bytes → 128-D encrypted-ready embedding.

    Args:
        image_bytes: raw JPEG/PNG bytes from admin upload

    Returns:
        EnrollmentResult with validated embedding

    Raises:
        EnrollmentError: descriptive message for the admin on any rejection
    """
    # ── Stage 1: Decode image ─────────────────────────────────────────────────
    nparr = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image_bgr is None:
        raise EnrollmentError("Cannot decode image. Upload a valid JPEG or PNG file.")

    h, w = image_bgr.shape[:2]

    if w < 160 or h < 160:
        raise EnrollmentError(
            f"Image too small ({w}×{h}). Minimum 160×160px required for accurate detection."
        )

    # ── Stage 2: YuNet face detection ─────────────────────────────────────────
    detection = detect_face_yunet(image_bgr)

    if detection is None:
        raise EnrollmentError(
            "Could not detect exactly one face in the image. "
            "Ensure the photo shows one person, facing forward, with good lighting."
        )

    if detection["w"] < settings.MIN_FACE_SIZE_PX or detection["h"] < settings.MIN_FACE_SIZE_PX:
        raise EnrollmentError(
            f"Detected face is too small ({detection['w']}×{detection['h']}px). "
            f"Use a closer photo (minimum face size: {settings.MIN_FACE_SIZE_PX}px)."
        )

    logger.info(
        f"YuNet detection: bbox=({detection['x']},{detection['y']},"
        f"{detection['w']},{detection['h']}) confidence={detection['confidence']:.3f}"
    )

    # ── Stage 3: Face alignment using eye landmarks ───────────────────────────
    aligned_112 = _align_and_crop(image_bgr, detection["landmarks"])

    # ── Stage 4: CLAHE normalization ──────────────────────────────────────────
    # Applied on the Y channel (luminance) to normalize outdoor lighting conditions
    # without distorting color information needed by MobileFaceNet RGB input
    aligned_112 = _clahe_normalize(aligned_112)

    # ── Stage 5: MobileFaceNet → 128-D embedding ──────────────────────────────
    embedding = extract_embedding_mobilefacenet(aligned_112)

    logger.info(f"Embedding extracted: 128-D, ||v||≈{sum(x**2 for x in embedding)**0.5:.4f}")

    return EnrollmentResult(
        embedding=embedding,
        face_confidence=detection["confidence"],
        face_bbox={"x": detection["x"], "y": detection["y"],
                   "w": detection["w"], "h": detection["h"]},
        image_shape=(h, w),
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _align_and_crop(image_bgr: np.ndarray, landmarks: list) -> np.ndarray:
    """
    Align face to canonical 112×112 crop using eye center landmarks.

    Uses a fixed set of reference eye positions (ArcFace standard) and computes
    a similarity transform (rotation + scale + translation, no shear) to map
    the detected eyes onto the reference positions.

    Reference positions from ArcFace paper (112×112 space):
      right_eye = (38.29, 51.70)
      left_eye  = (73.53, 51.70)
    """
    REFERENCE_LANDMARKS = np.float32([
        [38.29459953, 51.69630051],  # right eye
        [73.53179932, 51.50139999],  # left eye
        [56.02560089, 71.73660278],  # nose
        [41.54930115, 92.36550140],  # right mouth corner
        [70.72990036, 92.20410156],  # left mouth corner
    ])

    src_pts = np.float32([[lm[0], lm[1]] for lm in landmarks])

    # Estimate similarity transform (cv2.LMEDS is robust to landmark noise)
    M, _ = cv2.estimateAffinePartial2D(src_pts, REFERENCE_LANDMARKS, method=cv2.LMEDS)

    if M is None:
        # Fallback: simple center crop without alignment
        logger.warning("Affine alignment failed — using center crop fallback")
        x, y, fw, fh = 0, 0, image_bgr.shape[1], image_bgr.shape[0]
        face = image_bgr[y:y+fh, x:x+fw]
        return cv2.resize(face, (112, 112))

    aligned = cv2.warpAffine(image_bgr, M, (112, 112), flags=cv2.INTER_LINEAR)
    return aligned


def _clahe_normalize(face_bgr: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to the
    luminance channel of the face crop.

    - Converts to LAB color space, applies CLAHE on L channel only
    - Converts back to BGR (MobileFaceNet expects BGR or RGB — handled in onnx_runner)
    - clipLimit=2.0 and tileGridSize=(8,8) are empirically tuned for face crops
    """
    lab = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)

    lab_normalized = cv2.merge([l_ch, a_ch, b_ch])
    return cv2.cvtColor(lab_normalized, cv2.COLOR_LAB2BGR)
