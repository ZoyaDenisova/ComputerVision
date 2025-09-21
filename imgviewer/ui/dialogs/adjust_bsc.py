import tkinter as tk
from imgviewer.services import transforms as Sx  # для предпросмотра

class AdjustBSCDialog(tk.Toplevel):
    """Диалог Яркость/Насыщенность/Контраст с живым предпросмотром"""
    def __init__(self, master, before_image, on_preview, on_apply, on_cancel, init=(1.0, 1.0, 1.0)):
        super().__init__(master)
        self.title("Коррекция: яркость/насыщенность/контраст")
        self.resizable(False, False)

        self._before = before_image
        self._on_preview = on_preview      # принимает PIL.Image (временная картинка)
        self._on_apply = on_apply          # принимает (bright, sat, contr)
        self._on_cancel = on_cancel

        frm = tk.Frame(self); frm.pack(padx=10, pady=10)

        def make_scale(text, row, value):
            tk.Label(frm, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.DoubleVar(value=value)
            sc = tk.Scale(frm, from_=0.0, to=2.0, resolution=0.01, orient="horizontal", length=280, variable=var)
            sc.grid(row=row, column=1, padx=6, pady=4)
            return var

        self.v_b = make_scale("Яркость", 0, init[0])
        self.v_s = make_scale("Насыщенность", 1, init[1])
        self.v_c = make_scale("Контраст", 2, init[2])

        self.preview_var = tk.BooleanVar(value=True)

        btns = tk.Frame(self); btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Checkbutton(btns, text="Предпросмотр", variable=self.preview_var, command=self._render_preview) \
            .pack(side="left")

        tk.Button(btns, text="Применить", command=self._apply).pack(side="right")
        tk.Button(btns, text="Сбросить значения", command=self._reset_vals).pack(side="right", padx=6)
        tk.Button(btns, text="Отмена", command=self._cancel).pack(side="right", padx=6)

        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # бинды для живого предпросмотра
        def _on_var_change(_name: str, _index: str, _op: str) -> None:
            self._render_preview()
        for var in (self.v_b, self.v_s, self.v_c):
            var.trace_add("write", _on_var_change)

        self.after(0, self._render_preview)

    def _current_params(self):
        return (self.v_b.get(), self.v_s.get(), self.v_c.get())

    def _render_preview(self):
        if not self.winfo_exists():
            return
        if self.preview_var.get():
            b, s, c = self._current_params()
            temp = Sx.adjust_bsc(self._before, b, s, c)
            self._on_preview(temp)
        else:
            self._on_preview(self._before)

    def _apply(self):
        b, s, c = self._current_params()
        self._on_apply(b, s, c)
        self.destroy()

    def _reset_vals(self):
        self.v_b.set(1.0); self.v_s.set(1.0); self.v_c.set(1.0)

    def _cancel(self):
        self._on_preview(self._before)
        self._on_cancel()
        self.destroy()
