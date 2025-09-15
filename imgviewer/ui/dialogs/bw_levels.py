# imgviewer/ui/dialogs/bw_levels.py
import tkinter as tk
from imgviewer.services import transforms as Sx

class BWLevelsDialog(tk.Toplevel):
    """Диалог уровни/гамма для Ч/Б с предпросмотром через колбэки."""
    def __init__(self, master, before_image, on_preview, on_apply, on_cancel,
                 init_black=0, init_white=255, init_gamma=1.0):
        super().__init__(master)
        self.title("Коррекция Ч/Б: уровни и гамма")
        self.resizable(False, False)

        self._before = before_image
        # база для предпросмотра всегда L
        self._base_L = before_image if before_image.mode == "L" else before_image.convert("L")

        self._on_preview = on_preview      # принимает PIL.Image
        self._on_apply = on_apply          # принимает (black, white, gamma)
        self._on_cancel = on_cancel

        frm = tk.Frame(self); frm.pack(padx=10, pady=10)

        def make_int_scale(label, row, a, b, init):
            tk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.IntVar(value=init)
            sc = tk.Scale(frm, from_=a, to=b, resolution=1, orient=tk.HORIZONTAL, length=280, variable=var)
            sc.grid(row=row, column=1, padx=6, pady=4)
            return var

        self.v_black = make_int_scale("Чёрная точка", 0, 0, 255, init_black)
        self.v_white = make_int_scale("Белая точка", 1, 0, 255, init_white)

        tk.Label(frm, text="Гамма").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.v_gamma = tk.DoubleVar(value=init_gamma)
        tk.Scale(frm, from_=0.10, to=5.00, resolution=0.01, orient=tk.HORIZONTAL, length=280,
                 variable=self.v_gamma).grid(row=2, column=1, padx=6, pady=4)

        self.preview_var = tk.BooleanVar(value=True)

        btns = tk.Frame(self); btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Checkbutton(btns, text="Предпросмотр", variable=self.preview_var, command=self._render_preview) \
            .pack(side=tk.LEFT)

        tk.Button(btns, text="Применить", command=self._apply).pack(side=tk.RIGHT)
        tk.Button(btns, text="Отмена", command=self._cancel).pack(side=tk.RIGHT, padx=6)

        self.protocol("WM_DELETE_WINDOW", self._cancel)

        for var in (self.v_black, self.v_white, self.v_gamma):
            var.trace_add("write", lambda *_: self._render_preview())

        self.after(0, self._render_preview)

    def _current_params(self):
        return (self.v_black.get(), self.v_white.get(), self.v_gamma.get())

    def _render_preview(self):
        if not self.winfo_exists():
            return
        if self.preview_var.get():
            black, white, gamma = self._current_params()
            temp = Sx.bw_levels(self._base_L, black, white, gamma)
            self._on_preview(temp)
        else:
            self._on_preview(self._before)

    def _apply(self):
        self._on_apply(*self._current_params())
        self.destroy()

    def _cancel(self):
        self._on_preview(self._before)
        self._on_cancel()
        self.destroy()
