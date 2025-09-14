# mvp_viewer.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ExifTags

# --- вспомогательные таблицы и функции ---
BITS_PER_PIXEL = {
    "1": 1, "L": 8, "P": 8,
    "LA": 16, "RGB": 24, "RGBA": 32, "RGBa": 32,
    "CMYK": 32, "YCbCr": 24,
    "I;16": 16, "I": 32, "F": 32
}

MODE_HUMAN = {
    "1": "Бинарное (1 бит)",
    "L": "Оттенки серого (8 бит)",
    "P": "Индексированное (палитра)",
    "LA": "Серое + альфа",
    "RGB": "Цветное (RGB)",
    "RGBA": "Цветное (RGB + альфа)",
    "RGBa": "Цветное (RGB + премультипл. альфа)",
    "CMYK": "Печать (CMYK)",
    "YCbCr": "Видео (YCbCr)",
    "I;16": "16-бит целочисленное",
    "I": "32-бит целочисленное",
    "F": "32-бит float"
}

def human_size(n):
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.2f} {units[i]}"

def exif_dict(img):
    try:
        exif = img.getexif()
        if not exif:
            return {}
        return {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
    except Exception:
        return {}

def pick_exif_fields(ed):
    keys = [
        "DateTimeOriginal", "DateTime", "CreateDate",
        "Make", "Model", "LensModel",
        "ExposureTime", "FNumber", "ISOSpeedRatings", "PhotographicSensitivity",
        "FocalLength", "Orientation", "Software",
    ]
    out = []
    for k in keys:
        if k in ed:
            v = ed[k]
            if isinstance(v, bytes):
                try:
                    v = v.decode(errors="ignore")
                except Exception:
                    v = str(v)
            out.append(f"{k}: {v}")
    if len(out) < 5 and ed:
        for k, v in ed.items():
            if k in ("GPSInfo",) or any(s.startswith(f"{k}:") for s in out):
                continue
            out.append(f"{k}: {v}")
            if len(out) >= 5:
                break
    return out

# --- приложение ---
class ImageViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MVP: Просмотр + сведения")
        self.geometry("1100x700")
        self._pil_image = None
        self._tk_image = None
        self._path = None

        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 8.0
        self._zoom_step = 1.1

        # Верхняя панель
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)
        tk.Button(top, text="Открыть изображение…", command=self.open_image).pack(side=tk.LEFT)

        # Разделитель: слева картинка, справа инфо+кнопки
        self._paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self._paned.pack(expand=True, fill=tk.BOTH)

        # Левая панель (картинка)
        self.left = tk.Frame(self._paned, width=800, height=600)  # шире по умолчанию
        self._paned.add(self.left, minsize=480)  # не давать слишком сжимать
        self.image_label = tk.Label(self.left, bg="#111")
        self.image_label.pack(expand=True, fill=tk.BOTH)

        # Правая панель (сведения + управление)
        right = tk.Frame(self._paned)
        self._paned.add(right, minsize=300)

        # Сведения (со скроллом)
        self.info_text = tk.Text(right, wrap="word", height=10, state="disabled")
        scroll = tk.Scrollbar(right, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scroll.set)
        self.info_text.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Панель управления внизу справа
        controls = tk.Frame(right)
        controls.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=6)
        self.gray_btn = tk.Button(controls, text="В градации серого", command=self.to_grayscale, state="disabled")
        self.gray_btn.pack(side=tk.LEFT)

        # --- ВАЖНО: зум привязан ТОЛЬКО к области картинки ---
        self.image_label.bind("<MouseWheel>", self._on_mousewheel)          # Windows/macOS
        self.image_label.bind("<Button-4>", lambda e: self._apply_zoom_step(+1))  # Linux
        self.image_label.bind("<Button-5>", lambda e: self._apply_zoom_step(-1))  # Linux
        self.image_label.bind("<Double-Button-1>", lambda e: self._reset_zoom())

        # Изначально «толстая» левая панель: ставим разделитель на ~70% ширины
        self.after(50, self._init_sash_wide_left)

    def _init_sash_wide_left(self):
        try:
            self.update_idletasks()
            w = self._paned.winfo_width()
            x = int(w * 0.70)
            self._paned.sash_place(0, x, 1)
        except Exception:
            pass

    # --- загрузка ---
    def open_image(self):
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp *.ppm *.pgm *.pnm"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self._pil_image = Image.open(path)
            self._path = path
            self._zoom = 1.0
            self._render_zoomed()
            self._show_info()
            self.gray_btn.config(state="normal")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

    # --- зум (только над картинкой) ---
    def _on_mousewheel(self, event):
        if self._pil_image is None:
            return
        direction = 1 if event.delta > 0 else -1
        self._apply_zoom_step(direction)

    def _apply_zoom_step(self, direction):
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
        w, h = self._pil_image.size
        tw = max(1, int(w * self._zoom))
        th = max(1, int(h * self._zoom))
        img = self._pil_image.resize((tw, th), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(img)
        self.image_label.config(image=self._tk_image)
        self.title(f"MVP: Просмотр + сведения — {self._zoom:.2f}x")

    # --- кнопки преобразований ---
    def to_grayscale(self):
        if self._pil_image is None:
            return
        try:
            self._pil_image = self._pil_image.convert("L")
            self._render_zoomed()
            self._show_info()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось преобразовать в оттенки серого:\n{e}")

    # --- сводка о текущем изображении ---
    def _show_info(self):
        img = self._pil_image
        path = self._path
        file_size = os.path.getsize(path) if path and os.path.exists(path) else 0
        w, h = img.size
        fmt = img.format or os.path.splitext(path)[1].upper().lstrip(".")
        mode = img.mode
        bpp = BITS_PER_PIXEL.get(mode)
        bands = ",".join(img.getbands())

        # DPI
        dpi = None
        if isinstance(img.info.get("dpi"), (tuple, list)) and img.info.get("dpi"):
            dpi = img.info.get("dpi")
        elif "resolution" in img.info:
            dpi = img.info.get("resolution")

        # Прочее
        n_frames = getattr(img, "n_frames", 1)
        has_alpha = "A" in bands
        icc_len = len(img.info["icc_profile"]) if img.info.get("icc_profile") else 0
        approx_mem = int(w * h * bpp // 8) if bpp else None

        # EXIF (у временных преобразований может отсутствовать — это ок)
        ed = exif_dict(img)
        exif_lines = pick_exif_fields(ed)
        if not exif_lines:
            exif_lines = ["не обнаружен"]

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
        lines.append("")  # пустая строка
        lines.append("EXIF:")
        lines.extend(f"  • {s}" for s in exif_lines)

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.configure(state="disabled")

if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
