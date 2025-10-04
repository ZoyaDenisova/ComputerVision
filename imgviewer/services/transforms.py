from __future__ import annotations
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import cv2
from math import cos, sin, radians

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

def _np_from_pil(img: Image.Image) -> np.ndarray:
    arr = np.array(img, dtype=np.float32)
    return arr

def _pil_from_np(arr: np.ndarray, mode_like: Image.Image) -> Image.Image:
    # подчищаем диапазон и тип
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode_like.mode if mode_like.mode != "P" else "RGB")

def _convolve2d_single(channel: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """2D свёртка одного канала (same, зеркальная рамка)."""
    kh, kw = kernel.shape
    pad_y, pad_x = kh // 2, kw // 2
    padded = np.pad(channel, ((pad_y, pad_y), (pad_x, pad_x)), mode="reflect")
    out = np.zeros_like(channel, dtype=np.float32)
    k = kernel.astype(np.float32)
    for y in range(out.shape[0]):
        ys = y
        for x in range(out.shape[1]):
            xs = x
            roi = padded[ys:ys+kh, xs:xs+kw]
            out[y, x] = float((roi * k).sum())
    return out

def _convolve_image(img: Image.Image, kernel: np.ndarray, *, mode: str, normalize: bool) -> Image.Image:
    """
    mode: "L" (обработка в яркости) или "RGB" (поканально).
    normalize: если True — делим ядро на сумму (если сумма != 0).
    """
    if normalize:
        s = float(kernel.sum())
        if abs(s) > 1e-12:
            kernel = kernel / s

    if mode == "L":
        src = img.convert("L")
        ch = _np_from_pil(src)
        out = _convolve2d_single(ch, kernel)
        return _pil_from_np(out, src).convert(img.mode)
    else:
        # RGB по каналам
        if img.mode not in ("RGB", "RGBA"):
            base = img.convert("RGB")
        else:
            base = img
        arr = _np_from_pil(base)
        if base.mode == "RGBA":
            rgb = arr[:, :, :3]
            a = arr[:, :, 3]
        else:
            rgb = arr
            a = None

        out_rgb = []
        for c in range(3):
            ch = rgb[:, :, c]
            conv = _convolve2d_single(ch, kernel)
            out_rgb.append(conv)
        out = np.stack(out_rgb, axis=2)
        if a is not None:
            out = np.concatenate([out, a[..., None]], axis=2)
        return _pil_from_np(out, base)

def _median_filter(img: Image.Image, ksize: int, *, mode: str) -> Image.Image:
    # используем встроенный PIL, но уважаем режим
    if mode == "L":
        return img.convert("L").filter(ImageFilter.MedianFilter(size=ksize)).convert(img.mode)
    else:
        return img.filter(ImageFilter.MedianFilter(size=ksize))

def _emboss_kernel() -> np.ndarray:
    return np.array([[-2,-1, 0],
                     [-1, 1, 1],
                     [ 0, 1, 2]], dtype=np.float32)

def _sharpen_kernel() -> np.ndarray:
    return np.array([[ 0,-1, 0],
                     [-1, 5,-1],
                     [ 0,-1, 0]], dtype=np.float32)

def _motion_kernel(length: int, angle_deg: float) -> np.ndarray:
    L = int(length) if length % 2 == 1 else int(length) + 1
    k = np.zeros((L, L), dtype=np.float32)
    cy, cx = L // 2, L // 2
    theta = radians(-angle_deg)
    for t in range(-(L//2), L//2 + 1):
        y = int(round(cy + t * sin(theta)))
        x = int(round(cx + t * cos(theta)))
        if 0 <= y < L and 0 <= x < L:
            k[y, x] = 1.0
    # нормализация по сумме — сделаем здесь, чтобы kernel можно было показывать «как есть»
    s = k.sum()
    if s > 0:
        k /= s
    return k

def filter_apply(img: Image.Image,
                 op: str,
                 kernel: np.ndarray | None,
                 mode: str,
                 normalize: bool,
                 extra: dict | None = None) -> Image.Image:
    """
    Универсальный вход из диалога фильтров.
    op: 'sharpen' | 'motion' | 'emboss' | 'median' | 'custom'
    mode: 'L'|'RGB'
    normalize: для свёрток с произвольным ядром
    extra: {'median_size': int, 'motion_len': int, 'motion_angle': float}
    """
    extra = extra or {}

    if op == "median":
        ksize = int(extra.get("median_size", 3))
        if ksize % 2 == 0: ksize += 1
        return _median_filter(img, ksize, mode=mode)

    if op == "emboss":
        k = _emboss_kernel()
        return _convolve_image(img, k, mode=mode, normalize=False)

    if op == "sharpen":
        k = _sharpen_kernel()
        # нормализацию для sharpen обычно НЕ делаем, иначе эффект ослабнет
        return _convolve_image(img, k, mode=mode, normalize=False)

    if op == "motion":
        L = int(extra.get("motion_len", 9))
        ang = float(extra.get("motion_angle", 0.0))
        k = _motion_kernel(L, ang)
        # уже нормировано
        return _convolve_image(img, k, mode=mode, normalize=False)

    # custom
    if kernel is None:
        # страховка
        k = np.zeros((3,3), dtype=np.float32); k[1,1] = 1.0
    else:
        k = np.array(kernel, dtype=np.float32)
    return _convolve_image(img, k, mode=mode, normalize=normalize)