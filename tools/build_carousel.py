#!/usr/bin/env python3
"""Light & Loft carousel builder (4:5, 1080x1350).

Spec:
{
  "outdir": "/tmp/ig/out/carousel_x",
  "slides": [
    {"src": "a.webp", "center": [0.5, 0.5], "zoom": 1.0,
     "title": "DĚTI ROSTOU.", "sub": "optional line"},          # photo with text
    {"src": "b.webp", "center": [0.5, 0.45]},                     # plain photo
    {"text": ["Ne dokonale.", "Prostě tak, jak to máte teď."],   # brand text slide
     "foot": "RODINNÉ FOCENÍ · JIHLAVA · PRAHA · BRNO"}
  ]
}
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageOps
sys.path.insert(0, os.path.dirname(__file__))
from build_reel import oswald, didact, draw_spaced, frame_from, BG, TEXT, GOLD

W, H = 1080, 1350


def wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def photo_slide(s):
    img = ImageOps.exif_transpose(Image.open(s["src"])).convert("RGB")
    img.thumbnail((2600, 2600), Image.LANCZOS)
    cx, cy = s.get("center", [0.5, 0.5])
    fr = frame_from(img, W, H, cx, cy, s.get("zoom", 1.0)).convert("RGBA")
    if s.get("title"):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        top, bot = int(H * 0.36), int(H * 0.64)
        bd.rectangle([0, top, W, bot], fill=(15, 15, 15, 150))
        band = band.filter(ImageFilter.GaussianBlur(70))
        ov.alpha_composite(band)
        d = ImageDraw.Draw(ov)
        ft = oswald(104, 500)
        y = H * 0.42
        for ln in s["title"].split("\n"):
            draw_spaced(d, (W / 2, y), ln, ft, TEXT + (255,), 8)
            y += 128
        if s.get("sub"):
            fs = didact(40)
            for ln in wrap(d, s["sub"], fs, W * 0.72):
                draw_spaced(d, (W / 2, y + 14), ln, fs, TEXT + (235,), 0)
                y += 54
        fr.alpha_composite(ov)
    return fr.convert("RGB")


def text_slide(s):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    fb = didact(58)
    lines = []
    for para in s["text"]:
        lines += wrap(d, para, fb, W * 0.74)
    lh = 80
    y = H / 2 - lh * len(lines) / 2 - 40
    for ln in lines:
        draw_spaced(d, (W / 2, y), ln, fb, TEXT, 0)
        y += lh
    # gold rule
    d.line([(W / 2 - 40, y + 40), (W / 2 + 40, y + 40)], fill=GOLD, width=3)
    if s.get("foot"):
        draw_spaced(d, (W / 2, y + 80), s["foot"], oswald(30, 400), GOLD, 8)
    # small logo bottom
    f = oswald(34, 600)
    parts = [("LIGHT ", TEXT), ("&", GOLD), (" LOFT", TEXT)]
    sp = 6
    widths = [sum(d.textlength(c, font=f) for c in p) + sp * (len(p) - 1) for p, _ in parts]
    x = W / 2 - (sum(widths) + 2 * sp) / 2
    for (p, col), w in zip(parts, widths):
        xx = x
        for c in p:
            d.text((xx, H - 120), c, font=f, fill=col)
            xx += d.textlength(c, font=f) + sp
        x += w + sp
    return im


def main(path):
    spec = json.load(open(path))
    os.makedirs(spec["outdir"], exist_ok=True)
    for i, s in enumerate(spec["slides"], 1):
        im = text_slide(s) if "text" in s else photo_slide(s)
        p = os.path.join(spec["outdir"], f"{i:02d}.jpg")
        im.save(p, "JPEG", quality=88)
        print(p)


if __name__ == "__main__":
    main(sys.argv[1])
