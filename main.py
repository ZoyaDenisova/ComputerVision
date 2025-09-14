# mvp_viewer.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ExifTags, ImageEnhance

# matplotlib для гистограмм в Tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

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
        self.geometry("1200x750")

        # состояния
        self._pil_image = None
        self._orig_image = None
        self._tk_image = None
        self._path = None
        self._history = []
        self._previewing = False
        self._saved_for_preview = None

        # метаданные исходника (для сохранения)
        self._orig_exif_bytes = None
        self._orig_icc_profile = None

        # зум
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 8.0
        self._zoom_step = 1.1

        # Верхняя панель
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)
        tk.Button(top, text="Открыть изображение…", command=self.open_image).pack(side=tk.LEFT)

        # Разделитель: слева картинка (+кнопки), справа гистограмма + инфо + модификаторы
        self._paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self._paned.pack(expand=True, fill=tk.BOTH)

        # Левая панель (картинка) — шире по умолчанию
        self.left = tk.Frame(self._paned, width=860, height=640)
        self._paned.add(self.left, minsize=520)

        # Кнопки под изображением
        self.image_controls = tk.Frame(self.left)
        self.image_controls.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=6)

        self.undo_btn = tk.Button(self.image_controls, text="Отменить", command=self.undo_last, state="disabled")
        self.undo_btn.pack(side=tk.LEFT, padx=(0,6))
        self.orig_btn = tk.Button(self.image_controls, text="Оригинал (удерж.)", state="disabled")
        self.orig_btn.pack(side=tk.LEFT, padx=(0,6))
        self.orig_btn.bind("<ButtonPress-1>", self._preview_orig_press)
        self.orig_btn.bind("<ButtonRelease-1>", self._preview_orig_release)
        self.reset_btn = tk.Button(self.image_controls, text="Сбросить всё", command=self.reset_all, state="disabled")
        self.reset_btn.pack(side=tk.LEFT, padx=(0,6))
        self.save_btn = tk.Button(self.image_controls, text="Сохранить как…", command=self.save_as, state="disabled")
        self.save_btn.pack(side=tk.LEFT, padx=(0,6))

        # Поле изображения
        self.image_label = tk.Label(self.left, bg="#111")
        self.image_label.pack(expand=True, fill=tk.BOTH)

        # Правая панель (гистограмма + инфо + модификаторы)
        right = tk.Frame(self._paned)
        self._paned.add(right, minsize=360)

        # --- Гистограмма (контролы + canvas) ---
        hist_ctrls = tk.Frame(right)
        hist_ctrls.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8,4))

        tk.Label(hist_ctrls, text="Гистограмма:").grid(row=0, column=0, sticky="w")
        self._hist_variant = tk.StringVar(value="current")
        rb_frame = tk.Frame(hist_ctrls)
        rb_frame.grid(row=0, column=1, sticky="w")
        for val, txt in (("original", "Оригинал"), ("current", "Текущая"), ("previous", "Предыдущая")):
            tk.Radiobutton(rb_frame, text=txt, variable=self._hist_variant, value=val,
                           command=self._draw_histogram).pack(side=tk.LEFT, padx=(0,8))

        tk.Label(hist_ctrls, text="Каналы:").grid(row=1, column=0, sticky="w", pady=(4,0))
        ch_frame = tk.Frame(hist_ctrls)
        ch_frame.grid(row=1, column=1, sticky="w", pady=(4,0))
        self._ch_r = tk.BooleanVar(value=True)
        self._ch_g = tk.BooleanVar(value=True)
        self._ch_b = tk.BooleanVar(value=True)
        for var, name in ((self._ch_r, "R"), (self._ch_g, "G"), (self._ch_b, "B")):
            var.trace_add("write", lambda *_: self._draw_histogram())
            tk.Checkbutton(ch_frame, text=name, variable=var).pack(side=tk.LEFT)

        # matplotlib Figure в Tk
        self._hist_fig = Figure(figsize=(5.8, 2.6), dpi=100)
        self._hist_ax = self._hist_fig.add_subplot(111)
        self._hist_canvas = FigureCanvasTkAgg(self._hist_fig, master=right)
        self._hist_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.X, padx=8, pady=(4,8))

        # --- Сведения (со скроллом) ---
        info_wrap = tk.Frame(right)
        info_wrap.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        self.info_text = tk.Text(info_wrap, wrap="word", height=10, state="disabled")
        scroll = tk.Scrollbar(info_wrap, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scroll.set)
        self.info_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Модификаторы (столбик под инфо) ---
        mods = tk.Frame(right)
        mods.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)
        self.gray_btn = tk.Button(mods, text="В градации серого", command=self.to_grayscale, state="disabled")
        self.gray_btn.pack(fill=tk.X, pady=(0,6))
        self.adjust_btn = tk.Button(mods, text="Коррекция…", command=self.open_adjust_dialog, state="disabled")
        self.adjust_btn.pack(fill=tk.X)

        # --- Зум только над картинкой ---
        self.image_label.bind("<MouseWheel>", self._on_mousewheel)               # Windows/macOS
        self.image_label.bind("<Button-4>", lambda e: self._apply_zoom_step(+1)) # Linux
        self.image_label.bind("<Button-5>", lambda e: self._apply_zoom_step(-1)) # Linux
        self.image_label.bind("<Double-Button-1>", lambda e: self._reset_zoom())

        # Диалог коррекции — лениво создаём
        self._adj_win = None

        # Изначально «толстая» левая панель: ~70%
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
            img = Image.open(path)

            # сохранить исходные метаданные
            exif_bytes = img.info.get("exif")
            if not exif_bytes:
                try:
                    exif_bytes = img.getexif().tobytes()
                except Exception:
                    exif_bytes = None
            self._orig_exif_bytes = exif_bytes
            self._orig_icc_profile = img.info.get("icc_profile")

            self._orig_image = img.copy()
            self._pil_image = img
            self._path = path
            self._history.clear()
            self._zoom = 1.0

            self._render_zoomed()
            self._show_info()
            self._draw_histogram()
            self._update_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

    # --- кнопки доступности ---
    def _update_buttons(self):
        has_img = self._pil_image is not None
        self.gray_btn.config(state="normal" if has_img else "disabled")
        self.adjust_btn.config(state="normal" if has_img else "disabled")
        self.save_btn.config(state="normal" if has_img else "disabled")
        self.orig_btn.config(state="normal" if has_img else "disabled")
        self.undo_btn.config(state="normal" if (has_img and len(self._history) > 0) else "disabled")
        can_reset = has_img and (self._orig_image is not None) and (self._pil_image is not self._orig_image or len(self._history) > 0)
        self.reset_btn.config(state="normal" if can_reset else "disabled")

    # --- зум ---
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

    # --- операции и история ---
    def _apply_and_push(self, transform_fn):
        if self._pil_image is None:
            return
        try:
            prev = self._pil_image
            new_im = transform_fn(prev)
            if new_im is None:
                return
            self._history.append(prev)
            self._pil_image = new_im
            self._render_zoomed()
            self._show_info()
            self._draw_histogram()
            self._update_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось применить преобразование:\n{e}")

    def to_grayscale(self):
        self._apply_and_push(lambda im: im.convert("L"))

    def apply_bsc(self, bright, sat, contr):
        def _do(im):
            out = ImageEnhance.Brightness(im).enhance(bright)
            out = ImageEnhance.Color(out).enhance(sat)
            out = ImageEnhance.Contrast(out).enhance(contr)
            return out
        self._apply_and_push(_do)

    def undo_last(self):
        if not self._history:
            return
        self._pil_image = self._history.pop()
        self._render_zoomed()
        self._show_info()
        self._draw_histogram()
        self._update_buttons()

    def reset_all(self):
        if self._orig_image is None:
            return
        self._history.clear()
        self._pil_image = self._orig_image
        self._render_zoomed()
        self._show_info()
        self._draw_histogram()
        self._update_buttons()

    # --- предпросмотр оригинала при удержании ---
    def _preview_orig_press(self, _event=None):
        if self._orig_image is None or self._pil_image is None or self._previewing:
            return
        self._previewing = True
        self._saved_for_preview = self._pil_image
        self._pil_image = self._orig_image
        self._render_zoomed()
        self._show_info()
        self._draw_histogram()

    def _preview_orig_release(self, _event=None):
        if not self._previewing:
            return
        self._pil_image = self._saved_for_preview
        self._saved_for_preview = None
        self._previewing = False
        self._render_zoomed()
        self._show_info()
        self._draw_histogram()

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

        dpi = None
        if isinstance(img.info.get("dpi"), (tuple, list)) and img.info.get("dpi"):
            dpi = img.info.get("dpi")
        elif "resolution" in img.info:
            dpi = img.info.get("resolution")

        n_frames = getattr(img, "n_frames", 1)
        has_alpha = "A" in bands
        icc_len = len(img.info["icc_profile"]) if img.info.get("icc_profile") else 0
        approx_mem = int(w * h * bpp // 8) if bpp else None

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
        lines.append("")
        lines.append("EXIF:")
        lines.extend(f"  • {s}" for s in exif_lines)

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.configure(state="disabled")

    # --- сохранение ---
    def save_as(self):
        if self._pil_image is None:
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить как…",
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("BMP", "*.bmp"),
                ("TIFF", "*.tif *.tiff"),
                ("WEBP", "*.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            save_img = self._pil_image
            if ext in (".jpg", ".jpeg") and save_img.mode not in ("L", "RGB"):
                save_img = save_img.convert("RGB")

            params = {}
            if self._orig_exif_bytes and ext in (".jpg", ".jpeg", ".tif", ".tiff"):
                params["exif"] = self._orig_exif_bytes
            if self._orig_icc_profile:
                params["icc_profile"] = self._orig_icc_profile

            save_img.save(path, **params)
            self._path = path
            self._show_info()
            messagebox.showinfo("Готово", f"Файл сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

    # --- диалог коррекции B/S/C ---
    def open_adjust_dialog(self):
        if self._pil_image is None:
            return
        if self._adj_win and tk.Toplevel.winfo_exists(self._adj_win):
            self._adj_win.lift()
            return
        win = tk.Toplevel(self)
        win.title("Коррекция: яркость/насыщенность/контраст")
        win.resizable(False, False)
        self._adj_win = win

        def make_scale(parent, text, row):
            tk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.DoubleVar(value=1.0)
            scale = tk.Scale(parent, from_=0.0, to=2.0, resolution=0.01, orient=tk.HORIZONTAL,
                             length=280, variable=var)
            scale.grid(row=row, column=1, padx=6, pady=4)
            return var

        frm = tk.Frame(win)
        frm.pack(padx=10, pady=10)
        v_b = make_scale(frm, "Яркость", 0)
        v_s = make_scale(frm, "Насыщенность", 1)
        v_c = make_scale(frm, "Контраст", 2)

        btns = tk.Frame(win)
        btns.pack(fill=tk.X, padx=10, pady=(0,10))
        def on_apply():
            self.apply_bsc(v_b.get(), v_s.get(), v_c.get())
            win.destroy()
        tk.Button(btns, text="Применить", command=on_apply).pack(side=tk.LEFT)
        def on_reset():
            v_b.set(1.0); v_s.set(1.0); v_c.set(1.0)
        tk.Button(btns, text="Сбросить значения", command=on_reset).pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="Отмена", command=win.destroy).pack(side=tk.RIGHT)

    # --- построение гистограммы (matplotlib) ---
    def _get_variant_image(self):
        kind = self._hist_variant.get() if hasattr(self, "_hist_variant") else "current"
        if kind == "original" and self._orig_image is not None:
            return self._orig_image
        if kind == "previous" and self._history:
            return self._history[-1]
        return self._pil_image

    def _draw_histogram(self):
        if self._pil_image is None:
            # очистить ось, если нечего рисовать
            self._hist_ax.clear()
            self._hist_canvas.draw_idle()
            return

        img = self._get_variant_image()
        self._hist_ax.clear()

        # режим и гистограммы
        if img.mode == "L":
            hist = img.histogram()[:256]
            xs = list(range(256))
            self._hist_ax.plot(xs, hist, color="gray", linewidth=1, label="L")
            ymax = max(hist) or 1
            # выключаем чекбоксы RGB визуально (но не ломаем логику)
            # (просто игнорируем их состояние для L)
            legend = True
            mode_text = "L"
        else:
            rgb = img.convert("RGB")
            r_hist = rgb.getchannel("R").histogram()[:256]
            g_hist = rgb.getchannel("G").histogram()[:256]
            b_hist = rgb.getchannel("B").histogram()[:256]
            xs = list(range(256))

            show_r = self._ch_r.get()
            show_g = self._ch_g.get()
            show_b = self._ch_b.get()
            if not (show_r or show_g or show_b):
                # если всё снято — включим все, чтобы не было пусто
                self._ch_r.set(True); self._ch_g.set(True); self._ch_b.set(True)
                show_r = show_g = show_b = True

            vals = []
            if show_r: vals += r_hist
            if show_g: vals += g_hist
            if show_b: vals += b_hist
            ymax = max(vals) if vals else 1

            if show_r: self._hist_ax.plot(xs, r_hist, color="red", linewidth=1, label="R")
            if show_g: self._hist_ax.plot(xs, g_hist, color="green", linewidth=1, label="G")
            if show_b: self._hist_ax.plot(xs, b_hist, color="blue", linewidth=1, label="B")
            legend = True
            mode_text = "RGB"

        # оформление осей
        self._hist_ax.set_xlim(0, 255)
        self._hist_ax.set_ylim(0, ymax * 1.05)
        self._hist_ax.set_xlabel("Уровень яркости (0–255)")
        self._hist_ax.set_ylabel("Частота")
        var_map = {"original": "Оригинал", "current": "Текущая", "previous": "Предыдущая"}
        title = var_map.get(self._hist_variant.get(), "Текущая")
        self._hist_ax.set_title(f"{title} — {mode_text}")
        if legend:
            self._hist_ax.legend(loc="upper right", fontsize=8)
        self._hist_ax.grid(False)
        for spine in ("top", "right"):
            self._hist_ax.spines[spine].set_visible(False)

        self._hist_canvas.draw_idle()

# --- запуск ---
if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
