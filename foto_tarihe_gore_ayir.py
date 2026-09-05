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
    pip install pillow customtkinter

Çalıştırma:
    python foto_tarihe_gore_ayir.py
"""

import shutil
import threading
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    from PIL import Image
    from PIL import ExifTags
    PIL_AVAILABLE = True
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

# ---------------------------------------------------------------------------
# Renk paleti — (açık_mod_rengi, koyu_mod_rengi) şeklinde tuple veriliyor;
# customtkinter, set_appearance_mode() çağrıldığında bu renkleri otomatik
# olarak değiştiriyor, biz elle hiçbir widget'ı yeniden boyamıyoruz.
# ---------------------------------------------------------------------------
COLOR_BG = ("#f5f5f8", "#100f17")
COLOR_CARD = ("#ffffff", "#1c1b24")
COLOR_CARD_BORDER = ("#e4e4ec", "#2c2b38")
COLOR_INPUT = ("#eef0f4", "#232230")
COLOR_TEXT = ("#1c1c1e", "#f2f2f5")
COLOR_MUTED = ("#6b6b74", "#9a99a8")
COLOR_ACCENT = ("#3468e0", "#4c8bf5")
COLOR_ACCENT_HOVER = ("#2a55bd", "#3d76d6")
COLOR_BTN2 = ("#e7e9ee", "#2a2935")
COLOR_BTN2_HOVER = ("#dadce3", "#34333f")
COLOR_LOG_BG = ("#fbfbfd", "#15141b")


def get_exif_date(path: Path):
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
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def get_file_date(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def get_photo_date(path: Path, use_exif: bool) -> datetime:
    if use_exif:
        d = get_exif_date(path)
        if d:
            return d
    return get_file_date(path)


def format_folder_name(dt: datetime, pattern: str) -> str:
    result = dt.strftime(pattern)
    if "%B" in pattern:
        result = result.replace(dt.strftime("%B"), TR_MONTHS[dt.month])
    return result


def unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


class Card(ctk.CTkFrame):
    """Görseldeki gibi yuvarlak köşeli, ince kenarlıklı 'kart' paneli."""

    def __init__(self, master, title, **kwargs):
        super().__init__(
            master, corner_radius=14, fg_color=COLOR_CARD,
            border_width=1, border_color=COLOR_CARD_BORDER, **kwargs
        )
        self.grid_columnconfigure(1, weight=1)
        header = ctk.CTkLabel(
            self, text=title, text_color=COLOR_TEXT,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        header.grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 6))
        self._row = 1

    def next_row(self):
        r = self._row
        self._row += 1
        return r


class PhotoSorterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("Foto Tarihe Göre Ayır")
        self.geometry("780x760")
        self.minsize(720, 680)
        self.configure(fg_color=COLOR_BG)

        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.recurse_var = tk.BooleanVar(value=True)
        self.include_video_var = tk.BooleanVar(value=False)
        self.use_exif_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value=list(FORMAT_PRESETS.keys())[0])
        self.custom_format_var = tk.StringVar(value="%Y/%m/%d")
        self.move_var = tk.BooleanVar(value=False)
        self.order_var = tk.StringVar(value="Eskiden yeniye")
        self.prefix_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self._dark = True

        self._build_ui()

        if not PIL_AVAILABLE:
            self.log(
                "UYARI: Pillow (PIL) kurulu değil, EXIF tarihi okunamayacak; "
                "dosyaların değiştirilme tarihi kullanılacak.\n"
                "Kurmak için: pip install pillow\n"
            )

    # ---------- Tema ----------
    def toggle_theme(self):
        self._dark = not self._dark
        ctk.set_appearance_mode("Dark" if self._dark else "Light")
        self.theme_btn.configure(text="☀️  Gündüz Modu" if self._dark else "🌙  Gece Modu")

    # ---------- UI ----------
    def _build_ui(self):
        outer = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG)
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)

        # --- Üst bar ---
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        top.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(top, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box, text="Foto Tarihe Göre Ayır", text_color=COLOR_TEXT,
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, text="Fotoğraf ve videoları çekim tarihine göre klasörlere ayırır",
            text_color=COLOR_MUTED, font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        self.theme_btn = ctk.CTkButton(
            top, text="☀️  Gündüz Modu", command=self.toggle_theme,
            corner_radius=18, fg_color=COLOR_BTN2, hover_color=COLOR_BTN2_HOVER,
            text_color=COLOR_TEXT, font=ctk.CTkFont(size=12, weight="bold"),
            width=140, height=34,
        )
        self.theme_btn.grid(row=0, column=1, sticky="e")

        row = 1

        # --- Klasörler kartı ---
        card = Card(outer, "Klasörler")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
        row += 1

        r = card.next_row()
        ctk.CTkLabel(card, text="Kaynak klasör", text_color=COLOR_MUTED).grid(
            row=r, column=0, sticky="w", padx=16, pady=6)
        ctk.CTkEntry(
            card, textvariable=self.source_var, corner_radius=8,
            fg_color=COLOR_INPUT, border_width=1, border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT
        ).grid(row=r, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(
            card, text="Seç...", command=self.pick_source, width=90, corner_radius=8,
            fg_color=COLOR_BTN2, hover_color=COLOR_BTN2_HOVER, text_color=COLOR_TEXT
        ).grid(row=r, column=2, padx=(6, 16), pady=6)

        r = card.next_row()
        ctk.CTkLabel(card, text="Hedef klasör", text_color=COLOR_MUTED).grid(
            row=r, column=0, sticky="w", padx=16, pady=6)
        ctk.CTkEntry(
            card, textvariable=self.dest_var, corner_radius=8,
            fg_color=COLOR_INPUT, border_width=1, border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT
        ).grid(row=r, column=1, sticky="ew", padx=6, pady=6)
        ctk.CTkButton(
            card, text="Seç...", command=self.pick_dest, width=90, corner_radius=8,
            fg_color=COLOR_BTN2, hover_color=COLOR_BTN2_HOVER, text_color=COLOR_TEXT
        ).grid(row=r, column=2, padx=(6, 16), pady=6)

        r = card.next_row()
        ctk.CTkCheckBox(
            card, text="Alt klasörleri de tara (recursive)", variable=self.recurse_var,
            corner_radius=6, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT, border_color=COLOR_CARD_BORDER
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=(2, 6))

        r = card.next_row()
        ctk.CTkCheckBox(
            card,
            text="Videoları da dahil et (mp4, mov, avi, mkv, m4v, 3gp, wmv, mts...)",
            variable=self.include_video_var,
            corner_radius=6, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT, border_color=COLOR_CARD_BORDER
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 14))

        # --- Tarih ayarları kartı ---
        card = Card(outer, "Tarih Ayarları")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
        row += 1

        r = card.next_row()
        ctk.CTkCheckBox(
            card, text="Önce EXIF çekim tarihini kullan (yoksa dosya tarihine düş)",
            variable=self.use_exif_var,
            corner_radius=6, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT, border_color=COLOR_CARD_BORDER
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=(2, 10))

        r = card.next_row()
        ctk.CTkLabel(card, text="Klasör formatı", text_color=COLOR_MUTED).grid(
            row=r, column=0, sticky="w", padx=16, pady=6)
        self.preset_menu = ctk.CTkOptionMenu(
            card, values=list(FORMAT_PRESETS.keys()), variable=self.preset_var,
            command=self._on_preset_change, corner_radius=8,
            fg_color=COLOR_INPUT, button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD, dropdown_text_color=COLOR_TEXT,
        )
        self.preset_menu.grid(row=r, column=1, columnspan=2, sticky="ew", padx=(6, 16), pady=6)

        r = card.next_row()
        ctk.CTkLabel(card, text="Özel format (strftime, / = alt klasör)", text_color=COLOR_MUTED).grid(
            row=r, column=0, sticky="w", padx=16, pady=(6, 14))
        self.custom_entry = ctk.CTkEntry(
            card, textvariable=self.custom_format_var, corner_radius=8,
            fg_color=COLOR_INPUT, border_width=1, border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT
        )
        self.custom_entry.grid(row=r, column=1, columnspan=2, sticky="ew", padx=(6, 16), pady=(6, 14))
        self._on_preset_change(self.preset_var.get())

        # --- Sıralama kartı ---
        card = Card(outer, "Sıralama")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
        row += 1

        r = card.next_row()
        ctk.CTkLabel(card, text="İşlem/sıralama yönü", text_color=COLOR_MUTED).grid(
            row=r, column=0, sticky="w", padx=16, pady=6)
        ctk.CTkOptionMenu(
            card, values=["Eskiden yeniye", "Yeniden eskiye"], variable=self.order_var,
            corner_radius=8, fg_color=COLOR_INPUT, button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD, dropdown_text_color=COLOR_TEXT, width=180,
        ).grid(row=r, column=1, sticky="w", padx=6, pady=6)

        r = card.next_row()
        ctk.CTkCheckBox(
            card,
            text="Klasör adlarının başına sıra numarası ekle (01 - ..., 02 - ...)",
            variable=self.prefix_var,
            corner_radius=6, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT, border_color=COLOR_CARD_BORDER
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=(6, 14))

        # --- İşlem kartı ---
        card = Card(outer, "İşlem")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
        row += 1

        r = card.next_row()
        radio_box = ctk.CTkFrame(card, fg_color="transparent")
        radio_box.grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=6)
        ctk.CTkRadioButton(
            radio_box, text="Kopyala (kaynak dosyalar kalır)",
            variable=self.move_var, value=False,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT,
            border_color=COLOR_CARD_BORDER,
        ).pack(side="left", padx=(0, 24))
        ctk.CTkRadioButton(
            radio_box, text="Taşı (kaynak dosyalar silinir)",
            variable=self.move_var, value=True,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT,
            border_color=COLOR_CARD_BORDER,
        ).pack(side="left")

        r = card.next_row()
        ctk.CTkCheckBox(
            card, text="Sadece önizleme yap (dosyaları gerçekten taşıma/kopyalama)",
            variable=self.dry_run_var,
            corner_radius=6, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT, border_color=COLOR_CARD_BORDER
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=16, pady=(6, 14))

        # --- Başlat + ilerleme ---
        run_card = ctk.CTkFrame(outer, fg_color="transparent")
        run_card.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
        run_card.grid_columnconfigure(1, weight=1)
        row += 1

        self.run_btn = ctk.CTkButton(
            run_card, text="Başlat", command=self.start, width=140, height=40,
            corner_radius=10, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color="#ffffff", font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.run_btn.grid(row=0, column=0, padx=(0, 12))

        self.progress = ctk.CTkProgressBar(
            run_card, corner_radius=8, fg_color=COLOR_INPUT, progress_color=COLOR_ACCENT
        )
        self.progress.set(0)
        self.progress.grid(row=0, column=1, sticky="ew")

        # --- Log kartı ---
        log_card = Card(outer, "Kayıt")
        log_card.grid(row=row, column=0, sticky="ew", padx=18, pady=(8, 18))
        log_card.grid_columnconfigure(0, weight=1)
        row += 1

        r = log_card.next_row()
        self.log_box = ctk.CTkTextbox(
            log_card, height=220, corner_radius=10, fg_color=COLOR_LOG_BG,
            text_color=COLOR_TEXT, border_width=1, border_color=COLOR_CARD_BORDER,
            wrap="word",
        )
        self.log_box.grid(row=r, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _on_preset_change(self, value=None):
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
        self.progress.set(0)
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

        files = []
        it = source_p.rglob("*") if recurse else source_p.glob("*")
        for p in it:
            if p.is_file() and p.suffix.lower() in allowed_exts:
                files.append(p)

        if not files:
            kind = "fotoğraf/video" if include_video else "fotoğraf"
            self.after(0, lambda: self.log(f"Kaynak klasörde desteklenen bir {kind} bulunamadı."))
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            return

        self.after(0, lambda: self.log(f"{len(files)} dosya bulundu, tarih bilgisi okunuyor..."))

        dated_files = []
        for p in files:
            dt = get_photo_date(p, use_exif)
            dated_files.append((dt, p))

        dated_files.sort(key=lambda t: t[0], reverse=reverse)

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
        ok, errors = 0, 0
        for i, (dt, p) in enumerate(dated_files, start=1):
            try:
                folder_name = format_folder_name(dt, pattern)
                if add_prefix:
                    folder_name = prefix_map[folder_name]
                target_dir = dest_p.joinpath(*folder_name.split("/"))
                target_path = target_dir / p.name

                if dry_run:
                    self.after(0, lambda p=p, t=target_dir: self.log(f"[ÖNİZLEME] {p.name} -> {t}"))
                else:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = unique_destination(target_path)
                    if move:
                        shutil.move(str(p), str(target_path))
                    else:
                        shutil.copy2(str(p), str(target_path))
                    self.after(0, lambda p=p, t=target_path: self.log(f"{p.name} -> {t}"))
                ok += 1
            except Exception as e:
                errors += 1
                self.after(0, lambda p=p, e=e: self.log(f"HATA ({p.name}): {e}"))

            self.after(0, lambda v=i: self.progress.set(v / total))

        def finish():
            self.log(f"\nTamamlandı. Başarılı: {ok}, Hatalı: {errors}.")
            if dry_run:
                self.log("(Önizleme modundaydı, hiçbir dosya taşınmadı/kopyalanmadı.)")
            self.run_btn.configure(state="normal")

        self.after(0, finish)


if __name__ == "__main__":
    app = PhotoSorterApp()
    app.mainloop()
