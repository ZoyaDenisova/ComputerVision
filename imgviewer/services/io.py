# imgviewer/services/io.py
from __future__ import annotations
import os
from typing import Optional, Tuple
from PIL import Image

def open_image(path: str) -> Tuple[Image.Image, Optional[bytes], Optional[bytes]]:
    """Открыть изображение и вернуть (img, exif_bytes, icc_profile)."""
    img = Image.open(path)
    exif_bytes = img.info.get("exif")
    if not exif_bytes:
        try:
            exif_bytes = img.getexif().tobytes()
        except Exception:
            exif_bytes = None
    icc_profile = img.info.get("icc_profile")
    return img, exif_bytes, icc_profile

def save_image(path: str, img: Image.Image, *, exif_bytes: Optional[bytes] = None,
               icc_profile: Optional[bytes] = None) -> None:
    """Сохранить файл с попыткой протащить EXIF/ICC, где уместно."""
    ext = os.path.splitext(path)[1].lower()
    save_img = img
    if ext in (".jpg", ".jpeg") and save_img.mode not in ("L", "RGB"):
        save_img = save_img.convert("RGB")
    params = {}
    if exif_bytes and ext in (".jpg", ".jpeg", ".tif", ".tiff"):
        params["exif"] = exif_bytes
    if icc_profile:
        params["icc_profile"] = icc_profile
    save_img.save(path, **params)
