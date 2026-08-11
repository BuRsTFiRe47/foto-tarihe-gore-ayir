#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foto Tarihe Göre Ayır
======================
Bir klasördeki fotoğrafları (ve isterseniz videoları ve alt klasörlerdekileri)
çekim tarihine (EXIF) veya dosya tarihine göre yeni klasörlere kopyalar/taşır.
Videolarda EXIF bilgisi olmadığından, video dosyaları için her zaman dosyanın
değiştirilme tarihi kullanılır.

Gereksinimler:
    pip install pillow

Çalıştırma:
    python foto_tarihe_gore_ayir.py
"""

import shutil
import threading
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

try:
    from PIL import Image
    from PIL import ExifTags
    PIL_AVAILABLE = True
    # EXIF tag id -> isim eşlemesi içinde "DateTimeOriginal" olanı bul
    _DATE_TAG_ID = None
    for _tag_id, _tag_name in ExifTags.TAGS.items():
        if _tag_name == "DateTimeOriginal":
            _DATE_TAG_ID = _tag_id
            break
except ImportError:
    PIL_AVAILABLE = False
    _DATE_TAG_ID = None

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff",
    ".bmp", ".gif", ".webp", ".raw", ".cr2", ".nef", ".arw", ".dng",
}

VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".flv",
    ".webm", ".mts", ".m2ts",
}

FORMAT_PRESETS = {
    "Yıl / Ay / Gün  (2026/08/03)": "%Y/%m/%d",
    "Yıl-Ay-Gün  (2026-08-03)": "%Y-%m-%d",
    "Yıl / Ay  (2026/08)": "%Y/%m",
    "Yıl-Ay  (2026-08)": "%Y-%m",
    "Sadece Yıl  (2026)": "%Y",
    "Yıl / Ay Adı  (2026/Ağustos)": "%Y/%B",
    "Gün-Ay-Yıl  (03-08-2026)": "%d-%m-%Y",
    "Özel (aşağıya kendi formatınızı yazın)": "CUSTOM",
}

TR_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}

# ---------- Tema renkleri ----------
THEMES = {
    "light": {
        "bg": "#f4f4f6",
        "fg": "#1c1c1e",
        "subtle_fg": "#5b5b5f",
        "entry_bg": "#ffffff",
        "entry_fg": "#1c1c1e",
        "button_bg": "#e2e2e6",
        "button_active": "#d0d0d6",
        "accent": "#2563eb",
        "accent_fg": "#ffffff",
        "border": "#c9c9cf",
        "log_bg": "#ffffff",
        "log_fg": "#1c1c1e",
    },
    "dark": {
        "bg": "#1e1e22",
        "fg": "#e8e8ea",
        "subtle_fg": "#a0a0a6",
        "entry_bg": "#2a2a2f",
        "entry_fg": "#e8e8ea",
        "button_bg": "#33333a",
        "button_active": "#3f3f47",
        "accent": "#3b82f6",
        "accent_fg": "#ffffff",
        "border": "#3a3a41",
        "log_bg": "#141417",
        "log_fg": "#d8d8da",
    },
}


def get_exif_date(path: Path):
    """EXIF'ten çekim tarihini okumaya çalışır. Bulamazsa None döner."""
    if not PIL_AVAILABLE or _DATE_TAG_ID is None:
        return None
    try:
        with Image.open(path) as img:
            exif = img._getexif() if hasattr(img, "_getexif") else None
            if not exif:
                return None
            raw = exif.get(_DATE_TAG_ID)
            if not raw:
                return None
            # EXIF format: "2026:08:03 14:22:10"
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def get_file_date(path: Path) -> datetime:
    """Dosyanın değiştirilme tarihini döner (EXIF bulunamazsa yedek)."""
    return datetime.fromtimestamp(path.stat().st_mtime)


def get_photo_date(path: Path, use_exif: bool) -> datetime:
    if use_exif:
        d = get_exif_date(path)
        if d:
            return d
    return get_file_date(path)


def format_folder_name(dt: datetime, pattern: str) -> str:
    """strftime formatını uygular; Türkçe ay adı isteniyorsa değiştirir."""
    result = dt.strftime(pattern)
    if "%B" in pattern:
        # Sistem locale'ine bağlı kalmadan Türkçe ay adı kullan
        result = result.replace(dt.strftime("%B"), TR_MONTHS[dt.month])
    return result


def unique_destination(dest: Path) -> Path:
    """Aynı isimli dosya varsa sonuna (1), (2)... ekler."""
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


class PhotoSorterApp:
    def __init__(self, root):
        self.root = root
        root.title("Foto Tarihe Göre Ayır")
        root.geometry("740x680")
        root.minsize(700, 620)

        self.theme_name = "light"
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.recurse_var = tk.BooleanVar(value=True)
        self.include_video_var = tk.BooleanVar(value=False)
        self.use_exif_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value=list(FORMAT_PRESETS.keys())[0])
        self.custom_format_var = tk.StringVar(value="%Y/%m/%d")
        self.move_var = tk.BooleanVar(value=False)  # False = kopyala, True = taşı
        self.order_var = tk.StringVar(value="Eskiden yeniye")
        self.prefix_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.apply_theme("light")

        if not PIL_AVAILABLE:
            self.log(
                "UYARI: Pillow (PIL) kurulu değil, EXIF tarihi okunamayacak; "
                "dosyaların değiştirilme tarihi kullanılacak.\n"
                "Kurmak için: pip install pillow\n"
            )

    # ---------- Tema ----------
    def toggle_theme(self):
        self.apply_theme("dark" if self.theme_name == "light" else "light")

    def apply_theme(self, name: str):
        self.theme_name = name
        c = THEMES[name]
        s = self.style

        self.root.configure(background=c["bg"])

        s.configure(".", background=c["bg"], foreground=c["fg"],
                    fieldbackground=c["entry_bg"])
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("TLabelframe", background=c["bg"], foreground=c["fg"],
                    bordercolor=c["border"])
        s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        s.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
        s.map("TCheckbutton", background=[("active", c["bg"])],
              foreground=[("active", c["fg"])])
        s.configure("TRadiobutton", background=c["bg"], foreground=c["fg"])
        s.map("TRadiobutton", background=[("active", c["bg"])],
              foreground=[("active", c["fg"])])
        s.configure("TButton", background=c["button_bg"], foreground=c["fg"],
                    bordercolor=c["border"])
        s.map("TButton", background=[("active", c["button_active"])])
        s.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"])
        s.map("Accent.TButton", background=[("active", c["accent"])])
        s.configure("TEntry", fieldbackground=c["entry_bg"], foreground=c["entry_fg"],
                    bordercolor=c["border"])
        s.configure("TCombobox", fieldbackground=c["entry_bg"], foreground=c["entry_fg"],
                    background=c["entry_bg"])
        s.map("TCombobox", fieldbackground=[("readonly", c["entry_bg"])],
              foreground=[("readonly", c["entry_fg"])])
        s.configure("Horizontal.TProgressbar", background=c["accent"],
                    troughcolor=c["entry_bg"], bordercolor=c["border"])

        if hasattr(self, "log_box"):
            self.log_box.configure(
                background=c["log_bg"], foreground=c["log_fg"],
                insertbackground=c["fg"]
            )
        if hasattr(self, "theme_btn"):
            self.theme_btn.configure(
                text="☀️  Gündüz Modu" if name == "dark" else "🌙  Gece Modu"
            )

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Üst bar: başlık + tema düğmesi ---
        frm_top = ttk.Frame(self.root)
        frm_top.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(frm_top, text="Foto Tarihe Göre Ayır", font=("Segoe UI", 13, "bold")).pack(
            side="left"
        )
        self.theme_btn = ttk.Button(frm_top, text="🌙  Gece Modu", command=self.toggle_theme)
        self.theme_btn.pack(side="right")

        frm_paths = ttk.LabelFrame(self.root, text="Klasörler")
        frm_paths.pack(fill="x", **pad)

        ttk.Label(frm_paths, text="Kaynak klasör:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm_paths, textvariable=self.source_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm_paths, text="Seç...", command=self.pick_source).grid(row=0, column=2, **pad)

        ttk.Label(frm_paths, text="Hedef klasör:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm_paths, textvariable=self.dest_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm_paths, text="Seç...", command=self.pick_dest).grid(row=1, column=2, **pad)
        frm_paths.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            frm_paths, text="Alt klasörleri de tara (recursive)",
            variable=self.recurse_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        ttk.Checkbutton(
            frm_paths,
            text="Videoları da dahil et (mp4, mov, avi, mkv, m4v, 3gp, wmv, mts...) "
                 "— videolarda EXIF olmadığından dosya tarihi kullanılır",
            variable=self.include_video_var
        ).grid(row=3, column=0, columnspan=3, sticky="w", **pad)

        # --- Tarih ayarları ---
        frm_date = ttk.LabelFrame(self.root, text="Tarih Ayarları")
        frm_date.pack(fill="x", **pad)

        ttk.Checkbutton(
            frm_date, text="Önce EXIF çekim tarihini kullan (yoksa dosya tarihine düş)",
            variable=self.use_exif_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", **pad)

        ttk.Label(frm_date, text="Klasör formatı:").grid(row=1, column=0, sticky="w", **pad)
        preset_combo = ttk.Combobox(
            frm_date, textvariable=self.preset_var, values=list(FORMAT_PRESETS.keys()),
            state="readonly", width=40
        )
        preset_combo.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        ttk.Label(frm_date, text="Özel format (strftime, / = alt klasör):").grid(
            row=2, column=0, sticky="w", **pad
        )
        self.custom_entry = ttk.Entry(frm_date, textvariable=self.custom_format_var)
        self.custom_entry.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)
        self._on_preset_change()
        frm_date.columnconfigure(1, weight=1)

        # --- Sıralama ---
        frm_sort = ttk.LabelFrame(self.root, text="Sıralama")
        frm_sort.pack(fill="x", **pad)

        ttk.Label(frm_sort, text="İşlem/sıralama yönü:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(
            frm_sort, textvariable=self.order_var,
            values=["Eskiden yeniye", "Yeniden eskiye"],
            state="readonly", width=20
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Checkbutton(
            frm_sort,
            text="Klasör adlarının başına sıra numarası ekle (01 - ..., 02 - ...) "
                 "— alfabetik sıralamayı garanti eder (örn. ay adı kullanırken)",
            variable=self.prefix_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", **pad)

        # --- İşlem seçenekleri ---
        frm_opt = ttk.LabelFrame(self.root, text="İşlem")
        frm_opt.pack(fill="x", **pad)

        ttk.Radiobutton(
            frm_opt, text="Kopyala (kaynak dosyalar kalır)",
            variable=self.move_var, value=False
        ).grid(row=0, column=0, sticky="w", **pad)
        ttk.Radiobutton(
            frm_opt, text="Taşı (kaynak dosyalar silinir)",
            variable=self.move_var, value=True
        ).grid(row=0, column=1, sticky="w", **pad)
        ttk.Checkbutton(
            frm_opt, text="Sadece önizleme yap (dosyaları gerçekten taşıma/kopyalama)",
            variable=self.dry_run_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", **pad)

        # --- Başlat ---
        frm_run = ttk.Frame(self.root)
        frm_run.pack(fill="x", **pad)
        self.run_btn = ttk.Button(frm_run, text="Başlat", command=self.start, style="Accent.TButton")
        self.run_btn.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(frm_run, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)

        # --- Log ---
        frm_log = ttk.LabelFrame(self.root, text="Kayıt")
        frm_log.pack(fill="both", expand=True, **pad)
        self.log_box = scrolledtext.ScrolledText(frm_log, height=14, state="disabled", borderwidth=0)
        self.log_box.pack(fill="both", expand=True)

    def _on_preset_change(self, event=None):
        is_custom = FORMAT_PRESETS[self.preset_var.get()] == "CUSTOM"
        self.custom_entry.configure(state="normal" if is_custom else "disabled")
        if not is_custom:
            self.custom_format_var.set(FORMAT_PRESETS[self.preset_var.get()])

    def pick_source(self):
        d = filedialog.askdirectory(title="Kaynak klasörü seçin")
        if d:
            self.source_var.set(d)
            if not self.dest_var.get():
                self.dest_var.set(str(Path(d) / "Tarihe Göre Ayrılmış"))

    def pick_dest(self):
        d = filedialog.askdirectory(title="Hedef klasörü seçin")
        if d:
            self.dest_var.set(d)

    def log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ---------- İşlem ----------
    def start(self):
        source = self.source_var.get().strip()
        dest = self.dest_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showerror("Hata", "Geçerli bir kaynak klasör seçin.")
            return
        if not dest:
            messagebox.showerror("Hata", "Geçerli bir hedef klasör seçin.")
            return

        pattern = self.custom_format_var.get().strip()
        if not pattern:
            messagebox.showerror("Hata", "Klasör formatı boş olamaz.")
            return

        self.run_btn.configure(state="disabled")
        thread = threading.Thread(
            target=self._run, args=(source, dest, pattern), daemon=True
        )
        thread.start()

    def _run(self, source, dest, pattern):
        source_p = Path(source)
        dest_p = Path(dest)
        use_exif = self.use_exif_var.get()
        recurse = self.recurse_var.get()
        include_video = self.include_video_var.get()
        move = self.move_var.get()
        dry_run = self.dry_run_var.get()
        add_prefix = self.prefix_var.get()
        reverse = self.order_var.get() == "Yeniden eskiye"

        allowed_exts = IMAGE_EXTS | VIDEO_EXTS if include_video else IMAGE_EXTS

        # Dosyaları topla
        files = []
        if recurse:
            it = source_p.rglob("*")
        else:
            it = source_p.glob("*")
        for p in it:
            if p.is_file() and p.suffix.lower() in allowed_exts:
                files.append(p)

        if not files:
            kind = "fotoğraf/video" if include_video else "fotoğraf"
            self.root.after(0, lambda: self.log(f"Kaynak klasörde desteklenen bir {kind} bulunamadı."))
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))
            return

        self.root.after(0, lambda: self.log(f"{len(files)} dosya bulundu, tarih bilgisi okunuyor..."))

        # Her dosya için tarih hesapla
        dated_files = []
        for p in files:
            dt = get_photo_date(p, use_exif)
            dated_files.append((dt, p))

        dated_files.sort(key=lambda t: t[0], reverse=reverse)

        # Sıra numarası isteniyorsa, klasör isimlerini tarih sırasına göre eşle
        folder_order = []
        seen = set()
        for dt, _p in dated_files:
            folder_name = format_folder_name(dt, pattern)
            if folder_name not in seen:
                seen.add(folder_name)
                folder_order.append(folder_name)
        prefix_map = {}
        if add_prefix:
            width = len(str(len(folder_order)))
            for i, name in enumerate(folder_order, start=1):
                prefix_map[name] = f"{str(i).zfill(width)} - {name}"

        total = len(dated_files)
        self.root.after(0, lambda: self.progress.configure(maximum=total, value=0))

        ok, errors = 0, 0
        for i, (dt, p) in enumerate(dated_files, start=1):
            try:
                folder_name = format_folder_name(dt, pattern)
                if add_prefix:
                    folder_name = prefix_map[folder_name]
                # "/" içeren format alt klasörler oluşturur
                target_dir = dest_p.joinpath(*folder_name.split("/"))
                target_path = target_dir / p.name

                if dry_run:
                    self.root.after(0, lambda p=p, t=target_dir: self.log(f"[ÖNİZLEME] {p.name} -> {t}"))
                else:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = unique_destination(target_path)
                    if move:
                        shutil.move(str(p), str(target_path))
                    else:
                        shutil.copy2(str(p), str(target_path))
                    self.root.after(0, lambda p=p, t=target_path: self.log(f"{p.name} -> {t}"))
                ok += 1
            except Exception as e:
                errors += 1
                self.root.after(0, lambda p=p, e=e: self.log(f"HATA ({p.name}): {e}"))

            self.root.after(0, lambda v=i: self.progress.configure(value=v))

        def finish():
            self.log(f"\nTamamlandı. Başarılı: {ok}, Hatalı: {errors}.")
            if dry_run:
                self.log("(Önizleme modundaydı, hiçbir dosya taşınmadı/kopyalanmadı.)")
            self.run_btn.configure(state="normal")

        self.root.after(0, finish)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoSorterApp(root)
    root.mainloop()
