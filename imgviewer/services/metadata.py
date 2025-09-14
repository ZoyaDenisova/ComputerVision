# imgviewer/services/metadata.py
from __future__ import annotations
import os
from typing import Dict, List, Optional, Tuple
from PIL import Image, ExifTags

BITS_PER_PIXEL: Dict[str, int] = {
    "1": 1, "L": 8, "P": 8, "LA": 16, "RGB": 24, "RGBA": 32, "RGBa": 32,
    "CMYK": 32, "YCbCr": 24, "I;16": 16, "I": 32, "F": 32,
}

MODE_HUMAN: Dict[str, str] = {
    "1": "Бинарное (1 бит)", "L": "Оттенки серого (8 бит)", "P": "Индексированное (палитра)",
    "LA": "Серое + альфа", "RGB": "Цветное (RGB)", "RGBA": "Цветное (RGB + альфа)",
    "RGBa": "Цветное (RGB + премультипл. альфа)", "CMYK": "Печать (CMYK)",
    "YCbCr": "Видео (YCbCr)", "I;16": "16-бит целочисленное", "I": "32-бит целочисленное",
    "F": "32-бит float",
}

def human_size(n: int) -> str:
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    i = 0; f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024; i += 1
    return f"{f:.2f} {units[i]}"

def exif_dict(img: Image.Image) -> Dict[str, object]:
    try:
        exif = img.getexif()
        if not exif:
            return {}
        return {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
    except Exception:
        return {}

def pick_exif_fields(ed: Dict[str, object]) -> List[str]:
    keys = [
        "DateTimeOriginal", "DateTime", "CreateDate",
        "Make", "Model", "LensModel",
        "ExposureTime", "FNumber", "ISOSpeedRatings", "PhotographicSensitivity",
        "FocalLength", "Orientation", "Software",
    ]
    out: List[str] = []
    for k in keys:
        if k in ed:
            v = ed[k]
            if isinstance(v, bytes):
                try: v = v.decode(errors="ignore")
                except Exception: v = str(v)
            out.append(f"{k}: {v}")
    if len(out) < 5 and ed:
        for k, v in ed.items():
            if k in ("GPSInfo",) or any(s.startswith(f"{k}:") for s in out):
                continue
            out.append(f"{k}: {v}")
            if len(out) >= 5:
                break
    return out

def describe(img: Image.Image, *, path: Optional[str], icc_profile: Optional[bytes]) -> str:
    """Собрать человекочитаемую сводку по изображению (без Tk)."""
    file_size = os.path.getsize(path) if path and os.path.exists(path) else 0
    w, h = img.size
    fmt = img.format or (os.path.splitext(path)[1].upper().lstrip(".") if path else "N/A")
    mode = img.mode
    bpp = BITS_PER_PIXEL.get(mode)
    bands = ",".join(img.getbands())

    dpi = None
    if isinstance(img.info.get("dpi"), (tuple, list)) and img.info.get("dpi"):
        dpi = img.info.get("dpi")
    elif "resolution" in img.info:
        dpi = img.info.get("resolution")

    n_frames = getattr(img, "n_frames", 1)
    has_alpha = "A" in bands
    icc_len = len(icc_profile) if icc_profile else len(img.info.get("icc_profile", b"")) or 0
    approx_mem = int(w * h * bpp // 8) if bpp else None

    ed = exif_dict(img)
    exif_lines = pick_exif_fields(ed) or ["не обнаружен"]

    lines = []
    lines.append(f"Путь: {path}")
    lines.append(f"Размер на диске: {human_size(file_size)} ({file_size} байт)")
    lines.append(f"Разрешение (пиксели): {w} × {h}")
    if dpi:
        lines.append(f"DPI (если указано): {dpi}")
    lines.append(f"Формат файла: {fmt}")
    lines.append(f"Цветовая модель (mode): {mode} — {MODE_HUMAN.get(mode, 'неизвестная/редкая')}")
    if bpp:
        lines.append(f"Глубина цвета (общая): {bpp} бит/пикс")
    lines.append(f"Каналы: {bands}")
    if approx_mem is not None:
        lines.append(f"Оценка памяти при разжатии: {human_size(approx_mem)}")
    if n_frames > 1:
        lines.append(f"Кадров (анимация/мультистраница): {n_frames}")
    lines.append(f"Альфа-канал: {'да' if has_alpha else 'нет'}")
    lines.append(f"ICC-профиль: {'есть (' + str(icc_len) + ' байт)' if icc_len else 'нет/не указан'}")
    lines.append("")
    lines.append("EXIF:")
    lines.extend(f"  • {s}" for s in exif_lines)
    return "\n".join(lines)
