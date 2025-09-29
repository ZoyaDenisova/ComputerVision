from __future__ import annotations
from PIL import Image, ImageEnhance

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
