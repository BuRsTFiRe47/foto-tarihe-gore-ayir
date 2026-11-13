#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foto Tarihe Göre Ayır  (PySide6)
================================
Bir klasördeki fotoğrafları (ve isterseniz videoları ve alt klasörlerdekileri)
çekim tarihine (EXIF) veya dosya tarihine göre yeni klasörlere kopyalar/taşır.
Videolarda EXIF bilgisi olmadığından, video dosyaları için dosyanın
değiştirilme tarihi kullanılır.

İki sekme / Two tabs:
  1) Tarihe Göre Ayır      — tarih formatına göre klasörlere böler
  2) Adlandır ve Arşivle   — YIL-AYGÜN_cihaz-yer klasörleri + YIL-AYGÜN_SAATDAKİKASANİYE.jpg
     adları; EXIF yoksa dosya adından (IMG2026…, VID2026…) tarih; video UTC → yerel saat;
     bulunan/yaklaşık tarihi EXIF'e yazma.

Sort Photos by Date  (PySide6)
==============================
Copies/moves the photos (optionally videos too, and files in subfolders) of a
folder into new date-based folders using the EXIF capture date or the file
date. The second tab renames files by date and builds "date_device-place"
folders, recovers dates from file names and converts video UTC time to local.

Gereksinimler / Requirements:
    pip install PySide6 pillow piexif

Çalıştırma / Run:
    python foto_tarihe_gore_ayir.py
"""

import os
import re
import shutil
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QDateTime, QObject, QRectF, QSettings, QSize, Qt, QThread, Signal, Slot,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPalette, QPen,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QStackedWidget, QButtonGroup, QCheckBox, QComboBox, QDateTimeEdit,
    QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # Pillow yoksa dosya tarihine düşülür
    PIL_AVAILABLE = False

try:
    import piexif  # EXIF'e yeniden sıkıştırmadan tarih yazmak için (isteğe bağlı)
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

from app_icon import app_icon  # gömülü uygulama simgesi (tools/make_icon.py)
from breeze import (  # ortak Breeze teması (koyu arduvaz + mercan vurgu)
    PALETTES, PathField, Check, Combo, Radio, build_palette, build_qss,
)

APP_TITLE = "Foto Tarihe Göre Ayır"
APP_VERSION = "1.6.1"
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


def _same_tail(a: Path, b: Path, n: int = 8192) -> bool:
    """İki dosyanın son baytları aynı mı? (EXIF eklenince yalnızca baş kısım değişir.)"""
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            fa.seek(0, os.SEEK_END)
            fb.seek(0, os.SEEK_END)
            k = min(n, fa.tell() // 2, fb.tell() // 2)
            fa.seek(-k, os.SEEK_END)
            fb.seek(-k, os.SEEK_END)
            return fa.read(k) == fb.read(k)
    except OSError:
        return False


def already_in_place(src: Path, target: Path, ignore_size: bool = False) -> bool:
    """Hedefte aynı dosya zaten varsa True (aynı dosya veya aynı boyut + değiştirilme zamanı).
    Böylece aynı klasörü tekrar çalıştırmak '(1)' kopyaları üretmez.
    ignore_size: hedefe EXIF yazıldığı için boyut biraz büyümüş olabilir; bu durumda
    boyut farkı toleranslıdır ve dosya sonu karşılaştırılır (farklı fotoğraflar karışmasın)."""
    try:
        if os.path.samefile(src, target):
            return True
        a, b = src.stat(), target.stat()
        if abs(a.st_mtime - b.st_mtime) >= 2:
            return False
        if a.st_size == b.st_size:
            return True
        return ignore_size and 0 < b.st_size - a.st_size <= 256 * 1024 and _same_tail(src, target)
    except OSError:
        return False


def find_existing_copy(src: Path, target: Path, ignore_size: bool = False) -> bool:
    """Hedefte ya da 'ad (1)', 'ad (2)'… varyantlarında aynı dosya var mı?"""
    cand, n = target, 0
    while cand.exists():
        if already_in_place(src, cand, ignore_size):
            return True
        n += 1
        cand = target.with_name(f"{target.stem} ({n}){target.suffix}")
    return False


def _norm(path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))

def collect_files(source: str, dest: str, recurse: bool, exts) -> list:
    """Kaynaktaki dosyaları toplar. Hedef kaynağın içindeyse önceki çıktıyı taramaz."""
    src, dst = _norm(source), _norm(dest)
    prune = dst != src and dst.startswith(src + os.sep)

    def matches(p: Path) -> bool:
        return exts is None or p.suffix.lower() in exts

    files = []
    if recurse:
        for root, dirs, names in os.walk(source):
            if prune:
                dirs[:] = [d for d in dirs if _norm(Path(root, d)) != dst
                           and not _norm(Path(root, d)).startswith(dst + os.sep)]
            for name in names:
                p = Path(root, name)
                if matches(p):
                    files.append(p)
    else:
        for entry in os.scandir(source):
            p = Path(entry.path)
            if entry.is_file() and matches(p):
                files.append(p)
    return files


# ---------------------------------------------------------------------------
# Tarih çözümleme (2. sekme) / Date resolution (2nd tab)
# ---------------------------------------------------------------------------
VIDEO_META_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".3g2"}  # 'mvhd' kutusu okunabilen biçimler
_MAC_EPOCH = datetime(1904, 1, 1)


def _iter_boxes(f, pos: int, end: int):
    """MP4/QuickTime kutularını (atom) sırayla gezer: (tür, veri_başı, kutu_sonu)."""
    while pos + 8 <= end:
        f.seek(pos)
        head = f.read(8)
        if len(head) < 8:
            return
        size, kind = struct.unpack(">I4s", head)
        hdr = 8
        if size == 1:  # 64 bit boyut
            ext = f.read(8)
            if len(ext) < 8:
                return
            size, hdr = struct.unpack(">Q", ext)[0], 16
        elif size == 0:  # dosya sonuna kadar
            size = end - pos
        if size < hdr:
            return
        yield kind, pos + hdr, min(pos + size, end)
        pos += size


def read_video_creation_utc(path: Path) -> Optional[datetime]:
    """MP4/MOV/3GP dosyasının 'moov/mvhd' kutusundaki oluşturma zamanını (UTC) okur."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            for kind, s0, e0 in _iter_boxes(f, 0, end):
                if kind != b"moov":
                    continue
                for k2, s2, _e2 in _iter_boxes(f, s0, e0):
                    if k2 != b"mvhd":
                        continue
                    f.seek(s2)
                    vf = f.read(4)
                    if len(vf) < 4:
                        return None
                    if vf[0] == 1:
                        secs = struct.unpack(">Q", f.read(8))[0]
                    else:
                        secs = struct.unpack(">I", f.read(4))[0]
                    if secs == 0:
                        return None
                    dt = _MAC_EPOCH + timedelta(seconds=secs)
                    return dt if 1990 <= dt.year <= datetime.now().year + 1 else None
                return None
    except Exception:
        return None
    return None


# IMG20261029141449 · VID20261029224307 · IMG_20261029_141449 · PXL_20261029_141449123 ·
# 2026-10-29 14.14.49 · 2026-10-29 at 14.14.49 · 20261029-141449
_NAME_FULL = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(\d{2})[-_.]?(\d{2})"
    r"(?:[\sT_.\-]|\sat\s)*(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})(?:\d{3})?(?!\d)", re.I)
# IMG-20261029-WA0001 gibi yalnızca gün içerenler
_NAME_DAY = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)")


def parse_name_date(name: str):
    """Dosya adından tarih çıkarır -> (datetime, saat_kesin_mi) ya da None."""
    stem = Path(name).stem
    last_year = datetime.now().year + 1
    for m in _NAME_FULL.finditer(stem):
        try:
            dt = datetime(*(int(x) for x in m.groups()))
        except ValueError:
            continue
        if 1990 <= dt.year <= last_year:
            return dt, True
    for m in _NAME_DAY.finditer(stem):
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, 0)
        except ValueError:
            continue
        if 1990 <= dt.year <= last_year:
            return dt, False
    return None


@dataclass
class DateOptions:
    use_exif: bool = True          # EXIF (foto) / mvhd (video)
    from_filename: bool = True     # EXIF yoksa dosya adından
    video_utc: bool = True         # video tarihi UTC kayıtlı -> yerel saate çevir
    tz_hours: float = 3.0          # UTC farkı (Türkiye = +3)
    fallback: str = "mtime"        # "mtime" | "manual" | "skip"
    manual_dt: Optional[datetime] = None


@dataclass
class DateResult:
    dt: datetime
    kind: str       # "exif" | "video" | "name" | "approx"
    label: str      # günlükte gösterilecek kaynak açıklaması
    approx: bool


def resolve_date(path: Path, o: DateOptions) -> Optional[DateResult]:
    """EXIF/video -> dosya adı -> yaklaşık (dosya tarihi / elle) sırasıyla tarih bulur."""
    suffix = path.suffix.lower()
    if o.use_exif:
        if suffix in PHOTO_EXTS:
            d = get_exif_date(path)
            if d:
                return DateResult(d, "exif", "EXIF", False)
        elif suffix in VIDEO_META_EXTS:
            d = read_video_creation_utc(path)
            if d:
                if o.video_utc:
                    d += timedelta(hours=o.tz_hours)
                    return DateResult(d, "video", f"video, UTC{o.tz_hours:+g} saate çevrildi", False)
                return DateResult(d, "video", "video", False)
    if o.from_filename:
        r = parse_name_date(path.name)
        if r:
            dt, precise = r
            return DateResult(dt, "name", "dosya adı" if precise else "dosya adı, yalnız gün (saat yaklaşık)",
                              not precise)
    if o.fallback == "mtime":
        return DateResult(datetime.fromtimestamp(path.stat().st_mtime), "approx",
                          "yaklaşık: dosya tarihi", True)
    if o.fallback == "manual" and o.manual_dt:
        return DateResult(o.manual_dt, "approx", "yaklaşık: elle girilen tarih", True)
    return None


def write_exif_date(path: Path, dt: datetime) -> bool:
    """JPEG'e yeniden sıkıştırmadan çekim tarihini yazar (piexif). Başarılıysa True."""
    if not PIEXIF_AVAILABLE or path.suffix.lower() not in (".jpg", ".jpeg", ".jpe"):
        return False
    try:
        stamp = dt.strftime("%Y:%m:%d %H:%M:%S").encode()
        try:
            exif = piexif.load(str(path))
        except Exception:
            exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}, "thumbnail": None}
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = stamp
        exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = stamp
        exif["0th"][piexif.ImageIFD.DateTime] = stamp
        piexif.insert(piexif.dump(exif), str(path))
        return True
    except Exception:
        return False


_BAD_CHARS = '<>:"/\\|?*'


def clean_part(text: str) -> str:
    return "".join(c for c in text if c not in _BAD_CHARS and ord(c) >= 32).strip().strip(".")


def archive_names(dt: datetime, folder_pattern: str, name_pattern: str, device: str,
                  place: str, ext: str, rename: bool):
    """-> (klasör_yolu, yeni_dosya_adı veya None). Örn: ('2023-0710_op6-efes', '2023-0710_142530.jpg')"""
    folder = format_folder_name(dt, folder_pattern)
    suffix = "-".join(x for x in (clean_part(device), clean_part(place)) if x)
    if suffix:
        folder = f"{folder}_{suffix}"
    name = None
    if rename:
        name = clean_part(format_folder_name(dt, name_pattern)) + ext.lower()
    return folder, name


TZ_CHOICES = [(h / 2, None) for h in range(-24, 29)]  # -12 … +14, yarım saatlik adımlarla


def tz_label(h: float) -> str:
    sign = "+" if h >= 0 else "-"
    whole = int(abs(h))
    txt = f"UTC{sign}{whole}" + (":30" if abs(h) % 1 else "")
    return {3.0: f"{txt}  (Türkiye)", 0.0: "UTC±0  (GMT / Londra)"}.get(h, txt)



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
        return collect_files(cfg.source, cfg.dest, cfg.recurse, cfg.exts)

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



@dataclass
class ArchiveConfig:
    source: str
    dest: str
    recurse: bool
    with_video: bool
    device: str
    place: str
    folder_pattern: str
    name_pattern: str
    rename: bool
    date: DateOptions
    write_exif: bool
    move: bool
    dry_run: bool


class ArchiveWorker(QObject):
    """2. sekme: tarihi bulur, <tarih>_<cihaz>-<yer> klasörüne yeni adla kopyalar/taşır."""
    log = Signal(str)
    progress = Signal(int, int)
    done = Signal(int, int, int, bool, bool)

    def __init__(self, cfg: ArchiveConfig):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    @Slot()
    def run(self):
        cfg = self.cfg
        ok = err = skipped = 0
        counts = {"exif": 0, "video": 0, "name": 0, "approx": 0}
        exif_written = 0
        try:
            exts = PHOTO_EXTS | VIDEO_EXTS if cfg.with_video else PHOTO_EXTS
            files = sorted(collect_files(cfg.source, cfg.dest, cfg.recurse, exts),
                           key=lambda p: str(p).lower())
            if not files:
                self.log.emit("Kaynak klasörde desteklenen fotoğraf/video bulunamadı.")
                self.done.emit(0, 0, 0, cfg.dry_run, False)
                return
            total = len(files)
            self.log.emit(f"{total} dosya bulundu, tarihler çözülüyor…")
            dest_p = Path(cfg.dest)
            cancelled = False
            for i, p in enumerate(files, 1):
                if self._cancel:
                    cancelled = True
                    self.log.emit("Durduruldu.")
                    break
                try:
                    res = resolve_date(p, cfg.date)
                    if res is None:
                        skipped += 1
                        self.log.emit(f"{p.name}  (tarih bulunamadı, atlandı)")
                        self.progress.emit(i, total)
                        continue
                    counts[res.kind] += 1
                    folder, new_name = archive_names(res.dt, cfg.folder_pattern, cfg.name_pattern,
                                                     cfg.device, cfg.place, p.suffix, cfg.rename)
                    parts = [x for x in folder.replace("\\", "/").split("/") if x]
                    target_dir = dest_p.joinpath(*parts)
                    target = target_dir / (new_name or p.name)
                    shown = f"{'/'.join(parts)}/{target.name}"

                    if cfg.dry_run:
                        self.log.emit(f"[ÖNİZLEME] {p.name}  →  {shown}   [{res.label}]")
                    else:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        if find_existing_copy(p, target, ignore_size=cfg.write_exif):
                            skipped += 1
                            self.log.emit(f"{p.name}  (hedefte zaten var, atlandı)")
                            self.progress.emit(i, total)
                            continue
                        target = unique_destination(target)
                        st = p.stat()
                        if cfg.move:
                            shutil.move(str(p), str(target))
                        else:
                            shutil.copy2(str(p), str(target))
                        note = ""
                        if cfg.write_exif and res.kind != "exif" and target.suffix.lower() in (".jpg", ".jpeg", ".jpe"):
                            if write_exif_date(target, res.dt):
                                exif_written += 1
                                note = "  · EXIF'e yazıldı"
                                os.utime(target, (st.st_atime, st.st_mtime))  # tekrar çalıştırmada aynı dosya sayılsın
                            else:
                                note = "  · EXIF yazılamadı"
                        self.log.emit(f"{p.name}  →  {shown}   [{res.label}]{note}")
                    ok += 1
                except Exception as e:
                    err += 1
                    self.log.emit(f"HATA ({p.name}): {e}")
                self.progress.emit(i, total)
            summary = (f"Tarih kaynakları — EXIF: {counts['exif']}, video: {counts['video']}, "
                       f"dosya adı: {counts['name']}, yaklaşık: {counts['approx']}")
            if cfg.write_exif and not cfg.dry_run:
                summary += f"  ·  EXIF'e yazılan: {exif_written}"
            self.log.emit(summary)
            self.done.emit(ok, err, skipped, cfg.dry_run, cancelled)
        except Exception as e:
            self.log.emit(f"BEKLENMEYEN HATA: {e}")
            self.done.emit(ok, err + 1, skipped, cfg.dry_run, False)


# ---------------------------------------------------------------------------
# Özel bileşenler / Custom widgets
# ---------------------------------------------------------------------------
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
        self.resize(980, 900)
        self.setMinimumSize(860, 600)

        self._build_ui()
        saved = self.settings.value("theme", "dark")
        self.apply_theme(saved if saved in PALETTES else "dark")

        if not PIL_AVAILABLE:
            self.append_log("UYARI: Pillow kurulu değil, EXIF okunamayacak; dosya tarihi kullanılacak. "
                            "Kurmak için: pip install pillow")

    # ----- tema -----
    def apply_theme(self, name: str):
        name = name if name in PALETTES else "dark"
        app = QApplication.instance()
        app.setStyleSheet(build_qss(name))   # Breeze paleti (koyu/açık)
        app.setPalette(build_palette())
        self.theme_dark.setChecked(name == "dark")
        self.theme_light.setChecked(name == "light")
        self.settings.setValue("theme", name)
        for w in self.findChildren(QWidget):
            w.update()

    def _make_header(self, subtitle: str) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 12, 20, 12)
        h.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(1)
        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel(APP_TITLE)
        title.setObjectName("title")
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("version")
        row.addWidget(title)
        row.addWidget(ver, 0, Qt.AlignBottom)
        row.addStretch(1)
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        left.addLayout(row)
        left.addWidget(sub)
        h.addLayout(left, 1)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.theme_dark = QPushButton("Koyu")
        self.theme_dark.setObjectName("segL")
        self.theme_light = QPushButton("Açık")
        self.theme_light.setObjectName("segR")
        group = QButtonGroup(self)
        group.setExclusive(True)
        for b, name in ((self.theme_dark, "dark"), (self.theme_light, "light")):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            group.addButton(b)
            b.clicked.connect(lambda _=False, n=name: self.apply_theme(n))
            seg.addWidget(b)
        h.addLayout(seg)
        return header

    def _make_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 12, 20, 12)
        bl.setSpacing(14)
        self.run_btn = QPushButton("Başlat")
        self.run_btn.setProperty("role", "action")
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
        return bar

    def _set_run_state(self, running: bool):
        self.run_btn.setObjectName("cancel" if running else "")
        self.run_btn.setText("Durdur" if running else "Başlat")
        st = self.run_btn.style()
        st.unpolish(self.run_btn)
        st.polish(self.run_btn)

    # ----- klasör alanları (son kullanılanlar açılır listesi) -----
    def _hist(self, key: str) -> list:
        v = self.settings.value(f"history/{key}", [])
        if isinstance(v, str):
            v = [v]
        return [x for x in (v or []) if x]

    def _hist_add(self, key: str, path: str):
        items = [x for x in self._hist(key) if x != path]
        items.insert(0, path)
        self.settings.setValue(f"history/{key}", items[:10])

    def _hist_del(self, key: str, path: str):
        self.settings.setValue(f"history/{key}", [x for x in self._hist(key) if x != path])

    def _path_field(self, key: str, dialog_title: str, on_pick=None) -> PathField:
        def remember(p):
            self._hist_add(key, p)
            if on_pick:
                on_pick(p)
        f = PathField("", lambda _t: None, lambda: self._hist(key), remember,
                      lambda p: self._hist_del(key, p), "Seç…", "Son kullanılan klasörler",
                      "Henüz geçmiş yok", dialog_title)
        f.edit.setPlaceholderText("Seçin veya klasörü buraya sürükleyin…")
        return f

    @staticmethod
    def _autofill(field: PathField, src: str, name: str):
        if not field.text():
            field.setText(str(Path(src) / name))

    # ----- arayüz -----
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._make_header("Fotoğraf ve videoları tarihe göre ayırır, adlandırır ve arşivler"))

        mid = QHBoxLayout()
        mid.setSpacing(0)

        # Sol gezinme çubuğu (Breeze tarzı)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(0, 8, 0, 8)
        sl.setSpacing(0)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.stack = QStackedWidget()
        pages = (("Tarihe Göre Ayır", self._make_sort_tab), ("Adlandır ve Arşivle", self._make_archive_tab))
        for i, (label, maker) in enumerate(pages):
            b = QPushButton(label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(b, i)
            sl.addWidget(b)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            page = maker()
            page.layout().setContentsMargins(20, 16, 20, 12)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        sl.addStretch(1)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(lambda i: self.nav.button(i).setChecked(True))
        mid.addWidget(self.sidebar)
        vline = QFrame()
        vline.setObjectName("vline")
        mid.addWidget(vline)

        # İçerik: sayfa + ortak kayıt kartı
        content = QVBoxLayout()
        content.setSpacing(0)
        content.addWidget(self.stack, 1)
        card = Card("Kayıt")
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("log")
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(5000)
        self.log_box.setMinimumHeight(120)
        self.log_box.setMaximumHeight(170)
        card.wide(self.log_box)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(20, 0, 20, 12)
        wl.addWidget(card)
        content.addWidget(wrap)
        mid.addLayout(content, 1)
        outer.addLayout(mid, 1)

        outer.addWidget(self._make_bar())
        self._on_preset_change(self.preset_combo.currentText())

    def _make_tab_page(self):
        page = QWidget()
        page.setObjectName("tabpage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        return page, lay

    def _make_sort_tab(self) -> QWidget:
        page, body = self._make_tab_page()

        # -- Klasörler --
        card = Card("Klasörler")
        self.source_edit = self._path_field(
            "source", "Kaynak klasörü seçin",
            lambda p: self._autofill(self.dest_edit, p, "Tarihe Göre Ayrılmış"))
        self.dest_edit = self._path_field("dest", "Hedef klasörü seçin")
        card.row("Kaynak klasör", self.source_edit)
        card.row("Hedef klasör", self.dest_edit)
        self.recurse_cb = Check("Alt klasörleri de tara (recursive)")
        self.recurse_cb.setChecked(True)
        card.wide(self.recurse_cb)
        self.video_cb = Check("Videoları da dahil et")
        card.wide(self.video_cb)
        video_hint = QLabel("Videolarda EXIF bilgisi olmadığından dosya tarihi kullanılır.")
        video_hint.setObjectName("hint")
        card.wide(video_hint)
        body.addWidget(card)

        # -- Tarih ayarları --
        card = Card("Tarih Ayarları")
        self.exif_cb = Check("Önce EXIF çekim tarihini kullan (yoksa dosya tarihine düş)")
        self.exif_cb.setChecked(True)
        card.wide(self.exif_cb)
        self.preset_combo = Combo()
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
        self.order_combo = Combo()
        self.order_combo.addItems(["Eskiden yeniye", "Yeniden eskiye"])
        card.row("İşlem yönü", self.order_combo)
        self.prefix_cb = Check("Klasör adlarının başına sıra numarası ekle (01 - …, 02 - …)")
        card.wide(self.prefix_cb)
        body.addWidget(card)

        # -- İşlem --
        card = Card("İşlem")
        radios = QHBoxLayout()
        radios.setSpacing(28)
        self.copy_radio = Radio("Kopyala (kaynak dosyalar kalır)")
        self.move_radio = Radio("Taşı (kaynak dosyalar silinir)")
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
        self.dry_cb = Check("Sadece önizleme yap (dosyaları gerçekten taşıma/kopyalama)")
        card.wide(self.dry_cb)
        body.addWidget(card)

        return page

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

    def _make_archive_tab(self) -> QWidget:
        page, body = self._make_tab_page()

        intro = QLabel("Dosyaları  <b>yıl-aygün_saatdakikasaniye</b>  adıyla yeniden adlandırıp  "
                       "<b>yıl-aygün_cihaz-yer</b>  klasörlerine arşivler. EXIF yoksa tarih dosya adından "
                       "(IMG2026…, VID2026…) alınır; bulunan tarih istenirse EXIF'e yazılır.")
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        body.addWidget(intro)

        # -- Klasörler --
        card = Card("Klasörler")
        self.a_source = self._path_field(
            "a_source", "Kaynak klasörü seçin",
            lambda p: self._autofill(self.a_dest, p, "Arşiv"))
        self.a_dest = self._path_field("a_dest", "Arşiv klasörünü seçin")
        card.row("Kaynak klasör", self.a_source)
        card.row("Arşiv klasörü", self.a_dest)
        self.a_recurse = Check("Alt klasörleri de tara (recursive)")
        self.a_recurse.setChecked(True)
        card.wide(self.a_recurse)
        self.a_video = Check("Videoları da dahil et")
        self.a_video.setChecked(True)
        card.wide(self.a_video)
        body.addWidget(card)

        # -- Adlandırma --
        card = Card("Adlandırma")
        self.a_device = QLineEdit()
        self.a_device.setPlaceholderText("a7cii, findx9, op6 …  (çeken cihaz)")
        card.row("Cihaz adı", self.a_device)
        self.a_place = QLineEdit()
        self.a_place.setPlaceholderText("efes, tatil, düğün …  (yer / konu)")
        card.row("Yer / konu", self.a_place)
        self.a_folder_fmt = QLineEdit("%Y-%m%d")
        card.row("Klasör tarihi", self.a_folder_fmt)
        self.a_rename = Check("Dosyaları tarihe göre yeniden adlandır")
        self.a_rename.setChecked(True)
        card.wide(self.a_rename)
        self.a_name_fmt = QLineEdit("%Y-%m%d_%H%M%S")
        card.row("Dosya adı", self.a_name_fmt)
        self.a_example = QLabel()
        self.a_example.setObjectName("hint")
        card.wide(self.a_example)
        for w in (self.a_device, self.a_place, self.a_folder_fmt, self.a_name_fmt):
            w.textChanged.connect(self._update_a_example)
        self.a_rename.toggled.connect(self._update_a_example)
        self.a_rename.toggled.connect(self.a_name_fmt.setEnabled)
        body.addWidget(card)

        # -- Tarih kaynağı --
        card = Card("Tarih Kaynağı")
        self.a_exif = Check("Önce EXIF / video içi tarihi kullan")
        self.a_exif.setChecked(True)
        card.wide(self.a_exif)
        self.a_fname = Check("EXIF yoksa dosya adındaki tarihi kullan")
        self.a_fname.setChecked(True)
        card.wide(self.a_fname)
        fh = QLabel("IMG20261029141449, VID…, PXL_…, 2026-10-29 14.14.49 gibi adlardan okunur")
        fh.setObjectName("hint")
        card.wide(fh)
        self.a_vutc = Check("Video tarihi UTC/GMT kayıtlı: yerel saate çevir")
        self.a_vutc.setChecked(True)
        card.wide(self.a_vutc)
        self.a_tz = Combo()
        for h in range(-24, 29):
            self.a_tz.addItem(tz_label(h / 2), h / 2)
        self.a_tz.setCurrentIndex(self.a_tz.findData(3.0))
        card.row("Saat dilimi", self.a_tz)
        self.a_vutc.toggled.connect(self.a_tz.setEnabled)
        self.a_fallback = Combo()
        self.a_fallback.addItem("Dosya tarihi (yaklaşık)", "mtime")
        self.a_fallback.addItem("Elle girdiğim tarih (yaklaşık)", "manual")
        self.a_fallback.addItem("Atla (işlem yapma)", "skip")
        card.row("Tarih bulunamazsa", self.a_fallback)
        self.a_manual = QDateTimeEdit(QDateTime.currentDateTime())
        self.a_manual.setDisplayFormat("dd.MM.yyyy  HH:mm:ss")
        self.a_manual.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.a_manual.setEnabled(False)
        card.row("Yaklaşık tarih", self.a_manual)
        self.a_fallback.currentIndexChanged.connect(
            lambda _i: self.a_manual.setEnabled(self.a_fallback.currentData() == "manual"))
        self.a_write = Check("Bulunan/yaklaşık tarihi EXIF'e yaz (yalnızca JPEG, EXIF'i olmayanlara)")
        self.a_write.setChecked(True)
        if not PIEXIF_AVAILABLE:
            self.a_write.setChecked(False)
            self.a_write.setEnabled(False)
            self.a_write.setText("EXIF'e yazma için piexif gerekli:  pip install piexif")
        card.wide(self.a_write)
        body.addWidget(card)

        # -- İşlem --
        card = Card("İşlem")
        radios = QHBoxLayout()
        radios.setSpacing(28)
        radios.setContentsMargins(0, 0, 0, 0)
        self.a_copy = Radio("Kopyala (kaynak dosyalar kalır)")
        self.a_move = Radio("Taşı (kaynak dosyalar silinir)")
        self.a_copy.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.a_copy)
        group.addButton(self.a_move)
        radios.addWidget(self.a_copy)
        radios.addWidget(self.a_move)
        radios.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(radios)
        card.wide(wrap)
        self.a_dry = Check("Sadece önizleme yap (dosyaları gerçekten taşıma/kopyalama)")
        card.wide(self.a_dry)
        body.addWidget(card)

        self._update_a_example()
        return page

    def _update_a_example(self, *_):
        try:
            dt = datetime(2023, 7, 10, 14, 25, 30)
            folder, name = archive_names(dt, self.a_folder_fmt.text().strip() or "%Y-%m%d",
                                         self.a_name_fmt.text().strip() or "%Y-%m%d_%H%M%S",
                                         self.a_device.text(), self.a_place.text(), ".jpg",
                                         self.a_rename.isChecked())
            self.a_example.setText(f"Örnek:  {folder}/{name or 'özgün_ad.jpg'}")
        except (ValueError, KeyError):
            self.a_example.setText("Örnek: geçersiz format")

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
        if self.stack.currentIndex() == 1:
            self.start_archive()
        else:
            self.start()

    def _confirm_move(self) -> bool:
        answer = QMessageBox.question(
            self, "Onay",
            "Dosyalar kaynak klasörden TAŞINACAK (kaynakta kalmayacak).\nDevam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def _launch(self, worker):
        self._running = True
        self.sidebar.setEnabled(False)
        self._set_run_state(True)
        self.progress.setValue(0)
        self.status_label.setText("Hazırlanıyor…")

        if self._thread is not None:  # önceki çalıştırmanın iş parçacığını serbest bırak
            self._thread.deleteLater()
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.log.connect(self.append_log)
        worker.progress.connect(self.on_progress)
        worker.done.connect(self.on_done)
        worker.done.connect(self._thread.quit)
        self._thread.finished.connect(worker.deleteLater)
        self._thread.start()

    def start_archive(self):
        source = self.a_source.text().strip()
        dest = self.a_dest.text().strip()
        folder_fmt = self.a_folder_fmt.text().strip()
        name_fmt = self.a_name_fmt.text().strip()
        rename = self.a_rename.isChecked()
        if not source or not Path(source).is_dir():
            QMessageBox.warning(self, "Hata", "Geçerli bir kaynak klasör seçin.")
            return
        if not dest:
            QMessageBox.warning(self, "Hata", "Geçerli bir arşiv klasörü seçin.")
            return
        if not folder_fmt or (rename and not name_fmt):
            QMessageBox.warning(self, "Hata", "Klasör/dosya adı formatı boş olamaz.")
            return
        try:
            format_folder_name(datetime.now(), folder_fmt)
            format_folder_name(datetime.now(), name_fmt or "%Y")
        except (ValueError, KeyError):
            QMessageBox.warning(self, "Hata", "Tarih formatı geçersiz.")
            return
        fb = self.a_fallback.currentData()
        manual = self.a_manual.dateTime().toPython() if fb == "manual" else None
        move, dry = self.a_move.isChecked(), self.a_dry.isChecked()
        if move and not dry and not self._confirm_move():
            return
        cfg = ArchiveConfig(
            source=source, dest=dest, recurse=self.a_recurse.isChecked(),
            with_video=self.a_video.isChecked(),
            device=self.a_device.text(), place=self.a_place.text(),
            folder_pattern=folder_fmt, name_pattern=name_fmt or "%Y-%m%d_%H%M%S", rename=rename,
            date=DateOptions(use_exif=self.a_exif.isChecked(), from_filename=self.a_fname.isChecked(),
                             video_utc=self.a_vutc.isChecked(), tz_hours=float(self.a_tz.currentData()),
                             fallback=fb, manual_dt=manual),
            write_exif=self.a_write.isChecked() and PIEXIF_AVAILABLE,
            move=move, dry_run=dry,
        )
        self._launch(ArchiveWorker(cfg))

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
        if move and not dry and not self._confirm_move():
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
        self._launch(SortWorker(cfg))

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
        self.sidebar.setEnabled(True)
        self.run_btn.setEnabled(True)
        self._set_run_state(False)
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
    if sys.platform == "win32":
        # Görev çubuğunda "python" yerine bu uygulamanın kendi simgesi/grubu görünsün
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BuRsTFiRe47.FotoTariheGoreAyir")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
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
