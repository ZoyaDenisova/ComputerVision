from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
from imgviewer.services.history import History  # <-- добавь это

@dataclass
class Model:
    current: Optional[Image.Image] = None
    original: Optional[Image.Image] = None
    path: Optional[str] = None
    exif_bytes: Optional[bytes] = None
    icc_profile: Optional[bytes] = None
    history: History = field(default_factory=lambda: History(maxlen=100))  # <-- вот так

    # показать оригинал
    preview_saved: Optional[Image.Image] = None
    preview_active: bool = False
