# imgviewer/ui/dialogs/filters.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import numpy as np
import os, json
from typing import Optional

class FiltersDialog(tk.Toplevel):
    """
    Окно фильтров свёртки:
      • Повышение резкости
      • Размытие в движении
      • Тиснение
      • Медианная фильтрация
      • Произвольная матрица (пользовательский фильтр)

    Особенности:
      • Ручное редактирование веса каждой ячейки (float).
      • Пресеты (встроенные + пользовательские с сохранением на диск).
      • Предпросмотр по чекбоксу (как в коррекции B/S/C).
      • Режим обработки: L (яркость) или RGB (поканально).
    """
    OPS = [
        ("Повышение резкости", "sharpen"),
        ("Размытие в движении", "motion"),
        ("Тиснение", "emboss"),
        ("Медианная фильтрация", "median"),
        ("Пользовательская матрица", "custom"),
    ]

    PRESETS_MAIN = [
        "Ручной", "Identity", "Box blur 3×3", "Gaussian-ish 3×3",
        "Sharpen 3×3", "Emboss 3×3", "Edge (Sobel X)"
    ]

    def __init__(self, master, before_img, on_preview, on_apply, on_cancel):
        super().__init__(master)
        self.title("Фильтры (свёртка/медиана)")
        self.resizable(True, True)

        # внешние колбэки
        self.before_img = before_img
        self.on_preview = on_preview
        self.on_apply = on_apply
        self.on_cancel = on_cancel

        # состояние
        self.rows = tk.IntVar(value=3)
        self.cols = tk.IntVar(value=3)
        self.lock_square = tk.BooleanVar(value=True)
        self.mode = tk.StringVar(value="L")
        self.op = tk.StringVar(value="sharpen")
        self.preset = tk.StringVar(value="Sharpen 3×3")
        self.normalize = tk.BooleanVar(value=True)   # нормировать по сумме ядра
        self.preview_auto = tk.BooleanVar(value=True)

        # параметры спец-режимов
        self.motion_len = tk.IntVar(value=9)         # длина размытия (нечётная)
        self.motion_angle = tk.DoubleVar(value=0.0)  # угол в градусах
        self.median_size = tk.IntVar(value=3)        # окно медианы (нечётное)

        # хранилище пользовательских пресетов ядра
        self.custom_presets: dict[str, list[list[float]]] = {}
        self._preset_box: Optional[ttk.Combobox] = None
        self._load_custom_presets()

        # текущая матрица ядра (float)
        self._kernel = np.zeros((self.rows.get(), self.cols.get()), dtype=float)
        self._entries: list[list[tk.Entry]] = []

        self._rebuild_id = None
        self._live_preview_id = None

        self._build_ui()
        # применим выбранный пресет/операцию для первичного заполнения
        self._apply_preset()
        self.after(0, self._maybe_preview)

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}
        top = ttk.Frame(self); top.pack(side=tk.TOP, fill=tk.X, **pad)

        # Операция
        ttk.Label(top, text="Операция:").grid(row=0, column=0, sticky="w")
        opbox = ttk.Combobox(top, values=[t for t, _ in self.OPS], state="readonly")
        opbox.grid(row=0, column=1, sticky="we", padx=(6,0))
        opbox.current(0)
        opbox.bind("<<ComboboxSelected>>", lambda _e: (self._set_op_by_index(opbox.current()), self._maybe_preview()))
        top.grid_columnconfigure(1, weight=1)

        # Размеры ядра (нечётные)
        size_fr = ttk.Frame(top); size_fr.grid(row=1, column=0, columnspan=2, sticky="we", pady=(8,0))
        ttk.Label(size_fr, text="Размер ядра:").pack(side=tk.LEFT)

        ttk.Label(size_fr, text="rows").pack(side=tk.LEFT, padx=(8,2))
        rows_sb = tk.Spinbox(size_fr, from_=1, to=99, increment=2, width=4,
                             textvariable=self.rows, command=self._on_size_change)
        rows_sb.pack(side=tk.LEFT)

        ttk.Label(size_fr, text="cols").pack(side=tk.LEFT, padx=(8,2))
        self._cols_sb = tk.Spinbox(size_fr, from_=1, to=99, increment=2, width=4,
                                   textvariable=self.cols, command=self._on_size_change)
        self._cols_sb.pack(side=tk.LEFT)

        for sb in (rows_sb, self._cols_sb):
            sb.bind("<KeyRelease>", lambda _e: self._debounced_size_change())
            sb.bind("<FocusOut>", lambda _e: self._on_size_change())
            sb.bind("<Return>", lambda _e: self._on_size_change())

        ttk.Checkbutton(size_fr, text="Квадратное ядро (1:1)",
                        variable=self.lock_square,
                        command=lambda: (self._on_size_change(), self._sync_cols_spin_state())
                        ).pack(side=tk.LEFT, padx=(12, 0))

        # Пресеты ядра
        ttk.Label(top, text="Пресет ядра:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        preset_row = ttk.Frame(top); preset_row.grid(row=2, column=1, sticky="we", padx=(6, 0), pady=(8, 0))
        preset_row.grid_columnconfigure(0, weight=1)

        self._preset_box = ttk.Combobox(preset_row, state="readonly", textvariable=self.preset,
                                        values=self._preset_values())
        self._preset_box.grid(row=0, column=0, sticky="we")

        self._preset_box.bind("<<ComboboxSelected>>",
                              lambda _e: (self._apply_preset(), self._maybe_preview()))

        save_btn = ttk.Button(preset_row, text="Сохранить…", width=12, command=self._save_current_as_preset)
        ren_btn = ttk.Button(preset_row, text="Переименовать…", width=14, command=self._rename_current_preset)
        del_btn = ttk.Button(preset_row, text="Удалить", width=10, command=self._delete_current_preset)
        save_btn.grid(row=0, column=1, padx=(6, 0))
        ren_btn.grid(row=0, column=2, padx=(6, 0))
        del_btn.grid(row=0, column=3, padx=(6, 0))

        # Режим обработки
        mode_fr = ttk.Frame(top); mode_fr.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8,0))
        ttk.Label(mode_fr, text="Режим:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_fr, text="Градации серого (L)", value="L", variable=self.mode,
                        command=self._maybe_preview).pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_fr, text="По каналам RGB", value="RGB", variable=self.mode,
                        command=self._maybe_preview).pack(side=tk.LEFT, padx=6)

        # Доп. параметры
        extra_fr = ttk.LabelFrame(top, text="Параметры"); extra_fr.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8,0))
        # Нормализация ядра
        ttk.Checkbutton(extra_fr, text="Нормировать по сумме ядра", variable=self.normalize,
                        command=self._maybe_preview).pack(side=tk.LEFT, padx=(6,6))

        # Motion blur (длина/угол)
        self._motion_len_sb = self._labeled_spin(extra_fr, "Длина (motion):", self.motion_len, 1, 99, 2, 5)
        self._motion_angle_sb = self._labeled_spin(extra_fr, "Угол°:", self.motion_angle, -180, 180, 1, 7, float_=True)

        # Median (окно)
        self._median_sb = self._labeled_spin(extra_fr, "Окно медианы:", self.median_size, 1, 99, 2, 5)

        # Редактор матрицы (таблица Entry)
        grid_wrap = ttk.Frame(self); grid_wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True, **pad)
        ttk.Label(grid_wrap, text="Матрица ядра (float):").pack(side=tk.TOP, anchor="w")
        self._grid_frame = ttk.Frame(grid_wrap)
        self._grid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(6,0))
        self._rebuild_entries()

        # Низ: кнопки
        btn_fr = ttk.Frame(self); btn_fr.pack(side=tk.BOTTOM, fill=tk.X, **pad)
        ttk.Checkbutton(btn_fr, text="Предпросмотр", variable=self.preview_auto,
                        command=self._maybe_preview).pack(side=tk.RIGHT)
        ttk.Button(btn_fr, text="Применить", command=self._apply).pack(side=tk.RIGHT, padx=(8,6))
        ttk.Button(btn_fr, text="Отмена", command=self._cancel).pack(side=tk.RIGHT)

        self._sync_cols_spin_state()
        self._refresh_preset_combobox()
        self._update_controls_visibility()

    def _labeled_spin(self, parent, text, var, frm, to, inc, width, float_=False):
        box = ttk.Frame(parent); box.pack(side=tk.LEFT, padx=(6,0))
        ttk.Label(box, text=text).pack(side=tk.TOP, anchor="w")
        if float_:
            sb = tk.Spinbox(box, from_=frm, to=to, increment=0.5, width=width, textvariable=var, command=self._maybe_preview)
        else:
            sb = tk.Spinbox(box, from_=frm, to=to, increment=inc, width=width, textvariable=var, command=self._maybe_preview)
        sb.pack(side=tk.TOP)
        sb.bind("<KeyRelease>", lambda _e: self._maybe_preview())
        sb.bind("<Return>", lambda _e: self._maybe_preview())
        return sb

    # ---------------- helpers ----------------
    def _force_odd(self, v: int) -> int:
        v = max(1, int(v))
        return v if (v % 2 == 1) else (v + 1)

    def _sync_cols_spin_state(self):
        if hasattr(self, "_cols_sb") and self._cols_sb:
            state = "disabled" if self.lock_square.get() else "normal"
            self._cols_sb.configure(state=state)

    def _set_op_by_index(self, idx: int):
        self.op.set(self.OPS[idx][1])
        # смена операции может скрывать/показывать параметры
        self._update_controls_visibility()
        # для «motion/median» подгоняем размеры ядра под параметры
        if self.op.get() == "motion":
            L = self._force_odd(self.motion_len.get())
            self.rows.set(L); self.cols.set(L if self.lock_square.get() else self.cols.get())
            self._on_size_change()
            self._build_motion_kernel()
        elif self.op.get() == "median":
            k = self._force_odd(self.median_size.get())
            self.rows.set(k); self.cols.set(k if self.lock_square.get() else self.cols.get())
            self._on_size_change()
        else:
            # для остальных просто применим пресет
            self._apply_preset()

    def _update_controls_visibility(self):
        is_motion = (self.op.get() == "motion")
        is_median = (self.op.get() == "median")
        # motion controls видны только при motion
        self._motion_len_sb.configure(state="normal" if is_motion else "disabled")
        self._motion_angle_sb.configure(state="normal" if is_motion else "disabled")
        # median control только при median
        self._median_sb.configure(state="normal" if is_median else "disabled")
        # редактор матрицы доступен для всех, кроме чистой медианы (там ядро не используется)
        state_grid = "disabled" if is_median else "normal"
        for row in self._entries:
            for e in row:
                e.configure(state=state_grid)

    def _debounced_size_change(self):
        if self._rebuild_id is not None:
            try: self.after_cancel(self._rebuild_id)
            except Exception: pass
        self._rebuild_id = self.after(80, self._on_size_change)

    def _on_size_change(self):
        r = self._force_odd(self.rows.get())
        c = self._force_odd(self.cols.get())
        if self.lock_square.get():
            c = r
        self.rows.set(r); self.cols.set(c)
        self._resize_kernel(r, c)
        self._rebuild_entries()
        self._apply_preset_if_needed()
        self._sync_cols_spin_state()
        self._maybe_preview()

    def _resize_kernel(self, r, c):
        old = getattr(self, "_kernel", np.zeros((r, c), dtype=float))
        nr = np.zeros((r, c), dtype=float)
        rr = min(r, old.shape[0]); cc = min(c, old.shape[1])
        nr[:rr, :cc] = old[:rr, :cc]
        self._kernel = nr

    def _rebuild_entries(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()
        r, c = self.rows.get(), self.cols.get()
        self._entries = []
        for i in range(r):
            row_entries = []
            for j in range(c):
                e = tk.Entry(self._grid_frame, width=6, justify="center")
                e.grid(row=i, column=j, padx=2, pady=2)
                val = f"{self._kernel[i, j]:.3f}" if self._kernel.size else "0"
                e.insert(0, val)
                e.bind("<KeyRelease>", lambda _e, ii=i, jj=j: self._on_cell_edit(ii, jj))
                e.bind("<FocusOut>", lambda _e, ii=i, jj=j: self._on_cell_edit(ii, jj))
                row_entries.append(e)
            self._entries.append(row_entries)

    def _on_cell_edit(self, i, j):
        try:
            v = float(self._entries[i][j].get().replace(",", "."))
        except ValueError:
            return
        self._kernel[i, j] = v
        if self.preview_auto.get():
            self._maybe_preview()

    # ---------- пресеты ----------
    def _preset_values(self):
        vals = list(self.PRESETS_MAIN)
        if self.custom_presets:
            vals.append("— Пользовательские —")
            vals.extend(self.custom_presets.keys())
        return vals

    def _refresh_preset_combobox(self):
        if not self._preset_box:
            return
        cur = self.preset.get()
        vals = self._preset_values()
        self._preset_box.configure(values=vals)
        if cur not in vals:
            cur = "Ручной"; self.preset.set(cur)
        try:
            self._preset_box.current(vals.index(cur))
        except ValueError:
            self._preset_box.current(0)

        def on_select(_e):
            sel = self.preset.get()
            if sel == "— Пользовательские —":
                self._preset_box.set(cur);  # запрет выбора разделителя
                return
            self._apply_preset()
            self._maybe_preview()

        self._preset_box.unbind("<<ComboboxSelected>>")
        self._preset_box.bind("<<ComboboxSelected>>", on_select)

    def _apply_preset_if_needed(self):
        # если выбран не "Ручной" или кастом — пересоберём ядро
        name = self.preset.get()
        if name != "Ручной" and (name in self.PRESETS_MAIN or name in self.custom_presets):
            self._apply_preset()

    def _apply_preset(self):
        r, c = self.rows.get(), self.cols.get()
        name = self.preset.get()
        if name not in self.PRESETS_MAIN and name in self.custom_presets:
            src = np.array(self.custom_presets[name], dtype=float)
            self._resize_kernel(r, c)
            rr, cc = min(r, src.shape[0]), min(c, src.shape[1])
            self._kernel[:rr, :cc] = src[:rr, :cc]
            self._rebuild_entries()
            return

        k = np.zeros((r, c), dtype=float)

        if name == "Identity":
            k[r//2, c//2] = 1.0
        elif name == "Box blur 3×3":
            k[:, :] = 1.0
        elif name == "Gaussian-ish 3×3":
            # простая аппроксимация гаусса
            base = np.array([[1,2,1],
                             [2,4,2],
                             [1,2,1]], dtype=float)
            k = self._fit_3x3(base, r, c)
        elif name == "Sharpen 3×3":
            base = np.array([[0,-1, 0],
                             [-1, 5,-1],
                             [0,-1, 0]], dtype=float)
            k = self._fit_3x3(base, r, c)
        elif name == "Emboss 3×3":
            base = np.array([[-2,-1, 0],
                             [-1, 1, 1],
                             [ 0, 1, 2]], dtype=float)
            k = self._fit_3x3(base, r, c)
        elif name == "Edge (Sobel X)":
            base = np.array([[-1,0,1],
                             [-2,0,2],
                             [-1,0,1]], dtype=float)
            k = self._fit_3x3(base, r, c)
        elif name == "Ручной":
            k = self._kernel  # оставить как есть

        self._kernel = k
        self._rebuild_entries()

        # если выбрана операция "motion" — перестроим ядро направленного размытия
        if self.op.get() == "motion":
            self._build_motion_kernel()

    def _fit_3x3(self, base: np.ndarray, r: int, c: int) -> np.ndarray:
        out = np.zeros((r, c), dtype=float)
        y0 = r//2 - 1; x0 = c//2 - 1
        y0 = max(0, y0); x0 = max(0, x0)
        y1 = min(r, y0 + 3); x1 = min(c, x0 + 3)
        by = y1 - y0; bx = x1 - x0
        out[y0:y1, x0:x1] = base[:by, :bx]
        return out

    def _ask_preset_name(self, title, initial=""):
        name = simpledialog.askstring(title, "Введите имя пресета:", initialvalue=initial, parent=self)
        if name is None:
            return None
        name = name.strip()
        if not name:
            messagebox.showwarning("Имя пресета", "Имя не может быть пустым.")
            return None
        if name in self.PRESETS_MAIN:
            messagebox.showwarning("Имя пресета", "Это имя зарезервировано системным пресетом.")
            return None
        return name

    def _save_current_as_preset(self):
        name = self._ask_preset_name("Сохранить пресет")
        if not name:
            return
        k = np.array(self._kernel, dtype=float).tolist()
        self.custom_presets[name] = k
        self._save_custom_presets()
        self._refresh_preset_combobox()
        self.preset.set(name)
        self._refresh_preset_combobox()
        self._apply_preset()
        self._maybe_preview()

    def _rename_current_preset(self):
        cur = self.preset.get()
        if cur in self.PRESETS_MAIN or cur not in self.custom_presets:
            messagebox.showinfo("Переименование", "Переименовать можно только пользовательский пресет.")
            return
        new_name = self._ask_preset_name("Переименовать пресет", initial=cur)
        if not new_name:
            return
        if new_name in self.custom_presets:
            messagebox.showwarning("Имя пресета", "Такое имя уже используется среди пользовательских пресетов.")
            return
        self.custom_presets[new_name] = self.custom_presets.pop(cur)
        self._save_custom_presets()
        self.preset.set(new_name)
        self._refresh_preset_combobox()

    def _delete_current_preset(self):
        cur = self.preset.get()
        if cur in self.PRESETS_MAIN or cur not in self.custom_presets:
            messagebox.showinfo("Удаление пресета", "Удалять можно только пользовательский пресет.")
            return
        if not messagebox.askyesno("Удалить пресет", f"Удалить пользовательский пресет «{cur}»?"):
            return
        self.custom_presets.pop(cur, None)
        self._save_custom_presets()
        self.preset.set("Ручной")
        self._refresh_preset_combobox()
        self._apply_preset()
        self._maybe_preview()

    def _presets_path(self):
        base = os.path.expanduser("~")
        cfg_dir = os.path.join(base, ".imgviewer")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "filter_custom_kernels.json")

    def _load_custom_presets(self):
        try:
            with open(self._presets_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self.custom_presets = {k: v for k, v in data.items() if isinstance(v, list)}
        except FileNotFoundError:
            self.custom_presets = {}
        except Exception:
            self.custom_presets = {}

    def _save_custom_presets(self):
        try:
            with open(self._presets_path(), "w", encoding="utf-8") as f:
                json.dump(self.custom_presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Сохранение пресетов", f"Не удалось сохранить пресеты:\n{e}")

    # ---------- ядро motion blur ----------
    def _build_motion_kernel(self):
        L = self._force_odd(self.motion_len.get())
        angle = float(self.motion_angle.get())
        r, c = self.rows.get(), self.cols.get()
        self._resize_kernel(r, c)

        # формируем линию длины L по углу (ближ. пиксели Bresenham по центру)
        k = np.zeros((r, c), dtype=float)
        cy, cx = r//2, c//2
        theta = np.deg2rad(-angle)  # по часовой (как в ротейте)
        # дискретная линия от -L//2 до +L//2
        for t in range(-(L//2), L//2 + 1):
            y = int(round(cy + t * np.sin(theta)))
            x = int(round(cx + t * np.cos(theta)))
            if 0 <= y < r and 0 <= x < c:
                k[y, x] = 1.0
        self._kernel = k
        self._rebuild_entries()

    # ---------- предпросмотр/применение ----------
    def _get_kernel(self) -> np.ndarray:
        r, c = self.rows.get(), self.cols.get()
        k = np.zeros((r, c), dtype=float)
        for i in range(r):
            for j in range(c):
                try:
                    v = float(self._entries[i][j].get().replace(",", "."))
                except ValueError:
                    v = 0.0
                k[i, j] = v
        # если все нули — подставим identity, чтобы не «обнулять» картинку
        if np.allclose(k, 0.0):
            k[r//2, c//2] = 1.0
            messagebox.showwarning("Пустое ядро",
                                   "Матрица ядра не должна быть полностью нулевой. "
                                   "Вставлен единичный центр.")
        return k

    def _preview(self):
        try:
            from imgviewer.services import transforms as Sx
            op = self.op.get()
            mode = self.mode.get()

            if op == "median":
                ksize = self._force_odd(self.median_size.get())
                out = Sx.filter_apply(self.before_img, op, None, mode, False,
                                      extra={"median_size": ksize})
            else:
                k = self._get_kernel()
                out = Sx.filter_apply(self.before_img, op, k, mode, self.normalize.get(),
                                      extra={"motion_len": self._force_odd(self.motion_len.get()),
                                             "motion_angle": float(self.motion_angle.get())})
            self.on_preview(out)
        except Exception as e:
            messagebox.showerror("Ошибка предпросмотра", str(e))

    def _maybe_preview(self):
        if not self.preview_auto.get():
            if self._live_preview_id is not None:
                try: self.after_cancel(self._live_preview_id)
                except Exception: pass
                self._live_preview_id = None
            try:
                self.on_preview(self.before_img)
            except Exception:
                pass
            return
        if self._live_preview_id is not None:
            try: self.after_cancel(self._live_preview_id)
            except Exception: pass
        self._live_preview_id = self.after(60, self._preview)

    def _apply(self):
        try:
            op = self.op.get()
            mode = self.mode.get()
            if op == "median":
                ksize = self._force_odd(self.median_size.get())
                self.on_apply(op, None, mode, self.normalize.get(), {"median_size": ksize})
            else:
                k = self._get_kernel()
                self.on_apply(op, k, mode, self.normalize.get(),
                              {"motion_len": self._force_odd(self.motion_len.get()),
                               "motion_angle": float(self.motion_angle.get())})
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка применения", str(e))

    def _cancel(self):
        try:
            self.on_preview(self.before_img)
            self.on_cancel()
        finally:
            self.destroy()
