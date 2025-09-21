from __future__ import annotations
import tkinter as tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from imgviewer.services.histogram import histogram_data

class HistogramPanel(tk.Frame):
    """Панель: радиокнопки выбора варианта + чекбоксы каналов + график matplotlib."""
    def __init__(self, master):
        super().__init__(master)

        ctrl = tk.Frame(self); ctrl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8,4))
        tk.Label(ctrl, text="Гистограмма:").grid(row=0, column=0, sticky="w")
        self._variant = tk.StringVar(value="current")
        rb = tk.Frame(ctrl); rb.grid(row=0, column=1, sticky="w")
        for val, txt in (("original","Оригинал"), ("current","Текущая")):
            tk.Radiobutton(rb, text=txt, variable=self._variant, value=val, command=self.redraw)\
              .pack(side=tk.LEFT, padx=(0,8))

        tk.Label(ctrl, text="Каналы:").grid(row=1, column=0, sticky="w", pady=(4,0))
        ch = tk.Frame(ctrl); ch.grid(row=1, column=1, sticky="w", pady=(4,0))
        self._ch_r = tk.BooleanVar(value=True)
        self._ch_g = tk.BooleanVar(value=True)
        self._ch_b = tk.BooleanVar(value=True)
        for var, name in ((self._ch_r,"R"), (self._ch_g,"G"), (self._ch_b,"B")):
            var.trace_add("write", lambda *_: self.redraw())
            tk.Checkbutton(ch, text=name, variable=var).pack(side=tk.LEFT)

        self._fig = Figure(figsize=(5.8, 2.6), dpi=100)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.X, padx=8, pady=(4,8))

        self._provider = None

    def set_provider(self, provider):
        self._provider = provider

    def redraw(self):
        self._ax.clear()
        if not self._provider:
            self._canvas.draw_idle(); return

        kind = self._variant.get()
        img = self._provider(kind)
        if img is None:
            self._canvas.draw_idle(); return

        data = histogram_data(img)
        xs = list(range(256))
        if data["mode"] == "L":
            hist = data["L"]
            self._ax.plot(xs, hist, color="gray", linewidth=1, label="L")
            ymax = max(hist) or 1
            mode_text = "L"
        else:
            r, g, b = data["R"], data["G"], data["B"]
            show_r, show_g, show_b = self._ch_r.get(), self._ch_g.get(), self._ch_b.get()
            if not (show_r or show_g or show_b):
                show_r = show_g = show_b = True
                self._ch_r.set(True); self._ch_g.set(True); self._ch_b.set(True)

            vals = []
            if show_r: vals += r
            if show_g: vals += g
            if show_b: vals += b
            ymax = max(vals) if vals else 1

            if show_r: self._ax.plot(xs, r, color="red", linewidth=1, label="R")
            if show_g: self._ax.plot(xs, g, color="green", linewidth=1, label="G")
            if show_b: self._ax.plot(xs, b, color="blue", linewidth=1, label="B")
            mode_text = "RGB"

        # оформление
        self._ax.set_xlim(0, 255)
        self._ax.set_ylim(0, ymax * 1.05)
        self._ax.set_xlabel("Уровень яркости (0–255)")
        self._ax.set_ylabel("Частота")
        var_map = {"original": "Оригинал", "current": "Текущая"}
        title = var_map.get(kind, "Текущая")
        self._ax.set_title(f"{title} — {mode_text}")
        self._ax.legend(loc="upper right", fontsize=8)
        self._ax.grid(False)
        for spine in ("top","right"):
            self._ax.spines[spine].set_visible(False)

        self._canvas.draw_idle()
