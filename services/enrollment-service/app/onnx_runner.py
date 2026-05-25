"""
onnx_runner.py — ONNX Runtime wrappers for YuNet (face detection) and
MobileFaceNet (128-D embedding extraction).

Both models run in the same process during enrollment (admin-only, low-frequency).
ONNX Runtime uses CPU execution provider with 4 threads.

Model files are loaded from disk at startup and cached as module-level singletons.
In production the .onnx files are downloaded from S3 by the Model Delivery Service
OTA update pipeline and placed at the configured paths.
"""
import logging
from typing import Optional

import numpy as np
import onnxruntime as ort

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Singleton sessions ────────────────────────────────────────────────────────
_yunet_session: Optional[ort.InferenceSession] = None
_mobilefacenet_session: Optional[ort.InferenceSession] = None


def _create_session(model_path: str) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.inter_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(model_path, sess_options=opts,
                                providers=["CPUExecutionProvider"])


def load_models() -> None:
    """
    Load both ONNX models from disk at app startup.
    Raises FileNotFoundError if model files are missing.
    """
    global _yunet_session, _mobilefacenet_session

    logger.info(f"Loading YuNet from: {settings.YUNET_MODEL_PATH}")
    _yunet_session = _create_session(settings.YUNET_MODEL_PATH)

    logger.info(f"Loading MobileFaceNet from: {settings.MOBILEFACENET_MODEL_PATH}")
    _mobilefacenet_session = _create_session(settings.MOBILEFACENET_MODEL_PATH)

    logger.info("ONNX models loaded ✓")


# ── YuNet Face Detection ──────────────────────────────────────────────────────

def detect_face_yunet(image_bgr: np.ndarray) -> Optional[dict]:
    """
    Run YuNet face detection on a BGR image (OpenCV format).

    Returns a dict with bounding box and 5 facial landmarks if exactly one face found:
        {
          "x": int, "y": int, "w": int, "h": int,  # bounding box
          "landmarks": [(x,y), ...] * 5             # right_eye, left_eye, nose, right_mouth, left_mouth
        }

    Returns None if:
      - No face detected
      - More than one face detected (enrollment requires exactly one)

    YuNet input: (1, 3, H, W) float32 normalized [0,1]
    YuNet output: (N, 15) — bbox(4) + score(1) + landmarks(10)
    """
    if _yunet_session is None:
        raise RuntimeError("YuNet model not loaded. Call load_models() at startup.")

    h, w = image_bgr.shape[:2]

    # Preprocess: resize to 320×320, normalize
    import cv2
    resized = cv2.resize(image_bgr, (320, 320))
    blob = resized.astype(np.float32) / 255.0
    blob = blob.transpose(2, 0, 1)[np.newaxis, :]  # (1, 3, 320, 320)

    input_name = _yunet_session.get_inputs()[0].name
    outputs = _yunet_session.run(None, {input_name: blob})

    # outputs[0]: detected faces array
    detections = outputs[0]  # shape (N, 15) — N = num faces

    if detections is None or len(detections) == 0:
        return None

    # Filter by confidence threshold
    CONF_THRESHOLD = 0.7
    valid = [d for d in detections if d[14] >= CONF_THRESHOLD]

    if len(valid) == 0:
        return None
    if len(valid) > 1:
        # Enrollment requires exactly one face — reject ambiguous photos
        logger.warning(f"YuNet detected {len(valid)} faces — enrollment rejected (must be exactly 1)")
        return None

    det = valid[0]
    # Scale bbox back to original image size
    scale_x, scale_y = w / 320.0, h / 320.0
    x = int(det[0] * scale_x)
    y = int(det[1] * scale_y)
    fw = int(det[2] * scale_x)
    fh = int(det[3] * scale_y)

    landmarks = [
        (int(det[4] * scale_x),  int(det[5] * scale_y)),   # right eye
        (int(det[6] * scale_x),  int(det[7] * scale_y)),   # left eye
        (int(det[8] * scale_x),  int(det[9] * scale_y)),   # nose
        (int(det[10] * scale_x), int(det[11] * scale_y)),  # right mouth
        (int(det[12] * scale_x), int(det[13] * scale_y)),  # left mouth
    ]

    return {"x": x, "y": y, "w": fw, "h": fh, "landmarks": landmarks, "confidence": float(det[14])}


# ── MobileFaceNet Embedding Extraction ───────────────────────────────────────

def extract_embedding_mobilefacenet(aligned_face: np.ndarray) -> list[float]:
    """
    Run MobileFaceNet on a 112×112 aligned face crop and return a 128-D
    L2-normalized embedding vector.

    Input: aligned_face — uint8 BGR 112×112 aligned crop
    Output: list of 128 float32 values, unit-sphere normalized (||v|| = 1)

    MobileFaceNet input: (1, 3, 112, 112) float32 normalized [-1, 1]
    MobileFaceNet output: (1, 128) float32 embedding
    """
    if _mobilefacenet_session is None:
        raise RuntimeError("MobileFaceNet model not loaded. Call load_models() at startup.")

    # Preprocess: normalize to [-1, 1] (ArcFace training standard)
    face_float = aligned_face.astype(np.float32)
    face_norm = (face_float - 127.5) / 128.0          # maps [0,255] → [-1, 1]
    blob = face_norm.transpose(2, 0, 1)[np.newaxis, :] # (1, 3, 112, 112)

    input_name = _mobilefacenet_session.get_inputs()[0].name
    outputs = _mobilefacenet_session.run(None, {input_name: blob})
    embedding = outputs[0][0]  # (128,)

    # L2 normalization — project onto unit sphere
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return embedding.tolist()
