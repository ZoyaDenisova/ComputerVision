# imgviewer/services/histogram.py
from __future__ import annotations
from typing import Dict, List, Literal, Optional
from PIL import Image

def histogram_data(img: Image.Image) -> Dict[str, object]:
    """Подготовить данные гистограммы.
    Возвращает:
      {"mode": "L"|"RGB", "L": list|None, "R": list|None, "G": list|None, "B": list|None}
    """
    if img.mode == "L":
        return {"mode": "L", "L": img.histogram()[:256], "R": None, "G": None, "B": None}
    rgb = img.convert("RGB")
    return {
        "mode": "RGB",
        "L": None,
        "R": rgb.getchannel("R").histogram()[:256],
        "G": rgb.getchannel("G").histogram()[:256],
        "B": rgb.getchannel("B").histogram()[:256],
    }
