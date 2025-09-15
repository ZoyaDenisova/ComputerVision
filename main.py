# mvp_viewer.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ExifTags, ImageEnhance
from tkinter import simpledialog
from imgviewer.services import transforms as Sx, metadata as Smeta, histogram as Shist, io as Sio
from imgviewer.ui import ImageCanvas, HistogramPanel, InfoPanel, ToolsPanel


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

        # Поле изображения (виджет с собственным зумом)
        self.image_canvas = ImageCanvas(self.left, bg="#111", min_zoom=0.1, max_zoom=8.0, step=1.1)
        self.image_canvas.pack(expand=True, fill=tk.BOTH)
        self.image_canvas.set_on_zoom(lambda z: self.title(f"MVP: Просмотр + сведения — {z:.2f}x"))

        # Правая панель (гистограмма + инфо + модификаторы)
        right = tk.Frame(self._paned)
        self._paned.add(right, minsize=360)

        # === Правая часть теперь сама панель с вертикальным разделителем (инфо | кнопки) ===
        self._right_paned = tk.PanedWindow(right, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        self._right_paned.pack(expand=True, fill=tk.BOTH)

        # ---- Верхняя панель: гистограмма + инфо ----
        info_pane = tk.Frame(self._right_paned)
        self._right_paned.add(info_pane, minsize=240)

        self.hist_panel = HistogramPanel(info_pane)
        self.hist_panel.pack(side=tk.TOP, fill=tk.X)
        self.hist_panel.set_provider(self._images_provider)
        self.info_panel = InfoPanel(info_pane)
        self.info_panel.pack(side=tk.TOP, expand=True, fill=tk.BOTH)

        # ---- Нижняя панель: прокручиваемые модификаторы ----
        mods_pane = tk.Frame(self._right_paned)
        self._right_paned.add(mods_pane, minsize=140)

        self.tools_panel = ToolsPanel(mods_pane)
        self.tools_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # колбэки модификаторов
        self.tools_panel.set_callbacks({
            "grayscale": self.to_grayscale,
            "adjust": self.open_adjust_dialog,
            "bw": self.open_bw_dialog,
            "rot90cw": self.rotate_90_cw,
            "rot90ccw": self.rotate_90_ccw,
            "rot_custom": self.rotate_custom,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
        })

        # Инициализация позиций «сашей»: левая панель уже есть; добавим и для правой вертикальной
        self.after(60, self._init_right_vertical_sash)

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

    def _init_right_vertical_sash(self):
        try:
            self.update_idletasks()
            h = self._right_paned.winfo_height()
            y = int(h * 0.66)  # ~ верх (гистограмма+инфо) 2/3, низ (кнопки) 1/3
            self._right_paned.sash_place(0, 1, y)
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
            img, exif_bytes, icc_profile = Sio.open_image(path)
            self._orig_exif_bytes = exif_bytes
            self._orig_icc_profile = icc_profile

            self._orig_image = img.copy()
            self._pil_image = img
            self._path = path
            self._history.clear()
            self._zoom = 1.0

            self._render_zoomed()
            self._show_info()
            self.hist_panel.redraw()
            self._update_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

    # --- кнопки доступности ---
    def _update_buttons(self):
        has_img = self._pil_image is not None
        self.tools_panel.set_image_loaded(has_img)
        self.save_btn.config(state="normal" if has_img else "disabled")
        self.orig_btn.config(state="normal" if has_img else "disabled")
        self.undo_btn.config(state="normal" if (has_img and len(self._history) > 0) else "disabled")
        can_reset = has_img and (self._orig_image is not None) and (self._pil_image is not self._orig_image or len(self._history) > 0)
        self.reset_btn.config(state="normal" if can_reset else "disabled")

    def _render_zoomed(self):
        if self._pil_image is None:
            return
        self.image_canvas.set_image(self._pil_image)
        # обновим заголовок под текущий зум виджета
        self.title(f"MVP: Просмотр + сведения — {self.image_canvas.zoom:.2f}x")

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
            self.hist_panel.redraw()
            self._update_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось применить преобразование:\n{e}")

    def to_grayscale(self):
        self._apply_and_push(lambda im: Sx.to_grayscale(im))

    def apply_bsc(self, bright, sat, contr):
        self._apply_and_push(lambda im: Sx.adjust_bsc(im, bright, sat, contr))

    def undo_last(self):
        if not self._history:
            return
        self._pil_image = self._history.pop()
        self._render_zoomed()
        self._show_info()
        self.hist_panel.redraw()
        self._update_buttons()

    def reset_all(self):
        if self._orig_image is None:
            return
        self._history.clear()
        self._pil_image = self._orig_image
        self._render_zoomed()
        self._show_info()
        self.hist_panel.redraw()
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
        self.hist_panel.redraw()

    def _preview_orig_release(self, _event=None):
        if not self._previewing:
            return
        self._pil_image = self._saved_for_preview
        self._saved_for_preview = None
        self._previewing = False
        self._render_zoomed()
        self._show_info()
        self.hist_panel.redraw()

    # --- сводка о текущем изображении ---
    def _show_info(self):
        if self._pil_image is None:
            return
        text = Smeta.describe(self._pil_image, path=self._path, icc_profile=self._orig_icc_profile)
        self.info_panel.set_text(text)

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
        # БЫЛО: куча логики с ext = os.path.splitext(path)[1].lower  и save_img.save(...)
        # СТАЛО:
        try:
            Sio.save_image(
                path,
                self._pil_image,
                exif_bytes=self._orig_exif_bytes,
                icc_profile=self._orig_icc_profile,
            )
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

        # «базовое» состояние для предпросмотра (что показывалось до открытия)
        before = self._pil_image

        def make_scale(parent, text, row, init=1.0):
            tk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.DoubleVar(value=init)
            scale = tk.Scale(parent, from_=0.0, to=2.0, resolution=0.01, orient=tk.HORIZONTAL,
                             length=280, variable=var)
            scale.grid(row=row, column=1, padx=6, pady=4)
            return var

        frm = tk.Frame(win)
        frm.pack(padx=10, pady=10)
        v_b = make_scale(frm, "Яркость", 0, 1.0)
        v_s = make_scale(frm, "Насыщенность", 1, 1.0)
        v_c = make_scale(frm, "Контраст", 2, 1.0)

        preview_var = tk.BooleanVar(value=True)

        def render_preview(*_):
            if not tk.Toplevel.winfo_exists(win):
                return
            if preview_var.get():
                self._pil_image = Sx.adjust_bsc(before, v_b.get(), v_s.get(), v_c.get())
            else:
                self._pil_image = before
            self._render_zoomed()
            self._show_info()
            self.hist_panel.redraw()

        # бинды на слайдеры — живой предпросмотр
        for var in (v_b, v_s, v_c):
            var.trace_add("write", render_preview)

        btns = tk.Frame(win)
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Checkbutton(btns, text="Предпросмотр", variable=preview_var, command=render_preview) \
            .pack(side=tk.LEFT)

        def on_apply():
            # возвращаем исходное до предпросмотра и применяем как одну операцию
            self._pil_image = before
            self.apply_bsc(v_b.get(), v_s.get(), v_c.get())
            win.destroy()

        def on_reset_vals():
            v_b.set(1.0);
            v_s.set(1.0);
            v_c.set(1.0)

        def on_cancel():
            # откат предпросмотра
            self._pil_image = before
            self._render_zoomed();
            self._show_info();
            self.hist_panel.redraw()
            win.destroy()

        tk.Button(btns, text="Применить", command=on_apply).pack(side=tk.RIGHT)
        tk.Button(btns, text="Сбросить значения", command=on_reset_vals).pack(side=tk.RIGHT, padx=6)
        tk.Button(btns, text="Отмена", command=on_cancel).pack(side=tk.RIGHT, padx=6)

        win.protocol("WM_DELETE_WINDOW", on_cancel)
        render_preview()  # начальный предпросмотр

    def open_bw_dialog(self):
        if self._pil_image is None:
            return
        # разрешим открывать один такой диалог
        if hasattr(self, "_bw_win") and self._bw_win and tk.Toplevel.winfo_exists(self._bw_win):
            self._bw_win.lift()
            return

        win = tk.Toplevel(self)
        win.title("Коррекция Ч/Б: уровни и гамма")
        win.resizable(False, False)
        self._bw_win = win

        # то, что было на экране до открытия диалога
        before = self._pil_image
        # базовая картинка для расчетов: приводим к L (если уже L — не трогаем)
        base_L = before if before.mode == "L" else before.convert("L")

        # элементы управления
        frm = tk.Frame(win);
        frm.pack(padx=10, pady=10)

        def make_int_scale(label, row, frm, a, b, init):
            tk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.IntVar(value=init)
            sc = tk.Scale(frm, from_=a, to=b, resolution=1, orient=tk.HORIZONTAL, length=280, variable=var)
            sc.grid(row=row, column=1, padx=6, pady=4)
            return var

        v_black = make_int_scale("Чёрная точка", 0, frm, 0, 255, 0)
        v_white = make_int_scale("Белая точка", 1, frm, 0, 255, 255)
        tk.Label(frm, text="Гамма").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        v_gamma = tk.DoubleVar(value=1.0)
        sc_gamma = tk.Scale(frm, from_=0.10, to=5.00, resolution=0.01, orient=tk.HORIZONTAL, length=280,
                            variable=v_gamma)
        sc_gamma.grid(row=2, column=1, padx=6, pady=4)

        preview_var = tk.BooleanVar(value=True)

        def render_preview(*_):
            if not tk.Toplevel.winfo_exists(win):
                return
            if preview_var.get():
                # base_L уже L — но bw_levels нормально работает и с L, и с RGB
                self._pil_image = Sx.bw_levels(base_L, v_black.get(), v_white.get(), v_gamma.get())
            else:
                self._pil_image = before
            self._render_zoomed();
            self._show_info();
            self.hist_panel.redraw()

        for var in (v_black, v_white, v_gamma):
            var.trace_add("write", render_preview)

        btns = tk.Frame(win);
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Checkbutton(btns, text="Предпросмотр", variable=preview_var, command=render_preview) \
            .pack(side=tk.LEFT)

        def on_apply():
            # возвращаем исходное «до предпросмотра» и применяем как одну операцию
            self._pil_image = before
            self.apply_bw_levels(v_black.get(), v_white.get(), v_gamma.get())
            win.destroy()

        def on_cancel():
            self._pil_image = before
            self._render_zoomed();
            self._show_info();
            self.hist_panel.redraw()
            win.destroy()

        tk.Button(btns, text="Применить", command=on_apply).pack(side=tk.RIGHT)
        tk.Button(btns, text="Отмена", command=on_cancel).pack(side=tk.RIGHT, padx=6)

        win.protocol("WM_DELETE_WINDOW", on_cancel)
        render_preview()  # стартовый предпросмотр

    def apply_bw_levels(self, black, white, gamma):
        self._apply_and_push(lambda im: Sx.bw_levels(im, black, white, gamma))

    def rotate_90_cw(self):
        self._apply_and_push(lambda im: Sx.rotate_90_cw(im))

    def rotate_90_ccw(self):
        self._apply_and_push(lambda im: Sx.rotate_90_ccw(im))

    def rotate_custom(self):
        if self._pil_image is None:
            return
        angle = simpledialog.askfloat("Поворот", "Угол (в градусах, по часовой стрелке):",
                                      minvalue=-360.0, maxvalue=360.0)
        if angle is None:
            return
        self._apply_and_push(lambda im: Sx.rotate(im, angle))

    def flip_h(self):
        self._apply_and_push(lambda im: Sx.flip_h(im))

    def flip_v(self):
        self._apply_and_push(lambda im: Sx.flip_v(im))

    # --- построение гистограммы (matplotlib) ---
    def _images_provider(self, kind: str):
        if kind == "original" and self._orig_image is not None:
            return self._orig_image
        if kind == "previous" and self._history:
            return self._history[-1]
        return self._pil_image


# --- запуск ---
if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
