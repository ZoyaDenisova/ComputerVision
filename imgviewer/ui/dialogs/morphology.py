# imgviewer/ui/dialogs/morphology.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import os, json
from tkinter import simpledialog

class MorphologyDialog(tk.Toplevel):
    OPS = [
        ("Эрозия", "erosion"),
        ("Дилатация", "dilation"),
        ("Открытие", "opening"),
        ("Закрытие", "closing"),
        ("Градиент", "gradient"),
        ("Цилиндр (Top-hat)", "tophat"),
        ("Чёрная шляпа", "blackhat"),
    ]
    PRESETS_MAIN = ["Ручной", "Квадрат", "Крест", "Эллипс", "Ромб", "Центр"]

    def __init__(self, master, before_img, on_preview, on_apply, on_cancel):
        super().__init__(master)
        self.title("Морфологические операции")
        self.resizable(True, True)

        # внешние колбэки
        self.before_img = before_img
        self.on_preview = on_preview
        self.on_apply = on_apply
        self.on_cancel = on_cancel

        # состояние
        self.rows = tk.IntVar(value=5)
        self.cols = tk.IntVar(value=5)
        self.iterations = tk.IntVar(value=1)
        self.mode = tk.StringVar(value="L")
        self.op = tk.StringVar(value="erosion")
        self.preset = tk.StringVar(value="Ручной")
        self.lock_square = tk.BooleanVar(value=True)   # 1:1
        self.preview_auto = tk.BooleanVar(value=True)  # чекбокс «Предпросмотр» (как в коррекции)
        self._drag_value = None  # 0 или 1 в текущем «мазке»
        self.custom_presets = {}  # dict: name -> 2D list (0/1)
        self._preset_box = None  # ссылка на комбобокс пресетов
        self._load_custom_presets()

        # ядро (0/1)
        self._kernel = np.ones((self.rows.get(), self.cols.get()), dtype=np.uint8)

        # UI контейнеры
        self._grid_frame: ttk.Frame | None = None
        self._canvas: tk.Canvas | None = None
        self._cell_size = 24
        self._rebuild_id = None
        self._live_preview_id = None
        self._hover_cell = None

        self._build_ui()
        self._redraw_canvas()

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # первичный показ с учётом чекбокса
        self.after(0, self._maybe_preview)

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

        # Размер (только нечётные)
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

        # Пресеты
        ttk.Label(top, text="Пресет ядра:").grid(row=2, column=0, sticky="w", pady=(8, 0))

        preset_row = ttk.Frame(top)
        preset_row.grid(row=2, column=1, sticky="we", padx=(6, 0), pady=(8, 0))
        preset_row.grid_columnconfigure(0, weight=1)

        self._preset_box = ttk.Combobox(preset_row, state="readonly", textvariable=self.preset,
                                        values=self._preset_values())
        self._preset_box.grid(row=0, column=0, sticky="we")
        # выбор из списка -> применить пресет
        self._preset_box.bind("<<ComboboxSelected>>",
                              lambda _e: (self._apply_preset(), self._maybe_preview()))

        # Кнопки управления кастомными пресетами
        save_btn = ttk.Button(preset_row, text="Сохранить…", width=12, command=self._save_current_as_preset)
        ren_btn = ttk.Button(preset_row, text="Переименовать…", width=14, command=self._rename_current_preset)
        del_btn = ttk.Button(preset_row, text="Удалить", width=10, command=self._delete_current_preset)

        save_btn.grid(row=0, column=1, padx=(6, 0))
        ren_btn.grid(row=0, column=2, padx=(6, 0))
        del_btn.grid(row=0, column=3, padx=(6, 0))

        # Режим
        mode_fr = ttk.Frame(top); mode_fr.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8,0))
        ttk.Label(mode_fr, text="Режим:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_fr, text="Градации серого (L)", value="L", variable=self.mode,
                        command=self._maybe_preview).pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_fr, text="По каналам RGB", value="RGB", variable=self.mode,
                        command=self._maybe_preview).pack(side=tk.LEFT, padx=6)

        # Итерации
        it_fr = ttk.Frame(top); it_fr.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8,0))
        ttk.Label(it_fr, text="Iterations:").pack(side=tk.LEFT)
        it_sb = tk.Spinbox(it_fr, from_=1, to=20, width=4, textvariable=self.iterations, command=self._maybe_preview)
        it_sb.pack(side=tk.LEFT, padx=(6,0))
        it_sb.bind("<KeyRelease>", lambda _e: self._maybe_preview())

        # Область сетки ядра — Canvas с квадратными клетками
        self._grid_frame = ttk.Frame(self)
        self._grid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, **pad)

        ttk.Label(self._grid_frame, text="Клетка 1 = чёрная (включено), 0 = белая (выключено)")\
            .pack(side=tk.TOP, anchor="w")

        self._canvas = tk.Canvas(self._grid_frame, bg="#222", highlightthickness=1, highlightbackground="#444")
        self._canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(6,0))

        # реакция на resize — пересчитать квадратность клеток
        self._canvas.bind("<Configure>", lambda _e: self._redraw_canvas())
        # клики и перетаскивание для рисования
        self._canvas.bind("<Button-1>", self._on_canvas_click)
        self._canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>", lambda _e: (setattr(self, "_hover_cell", None),
                                                           setattr(self, "_drag_value", None)))

        # Низ: кнопки действий
        btn_fr = ttk.Frame(self); btn_fr.pack(side=tk.BOTTOM, fill=tk.X, **pad)
        # чекбокс «Предпросмотр» — ПРАВЫЙ НИЖНИЙ УГОЛ (на месте старой кнопки)
        ttk.Checkbutton(btn_fr, text="Предпросмотр", variable=self.preview_auto,
                        command=self._maybe_preview).pack(side=tk.RIGHT)
        ttk.Button(btn_fr, text="Применить", command=self._apply).pack(side=tk.RIGHT, padx=(8,6))
        ttk.Button(btn_fr, text="Отмена", command=self._cancel).pack(side=tk.RIGHT, padx=(0,6))
        self._sync_cols_spin_state()
        self._refresh_preset_combobox()

    # ---------------- helpers/logic ----------------
    def _force_odd(self, v: int) -> int:
        v = max(1, int(v))
        return v if (v % 2 == 1) else (v + 1)

    def _sync_cols_spin_state(self):
        # если 1:1 — блокируем спинбокс колонок визуально (серый/disabled)
        if hasattr(self, "_cols_sb") and self._cols_sb:
            state = "disabled" if self.lock_square.get() else "normal"
            self._cols_sb.configure(state=state)

    def _set_op_by_index(self, idx: int):
        self.op.set(self.OPS[idx][1])
        if self.op.get() in ("tophat", "blackhat", "opening", "closing", "gradient"):
            if self.rows.get() % 2 == 0 or self.cols.get() % 2 == 0:
                self.after(50, lambda: self._hint("Для симметрии удобнее нечётные размеры ядра."))

    def _hint(self, text: str):
        try:
            self.status.destroy()
        except Exception:
            pass
        self.status = ttk.Label(self, text=text, foreground="#666")
        self.status.pack(side=tk.BOTTOM, pady=(0,6))

    # размеры ядра
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

        if self.preset.get() == "Ручной":
            self._kernel = self._resize_manual(self._kernel, r, c)
        else:
            # пере-применяем выбранный пресет с новыми r, c
            self._apply_preset()

        self._redraw_canvas()
        self._sync_cols_spin_state()
        self._maybe_preview()

    def _resize_manual(self, old: np.ndarray, r: int, c: int) -> np.ndarray:
        nr = np.zeros((r, c), dtype=np.uint8)
        rr = min(r, old.shape[0]); cc = min(c, old.shape[1])
        nr[:rr, :cc] = old[:rr, :cc]
        return nr

    def _apply_preset(self):
        r, c = self.rows.get(), self.cols.get()
        name = self.preset.get()
        cy, cx = r // 2, c // 2

        # 1) Кастомные пресеты (имя не из PRESETS_MAIN)
        if name not in self.PRESETS_MAIN and name in self.custom_presets:
            src = np.array(self.custom_presets[name], dtype=np.uint8)
            # подгоняем сохранённую матрицу под текущий размер (без изменения сохранённого пресета)
            self._kernel = self._resize_manual(src, r, c)
            self._redraw_canvas()
            return

        # 2) Встроенные пресеты
        k = np.zeros((r, c), dtype=np.uint8)
        if name == "Квадрат":
            k[:, :] = 1
        elif name == "Крест":
            k[cy, :] = 1;
            k[:, cx] = 1;
            k[cy, cx] = 1
        elif name == "Эллипс":
            y, x = np.ogrid[:r, :c]
            ry = max(1, r // 2);
            rx = max(1, c // 2)
            mask = ((y - cy) ** 2) / (ry ** 2) + ((x - cx) ** 2) / (rx ** 2) <= 1.0
            k[mask] = 1
        elif name == "Ромб":
            for y in range(r):
                for x in range(c):
                    if abs(y - cy) + abs(x - cx) <= max(r, c) // 2:
                        k[y, x] = 1
        elif name == "Центр":
            k[cy, cx] = 1
        elif name == "Ручной":
            k = self._resize_manual(getattr(self, "_kernel", np.zeros((r, c), dtype=np.uint8)), r, c)

        self._kernel = k
        self._redraw_canvas()

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
        # берём текущую матрицу как есть (не важно, какой пресет выбран)
        name = self._ask_preset_name("Сохранить пресет")
        if not name:
            return
        # копия текущего ядра
        k = np.array(self._kernel, dtype=np.uint8).tolist()
        self.custom_presets[name] = k
        self._save_custom_presets()
        # обновить комбобокс и выбрать новый
        self._refresh_preset_combobox()
        self.preset.set(name)
        self._refresh_preset_combobox()
        # применить (на случай если размеры отличаются)
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
        # перенос
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
        # откат на «Ручной»
        self.preset.set("Ручной")
        self._refresh_preset_combobox()
        self._apply_preset()
        self._maybe_preview()

    def _preset_values(self):
        """Возвращает список значений для комбобокса, с визуальным разделителем."""
        values = list(self.PRESETS_MAIN)
        if self.custom_presets:
            values.append("— Пользовательские —")
            values.extend(self.custom_presets.keys())
        return values

    def _refresh_preset_combobox(self):
        if not self._preset_box:
            return
        cur = self.preset.get()
        vals = self._preset_values()
        self._preset_box.configure(values=vals)

        if cur not in vals:
            cur = "Ручной"
            self.preset.set(cur)

        try:
            self._preset_box.current(vals.index(cur))
        except ValueError:
            self._preset_box.current(0)

        # блокировка выбора разделителя
        def on_select(event):
            sel = self.preset.get()
            if sel == "— Пользовательские —":
                # возвращаемся на прошлый выбранный
                self._preset_box.set(cur)
                return
            self._apply_preset()
            self._maybe_preview()

        self._preset_box.unbind("<<ComboboxSelected>>")
        self._preset_box.bind("<<ComboboxSelected>>", on_select)

    def _presets_path(self):
        # можно поменять на свой путь приложения
        base = os.path.expanduser("~")
        cfg_dir = os.path.join(base, ".imgviewer")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "morph_custom_presets.json")

    def _load_custom_presets(self):
        try:
            with open(self._presets_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            # в файле ожидаем {"name":[[0,1,...],[...],...]}
            self.custom_presets = {k: v for k, v in data.items() if isinstance(v, list)}
        except FileNotFoundError:
            self.custom_presets = {}
        except Exception:
            # если файл битый — не падаем
            self.custom_presets = {}

    def _save_custom_presets(self):
        try:
            with open(self._presets_path(), "w", encoding="utf-8") as f:
                json.dump(self.custom_presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Сохранение пресетов", f"Не удалось сохранить пресеты:\n{e}")

    # ---------------- Canvas grid ----------------
    def _grid_geom(self):
        """Вернуть параметры расположения: cell_size, offset_x, offset_y."""
        r, c = self.rows.get(), self.cols.get()
        w = max(1, self._canvas.winfo_width() - 2)
        h = max(1, self._canvas.winfo_height() - 2)
        cell = max(6, min(w // c, h // r))
        used_w, used_h = cell * c, cell * r
        off_x = (w - used_w) // 2
        off_y = (h - used_h) // 2
        return cell, off_x, off_y

    def _redraw_canvas(self):
        if not self._canvas:
            return
        self._canvas.delete("all")
        cell, off_x, off_y = self._grid_geom()
        r, c = self.rows.get(), self.cols.get()

        for i in range(r):
            for j in range(c):
                v = int(self._kernel[i, j])
                x0 = off_x + j * cell
                y0 = off_y + i * cell
                x1 = x0 + cell
                y1 = y0 + cell
                fill = "#000000" if v else "#ffffff"
                outline = "#444"
                self._canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, tags=(f"cell_{i}_{j}", "cell"))

    def _xy_to_cell(self, x, y):
        cell, off_x, off_y = self._grid_geom()
        r, c = self.rows.get(), self.cols.get()
        j = (x - off_x) // cell
        i = (y - off_y) // cell
        if 0 <= i < r and 0 <= j < c:
            return int(i), int(j)
        return None

    def _paint_cell(self, i, j, value=None):
        """Переключить клетку i,j; если value задан, установить 0/1, иначе инвертировать."""
        if value is None:
            self._kernel[i, j] = 0 if self._kernel[i, j] else 1
        else:
            self._kernel[i, j] = 1 if value else 0
        cell, off_x, off_y = self._grid_geom()
        x0 = off_x + j * cell
        y0 = off_y + i * cell
        x1 = x0 + cell
        y1 = y0 + cell
        fill = "#000000" if self._kernel[i, j] else "#ffffff"
        self._canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#444")
        if self.preset.get() != "Ручной":
            self.preset.set("Ручной")

    def _on_canvas_click(self, e):
        cell = self._xy_to_cell(e.x, e.y)
        if cell is None:
            return
        i, j = cell
        current = int(self._kernel[i, j])
        # если клетка была 1 — начнём «стирать» (0); если 0 — «рисовать» (1)
        self._drag_value = 0 if current == 1 else 1
        self._paint_cell(i, j, value=self._drag_value)
        self._hover_cell = (i, j)
        self._maybe_preview()

    def _on_canvas_drag(self, e):
        if self._drag_value is None:
            return
        cell = self._xy_to_cell(e.x, e.y)
        if cell is None:
            return
        i, j = cell
        if self._hover_cell != (i, j):
            self._paint_cell(i, j, value=self._drag_value)
            self._hover_cell = (i, j)
            self._maybe_preview()

    # ---------------- применение ----------------
    def _get_kernel(self) -> np.ndarray:
        k = np.array(self._kernel, dtype=np.uint8)
        if k.sum() == 0:
            cy, cx = k.shape[0] // 2, k.shape[1] // 2
            k[cy, cx] = 1
            messagebox.showwarning("Ядро пустое",
                                   "Структурный элемент не должен быть пустым. Центр включён автоматически.")
        return k

    def _preview(self):
        try:
            from imgviewer.services import transforms as Sx
            k = self._get_kernel()
            out = Sx.morph_apply(self.before_img, self.op.get(), k,
                                 int(self.iterations.get()), self.mode.get())
            self.on_preview(out)
        except Exception as e:
            messagebox.showerror("Ошибка предпросмотра", str(e))

    def _maybe_preview(self):
        """Если чекбокс выключен — показываем исходное изображение.
        Если включён — живой предпросмотр (с коротким дебаунсом)."""
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
            k = self._get_kernel()
            self.on_apply(self.op.get(), k, int(self.iterations.get()), self.mode.get())
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка применения", str(e))

    def _cancel(self):
        try:
            self.on_preview(self.before_img)
            self.on_cancel()
        finally:
            self.destroy()
