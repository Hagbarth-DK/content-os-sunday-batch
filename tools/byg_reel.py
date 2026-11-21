#!/usr/bin/env python3
"""Byg en reel efter Video Templates — HeyGen / Redigeringsopskrift (hybrid, låst 21/11-2026).

Metode B (standard): avatar-video fra create_video_from_avatar (ét look, ét talespor) + SRT.
Metode C (Iman-mode): lydfil fra create_speech (ét talespor) + SRT med ord-tider + én
avatar-video pr. AV-beat (renderet i HeyGen med lydstykket fra "split" og et look efter
beatets kamera-kode, se Notion: HeyGen-looks — masterdata).

JSON-konfiguration:
{
  "skaermtekst": "Har du en *tandlægetid*",
  "beats": [
    {"type": "AV",   "text": "...", "billede": "[TÆT] Look: bibliotek, sort jakke",
                     "av_klip": "valgfri/sti/beat01.mp4"},   # kun Metode C
    {"type": "SIT",  "text": "...", "klip": "sti/til/klip.mp4"},
    {"type": "GRAF", "text": "...", "billede": "[MEDIUM] ...", "grafik": [["Tandlæge:", "i kalenderen", "Tandlægen"], ...]},
    ...
  ],
  "accent": ["ord1", "", "ord3", ...]  # accentord pr. sætning i rækkefølge ("" = intet)
}
grafik-linjer: [label, værdi, udløserord] — linjen toner frem, når udløserordet siges.

Kamera-koder (Hagbarth 21/11-2026, Scripting Framework → Klip-rytme og B-roll):
  Billedbeskrivelsen ("billede", eller "beskrivelse") på et avatar-beat starter med
  [TÆT], [MEDIUM] eller [UDE] ([FORSKUDT] læses som [UDE]).
  Metode B: koden styrer den digitale beskæring af avataren (KAMERA nedenfor). Mangler
  koden, skifter beskæringen automatisk mellem helt billede og tæt.
  Metode C: maks. 2 looks pr. video (ét pr. miljø, inde/ude, Hagbarth 21/11-2026). Beatets
  klip er renderet med miljøets look; [TÆT] beskæres tæt, [MEDIUM] og [UDE] vises helt.
  Deles et langt beat i flere stykker, skifter de næste stykker automatisk, så der stadig
  er et billedskift.

Lyden er altid det ene ubrudte talespor. Billedet skifter ovenpå.

Brug:
  Metode B:  python3 tools/byg_reel.py config.json avatar.mp4 avatar.srt ud.mp4
  Metode C:  python3 tools/byg_reel.py split config.json tale.mp3 tale.srt mappe/
             (lav beatNN.mp4 i HeyGen fra hver beatNN.mp3, læg dem i mappe/)
             python3 tools/byg_reel.py config.json tale.mp3 tale.srt ud.mp4 --av-mappe mappe/
  Ord-tidsstempler fra create_speech skrives som SRT med ét ord pr. blok.
  beatNN svarer til beatets nummer i konfigurationen (01 = første beat).
"""
import json, re, subprocess, sys, os, tempfile

W, H, FPS = 1080, 1920, 25
# Alle avatar-klip bringes først til 1080x1920 (fx digital_twin-looks i 720x1280,
# skovsti-lookket i 3:4), derefter beskæres efter kamera-kode.
NORM = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
KAMERA = {
    "TÆT": "crop=760:1350:160:60,scale=1080:1920",
    "UDE": "crop=840:1493:190:120,scale=1080:1920",   # tidligere [FORSKUDT]
    "MEDIUM": "scale=1080:1920",
}
ZOOM = KAMERA["TÆT"]   # bevaret navn (tidligere eneste zoom)
MAX_MID = 3.4      # klippegrænse i midten: holder Realisme-tjekkets 4,0 sek. med margin
MAX_END = 5.5      # klippegrænse i hook og CTA: holder Realisme-tjekkets 6,0 sek. med margin
SKAERM_SLUT = 2.5
KODE_RE = re.compile(r"^\s*\[(TÆT|MEDIUM|UDE|FORSKUDT)\]", re.I)
ALIAS = {"FORSKUDT": "UDE"}


def kamera_kode(b):
    """Kamera-koden forrest i beatets billedbeskrivelse, eller None."""
    m = KODE_RE.match(b.get("billede") or b.get("beskrivelse") or "")
    if not m:
        return None
    k = m.group(1).upper()
    return ALIAS.get(k, k)


def er_avatar_beat(b):
    """Beats, hvor avataren ses: AV, GRAF og SIT uden klip."""
    return not (b["type"] == "SIT" and b.get("klip"))


def har_video(path):
    return bool(run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                     "stream=index", "-of", "csv=p=0", path]).strip())


def skift(forrige):
    """Automatisk skift, når koden mangler: helt billede ↔ tæt."""
    return "TÆT" if forrige == "MEDIUM" else "MEDIUM"


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


def grænser(beats, total):
    """Faste start/slut pr. beat. Bruges både af split og af klipningen, så de altid passer."""
    beats[0]["s"] = 0.0
    beats[-1]["e"] = total


def av_klip(b, k, av_mappe):
    """Metode C: beatets eget avatar-klip, eller None."""
    if b.get("av_klip"):
        return b["av_klip"]
    if av_mappe:
        p = os.path.join(av_mappe, f"beat{k + 1:02d}.mp4")
        if os.path.exists(p):
            return p
    return None


def plan(beats, total, av_mappe=None, avatar_video=True):
    """Segmenter: (start, slut, kilde, kamera-kode eller None for klip, (av-klip, beat-start) eller None)."""
    segs = []
    grænser(beats, total)
    forrige = None      # seneste avatar-beskæring
    sidste_kode = None  # kamera-koden på det avatar-beat, der ligger lige før (til advarslen)
    for k, b in enumerate(beats):
        end = k in (0, len(beats) - 1)
        lim = MAX_END if end else MAX_MID
        if not avatar_video and not er_avatar_beat(b):
            segs.append((b["s"], b["e"], b["klip"], None, None))    # Metode C: klippet dækker hele beatet
            sidste_kode = None
            continue
        if b["type"] == "SIT" and b.get("klip"):
            klen = min(dur(b["klip"]) - 0.1, MAX_MID)
            sit_end = min(b["e"], b["s"] + klen)
            if 0.3 < b["e"] - sit_end < 1.2:      # undgå et kort hak bagefter
                sit_end = b["e"] - 1.2
            segs.append((b["s"], sit_end, b["klip"], None, None))
            if b["e"] - sit_end > 0.3:
                for a, c in chunk(sit_end, b["e"], MAX_MID):
                    forrige = skift(forrige)
                    segs.append((a, c, "AV", forrige, None))
            else:
                segs[-1] = (b["s"], b["e"], b["klip"], None, None)
            sidste_kode = None
            continue
        kode = kamera_kode(b)
        klip = av_klip(b, k, av_mappe)
        if not avatar_video and not klip:
            raise SystemExit(f"Fejl: beat {k + 1} mangler sit avatar-klip (beat{k + 1:02d}.mp4 eller \"av_klip\")")
        if kode and kode == sidste_kode:
            sys.stderr.write(f"Advarsel: beat {k + 1} har samme kamera-kode [{kode}] som avatar-beatet lige før\n")
        sidste_kode = kode
        for n, (a, c) in enumerate(chunk(b["s"], b["e"], lim)):
            if n == 0 and klip:
                # Metode C: miljøets look (maks. 2 pr. video); koden styrer beskæringen
                valgt = "TÆT" if kode == "TÆT" else "MEDIUM"
            elif n == 0 and kode:
                valgt = kode
            elif n == 0 and k == 0:
                valgt = "MEDIUM"                 # hook uden kode: helt billede, som før
            else:
                valgt = skift(forrige)
            segs.append((a, c, "AV", valgt, (klip, b["s"]) if klip else None))
            forrige = valgt
    return segs


def render(segs, avatar, tmp):
    parts = []
    for n, (a, c, src, kode, avk) in enumerate(segs):
        out = os.path.join(tmp, f"s{n:02d}.mp4")
        d = c - a
        if src == "AV":
            kilde, start = (avk[0], a - avk[1]) if avk else (avatar, a)
            # tpad: er beatets klip lidt kortere end beatet, holdes sidste billede
            vf = f"{NORM},{KAMERA[kode]},fps={FPS},setsar=1,tpad=stop_mode=clone:stop_duration=2"
            run(["ffmpeg", "-y", "-ss", f"{max(0, start):.3f}", "-i", kilde, "-an",
                 "-vf", vf, "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-pix_fmt", "yuv420p", out])
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


def split(cfg_p, lyd, srt, mappe):
    """Metode C: klip talesporet ud pr. avatar-beat (beatNN.mp3) med klipningens grænser."""
    cfg = json.load(open(cfg_p, encoding="utf-8"))
    beats = align(cfg["beats"], srt_words(srt))
    grænser(beats, dur(lyd))
    os.makedirs(mappe, exist_ok=True)
    for k, b in enumerate(beats):
        if not er_avatar_beat(b):
            continue
        out = os.path.join(mappe, f"beat{k + 1:02d}.mp3")
        run(["ffmpeg", "-y", "-ss", f"{b['s']:.3f}", "-t", f"{b['e'] - b['s']:.3f}", "-i", lyd,
             "-vn", "-c:a", "libmp3lame", "-b:a", "192k", out])
        print(f"beat{k + 1:02d}  {b['s']:6.2f}-{b['e']:6.2f}  [{kamera_kode(b) or '-'}]  {out}")
    print("OK", mappe)


def main():
    args = sys.argv[1:]
    if args and args[0] == "split":
        return split(*args[1:5])
    av_mappe = None
    if "--av-mappe" in args:
        i = args.index("--av-mappe")
        av_mappe = args[i + 1]
        del args[i:i + 2]
    cfg_p, avatar, srt, out = args[:4]
    cfg = json.load(open(cfg_p, encoding="utf-8"))
    words = srt_words(srt)
    beats = align(cfg["beats"], words)
    total = dur(avatar)
    segs = plan(beats, total, av_mappe, har_video(avatar))
    tmp = tempfile.mkdtemp(prefix="reel_")
    vid = render(segs, avatar, tmp)
    ass = os.path.join(tmp, "tekst.ass")
    open(ass, "w", encoding="utf-8").write(build_ass(cfg, words, beats))
    run(["ffmpeg", "-y", "-i", vid, "-i", avatar, "-map", "0:v", "-map", "1:a",
         "-vf", f"subtitles={ass}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", out])
    for a, c, src, kode, avk in segs:
        navn = (f"AV-{kode}" + (f" ({os.path.basename(avk[0])})" if avk else "")) if src == "AV" else os.path.basename(src)
        print(f"{a:6.2f}-{c:6.2f}  {c-a:4.2f}s  {navn}")
    print("OK", out)


if __name__ == "__main__":
    main()
