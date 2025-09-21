from __future__ import annotations
import tkinter as tk
from PIL import Image, ImageTk

class ImageCanvas(tk.Frame):
    """Виджет отображения изображения"""
    def __init__(self, master, *, bg="#111", min_zoom=0.1, max_zoom=8.0, step=1.1):
        super().__init__(master, bg=bg)
        self._label = tk.Label(self, bg=bg)
        self._label.pack(expand=True, fill=tk.BOTH)

        self._pil_image: Image.Image | None = None
        self._tk_image: ImageTk.PhotoImage | None = None

        self.min_zoom = float(min_zoom)
        self.max_zoom = float(max_zoom)
        self.step = float(step)
        self.zoom = 1.0

        self._on_zoom_cb = None

        # зум только над картинкой
        self._label.bind("<MouseWheel>", self._on_mousewheel)
        self._label.bind("<Double-Button-1>", lambda e: self.reset_zoom())

    # внешний код реагирует на изменение масштаба
    def set_on_zoom(self, cb):
        self._on_zoom_cb = cb

    def set_image(self, img: Image.Image | None):
        self._pil_image = img
        self.refresh()

    def set_zoom(self, z: float):
        self.zoom = max(self.min_zoom, min(self.max_zoom, float(z)))
        self.refresh()
        if self._on_zoom_cb:
            self._on_zoom_cb(self.zoom)

    def reset_zoom(self):
        self.set_zoom(1.0)

    def _on_mousewheel(self, event):
        self._apply_zoom(+1 if event.delta > 0 else -1)

    def _apply_zoom(self, direction: int):
        factor = self.step if direction > 0 else (1.0 / self.step)
        self.set_zoom(self.zoom * factor)

    def refresh(self):
        if self._pil_image is None:
            self._label.config(image="")
            self._tk_image = None
            return
        w, h = self._pil_image.size
        tw = max(1, int(w * self.zoom))
        th = max(1, int(h * self.zoom))
        img = self._pil_image.resize((tw, th), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(img)
        self._label.config(image=self._tk_image)
