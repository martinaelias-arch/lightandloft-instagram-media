#!/usr/bin/env python3
"""Light & Loft reel builder.

Spec (JSON):
{
  "out": "reel.mp4",
  "fps": 30,
  "size": [1080, 1920],
  "hook": {"text": "CO BUDETE CHTÍT\nVIDĚT ZA DESET LET?", "dur": 2.6},
  "clips": [
     {"src": "a.webp", "dur": 1.7, "from": [0.3, 0.5, 1.0], "to": [0.6, 0.5, 1.08]},
     ...
  ],
  "end": {"lines": ["SVATBY", "Jihlava · Praha · Brno"], "dur": 2.0},
  "xfade": 0.25,
  "music": "track.mp3" (optional)
}
from/to = [center_x, center_y, zoom] normalized to the image; zoom 1.0 = crop just covers frame.
The hook text is overlaid on the first clip.
"""
import json, subprocess, sys, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import os, tempfile, glob

FONT_DIR = "/tmp/ig/fonts"
BG = (25, 25, 25)
TEXT = (232, 228, 222)
GOLD = (201, 169, 110)


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def oswald(size, weight=500):
    f = ImageFont.truetype(f"{FONT_DIR}/Oswald.ttf", size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def didact(size):
    return ImageFont.truetype(f"{FONT_DIR}/DidactGothic.ttf", size)


def draw_spaced(draw, xy, text, font, fill, spacing):
    """Draw text with letter spacing, x is the centre."""
    cx, y = xy
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing
    return total


def frame_from(img, W, H, cx, cy, z):
    iw, ih = img.size
    # crop box with aspect W/H that covers frame at zoom 1
    base = min(iw / W, ih / H)
    cw, ch = W * base / z, H * base / z
    cw, ch = min(cw, iw), min(ch, ih)
    x0 = max(min(max(cx * iw - cw / 2, 0), iw - cw), 0)
    y0 = max(min(max(cy * ih - ch / 2, 0), ih - ch), 0)
    return img.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def hook_overlay(W, H, text):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # soft dark band behind the text for legibility
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    top, bot = int(H * 0.30), int(H * 0.52)
    bd.rectangle([0, top, W, bot], fill=(15, 15, 15, 140))
    band = band.filter(ImageFilter.GaussianBlur(60))
    ov.alpha_composite(band)
    d = ImageDraw.Draw(ov)
    lines = text.split("\n")
    f = oswald(78, 500)
    lh = 104
    y = (top + bot) / 2 - lh * len(lines) / 2
    for ln in lines:
        draw_spaced(d, (W / 2, y), ln, f, TEXT + (255,), 6)
        y += lh
    return ov


def end_card(W, H, lines):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f = oswald(96, 600)
    # logo: Light & Loft, & in gold
    parts = [("LIGHT ", TEXT), ("&", GOLD), (" LOFT", TEXT)]
    sp = 14
    widths = [sum(d.textlength(c, font=f) for c in p) + sp * (len(p) - 1) for p, _ in parts]
    total = sum(widths) + sp * 2
    x = W / 2 - total / 2
    y = H * 0.40
    for (p, col), w in zip(parts, widths):
        xx = x
        for c in p:
            d.text((xx, y), c, font=f, fill=col)
            xx += d.textlength(c, font=f) + sp
        x += w + sp
    fs = oswald(40, 400)
    yy = y + 150
    for i, ln in enumerate(lines):
        font = fs if i == 0 else didact(38)
        col = GOLD if i == 0 else TEXT
        draw_spaced(d, (W / 2, yy), ln, font, col, 10 if i == 0 else 2)
        yy += 64
    return im


def main(spec_path):
    spec = json.load(open(spec_path))
    W, H = spec.get("size", [1080, 1920])
    fps = spec.get("fps", 30)
    xf = spec.get("xfade", 0.25)
    clips = spec["clips"]
    hook = spec.get("hook")
    endc = spec.get("end")

    # build list of "segments": each yields frames via function(t_local)
    segs = []
    for i, c in enumerate(clips):
        dur = c["dur"] + (hook["dur"] - c["dur"] if (i == 0 and hook) else 0)
        if "video" in c:
            td = tempfile.mkdtemp(prefix="vid_")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(c.get("start", 0)), "-t", str(dur + 0.1),
                            "-i", c["video"], "-an", "-vf",
                            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
                            "-q:v", "3", f"{td}/%05d.jpg"], check=True)
            frames = sorted(glob.glob(f"{td}/*.jpg"))
            segs.append(("vid", frames, dur, None, None))
            continue
        img = ImageOps.exif_transpose(Image.open(c["src"])).convert("RGB")
        img.thumbnail((2600, 2600), Image.LANCZOS)
        segs.append(("img", img, dur, c.get("from", [0.5, 0.5, 1.0]), c.get("to", [0.5, 0.5, 1.06])))
    if endc:
        segs.append(("end", end_card(W, H, endc["lines"]), endc["dur"], None, None))

    hook_ov = hook_overlay(W, H, hook["text"]) if hook else None

    def render(seg, t):
        kind, img, dur, fr, to = seg
        if kind == "end":
            return img
        if kind == "vid":
            k = min(int(t * fps), len(img) - 1)
            return Image.open(img[max(k, 0)]).convert("RGB")
        k = ease(min(max(t / dur, 0), 1))
        cx = fr[0] + (to[0] - fr[0]) * k
        cy = fr[1] + (to[1] - fr[1]) * k
        z = fr[2] + (to[2] - fr[2]) * k
        return frame_from(img, W, H, cx, cy, z)

    out = spec["out"]
    silent = out + ".silent.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", silent], stdin=subprocess.PIPE)

    # timeline with crossfades
    starts, t = [], 0.0
    for s in segs:
        starts.append(t)
        t += s[2] - xf
    total = t + xf
    nframes = int(total * fps)
    for n in range(nframes):
        tt = n / fps
        # active segments
        act = [(i, tt - starts[i]) for i in range(len(segs)) if starts[i] <= tt < starts[i] + segs[i][2]]
        if not act:
            act = [(len(segs) - 1, segs[-1][2])]
        i, tl = act[-1]
        fr = render(segs[i], tl).convert("RGBA")
        if i == 0 and hook_ov is not None and tl < hook["dur"]:
            # fade hook out over the last 0.3 s
            a = 1.0 if tl < hook["dur"] - 0.3 else max(0, (hook["dur"] - tl) / 0.3)
            ov = hook_ov.copy()
            if a < 1:
                ov.putalpha(ov.getchannel("A").point(lambda v: int(v * a)))
            fr.alpha_composite(ov)
        if len(act) > 1:
            j, tlj = act[0]
            prev = render(segs[j], tlj).convert("RGBA")
            if j == 0 and hook_ov is not None and tlj < hook["dur"]:
                prev.alpha_composite(hook_ov)
            alpha = min(max(tl / xf, 0), 1)
            fr = Image.blend(prev, fr, alpha)
        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()

    music = spec.get("music")
    if music:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", music,
               "-af", f"afade=t=out:st={max(total-1.5,0):.2f}:d=1.5", "-shortest",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", out]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-f", "lavfi",
               "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-shortest",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", out]
    subprocess.run(cmd, check=True)
    subprocess.run(["rm", "-f", silent])
    print(f"{out}: {total:.1f}s, {nframes} frames")


if __name__ == "__main__":
    main(sys.argv[1])
