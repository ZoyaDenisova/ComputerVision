# imgviewer/ui/info_panel.py
from __future__ import annotations
import tkinter as tk

class InfoPanel(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        wrap = tk.Frame(self); wrap.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        self._text = tk.Text(wrap, wrap="word", height=10, state="disabled")
        scroll = tk.Scrollbar(wrap, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def set_text(self, text: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.insert(tk.END, text)
        self._text.configure(state="disabled")
