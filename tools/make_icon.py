#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Uygulama simgesi üretici / App icon generator  (Pillow)
    python tools/make_icon.py foto     |   python tools/make_icon.py dosya
Çıktı / Output: assets/icon.png, icon.ico, icon.icns  +  app_icon.py (gömülü PNG'ler, QIcon)
"""
import base64, io, sys
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024                      # süper örnekleme boyutu
NAVY, NAVY2 = (24, 24, 38), (42, 43, 64)
CORAL, CORAL_HI, CORAL_LO = (217, 74, 79), (232, 98, 102), (186, 56, 62)
WHITE, SOFT = (255, 255, 255), (239, 240, 241)


def vgrad(size, top, bottom):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = c
    return img


def base(top, bottom):
    bg = vgrad(S, top, bottom).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.225), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    return out


def draw_foto():
    img = base(CORAL_HI, CORAL_LO)
    d = ImageDraw.Draw(img)
    # beyaz fotoğraf kartı (hafif gölge)
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((200, 190, 824, 840), radius=70, fill=(0, 0, 0, 70))
    from PIL import ImageFilter
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((190, 170, 834, 800), radius=70, fill=WHITE)
    # koyu "çekim" alanı
    d.rounded_rectangle((250, 230, 774, 640), radius=34, fill=NAVY)
    d.ellipse((560, 290, 690, 420), fill=WHITE)                              # güneş
    d.polygon([(250, 640), (420, 380), (540, 540), (610, 450), (774, 640)], fill=CORAL)   # dağlar
    d.polygon([(250, 640), (340, 520), (430, 640)], fill=CORAL_HI)
    # takvim rozeti (tarihe göre ayırma)
    cx, cy, r = 740, 760, 200
    d.rounded_rectangle((cx - r, cy - r + 20, cx + r, cy + r - 20), radius=58, fill=NAVY, outline=WHITE, width=26)
    d.rectangle((cx - r + 13, cy - r + 33, cx + r - 13, cy - 40), fill=WHITE)
    for gx in (-100, 0, 100):
        for gy in (30, 110):
            d.rounded_rectangle((cx + gx - 28, cy + gy - 24, cx + gx + 28, cy + gy + 24), radius=12,
                                fill=CORAL if (gx, gy) == (100, 110) else WHITE)
    return img


def draw_dosya():
    img = base(NAVY2, NAVY)
    d = ImageDraw.Draw(img)
    # klasörden taşan üç dosya
    sheets = [((300, 250, 640, 640), (170, 186, 214), -8), ((380, 210, 720, 600), SOFT, 0),
              ((460, 260, 780, 640), (255, 214, 224), 8)]
    for box, col, _ in sheets:
        d.rounded_rectangle(box, radius=34, fill=col)
    for y in (330, 400, 470):
        d.rounded_rectangle((430, y, 670, y + 26), radius=13, fill=(130, 140, 170))
    # klasör gövdesi
    d.rounded_rectangle((130, 360, 450, 480), radius=44, fill=CORAL_HI)                # sekme
    d.rounded_rectangle((130, 430, 894, 840), radius=62, fill=CORAL)
    d.rounded_rectangle((130, 430, 894, 520), radius=62, fill=CORAL_HI)
    d.rectangle((130, 490, 894, 520), fill=CORAL_HI)
    d.rounded_rectangle((130, 500, 894, 840), radius=62, fill=CORAL)
    d.rectangle((130, 500, 894, 560), fill=CORAL)
    # tür noktaları
    for i, col in enumerate((WHITE, (255, 214, 224), (170, 186, 214))):
        x = 330 + i * 180
        d.ellipse((x - 34, 650 - 34, x + 34, 650 + 34), fill=col)
    return img


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "foto").lower()
    img = {"foto": draw_foto, "dosya": draw_dosya}[which]()
    root = Path(__file__).resolve().parent.parent
    (root / "assets").mkdir(exist_ok=True)
    png = {n: img.resize((n, n), Image.LANCZOS) for n in (16, 24, 32, 48, 64, 128, 256, 512)}
    png[256].save(root / "assets" / "icon.png")
    img.resize((512, 512), Image.LANCZOS).save(root / "assets" / "icon-512.png")
    png[256].save(root / "assets" / "icon.ico", format="ICO",
                  sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    img.resize((1024, 1024), Image.LANCZOS).save(root / "assets" / "icon.icns", format="ICNS")
    # Qt için gömülü PNG'ler (PyInstaller'a ek dosya vermeye gerek kalmasın)
    blobs = {}
    for n in (16, 32, 48, 64, 128, 256):
        b = io.BytesIO(); png[n].save(b, "PNG", optimize=True); blobs[n] = base64.b64encode(b.getvalue()).decode()
    lines = ['# -*- coding: utf-8 -*-', '"""Gömülü uygulama simgesi (tools/make_icon.py ile üretilir). / Embedded app icon."""',
             'import base64', '', 'from PySide6.QtGui import QIcon, QPixmap', '', '_PNGS = {']
    for n, b in blobs.items():
        lines.append(f'    {n}: (')
        lines += [f'        "{b[i:i + 100]}"' for i in range(0, len(b), 100)]
        lines.append('    ),')
    lines += ['}', '', '', 'def app_icon() -> QIcon:', '    icon = QIcon()',
              '    for data in _PNGS.values():', '        pm = QPixmap()',
              '        pm.loadFromData(base64.b64decode(data))', '        icon.addPixmap(pm)', '    return icon', '']
    (root / "app_icon.py").write_text("\n".join(lines), encoding="utf-8")
    print("ok:", which)


if __name__ == "__main__":
    main()
