# imgviewer/services/history.py
from __future__ import annotations
from typing import Optional, List
from PIL import Image

class History:
    """Простой стек undo/redo для Pillow-изображений (без копий, на ответственности вызывающего)."""
    def __init__(self, maxlen: int = 100):
        self._undo: List[Image.Image] = []
        self._redo: List[Image.Image] = []
        self.maxlen = maxlen

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, prev: Image.Image) -> None:
        self._undo.append(prev)
        if len(self._undo) > self.maxlen:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, current: Image.Image) -> Optional[Image.Image]:
        if not self._undo:
            return None
        prev = self._undo.pop()
        self._redo.append(current)
        return prev

    def redo(self, current: Image.Image) -> Optional[Image.Image]:
        if not self._redo:
            return None
        nxt = self._redo.pop()
        self._undo.append(current)
        return nxt
