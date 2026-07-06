"""전처리 — 회전 보정.

순서: ① 방향 보정(90°/180° 단위) → ② 미세 기울기 보정(deskew, ±10° 이내).
- 텍스트 조각 단위 180° 반전은 PaddleOCR 내장 방향 분류기가 처리하므로,
  여기서는 페이지 전체 90° 단위 회전과 미세 기울기만 다룬다.
- deskew 를 건너뛰면 OCR bbox 가 기울어져 치환 렌더링이 어려워진다.

OpenCV(cv2)는 폐쇄망 반입 대상이므로 함수 호출 시점에 import 한다.
"""


def _cv2():
    import cv2
    return cv2


def _np():
    import numpy as np
    return np


def estimate_skew_angle(image) -> float:
    """이진화 후 텍스트 픽셀의 최소면적 사각형으로 미세 기울기(도)를 추정."""
    cv2, np = _cv2(), _np()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 10:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle > 45:
        angle -= 90
    return float(angle)


def rotate(image, angle_deg: float):
    """이미지 중심 기준 회전. 배경은 흰색으로 채운다 (문서 가정)."""
    cv2 = _cv2()
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    return cv2.warpAffine(image, matrix, (w, h),
                          flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def deskew(image, max_angle: float = 10.0):
    """미세 기울기 보정. max_angle 초과 추정치는 오탐으로 보고 회전하지 않는다."""
    angle = estimate_skew_angle(image)
    if abs(angle) < 0.1 or abs(angle) > max_angle:
        return image, 0.0
    return rotate(image, angle), angle


def fix_orientation(image, ocr_confidence_fn):
    """페이지 전체 90° 단위 방향 보정.

    ocr_confidence_fn(image) -> float 를 4방향에 대해 호출해 신뢰도가 가장
    높은 방향을 선택하는 휴리스틱. 물량이 크면 PaddleOCR 문서 방향 분류
    모델(doc orientation)로 교체한다 (계획서 ① 전처리 참조).
    """
    cv2 = _cv2()
    rotations = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE]
    best, best_conf, best_deg = image, -1.0, 0
    for deg, rot in zip((0, 90, 180, 270), rotations):
        candidate = image if rot is None else cv2.rotate(image, rot)
        conf = ocr_confidence_fn(candidate)
        if conf > best_conf:
            best, best_conf, best_deg = candidate, conf, deg
    return best, best_deg
