#!/usr/bin/env python3
"""Byg en format A-reel (Talking Head) efter Video Templates — HeyGen / Redigeringsopskrift.

Input: avatar-video (HeyGen create_video_from_avatar, Twin V2) + SRT + en JSON-konfiguration:
{
  "skaermtekst": "Har du en *tandlægetid*",
  "beats": [
    {"type": "AV",   "text": "..."},
    {"type": "SIT",  "text": "...", "klip": "sti/til/klip.mp4"},
    {"type": "GRAF", "text": "...", "grafik": [["Tandlæge:", "i kalenderen", "Tandlægen"], ...]},
    ...
  ],
  "accent": ["ord1", "", "ord3", ...]  # accentord pr. sætning i rækkefølge ("" = intet)
}
grafik-linjer: [label, værdi, udløserord] — linjen toner frem, når udløserordet siges.

Lyden er altid avatarens ubrudte talespor. Billedet skifter ovenpå.
Brug: python3 tools/byg_reel.py config.json avatar.mp4 avatar.srt ud.mp4
"""
import json, re, subprocess, sys, os, tempfile

W, H, FPS = 1080, 1920, 25
ZOOM = "crop=760:1350:160:60,scale=1080:1920"
MAX_MID = 3.4      # midterstykker holdes under 4 sek.
MAX_END = 5.5      # hook og CTA må være op til 6 sek.
SKAERM_SLUT = 2.5


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit(f"Fejl: {' '.join(cmd[:6])} ...")
    return r.stdout


def dur(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())


def ts(s):
    h, m, rest = s.strip().split(":")
    sec, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def norm(w):
    return re.sub(r"[^\wæøåÆØÅ]", "", w.lower())


def srt_words(path):
    """Ord med start/slut. Tiden i hver SRT-blok fordeles efter ordlængde."""
    blocks = open(path, encoding="utf-8").read().strip().split("\n\n")
    words = []
    for b in blocks:
        lines = [l for l in b.strip().splitlines() if l.strip()]
        tl = next(i for i, l in enumerate(lines) if "-->" in l)
        a, c = lines[tl].split("-->")
        t0, t1 = ts(a), ts(c)
        toks = " ".join(lines[tl + 1:]).split()
        if not toks:
            continue
        weights = [len(norm(t)) + 2 for t in toks]
        tot = sum(weights)
        t = t0
        for tok, wgt in zip(toks, weights):
            d = (t1 - t0) * wgt / tot
            words.append({"w": tok, "n": norm(tok), "s": t, "e": t + d})
            t += d
    return words


def align(beats, words):
    """Find start/slut for hvert beat ud fra ordrækkefølgen."""
    i = 0
    for b in beats:
        bw = [norm(x) for x in b["text"].split() if norm(x)]
        b["s"] = words[i]["s"]
        b["wi"] = (i, i + len(bw))
        i += len(bw)
        b["e"] = words[min(i, len(words)) - 1]["e"]
    if i != len(words):
        sys.stderr.write(f"Advarsel: beats har {i} ord, SRT har {len(words)}\n")
    for a, b in zip(beats, beats[1:]):   # luk huller, så billedet er sammenhængende
        a["e"] = b["s"]
    return beats


def chunk(t0, t1, maxlen):
    n = max(1, int((t1 - t0) / maxlen + 0.999))
    step = (t1 - t0) / n
    return [(t0 + k * step, t0 + (k + 1) * step) for k in range(n)]


def plan(beats, total):
    segs = []           # (start, slut, kilde, zoom)
    beats[0]["s"] = 0.0
    beats[-1]["e"] = total
    zoom = False
    for k, b in enumerate(beats):
        end = k in (0, len(beats) - 1)
        lim = MAX_END if end else MAX_MID
        if b["type"] == "SIT" and b.get("klip"):
            klen = min(dur(b["klip"]) - 0.1, MAX_MID)
            sit_end = min(b["e"], b["s"] + klen)
            if 0.3 < b["e"] - sit_end < 1.2:      # undgå et kort hak bagefter
                sit_end = b["e"] - 1.2
            segs.append((b["s"], sit_end, b["klip"], False))
            if b["e"] - sit_end > 0.3:
                for a, c in chunk(sit_end, b["e"], MAX_MID):
                    zoom = not zoom
                    segs.append((a, c, "AV", zoom))
            else:
                segs[-1] = (b["s"], b["e"], b["klip"], False)
            continue
        for a, c in chunk(b["s"], b["e"], lim):
            if not (k == 0 and a == 0.0):
                zoom = not zoom
            segs.append((a, c, "AV", zoom))
    return segs


def render(segs, avatar, tmp):
    parts = []
    for n, (a, c, src, z) in enumerate(segs):
        out = os.path.join(tmp, f"s{n:02d}.mp4")
        d = c - a
        if src == "AV":
            vf = (ZOOM + "," if z else "scale=1080:1920,") + f"fps={FPS},setsar=1"
            run(["ffmpeg", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", avatar, "-an",
                 "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
        else:
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"fps={FPS},setsar=1")
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-t", f"{d:.3f}", "-i", src, "-an",
                 "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
        parts.append(out)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    vid = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])
    return vid


def asst(t):
    t = max(0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


GUL = r"{\c&H3FD2FF&}"
HVID = r"{\c&HFFFFFF&}"


def accent_markup(text):
    return re.sub(r"\*(.+?)\*", lambda m: GUL + m.group(1) + HVID, text)


def groups(words, accents):
    """1-3 ord pr. visning, brudt ved tegnsætning."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.,?!:][\"”]?$", w["w"]) or (len(cur) == 2 and len(cur[0]["n"]) + len(cur[1]["n"]) > 12):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    # undgå enlige småord
    merged = []
    for g in out:
        if merged and len(g) == 1 and len(g[0]["n"]) <= 2 and len(merged[-1]) < 3:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    return merged


def build_ass(cfg, words, beats):
    accents = [norm(a) for a in cfg.get("accent", [])]
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,2,60,60,350,1
Style: Hook,DejaVu Sans,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,1,2,60,60,350,1
Style: Graf,DejaVu Sans,70,&H00FFFFFF,&H00FFFFFF,&H00412A1B,&H26412A1B,-1,0,0,0,100,100,0,0,3,22,0,8,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    sk = cfg.get("skaermtekst")
    if sk:
        ev.append(f"Dialogue: 1,{asst(0)},{asst(SKAERM_SLUT)},Hook,,0,0,0,,{{\\fad(0,150)}}{accent_markup(sk)}")
    # undertekster: én accent pr. sætning, starter når skærmteksten er væk
    used_sentence = set()
    sent = 0
    for w in words:                      # sætningsnummer pr. ord
        w["sent"] = sent
        if re.search(r"[.?!][\"”]?$", w["w"]):
            sent += 1
    for g in groups(words, accents):
        s, e = g[0]["s"], g[-1]["e"]
        if sk and e <= SKAERM_SLUT:
            continue
        s = max(s, SKAERM_SLUT if sk else 0)
        e = max(e, s + 0.3)
        toks = []
        for w in g:
            n = w["sent"]
            target = accents[n] if n < len(accents) else ""
            if n not in used_sentence and target and w["n"] == target:
                toks.append(GUL + w["w"] + HVID); used_sentence.add(n)
            else:
                toks.append(w["w"])
        ev.append(f"Dialogue: 0,{asst(s)},{asst(e)},Sub,,0,0,0,,{' '.join(toks)}")
    # grafik-punkter: på brystet, under ansigtet og over underteksterne
    for b in beats:
        if b["type"] != "GRAF" and not b.get("grafik"):
            continue
        lines = b.get("grafik", [])
        i0, i1 = b["wi"]
        bwords = words[i0:i1]
        y = 1060
        for label, value, trig in lines:
            t = next((w["s"] for w in bwords if w["n"] == norm(trig)), b["s"])
            ev.append(f"Dialogue: 2,{asst(t)},{asst(b['e'])},Graf,,0,0,{y},,{{\\fad(200,0)}}{label} {GUL}{value}{HVID}")
            y += 150
    return hdr + "\n".join(ev) + "\n"


def main():
    cfg_p, avatar, srt, out = sys.argv[1:5]
    cfg = json.load(open(cfg_p, encoding="utf-8"))
    words = srt_words(srt)
    beats = align(cfg["beats"], words)
    total = dur(avatar)
    segs = plan(beats, total)
    tmp = tempfile.mkdtemp(prefix="reel_")
    vid = render(segs, avatar, tmp)
    ass = os.path.join(tmp, "tekst.ass")
    open(ass, "w", encoding="utf-8").write(build_ass(cfg, words, beats))
    run(["ffmpeg", "-y", "-i", vid, "-i", avatar, "-map", "0:v", "-map", "1:a",
         "-vf", f"subtitles={ass}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", out])
    for a, c, src, z in segs:
        print(f"{a:6.2f}-{c:6.2f}  {c-a:4.2f}s  {'AV-zoom' if src=='AV' and z else ('AV' if src=='AV' else os.path.basename(src))}")
    print("OK", out)


if __name__ == "__main__":
    main()
