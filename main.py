# mvp_viewer.py
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

class ImageViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MVP: Загрузка и отображение изображения")
        self.geometry("800x600")
        self._pil_image = None   # исходный объект Pillow
        self._tk_image = None    # ссылка на ImageTk для предотвращения GC

        self._zoom = 1.0  # текущий зум
        self._min_zoom = 0.1
        self._max_zoom = 8.0
        self._zoom_step = 1.1  # множитель за один щелчок колесика

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(top, text="Открыть изображение…", command=self.open_image).pack(side=tk.LEFT)

        # Контейнер для картинки
        self.image_label = tk.Label(self, bg="#111")
        self.image_label.pack(expand=True, fill=tk.BOTH)

        for widget in (self, self.image_label):
            widget.bind("<MouseWheel>", self._on_mousewheel)  # Windows / macOS

        # Сброс зума двойным кликом
        self.image_label.bind("<Double-Button-1>", lambda e: self._reset_zoom())

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self._pil_image = Image.open(path)
            self._zoom = 1.0
            self._render_zoomed()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

# === Зум ===

    def _on_mousewheel(self, event):
        """Windows/macOS: event.delta = ±120 (обычно)."""
        if self._pil_image is None:
            return
        direction = 1 if event.delta > 0 else -1
        self._apply_zoom_step(direction)

    def _apply_zoom_step(self, direction):
        """direction: +1 — увеличить, -1 — уменьшить."""
        factor = self._zoom_step if direction > 0 else (1 / self._zoom_step)
        new_zoom = max(self._min_zoom, min(self._max_zoom, self._zoom * factor))
        if abs(new_zoom - self._zoom) > 1e-6:
            self._zoom = new_zoom
            self._render_zoomed()

    def _reset_zoom(self):
        if self._pil_image is None:
            return
        self._zoom = 1.0
        self._render_zoomed()

    def _render_zoomed(self):
        """Пересчитывает изображение под текущий self._zoom и отображает в Label."""
        # Размеры исходника
        w, h = self._pil_image.size

        # Желаемый размер с учётом зума
        target_w = max(1, int(w * self._zoom))
        target_h = max(1, int(h * self._zoom))

        # Меняем размер с хорошей интерполяцией
        img = self._pil_image.resize((target_w, target_h), Image.LANCZOS)

        # В Tk
        self._tk_image = ImageTk.PhotoImage(img)
        self.image_label.config(image=self._tk_image)

        # Показать текущий зум в заголовке
        self.title(f"MVP: Загрузка и отображение изображения — {self._zoom:.2f}x")


if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
