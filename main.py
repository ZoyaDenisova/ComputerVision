# mvp_viewer.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ExifTags, ImageEnhance
from tkinter import simpledialog
from imgviewer.services import transforms as Sx, metadata as Smeta, histogram as Shist, io as Sio
from imgviewer.services.history import History  # стек undo/redo

# matplotlib для гистограмм в Tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


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

        # === Правая часть теперь сама панель с вертикальным разделителем (инфо | кнопки) ===
        self._right_paned = tk.PanedWindow(right, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        self._right_paned.pack(expand=True, fill=tk.BOTH)

        # ---- Верхняя панель: гистограмма + инфо (как одна секция) ----
        info_pane = tk.Frame(self._right_paned)
        self._right_paned.add(info_pane, minsize=240)

        # Гистограмма: контролы
        hist_ctrls = tk.Frame(info_pane)
        hist_ctrls.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(hist_ctrls, text="Гистограмма:").grid(row=0, column=0, sticky="w")
        self._hist_variant = tk.StringVar(value="current")
        rb_frame = tk.Frame(hist_ctrls)
        rb_frame.grid(row=0, column=1, sticky="w")
        for val, txt in (("original", "Оригинал"), ("current", "Текущая"), ("previous", "Предыдущая")):
            tk.Radiobutton(rb_frame, text=txt, variable=self._hist_variant, value=val,
                           command=self._draw_histogram).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(hist_ctrls, text="Каналы:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ch_frame = tk.Frame(hist_ctrls);
        ch_frame.grid(row=1, column=1, sticky="w", pady=(4, 0))
        self._ch_r = tk.BooleanVar(value=True)
        self._ch_g = tk.BooleanVar(value=True)
        self._ch_b = tk.BooleanVar(value=True)
        for var, name in ((self._ch_r, "R"), (self._ch_g, "G"), (self._ch_b, "B")):
            var.trace_add("write", lambda *_: self._draw_histogram())
            tk.Checkbutton(ch_frame, text=name, variable=var).pack(side=tk.LEFT)

        # Гистограмма: matplotlib-канвас
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        self._hist_fig = Figure(figsize=(5.8, 2.6), dpi=100)
        self._hist_ax = self._hist_fig.add_subplot(111)
        self._hist_canvas = FigureCanvasTkAgg(self._hist_fig, master=info_pane)
        self._hist_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.X, padx=8, pady=(4, 8))

        # Инфо (как раньше)
        info_wrap = tk.Frame(info_pane)
        info_wrap.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        self.info_text = tk.Text(info_wrap, wrap="word", height=10, state="disabled")
        scroll = tk.Scrollbar(info_wrap, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scroll.set)
        self.info_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ---- Нижняя панель: Кнопки-модификаторы (прокручиваемая область) ----
        mods_pane = tk.Frame(self._right_paned)
        self._right_paned.add(mods_pane, minsize=140)

        # Canvas + Scrollbar (без bind_all; колесо привяжем по bindtags)
        self._mods_canvas = tk.Canvas(mods_pane, borderwidth=0, highlightthickness=1)
        mods_scroll = tk.Scrollbar(mods_pane, orient="vertical", command=self._mods_canvas.yview)
        self._mods_canvas.configure(yscrollcommand=mods_scroll.set)
        self._mods_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        mods_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 8))

        # Внутренний фрейм с кнопками
        self._mods_inner = tk.Frame(self._mods_canvas)
        self._mods_window = self._mods_canvas.create_window((0, 0), window=self._mods_inner, anchor="nw")

        def _mods_configure(_evt=None):
            # обновить область прокрутки и ширину внутреннего фрейма
            self._mods_canvas.configure(scrollregion=self._mods_canvas.bbox("all"))
            self._mods_canvas.itemconfigure(self._mods_window, width=self._mods_canvas.winfo_width())

        self._mods_inner.bind("<Configure>", _mods_configure)
        self._mods_canvas.bind("<Configure>",
                               lambda e: self._mods_canvas.itemconfigure(self._mods_window, width=e.width))

        # Правильная прокрутка: добавляем пользовательский bindtag всем детям области кнопок
        MODS_TAG = "ModsScroll"
        self.bind_class(MODS_TAG, "<MouseWheel>",
                        lambda e: self._mods_canvas.yview_scroll(-int(e.delta / 120), "units"))
        self.bind_class(MODS_TAG, "<Button-4>", lambda e: self._mods_canvas.yview_scroll(-1, "units"))  # Linux
        self.bind_class(MODS_TAG, "<Button-5>", lambda e: self._mods_canvas.yview_scroll(1, "units"))  # Linux

        def _tag_mods_descendants(widget):
            # вставляем кастомный tag вторым (после индивидуального тега виджета)
            tags = list(widget.bindtags())
            if MODS_TAG not in tags:
                tags.insert(1, MODS_TAG)
                widget.bindtags(tuple(tags))
            for ch in widget.winfo_children():
                _tag_mods_descendants(ch)

        # Кнопки (перенесены сюда) — размещаем внутри self._mods_inner
        self.gray_btn = tk.Button(self._mods_inner, text="В градации серого", command=self.to_grayscale,
                                  state="disabled")
        self.gray_btn.pack(fill=tk.X, pady=(8, 6), padx=8)

        self.adjust_btn = tk.Button(self._mods_inner, text="Коррекция…", command=self.open_adjust_dialog,
                                    state="disabled")
        self.adjust_btn.pack(fill=tk.X, pady=(0, 6), padx=8)

        self.bw_btn = tk.Button(self._mods_inner, text="Коррекция Ч/Б…", command=self.open_bw_dialog, state="disabled")
        self.bw_btn.pack(fill=tk.X, pady=(6, 6), padx=8)

        self.rot90cw_btn = tk.Button(self._mods_inner, text="Повернуть 90°↻", command=self.rotate_90_cw,
                                     state="disabled")
        self.rot90cw_btn.pack(fill=tk.X, pady=(0, 6), padx=8)
        self.rot90ccw_btn = tk.Button(self._mods_inner, text="Повернуть 90°↺", command=self.rotate_90_ccw,
                                      state="disabled")
        self.rot90ccw_btn.pack(fill=tk.X, pady=(0, 6), padx=8)
        self.rot_custom_btn = tk.Button(self._mods_inner, text="Повернуть…", command=self.rotate_custom,
                                        state="disabled")
        self.rot_custom_btn.pack(fill=tk.X, pady=(0, 6), padx=8)
        self.flip_h_btn = tk.Button(self._mods_inner, text="Отразить по горизонтали", command=self.flip_h,
                                    state="disabled")
        self.flip_h_btn.pack(fill=tk.X, pady=(0, 6), padx=8)
        self.flip_v_btn = tk.Button(self._mods_inner, text="Отразить по вертикали", command=self.flip_v,
                                    state="disabled")
        self.flip_v_btn.pack(fill=tk.X, pady=(0, 8), padx=8)

        # Проставляем bindtag всем кнопкам (и, на всякий случай, самому контейнеру)
        _tag_mods_descendants(self._mods_inner)
        _tag_mods_descendants(self._mods_canvas)

        # Инициализация позиций «сашей»: левая панель уже есть; добавим и для правой вертикальной
        self.after(60, self._init_right_vertical_sash)

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
        self.bw_btn.config(state="normal" if has_img else "disabled")
        self.rot90cw_btn.config(state="normal" if has_img else "disabled")
        self.rot90ccw_btn.config(state="normal" if has_img else "disabled")
        self.rot_custom_btn.config(state="normal" if has_img else "disabled")
        self.flip_h_btn.config(state="normal" if has_img else "disabled")
        self.flip_v_btn.config(state="normal" if has_img else "disabled")

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
        self._apply_and_push(lambda im: Sx.to_grayscale(im))

    def apply_bsc(self, bright, sat, contr):
        self._apply_and_push(lambda im: Sx.adjust_bsc(im, bright, sat, contr))

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
        if self._pil_image is None:
            return
        text = Smeta.describe(
            self._pil_image,
            path=self._path,
            icc_profile=self._orig_icc_profile,
        )
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, text)
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
            self._draw_histogram()

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
            self._draw_histogram()
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
            self._draw_histogram()

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
            self._draw_histogram()
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
    def _get_variant_image(self):
        kind = self._hist_variant.get() if hasattr(self, "_hist_variant") else "current"
        if kind == "original" and self._orig_image is not None:
            return self._orig_image
        if kind == "previous" and self._history:
            return self._history[-1]
        return self._pil_image

    def _draw_histogram(self):
        if self._pil_image is None:
            self._hist_ax.clear()
            self._hist_canvas.draw_idle()
            return

        img = self._get_variant_image()
        self._hist_ax.clear()

        data = Shist.histogram_data(img)
        xs = list(range(256))

        if data["mode"] == "L":
            hist = data["L"]
            self._hist_ax.plot(xs, hist, color="gray", linewidth=1, label="L")
            ymax = max(hist) or 1
            mode_text = "L"
        else:
            r, g, b = data["R"], data["G"], data["B"]
            show_r, show_g, show_b = self._ch_r.get(), self._ch_g.get(), self._ch_b.get()
            if not (show_r or show_g or show_b):
                self._ch_r.set(True);
                self._ch_g.set(True);
                self._ch_b.set(True)
                show_r = show_g = show_b = True

            vals = []
            if show_r: vals += r
            if show_g: vals += g
            if show_b: vals += b
            ymax = max(vals) if vals else 1

            if show_r: self._hist_ax.plot(xs, r, color="red", linewidth=1, label="R")
            if show_g: self._hist_ax.plot(xs, g, color="green", linewidth=1, label="G")
            if show_b: self._hist_ax.plot(xs, b, color="blue", linewidth=1, label="B")
            mode_text = "RGB"

        # оформление
        self._hist_ax.set_xlim(0, 255)
        self._hist_ax.set_ylim(0, ymax * 1.05)
        self._hist_ax.set_xlabel("Уровень яркости (0–255)")
        self._hist_ax.set_ylabel("Частота")
        var_map = {"original": "Оригинал", "current": "Текущая", "previous": "Предыдущая"}
        title = var_map.get(self._hist_variant.get(), "Текущая")
        self._hist_ax.set_title(f"{title} — {mode_text}")
        self._hist_ax.legend(loc="upper right", fontsize=8)
        self._hist_ax.grid(False)
        for spine in ("top", "right"):
            self._hist_ax.spines[spine].set_visible(False)

        self._hist_canvas.draw_idle()


# --- запуск ---
if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
