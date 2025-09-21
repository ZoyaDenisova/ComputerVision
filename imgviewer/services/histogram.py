from __future__ import annotations

from typing import List, Optional, TypedDict, Literal
from PIL import Image

class HistogramData(TypedDict):
    mode: Literal["L", "RGB"]
    L: Optional[List[int]]
    R: Optional[List[int]]
    G: Optional[List[int]]
    B: Optional[List[int]]

__all__ = ["HistogramData", "histogram_data"]

def _hist256(h: List[int]) -> List[int]:
    n = len(h)
    if n == 256:
        return h
    if n < 256:
        return h + [0] * (256 - n)

    bins = [0] * 256
    ratio = n / 256.0
    for i, count in enumerate(h):
        j = int(i / ratio)
        if j >= 256:
            j = 255
        bins[j] += count
    return bins


def histogram_data(img: Image.Image) -> HistogramData:
    if img.mode == "L":
        return {
            "mode": "L",
            "L": _hist256(img.histogram()),
            "R": None,
            "G": None,
            "B": None,
        }

    rgb = img.convert("RGB")
    r = _hist256(rgb.getchannel("R").histogram())
    g = _hist256(rgb.getchannel("G").histogram())
    b = _hist256(rgb.getchannel("B").histogram())

    return {
        "mode": "RGB",
        "L": None,
        "R": r,
        "G": g,
        "B": b,
    }
