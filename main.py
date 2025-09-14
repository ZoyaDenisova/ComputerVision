# mvp_viewer.py
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

class ImageViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MVP: Загрузка и отображение изображения")
        self.geometry("800x600")
        self._pil_image = None   # исходный объект Pillow
        self._tk_image = None    # ссылка на ImageTk для предотвращения GC

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(top, text="Открыть изображение…", command=self.open_image).pack(side=tk.LEFT)

        # Контейнер для картинки
        self.image_label = tk.Label(self, bg="#111")
        self.image_label.pack(expand=True, fill=tk.BOTH)

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self._pil_image = Image.open(path)
            # Простое масштабирование по длинной стороне, чтобы влезало в окно (минимум логики)
            max_w = self.image_label.winfo_width() or 800
            max_h = self.image_label.winfo_height() or 600
            img = self._pil_image.copy()
            img.thumbnail((max_w, max_h), Image.LANCZOS)

            self._tk_image = ImageTk.PhotoImage(img)
            self.image_label.config(image=self._tk_image)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
