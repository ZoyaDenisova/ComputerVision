# imgviewer/model.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from PIL import Image

@dataclass
class Model:
    current: Optional[Image.Image] = None
    original: Optional[Image.Image] = None
    path: Optional[str] = None
    exif_bytes: Optional[bytes] = None
    icc_profile: Optional[bytes] = None
    history: List[Image.Image] = field(default_factory=list)

    # для «показать оригинал (удерж.)»
    preview_saved: Optional[Image.Image] = None
    preview_active: bool = False
