# imgviewer/controller.py
from __future__ import annotations
from typing import Callable, Optional
from PIL import Image
from imgviewer.model import Model
from imgviewer.services import io as Sio, metadata as Smeta, transforms as Sx
from imgviewer.services.history import History

class Controller:
    def __init__(self, model: Model):
        self.m = model

    # ---- файлы ----
    def open_image(self, path: str) -> None:
        img, exif, icc = Sio.open_image(path)
        self.m.original = img.copy()
        self.m.current = img
        self.m.path = path
        self.m.exif_bytes = exif
        self.m.icc_profile = icc
        self.m.history.clear()
        self.m.preview_saved = None
        self.m.preview_active = False

    def save_as(self, path: str) -> None:
        if self.m.current is None:
            return
        Sio.save_image(path, self.m.current, exif_bytes=self.m.exif_bytes, icc_profile=self.m.icc_profile)
        self.m.path = path

    def info_text(self) -> str:
        return "" if self.m.current is None else Smeta.describe(
            self.m.current, path=self.m.path, icc_profile=self.m.icc_profile
        )

    # ---- гистограмма ----
    def hist_image(self, kind: str):
        if kind == "original":
            return self.m.original
        if kind == "previous" and self.m.history and self.m.history.can_undo():
            return self.m.history.peek_undo()
        return self.m.current

    # ---- базовые операции состояния ----
    def has_image(self) -> bool:
        return self.m.current is not None

    def can_undo(self) -> bool:
        return bool(self.m.history and self.m.history.can_undo())

    def can_redo(self) -> bool:
        return bool(self.m.history and self.m.history.can_redo())

    def apply_transform(self, fn):
        if self.m.current is None:
            return False
        new_im = fn(self.m.current)
        if new_im is None:
            return False
        self.m.history.push(self.m.current)   # теперь это вызовет History.push()
        self.m.current = new_im
        return True

    def undo(self) -> bool:
        if self.m.current is None or not self.m.history:
            return False
        prev = self.m.history.undo(self.m.current)
        if prev is None:
            return False
        self.m.current = prev
        return True

    def redo(self) -> bool:
        if self.m.current is None or not self.m.history:
            return False
        nxt = self.m.history.redo(self.m.current)
        if nxt is None:
            return False
        self.m.current = nxt
        return True

    def reset(self) -> bool:
        if self.m.original is None:
            return False
        self.m.history.clear()
        self.m.current = self.m.original
        return True

    # ---- предпросмотры ----
    def set_temp_image(self, img: Image.Image) -> None:
        """Установить временное изображение без записи в историю (для живого предпросмотра)."""
        self.m.current = img

    def preview_original_start(self) -> bool:
        if self.m.original is None or self.m.current is None or self.m.preview_active:
            return False
        self.m.preview_saved = self.m.current
        self.m.current = self.m.original
        self.m.preview_active = True
        return True

    def preview_original_end(self) -> bool:
        if not self.m.preview_active:
            return False
        self.m.current = self.m.preview_saved
        self.m.preview_saved = None
        self.m.preview_active = False
        return True

    # ---- обёртки над трансформациями ----
    def to_grayscale(self) -> bool:
        return self.apply_transform(lambda im: Sx.to_grayscale(im))

    def apply_bsc(self, b: float, s: float, c: float) -> bool:
        return self.apply_transform(lambda im: Sx.adjust_bsc(im, b, s, c))

    def apply_bw_levels(self, black: int, white: int, gamma: float) -> bool:
        return self.apply_transform(lambda im: Sx.bw_levels(im, black, white, gamma))

    def rotate_90_cw(self) -> bool:
        return self.apply_transform(lambda im: Sx.rotate_90_cw(im))

    def rotate_90_ccw(self) -> bool:
        return self.apply_transform(lambda im: Sx.rotate_90_ccw(im))

    def rotate(self, angle_deg: float) -> bool:
        return self.apply_transform(lambda im: Sx.rotate(im, angle_deg))

    def flip_h(self) -> bool:
        return self.apply_transform(lambda im: Sx.flip_h(im))

    def flip_v(self) -> bool:
        return self.apply_transform(lambda im: Sx.flip_v(im))
