# mvp_viewer.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from imgviewer.model import Model
from imgviewer.controller import Controller
from tkinter import simpledialog
from imgviewer.services import transforms as Sx, metadata as Smeta, histogram as Shist, io as Sio
from imgviewer.ui import ImageCanvas, HistogramPanel, InfoPanel, ToolsPanel
from imgviewer.ui.dialogs.adjust_bsc import AdjustBSCDialog
from imgviewer.ui.dialogs.bw_levels import BWLevelsDialog


# --- приложение ---
class ImageViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MVP: Просмотр + сведения")
        self.geometry("1200x750")

        # модель/контроллер
        self.model = Model()
        self.ctrl = Controller(self.model)

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
            self.ctrl.open_image(path)
            self.image_canvas.reset_zoom()
            self._render_zoomed()
            self._show_info()
            self.hist_panel.redraw()
            self._update_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

    # --- кнопки доступности ---
    def _update_buttons(self):
        has_img = self.ctrl.has_image()
        self.tools_panel.set_image_loaded(has_img)
        self.save_btn.config(state="normal" if has_img else "disabled")
        self.orig_btn.config(state="normal" if has_img else "disabled")
        self.undo_btn.config(state="normal" if (has_img and self.ctrl.can_undo()) else "disabled")
        can_reset = has_img and (
                self.model.original is not None and
                (self.model.current is not self.model.original or self.ctrl.can_undo())
        )
        self.reset_btn.config(state="normal" if can_reset else "disabled")

    def _render_zoomed(self):
        if not self.ctrl.has_image():
            return
        self.image_canvas.set_image(self.model.current)
        self.title(f"MVP: Просмотр + сведения — {self.image_canvas.zoom:.2f}x")

    def _repaint(self):
        """Перерисовать картинку + инфо + гистограмму без тикания кнопок."""
        self._render_zoomed()
        self._show_info()
        self.hist_panel.redraw()

    def _refresh_all(self):
        """Полное обновление после операции."""
        self._repaint()
        self._update_buttons()

    # --- операции и история ---
    def _apply_and_push(self, transform_fn):
        if self.ctrl.apply_transform(transform_fn):
            self._render_zoomed()
            self._show_info()
            self.hist_panel.redraw()
            self._update_buttons()

    def to_grayscale(self):
        if self.ctrl.to_grayscale():
            self._refresh_all()

    def apply_bsc(self, bright, sat, contr):
        if self.ctrl.apply_bsc(bright, sat, contr):
            self._refresh_all()

    def undo_last(self):
        if self.ctrl.undo():
            self._refresh_all()

    def reset_all(self):
        if self.ctrl.reset():
            self._refresh_all()

    # --- предпросмотр оригинала при удержании ---
    def _preview_orig_press(self, _event=None):
        if self.ctrl.preview_original_start():
            self._render_zoomed();
            self._show_info();
            self.hist_panel.redraw()

    def _preview_orig_release(self, _event=None):
        if self.ctrl.preview_original_end():
            self._render_zoomed();
            self._show_info();
            self.hist_panel.redraw()

    # --- сводка о текущем изображении ---
    def _show_info(self):
        self.info_panel.set_text(self.ctrl.info_text())

    # --- сохранение ---
    def save_as(self):
        if not self.ctrl.has_image():
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
            self.ctrl.save_as(path)
            # обновим инфо, т.к. путь изменился
            self._show_info()
            messagebox.showinfo("Готово", f"Файл сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

    # --- диалог коррекции B/S/C ---
    def open_adjust_dialog(self):
        if not self.ctrl.has_image():
            return
        if getattr(self, "_adj_win", None) and tk.Toplevel.winfo_exists(self._adj_win):
            self._adj_win.lift()
            return

        before = self.model.current

        def on_preview(img):
            self.ctrl.set_temp_image(img)
            self._repaint()

        def on_apply(b, s, c):
            # откатываем времёнку и применяем как одну историю
            self.ctrl.set_temp_image(before)
            self.apply_bsc(b, s, c)

        def on_cancel():
            self.ctrl.set_temp_image(before)
            self._repaint()

        self._adj_win = AdjustBSCDialog(self, before, on_preview, on_apply, on_cancel, init=(1.0, 1.0, 1.0))

    def open_bw_dialog(self):
        if not self.ctrl.has_image():
            return
        if getattr(self, "_bw_win", None) and tk.Toplevel.winfo_exists(self._bw_win):
            self._bw_win.lift()
            return

        before = self.model.current

        def on_preview(img):
            self.ctrl.set_temp_image(img)
            self._repaint()

        def on_apply(black, white, gamma):
            self.ctrl.set_temp_image(before)
            self.apply_bw_levels(black, white, gamma)

        def on_cancel():
            self.ctrl.set_temp_image(before)
            self._repaint()

        self._bw_win = BWLevelsDialog(self, before, on_preview, on_apply, on_cancel,
                                      init_black=0, init_white=255, init_gamma=1.0)

    def apply_bw_levels(self, black, white, gamma):
        if self.ctrl.apply_bw_levels(black, white, gamma):
            self._refresh_all()

    def rotate_90_cw(self):
        if self.ctrl.rotate_90_cw():
            self._refresh_all()

    def rotate_90_ccw(self):
        if self.ctrl.rotate_90_ccw():
            self._refresh_all()

    def rotate_custom(self):
        if not self.ctrl.has_image():
            return
        angle = simpledialog.askfloat("Поворот", "Угол (в градусах, по часовой стрелке):",
                                      minvalue=-360.0, maxvalue=360.0)
        if angle is None:
            return
        if self.ctrl.rotate(angle):
            self._refresh_all()

    def flip_h(self):
        if self.ctrl.flip_h():
            self._refresh_all()

    def flip_v(self):
        if self.ctrl.flip_v():
            self._refresh_all()

    # --- построение гистограммы (matplotlib) ---
    def _images_provider(self, kind: str):
        return self.ctrl.hist_image(kind)


# --- запуск ---
if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
