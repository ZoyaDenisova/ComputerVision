from __future__ import annotations
import tkinter as tk

class ToolsPanel(tk.Frame):
    """Панель инструментов"""
    def __init__(self, master):
        super().__init__(master)

        # Canvas + Scrollbar
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=1)
        self._scroll = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scroll.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self._scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(0,8))

        # внутренний фрейм с кнопками
        self._inner = tk.Frame(self._canvas)
        self._win = self._canvas.create_window((0,0), window=self._inner, anchor="nw")

        def _cfg(_e=None):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
            self._canvas.itemconfigure(self._win, width=self._canvas.winfo_width())

        self._inner.bind("<Configure>", _cfg)
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(self._win, width=e.width))

        # прокрутка колесиком
        MODS_TAG = "ModsScroll"
        self.bind_class(MODS_TAG, "<MouseWheel>", lambda e: self._canvas.yview_scroll(-int(e.delta/120), "units"))
        self._apply_tag(self._inner, MODS_TAG)
        self._apply_tag(self._canvas, MODS_TAG)

        # кнопки
        self.btns = {}
        self.btns["morphology"] = self._mk_button("Морфология…", pady=(0,8))
        self.btns["grayscale"] = self._mk_button("В градации серого")
        self.btns["adjust"]    = self._mk_button("Коррекция…")
        self.btns["bw"]        = self._mk_button("Коррекция Ч/Б…", pady=(6,6))
        self.btns["rot90cw"]   = self._mk_button("Повернуть 90°↻")
        self.btns["rot90ccw"]  = self._mk_button("Повернуть 90°↺")
        self.btns["rot_custom"]= self._mk_button("Повернуть…")
        self.btns["flip_h"]    = self._mk_button("Отразить по горизонтали")
        self.btns["flip_v"]    = self._mk_button("Отразить по вертикали", pady=(0,8))

        self.set_image_loaded(False)

    def _mk_button(self, text, *, pady=(0,6)):
        b = tk.Button(self._inner, text=text, state="disabled")
        b.pack(fill=tk.X, pady=pady, padx=8)
        return b

    def _apply_tag(self, widget, tag):
        tags = list(widget.bindtags())
        if tag not in tags:
            tags.insert(1, tag)
            widget.bindtags(tuple(tags))
        for ch in widget.winfo_children():
            self._apply_tag(ch, tag)

    # публичные API
    def set_callbacks(self, mapping: dict[str, callable]):
        """Привязать обработчики к кнопкам по ключам"""
        for k, cb in mapping.items():
            if k in self.btns:
                self.btns[k].config(command=cb)

    def set_image_loaded(self, flag: bool):
        state = "normal" if flag else "disabled"
        for k, b in self.btns.items():
            b.config(state=state)
