from __future__ import annotations
from PIL import Image, ImageEnhance
import numpy as np
import cv2

def to_grayscale(img: Image.Image) -> Image.Image:
    """Градации серого"""
    return img.convert("L")

def adjust_bsc(img: Image.Image, brightness: float, saturation: float, contrast: float) -> Image.Image:
    """Яркость/насыщенность/контраст"""
    out = ImageEnhance.Brightness(img).enhance(brightness)
    out = ImageEnhance.Color(out).enhance(saturation)
    out = ImageEnhance.Contrast(out).enhance(contrast)
    return out

def _build_levels_lut(black: int, white: int, gamma: float) -> list[int]:
    black = max(0, min(255, int(black)))
    white = max(0, min(255, int(white)))
    if white <= black:
        white = black + 1
    gamma = max(0.01, float(gamma))
    scale = 255.0 / (white - black)

    lut: list[int] = []
    for x in range(256):
        if x <= black:
            y = 0.0
        elif x >= white:
            y = 255.0
        else:
            y = ((x - black) * scale)
            y = (y / 255.0) ** gamma * 255.0
        lut.append(int(round(max(0.0, min(255.0, y)))))
    return lut


def bw_levels(img: Image.Image, black: int, white: int, gamma: float) -> Image.Image:
    """Линейная и нелинейная коррекция чёрно-белого изображения
    Если вход не L — сначала конвертируем в L.
    """
    lut = _build_levels_lut(black, white, gamma)
    imgL = img if img.mode == "L" else img.convert("L")
    return imgL.point(lut)

def rotate(img: Image.Image, angle_deg: float) -> Image.Image:
    """Поворот по часовой стрелке на произвольный угол"""
    fill = (0, 0, 0, 0) if "A" in img.getbands() else (0 if img.mode == "L" else (0, 0, 0))
    try:
        return img.rotate(-angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=fill)
    except TypeError:
        return img.rotate(-angle_deg, resample=Image.BICUBIC, expand=True)

def rotate_90_cw(img: Image.Image) -> Image.Image:
    return img.rotate(-90, expand=True)

def rotate_90_ccw(img: Image.Image) -> Image.Image:
    return img.rotate(90, expand=True)

def flip_h(img: Image.Image) -> Image.Image:
    return img.transpose(Image.FLIP_LEFT_RIGHT)

def flip_v(img: Image.Image) -> Image.Image:
    return img.transpose(Image.FLIP_TOP_BOTTOM)

def _pil_to_cv_gray(img: Image.Image) -> np.ndarray:
    """PIL -> OpenCV (uint8, однотоновое)"""
    if img.mode != "L":
        img = img.convert("L")
    return np.array(img, dtype=np.uint8)

def _pil_to_cv_bgr(img: Image.Image) -> np.ndarray:
    """PIL -> OpenCV (BGR)"""
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def _cv_to_pil_from_gray(arr: np.ndarray) -> Image.Image:
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")

def _cv_to_pil_from_bgr(arr: np.ndarray) -> Image.Image:
    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")

_MORPH_MAP = {
    "erosion":        ("basic", cv2.erode),
    "dilation":       ("basic", cv2.dilate),
    "opening":        ("ex",    cv2.MORPH_OPEN),
    "closing":        ("ex",    cv2.MORPH_CLOSE),
    "gradient":       ("ex",    cv2.MORPH_GRADIENT),
    "tophat":         ("ex",    cv2.MORPH_TOPHAT),     # «Цилиндр/топ-хэт»
    "blackhat":       ("ex",    cv2.MORPH_BLACKHAT),   # «Чёрная шляпа»
}

def _ensure_kernel(matrix_01: np.ndarray) -> np.ndarray:
    """0/1 -> uint8 ядро для OpenCV; если всё нули — ставим центр = 1."""
    k = (matrix_01 > 0).astype(np.uint8)
    if k.sum() == 0:
        cy, cx = k.shape[0] // 2, k.shape[1] // 2
        k[cy, cx] = 1
    return k

def morph_apply(img: Image.Image,
                op: str,
                kernel_matrix: np.ndarray,
                iterations: int = 1,
                mode: str = "L") -> Image.Image:
    """
    Применение морфологических операций через OpenCV.
    op: 'erosion'|'dilation'|'opening'|'closing'|'gradient'|'tophat'|'blackhat'
    kernel_matrix: 2D ndarray из 0/1
    iterations: >=1
    mode: 'L' — конвертировать в серое; 'RGB' — по каналам
    """
    if op not in _MORPH_MAP:
        raise ValueError(f"Unknown morph op: {op}")
    iterations = max(1, int(iterations))
    kernel = _ensure_kernel(np.asarray(kernel_matrix, dtype=np.uint8))

    kind, fn = _MORPH_MAP[op]

    if mode == "L":
        src = _pil_to_cv_gray(img)
        if kind == "basic":
            out = fn(src, kernel, iterations=iterations)
        else:
            out = cv2.morphologyEx(src, fn, kernel, iterations=iterations)
        return _cv_to_pil_from_gray(out)

    # RGB по каналам (обработка в BGR, но поканально)
    src_bgr = _pil_to_cv_bgr(img)
    channels = cv2.split(src_bgr)  # B, G, R
    out_ch = []
    for chan in channels:
        if kind == "basic":
            ch = fn(chan, kernel, iterations=iterations)
        else:
            ch = cv2.morphologyEx(chan, fn, kernel, iterations=iterations)
        out_ch.append(ch)
    out_bgr = cv2.merge(out_ch)
    return _cv_to_pil_from_bgr(out_bgr)