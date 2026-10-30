#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foto Tarihe Göre Ayır  (PySide6)
================================
Bir klasördeki fotoğrafları (ve isterseniz videoları ve alt klasörlerdekileri)
çekim tarihine (EXIF) veya dosya tarihine göre yeni klasörlere kopyalar/taşır.
Videolarda EXIF bilgisi olmadığından, video dosyaları için dosyanın
değiştirilme tarihi kullanılır.

Sort Photos by Date  (PySide6)
==============================
Copies/moves the photos (optionally videos too, and files in subfolders) of a
folder into new date-based folders using the EXIF capture date or the file
date. Videos have no EXIF, so their file modified date is used.

Gereksinimler / Requirements:
    pip install PySide6 pillow

Çalıştırma / Run:
    python foto_tarihe_gore_ayir.py
"""

import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QObject, QRectF, QSettings, QSize, Qt, QThread, Signal, Slot,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPalette, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QVBoxLayout, QWidget,
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # Pillow yoksa dosya tarihine düşülür
    PIL_AVAILABLE = False

APP_TITLE = "Foto Tarihe Göre Ayır"
APP_VERSION = "1.5.0"
SETTINGS_ORG = "BuRsTFiRe47"
SETTINGS_APP = "FotoTariheGoreAyir"

PHOTO_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".tif", ".tiff",
    ".bmp", ".gif", ".webp", ".raw", ".cr2", ".cr3", ".nef", ".arw",
    ".dng", ".orf", ".rw2", ".raf", ".pef", ".srw",
}
VIDEO_EXTS = {
    ".mp4", ".mpeg", ".mpg", ".avi", ".mkv", ".m4v", ".3gp", ".wmv",
    ".flv", ".webm", ".mts", ".m2ts", ".mov", ".vob", ".ogv",
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
# Temalar / Themes
# ---------------------------------------------------------------------------
THEMES = {
    "dark": {
        "bg": "#100f17", "card": "#1c1b24", "border": "#2c2b38",
        "border_strong": "#4a4960", "input": "#232230", "text": "#f2f2f5",
        "muted": "#9a99a8", "disabled": "#5f5e6e", "accent": "#4c8bf5",
        "accent_hover": "#3d76d6", "btn": "#2a2935", "btn_hover": "#34333f",
        "log": "#15141b",
    },
    "light": {
        "bg": "#f5f5f8", "card": "#ffffff", "border": "#e4e4ec",
        "border_strong": "#b9bbc6", "input": "#eef0f4", "text": "#1c1c1e",
        "muted": "#6b6b74", "disabled": "#a3a4ae", "accent": "#3468e0",
        "accent_hover": "#2a55bd", "btn": "#e7e9ee", "btn_hover": "#dadce3",
        "log": "#fbfbfd",
    },
}


class Theme:
    name = "dark"

    @classmethod
    def c(cls) -> dict:
        return THEMES[cls.name]


QSS_TEMPLATE = """
QMainWindow, QWidget#root, QScrollArea, QScrollArea > QWidget > QWidget#body {
    background: @bg@;
}
QScrollArea { border: none; }
QLabel { background: transparent; color: @text@; }
QLabel#title { font-size: 21px; font-weight: 700; }
QLabel#cardTitle { font-size: 14px; font-weight: 700; }
QLabel#muted { color: @muted@; }
QLabel#hint { color: @muted@; font-size: 12px; }

QFrame#card {
    background: @card@; border: 1px solid @border@; border-radius: 14px;
}
QFrame#bar {
    background: @card@; border: none; border-top: 1px solid @border@;
}

QLineEdit {
    background: @input@; color: @text@; border: 1px solid @border@;
    border-radius: 8px; padding: 7px 10px;
    selection-background-color: @accent@; selection-color: #ffffff;
}
QLineEdit:focus { border: 1px solid @accent@; }
QLineEdit:disabled { color: @disabled@; }

QComboBox {
    background: @input@; color: @text@; border: 1px solid @border@;
    border-radius: 8px; padding: 7px 34px 7px 10px;
}
QComboBox:hover, QComboBox:focus { border: 1px solid @accent@; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: @card@; color: @text@; border: 1px solid @border@;
    border-radius: 8px; padding: 4px; outline: 0;
    selection-background-color: @accent@; selection-color: #ffffff;
}

QPushButton {
    background: @btn@; color: @text@; border: none; border-radius: 8px;
    padding: 8px 16px;
}
QPushButton:hover { background: @btn_hover@; }
QPushButton:disabled { color: @disabled@; }
QPushButton#primary {
    background: @accent@; color: #ffffff; font-weight: 700;
    font-size: 14px; border-radius: 10px; padding: 10px 30px;
}
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @border_strong@; color: #ffffff; }
QPushButton#theme { border-radius: 16px; padding: 0 18px; font-weight: 600; }

QProgressBar {
    background: @input@; border: none; border-radius: 6px;
    min-height: 12px; max-height: 12px;
}
QProgressBar::chunk { background: @accent@; border-radius: 6px; }

QPlainTextEdit#log {
    background: @log@; color: @text@; border: 1px solid @border@;
    border-radius: 10px; padding: 8px;
    selection-background-color: @accent@; selection-color: #ffffff;
}

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical {
    background: @border_strong@; border-radius: 4px; min-height: 36px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip {
    background: @card@; color: @text@; border: 1px solid @border@; padding: 4px;
}
"""


def build_qss(t: dict) -> str:
    qss = QSS_TEMPLATE
    for key, value in t.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def build_palette(t: dict) -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.Window: t["bg"], QPalette.WindowText: t["text"],
        QPalette.Base: t["input"], QPalette.AlternateBase: t["card"],
        QPalette.Text: t["text"], QPalette.Button: t["btn"],
        QPalette.ButtonText: t["text"], QPalette.Highlight: t["accent"],
        QPalette.HighlightedText: "#ffffff", QPalette.ToolTipBase: t["card"],
        QPalette.ToolTipText: t["text"], QPalette.PlaceholderText: t["muted"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["disabled"]))
    return pal


# ---------------------------------------------------------------------------
# Çekirdek mantık / Core logic
# ---------------------------------------------------------------------------
def _parse_exif_dt(raw) -> Optional[datetime]:
    if isinstance(raw, bytes):
        raw = raw.decode(errors="ignore")
    raw = str(raw).strip().strip("\x00")[:19]
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def get_exif_date(path: Path) -> Optional[datetime]:
    """Çekim tarihini EXIF'ten okur (DateTimeOriginal -> Digitized -> DateTime)."""
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            candidates = []
            try:
                sub = exif.get_ifd(0x8769)  # Exif alt dizini
                candidates += [sub.get(36867), sub.get(36868)]
            except Exception:
                pass
            candidates.append(exif.get(306))
            for raw in candidates:
                if raw:
                    dt = _parse_exif_dt(raw)
                    if dt and dt.year > 1970:
                        return dt
    except Exception:
        return None
    return None


def get_item_date(path: Path, use_exif: bool) -> datetime:
    if use_exif and path.suffix.lower() in PHOTO_EXTS:
        d = get_exif_date(path)
        if d:
            return d
    return datetime.fromtimestamp(path.stat().st_mtime)


def format_folder_name(dt: datetime, pattern: str) -> str:
    # %B için sistem diline bağlı kalmadan Türkçe ay adı kullan
    return dt.strftime(pattern.replace("%B", TR_MONTHS[dt.month]))


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


def already_in_place(src: Path, target: Path) -> bool:
    """Hedefte aynı dosya zaten varsa True (aynı dosya veya aynı boyut + değiştirilme zamanı).
    Böylece aynı klasörü tekrar çalıştırmak '(1)' kopyaları üretmez."""
    try:
        if os.path.samefile(src, target):
            return True
        a, b = src.stat(), target.stat()
        return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) < 2
    except OSError:
        return False


def _norm(path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


@dataclass
class SortConfig:
    source: str
    dest: str
    pattern: str
    category: str
    exts: Optional[frozenset]
    recurse: bool
    use_exif: bool
    move: bool
    dry_run: bool
    prefix: bool
    reverse: bool


class SortWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    done = Signal(int, int, int, bool, bool)  # ok, hata, atlanan, önizleme, durduruldu

    def __init__(self, cfg: SortConfig):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _collect(self):
        cfg = self.cfg
        src, dest = _norm(cfg.source), _norm(cfg.dest)
        # Hedef klasör kaynağın içindeyse, önceki çalıştırmaların çıktısını tekrar tarama
        prune = dest != src and dest.startswith(src + os.sep)

        def matches(p: Path) -> bool:
            return cfg.exts is None or p.suffix.lower() in cfg.exts

        files = []
        if cfg.recurse:
            for root, dirs, names in os.walk(cfg.source):
                if prune:
                    dirs[:] = [d for d in dirs if _norm(Path(root, d)) != dest
                               and not _norm(Path(root, d)).startswith(dest + os.sep)]
                for name in names:
                    p = Path(root, name)
                    if matches(p):
                        files.append(p)
        else:
            for entry in os.scandir(cfg.source):
                p = Path(entry.path)
                if entry.is_file() and matches(p):
                    files.append(p)
        return files

    @Slot()
    def run(self):
        cfg = self.cfg
        ok = err = skipped = 0
        try:
            files = self._collect()
            if not files:
                self.log.emit(f"Kaynak klasörde desteklenen bir {cfg.category.lower()} bulunamadı.")
                self.done.emit(0, 0, 0, cfg.dry_run, False)
                return

            self.log.emit(f"{len(files)} dosya bulundu, tarih bilgisi okunuyor…")
            dated = []
            for p in files:
                if self._cancel:
                    break
                try:
                    dated.append((get_item_date(p, cfg.use_exif), p))
                except OSError as e:
                    err += 1
                    self.log.emit(f"HATA ({p.name}): {e}")
            if self._cancel:
                self.log.emit("Durduruldu.")
                self.done.emit(ok, err, skipped, cfg.dry_run, True)
                return

            dated.sort(key=lambda t: (t[0], str(t[1])), reverse=cfg.reverse)

            prefix_map = {}
            if cfg.prefix:
                order, seen = [], set()
                for dt, _p in dated:
                    name = format_folder_name(dt, cfg.pattern)
                    if name not in seen:
                        seen.add(name)
                        order.append(name)
                width = len(str(len(order)))
                prefix_map = {n: f"{str(i).zfill(width)} - {n}" for i, n in enumerate(order, 1)}

            total = len(dated)
            dest_p = Path(cfg.dest)
            cancelled = False
            for i, (dt, p) in enumerate(dated, 1):
                if self._cancel:
                    cancelled = True
                    self.log.emit("Durduruldu.")
                    break
                try:
                    folder = format_folder_name(dt, cfg.pattern)
                    if cfg.prefix:
                        folder = prefix_map[folder]
                    parts = [x for x in folder.replace("\\", "/").split("/") if x]
                    target_dir = dest_p.joinpath(*parts)
                    target = target_dir / p.name

                    if cfg.dry_run:
                        self.log.emit(f"[ÖNİZLEME] {p.name}  →  {target_dir}")
                    else:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        if target.exists() and already_in_place(p, target):
                            skipped += 1
                            self.log.emit(f"{p.name}  (hedefte zaten var, atlandı)")
                            self.progress.emit(i, total)
                            continue
                        target = unique_destination(target)
                        if cfg.move:
                            shutil.move(str(p), str(target))
                        else:
                            shutil.copy2(str(p), str(target))
                        self.log.emit(f"{p.name}  →  {target}")
                    ok += 1
                except Exception as e:  # tek dosya hatası tüm işlemi durdurmasın
                    err += 1
                    self.log.emit(f"HATA ({p.name}): {e}")
                self.progress.emit(i, total)
            self.done.emit(ok, err, skipped, cfg.dry_run, cancelled)
        except Exception as e:
            self.log.emit(f"BEKLENMEYEN HATA: {e}")
            self.done.emit(ok, err + 1, skipped, cfg.dry_run, False)


# ---------------------------------------------------------------------------
# Özel bileşenler / Custom widgets
# ---------------------------------------------------------------------------
class ModernCheckBox(QCheckBox):
    SIZE = 20

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(text)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.SIZE + 12 + fm.horizontalAdvance(self.text()) + 6,
                     max(self.SIZE, fm.height()) + 8)

    def minimumSizeHint(self):
        return QSize(self.SIZE + 60, self.sizeHint().height())

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        t = Theme.c()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1.5, (self.height() - self.SIZE) / 2, self.SIZE, self.SIZE)
        enabled = self.isEnabled()
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent"] if enabled else t["border_strong"]))
        else:
            hot = enabled and (self.underMouse() or self.hasFocus())
            p.setPen(QPen(QColor(t["accent"] if hot else t["border_strong"]), 1.5))
            p.setBrush(QColor(t["input"]))
        p.drawRoundedRect(box, 6, 6)
        if self.isChecked():
            pen = QPen(QColor("#ffffff"), 2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(box.left() + 5.2, box.top() + 10.4)
            path.lineTo(box.left() + 8.6, box.top() + 13.8)
            path.lineTo(box.left() + 14.8, box.top() + 6.6)
            p.drawPath(path)
        p.setPen(QColor(t["text"] if enabled else t["disabled"]))
        text_w = self.width() - self.SIZE - 12
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, max(text_w, 10))
        p.drawText(QRectF(self.SIZE + 12, 0, text_w, self.height()),
                   int(Qt.AlignVCenter | Qt.AlignLeft), text)


class ModernRadio(QRadioButton):
    SIZE = 20

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.SIZE + 12 + fm.horizontalAdvance(self.text()) + 6,
                     max(self.SIZE, fm.height()) + 8)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        t = Theme.c()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1.5, (self.height() - self.SIZE) / 2, self.SIZE, self.SIZE)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent"]))
            p.drawEllipse(box)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(box.center(), 4.2, 4.2)
        else:
            hot = self.underMouse() or self.hasFocus()
            p.setPen(QPen(QColor(t["accent"] if hot else t["border_strong"]), 1.5))
            p.setBrush(QColor(t["input"]))
            p.drawEllipse(box)
        p.setPen(QColor(t["text"]))
        p.drawText(QRectF(self.SIZE + 12, 0, self.width() - self.SIZE - 12, self.height()),
                   int(Qt.AlignVCenter | Qt.AlignLeft), self.text())


class ChevronCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setMaxVisibleItems(12)
        self.setCursor(Qt.PointingHandCursor)

    def wheelEvent(self, event):  # kaydırırken yanlışlıkla seçim değişmesin
        event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(Theme.c()["muted"]), 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        cx, cy = self.width() - 18, self.height() / 2
        path = QPainterPath()
        path.moveTo(cx - 4, cy - 2)
        path.lineTo(cx, cy + 2)
        path.lineTo(cx + 4, cy - 2)
        p.drawPath(path)


class FolderLineEdit(QLineEdit):
    """Klasör (veya dosya) sürükleyip bırakmayı destekleyen giriş kutusu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Seçin veya klasörü buraya sürükleyin…")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            self.setText(str(path if path.is_dir() else path.parent))


class Card(QFrame):
    LABEL_W = 130

    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(18, 16, 18, 18)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(1, 1)
        head = QLabel(title)
        head.setObjectName("cardTitle")
        self.grid.addWidget(head, 0, 0, 1, 3)
        self._r = 1

    def row(self, label: str, field: QWidget, button: Optional[QWidget] = None):
        lab = QLabel(label)
        lab.setObjectName("muted")
        lab.setMinimumWidth(self.LABEL_W)
        self.grid.addWidget(lab, self._r, 0)
        if button is None:
            self.grid.addWidget(field, self._r, 1, 1, 2)
        else:
            self.grid.addWidget(field, self._r, 1)
            self.grid.addWidget(button, self._r, 2)
        self._r += 1

    def wide(self, widget: QWidget):
        self.grid.addWidget(widget, self._r, 0, 1, 3)
        self._r += 1


# ---------------------------------------------------------------------------
# Ana pencere / Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._thread: Optional[QThread] = None
        self._worker: Optional[SortWorker] = None
        self._running = False

        self.setWindowTitle(f"{APP_TITLE}  v{APP_VERSION}")
        self.resize(820, 900)
        self.setMinimumSize(700, 560)

        self._build_ui()
        saved = self.settings.value("theme", "dark")
        self.apply_theme(saved if saved in THEMES else "dark")

        if not PIL_AVAILABLE:
            self.append_log("UYARI: Pillow kurulu değil, EXIF okunamayacak; dosya tarihi kullanılacak. "
                            "Kurmak için: pip install pillow")

    # ----- tema -----
    def apply_theme(self, name: str):
        Theme.name = name
        t = Theme.c()
        app = QApplication.instance()
        app.setPalette(build_palette(t))
        app.setStyleSheet(build_qss(t))
        self.theme_btn.setText("☀  Gündüz Modu" if name == "dark" else "☾  Gece Modu")
        self.settings.setValue("theme", name)
        for w in self.findChildren(QWidget):
            w.update()

    def toggle_theme(self):
        self.apply_theme("light" if Theme.name == "dark" else "dark")

    # ----- arayüz -----
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Üst bar
        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 24, 10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(APP_TITLE)
        title.setObjectName("title")
        sub = QLabel("Fotoğraf ve videoları çekim tarihine göre klasörlere ayırır")
        sub.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(sub)
        header.addLayout(titles, 1)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("theme")
        self.theme_btn.setFixedHeight(34)  # QSS yarıçapı yükseklikten büyük olursa köşe yuvarlanmaz
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn, 0, Qt.AlignVCenter)
        outer.addLayout(header)

        # Kaydırılabilir kartlar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("body")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(24, 6, 24, 20)
        body.setSpacing(14)
        scroll.setWidget(self.body)
        outer.addWidget(scroll, 1)

        # -- Klasörler --
        card = Card("Klasörler")
        self.source_edit = FolderLineEdit()
        self.dest_edit = FolderLineEdit()
        b1, b2 = QPushButton("Seç…"), QPushButton("Seç…")
        for b in (b1, b2):
            b.setCursor(Qt.PointingHandCursor)
        b1.clicked.connect(self.pick_source)
        b2.clicked.connect(self.pick_dest)
        card.row("Kaynak klasör", self.source_edit, b1)
        card.row("Hedef klasör", self.dest_edit, b2)
        self.recurse_cb = ModernCheckBox("Alt klasörleri de tara (recursive)")
        self.recurse_cb.setChecked(True)
        card.wide(self.recurse_cb)
        self.video_cb = ModernCheckBox("Videoları da dahil et (mp4, mov, avi, mkv, 3gp, wmv, mts…)")
        card.wide(self.video_cb)
        video_hint = QLabel("Videolarda EXIF bilgisi olmadığından dosya tarihi kullanılır.")
        video_hint.setObjectName("hint")
        card.wide(video_hint)
        body.addWidget(card)

        # -- Tarih ayarları --
        card = Card("Tarih Ayarları")
        self.exif_cb = ModernCheckBox("Önce EXIF çekim tarihini kullan (yoksa dosya tarihine düş)")
        self.exif_cb.setChecked(True)
        card.wide(self.exif_cb)
        self.preset_combo = ChevronCombo()
        self.preset_combo.addItems(list(FORMAT_PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self._on_preset_change)
        card.row("Klasör formatı", self.preset_combo)
        self.custom_edit = QLineEdit("%Y/%m/%d")
        self.custom_edit.setPlaceholderText("%Y/%m/%d   —   / ile alt klasör açılır")
        self.custom_edit.textChanged.connect(self._update_example)
        card.row("Özel format", self.custom_edit)
        self.example_label = QLabel()
        self.example_label.setObjectName("hint")
        card.wide(self.example_label)
        body.addWidget(card)

        # -- Sıralama --
        card = Card("Sıralama")
        self.order_combo = ChevronCombo()
        self.order_combo.addItems(["Eskiden yeniye", "Yeniden eskiye"])
        card.row("İşlem yönü", self.order_combo)
        self.prefix_cb = ModernCheckBox("Klasör adlarının başına sıra numarası ekle (01 - …, 02 - …)")
        card.wide(self.prefix_cb)
        body.addWidget(card)

        # -- İşlem --
        card = Card("İşlem")
        radios = QHBoxLayout()
        radios.setSpacing(28)
        self.copy_radio = ModernRadio("Kopyala (kaynak dosyalar kalır)")
        self.move_radio = ModernRadio("Taşı (kaynak dosyalar silinir)")
        self.copy_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.copy_radio)
        group.addButton(self.move_radio)
        radios.addWidget(self.copy_radio)
        radios.addWidget(self.move_radio)
        radios.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(radios)
        radios.setContentsMargins(0, 0, 0, 0)
        card.wide(wrap)
        self.dry_cb = ModernCheckBox("Sadece önizleme yap (dosyaları gerçekten taşıma/kopyalama)")
        card.wide(self.dry_cb)
        body.addWidget(card)

        # -- Kayıt --
        card = Card("Kayıt")
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("log")
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(5000)
        self.log_box.setMinimumHeight(190)
        card.wide(self.log_box)
        body.addWidget(card)
        body.addStretch(1)

        # Alt çubuk: Başlat / ilerleme (her zaman görünür)
        bar = QFrame()
        bar.setObjectName("bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(24, 12, 24, 12)
        bl.setSpacing(14)
        self.run_btn = QPushButton("Başlat")
        self.run_btn.setObjectName("primary")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_run_clicked)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.status_label.setMinimumWidth(90)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bl.addWidget(self.run_btn)
        bl.addWidget(self.progress, 1)
        bl.addWidget(self.status_label)
        outer.addWidget(bar)

        self._on_preset_change(self.preset_combo.currentText())

    # ----- olaylar -----
    def _on_preset_change(self, label: str):
        pattern = FORMAT_PRESETS.get(label, "CUSTOM")
        is_custom = pattern == "CUSTOM"
        self.custom_edit.setEnabled(is_custom)
        if not is_custom:
            self.custom_edit.setText(pattern)
        self._update_example()

    def _update_example(self, *_):
        pattern = self.custom_edit.text().strip()
        if not pattern:
            self.example_label.setText("Örnek klasör: —")
            return
        try:
            example = format_folder_name(datetime.now(), pattern)
            self.example_label.setText(f"Örnek klasör:  {example}")
        except (ValueError, KeyError):
            self.example_label.setText("Örnek klasör: geçersiz format")

    def pick_source(self):
        d = QFileDialog.getExistingDirectory(self, "Kaynak klasörü seçin", self.source_edit.text())
        if d:
            self.source_edit.setText(d)
            if not self.dest_edit.text():
                self.dest_edit.setText(str(Path(d) / "Tarihe Göre Ayrılmış"))

    def pick_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Hedef klasörü seçin", self.dest_edit.text())
        if d:
            self.dest_edit.setText(d)

    def append_log(self, msg: str):
        self.log_box.appendPlainText(msg)

    # ----- işlem -----
    def on_run_clicked(self):
        if self._running:
            if self._worker:
                self._worker.cancel()
            self.run_btn.setEnabled(False)
            self.run_btn.setText("Durduruluyor…")
            return
        self.start()

    def start(self):
        source = self.source_edit.text().strip()
        dest = self.dest_edit.text().strip()
        pattern = self.custom_edit.text().strip()
        if not source or not Path(source).is_dir():
            QMessageBox.warning(self, "Hata", "Geçerli bir kaynak klasör seçin.")
            return
        if not dest:
            QMessageBox.warning(self, "Hata", "Geçerli bir hedef klasör seçin.")
            return
        if not pattern:
            QMessageBox.warning(self, "Hata", "Klasör formatı boş olamaz.")
            return
        try:
            format_folder_name(datetime.now(), pattern)
        except (ValueError, KeyError):
            QMessageBox.warning(self, "Hata", "Klasör formatı geçersiz.")
            return

        move = self.move_radio.isChecked()
        dry = self.dry_cb.isChecked()
        if move and not dry:
            answer = QMessageBox.question(
                self, "Onay",
                "Dosyalar kaynak klasörden TAŞINACAK (kaynakta kalmayacak).\nDevam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return

        with_video = self.video_cb.isChecked()
        exts = PHOTO_EXTS | VIDEO_EXTS if with_video else PHOTO_EXTS
        cfg = SortConfig(
            source=source, dest=dest, pattern=pattern,
            category="Fotoğraf + Video" if with_video else "Fotoğraf",
            exts=frozenset(exts),
            recurse=self.recurse_cb.isChecked(),
            use_exif=self.exif_cb.isChecked(),
            move=move, dry_run=dry, prefix=self.prefix_cb.isChecked(),
            reverse=self.order_combo.currentText() == "Yeniden eskiye",
        )

        self._running = True
        self.run_btn.setText("Durdur")
        self.progress.setValue(0)
        self.status_label.setText("Hazırlanıyor…")

        if self._thread is not None:  # önceki çalıştırmanın iş parçacığını serbest bırak
            self._thread.deleteLater()
        self._thread = QThread(self)
        self._worker = SortWorker(cfg)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.append_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.done.connect(self.on_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    @Slot(int, int)
    def on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.status_label.setText(f"{done} / {total}")

    @Slot(int, int, int, bool, bool)
    def on_done(self, ok: int, err: int, skipped: int, dry: bool, cancelled: bool):
        head = "Durduruldu" if cancelled else "Tamamlandı"
        extra = f", Atlanan: {skipped}" if skipped else ""
        self.append_log(f"\n{head}. Başarılı: {ok}, Hatalı: {err}{extra}.")
        if dry:
            self.append_log("(Önizleme modundaydı, hiçbir dosya taşınmadı/kopyalanmadı.)")
        self._running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Başlat")
        if not cancelled and self.progress.maximum() > 0:
            self.progress.setValue(self.progress.maximum())

    def closeEvent(self, event):
        if self._running and self._worker:
            self._worker.cancel()
            if self._thread:
                self._thread.quit()
                self._thread.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue",
                      "Inter", "Roboto", "Noto Sans", "DejaVu Sans"])
    font.setPixelSize(13)
    app.setFont(font)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
