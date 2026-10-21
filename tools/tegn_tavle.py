#!/usr/bin/env python3
"""Storyboard-tavler som skitser (0 credits).

Tegner ét 9:16-billede pr. beat og én samlet tavle pr. opslag, i samme layout
som storyboard/uge1. Reglerne (skærmtekst, accentfarve, trin) er Notions; her
er kun tegningen.

Brug:
  python3 tools/tegn_tavle.py opslag.json storyboard/<mappe>

opslag.json: liste af opslag med felterne id, dag, titel, videoformat, soejle,
tragt, indholdstype, skaermtekst, billedtekst, lyd, stemning og beats.
Hvert beat: [type, trin, talt tekst, billedbeskrivelse]. Type AV, KLIP, SIT, GRAF.
KLIP-beats skal nævne en fil i assets/broll (fx "cafe.mp4: …"); der tages et
billede midt i klippet. AV-beats bruger et udsnit af Twin-stillbilledet
(AV_KILDE nedenfor) — en skitse, ikke det endelige look.
"""
import json, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AV_KILDE = os.path.join(ROOT, "storyboard/uge1/dag6_beat03.jpg")
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_SB = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
FONT_R = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
GUL = (255, 210, 63)        # accentfarve #FFD23F (Notion: Video Templates / Redigeringsopskrift)
NAVY = (27, 38, 59)
BG = (245, 243, 239)
GRA = (110, 116, 128)
TRIN_FARVE = {"Genkendelse": (219, 230, 250), "Forståelse": (232, 224, 248),
              "Handling": (214, 240, 228), "Udbytte": (252, 238, 196), "CTA": (252, 238, 196)}
TYPE_FARVE = {"AV": (58, 110, 220), "KLIP": (230, 130, 60), "SIT": (230, 130, 60), "GRAF": (140, 90, 200)}
W, H = 648, 1152


def f(path, size):
    return ImageFont.truetype(path, size)


def av_billede(variant):
    """Udsnit uden tekst fra Twin-stillbilledet (øverste del), varieret pr. beat."""
    im = Image.open(AV_KILDE).convert("RGB")
    top = 760  # under ansigt/bryst, over den indbrændte tekst
    ch = top - 40 * (variant % 3)
    cw = int(ch * 9 / 16)
    x0 = (im.width - cw) // 2 + (variant % 2) * 20 - 10
    crop = im.crop((x0, 0, x0 + cw, ch))
    return crop.resize((W, H), Image.LANCZOS)


def klip_billede(beskrivelse):
    m = re.search(r"([\w\-]+\.mp4)", beskrivelse)
    if not m:
        return None
    fil = os.path.join(ROOT, "assets/broll", m.group(1))
    if not os.path.exists(fil):
        return None
    ud = "/tmp/_klip_frame.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.5", "-i", fil, "-frames:v", "1", ud], check=True)
    im = Image.open(ud).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def skitse(beskrivelse):
    im = Image.new("RGB", (W, H), (214, 222, 232))
    d = ImageDraw.Draw(im)
    d.rectangle((0, int(H * .62), W, H), fill=(190, 200, 214))
    d.text((40, 60), "SKITSE", font=f(FONT_SB, 34), fill=GRA)
    d.multiline_text((40, 120), wrap(beskrivelse, f(FONT_R, 34), W - 80), font=f(FONT_R, 34), fill=NAVY)
    return im


def wrap(tekst, font, bredde):
    ord_, linjer, linje = tekst.split(), [], ""
    for o in ord_:
        test = (linje + " " + o).strip()
        if font.getlength(test) <= bredde:
            linje = test
        else:
            linjer.append(linje)
            linje = o
    linjer.append(linje)
    return "\n".join(linjer)


def overlay(im, tekst, stor=False):
    """Hvid tekst med sort kant, ét accentord i gul (*ord*), midt/nederst (Imans placering)."""
    d = ImageDraw.Draw(im)
    font = f(FONT, 66 if stor else 50)
    ord_ = tekst.split()
    linjer, linje = [], []
    for o in ord_:
        if font.getlength(" ".join(x.strip("*") for x in linje + [o])) > W - 90 and linje:
            linjer.append(linje); linje = []
        linje.append(o)
    linjer.append(linje)
    lh = font.size + 10
    y = int(H * (0.42 if stor else 0.70)) - lh * len(linjer) // 2
    for l in linjer:
        bredde = font.getlength(" ".join(x.strip("*") for x in l)) + 10 * (len(l) - 1)
        x = (W - bredde) / 2
        for o in l:
            farve = GUL if o.startswith("*") else (255, 255, 255)
            ren = o.strip("*")
            d.text((x, y), ren, font=font, fill=farve, stroke_width=5, stroke_fill=(0, 0, 0))
            x += font.getlength(ren) + font.getlength(" ") + 10
        y += lh
    return im


def undertekst(talt):
    """Kort undertekst-bid til skitsen: 2–3 ord, sidste ord som accent."""
    ord_ = re.sub(r"[.,!?]", "", talt).split()[:3]
    ord_[-1] = "*" + ord_[-1] + "*"
    return " ".join(ord_)


def tegn_beat(p, i, beat):
    typ, trin, talt, beskr = beat
    if typ == "AV":
        im = av_billede(i)
    elif typ == "KLIP":
        im = klip_billede(beskr) or skitse(beskr)
    else:
        im = skitse(beskr)
    if trin == "CTA":
        return overlay(im, "Kommenter *START*", stor=True)
    if i == 0:
        return overlay(im, p["skaermtekst"])
    return overlay(im, undertekst(talt))


def runde(im, r=22):
    maske = Image.new("L", im.size, 0)
    ImageDraw.Draw(maske).rounded_rectangle((0, 0, im.width, im.height), r, fill=255)
    bg = Image.new("RGB", im.size, BG)
    bg.paste(im, (0, 0), maske)
    return bg


def tavle(p, beat_billeder):
    n = len(beat_billeder)
    kw, kh, gap, mx = 338, 600, 30, 88
    bredde = max(2000, mx * 2 + n * kw + (n - 1) * gap)
    T = Image.new("RGB", (bredde, 1560), BG)
    d = ImageDraw.Draw(T)
    d.text((mx, 64), p["dag"], font=f(FONT_SB, 22), fill=GRA)
    d.text((mx, 100), p["titel"].split("— ")[-1], font=f(FONT, 56), fill=NAVY)
    x = mx
    for chip in [f"Format {p['videoformat']} · Talking head + klip", p["soejle"], f"{p['tragt']} · {p['indholdstype']}", "Skitse · 0 credits"]:
        cw = f(FONT_SB, 22).getlength(chip) + 40
        d.rounded_rectangle((x, 182, x + cw, 222), 20, fill=(232, 228, 220))
        d.text((x + 20, 189), chip, font=f(FONT_SB, 22), fill=NAVY)
        x += cw + 14
    y0 = 256
    for i, (im, beat) in enumerate(zip(beat_billeder, p["beats"])):
        x = mx + i * (kw + gap)
        T.paste(runde(im.resize((kw, kh), Image.LANCZOS)), (x, y0))
        typ, trin, talt, beskr = beat
        ty = y0 + kh + 14
        lab = f"{trin.upper()}"
        lw = f(FONT_SB, 19).getlength(lab) + 26
        d.rounded_rectangle((x, ty, x + lw, ty + 32), 8, fill=TRIN_FARVE.get(trin, (230, 230, 230)))
        d.text((x + 13, ty + 5), lab, font=f(FONT_SB, 19), fill=NAVY)
        d.rectangle((x, ty + 48, x + 14, ty + 62), fill=TYPE_FARVE.get(typ, GRA))
        d.text((x + 24, ty + 42), f"BEAT {i + 1} · {typ}", font=f(FONT_SB, 19), fill=NAVY)
        tt = wrap(f'"{talt}"', f(FONT_R, 21), kw)
        d.multiline_text((x, ty + 78), tt, font=f(FONT_R, 21), fill=NAVY, spacing=6)
        hy = ty + 78 + d.multiline_textbbox((0, 0), tt, font=f(FONT_R, 21), spacing=6)[3] + 14
        d.multiline_text((x, hy), wrap(beskr, f(FONT_R, 18), kw), font=f(FONT_R, 18), fill=GRA, spacing=5)
    yb = 1230
    d.line((mx, yb - 20, bredde - mx, yb - 20), fill=(220, 216, 208), width=2)
    kol = (bredde - 2 * mx) // 3
    for j, (navn, tekst) in enumerate([("BILLEDTEKST", p["billedtekst"].replace("🤖 ", "")), ("LYD", p["lyd"]), ("STEMNING", p["stemning"])]):
        x = mx + j * kol
        d.text((x, yb), navn, font=f(FONT_SB, 20), fill=GRA)
        afsnit = [wrap(a, f(FONT_R, 20), kol - 40) for a in tekst.split("\n\n")]
        d.multiline_text((x, yb + 34), "\n".join(afsnit), font=f(FONT_R, 20), fill=NAVY, spacing=6)
    return T


def main(json_fil, mappe):
    os.makedirs(mappe, exist_ok=True)
    for p in json.load(open(json_fil, encoding="utf-8")):
        billeder = []
        for i, beat in enumerate(p["beats"]):
            im = tegn_beat(p, i, beat)
            im.save(os.path.join(mappe, f"{p['id'].lower()}_beat{i + 1:02d}.jpg"), quality=88)
            billeder.append(im)
        tavle(p, billeder).save(os.path.join(mappe, f"{p['id'].lower()}_board.jpg"), quality=88)
        print("tegnet", p["id"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
