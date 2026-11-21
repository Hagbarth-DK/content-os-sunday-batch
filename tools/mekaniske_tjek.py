"""Mekaniske tjek — kun brand- og teknik-tjek (ja/nej, intet skøn).

Brug: python3 tools/mekaniske_tjek.py opslag.json   (liste af opslag; manuskript eller beats)

Beslutning 24/10-2026 (Hagbarth):
  - Skribenten skriver efter Imans opskrift (hensigt, mekanik, eksempler) og bruger skøn.
  - Gatekeeperen sikrer det danske sprog.
  - Formreglerne fra testkørsel 1-15 er parkeret. Den gamle version ligger i
    tools/arkiv/mekaniske_tjek_K15_2026-10-22.py og bruges ikke.

Tilføjet 15/11-2026 (Hagbarth, rodårsag: B-roll blev ikke lavet i første omgang):
  - Klip-rytme: hvert midter-beat højst ca. 4 sek. anslået taletid.
  - Hvert KLIP/SIT-beat skal nævne et .mp4, der findes i assets/broll eller assets/situationer.
  - Ingen pladsholdertekst (fx "Kandidat", "mangler") i billedbeskrivelser.

Tilføjet 21/11-2026 (Hagbarth, dynamisk kamerastyring):
  - Advarsel, hvis to AV-beats lige efter hinanden har samme kamera-kode ([TÆT]/[MEDIUM]/[UDE];
    [FORSKUDT] læses som [UDE]).
  - Advarsel, hvis en video har mere end 2 forskellige looks ("Look: …" i AV-beatenes billede).

Tjekket her fanger kun det, der aldrig må slippe igennem (Låste regler i Notion),
plus det, produktionen teknisk afhænger af. ❌ = stop, ⚠️ = advarsel.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KLIP_MAPPER = ["assets/broll", "assets/situationer"]
# Klip-rytme (Hagbarth 15/11-2026, Iman-stil): midter-beats højst ca. 4 sek.
ORD_PR_SEK = 3.5        # målt på onsdagsvideoen 18/11 (98 ord / 27,9 sek., speed 0.98)
MAX_BEAT_SEK = 4.5      # "ca. 4 sek." med lidt luft
PLADSHOLDER = r"kandidat|pladsholder|placeholder|\btbd\b|\btodo\b|mangler|når den er|skal laves|\?\?"

FORBUDT = [r"diagnos\w*", r"\bvaner?\w*", r"\bbasic\b", r"t-kryds\w*", r"\breview\b", r"check-in",
           r"\bmatch\b", r"to-do", r"selvindsigt", r"selvforståelse", r"\btændt\b", r"selvtilfredshed"]
FOERSTE_KONTAKT = [r"bundniveau\w*", r"dårlige? dag\w*"]   # kun i forløbet, aldrig i første kontakt
PRIS_KURSUS = [r"\bkr\.?\b", r"4\.?995", r"bliv ceo"]
DISCLOSURE = "🤖 Skabt med AI (avatar, stemme og video)."
KEYWORD = "START"
CTA_ORD = r"\bkommenter\b|følg mig|link i bio|del (den|det|opslaget) med|\bgem (den|det|opslaget)\b"
FORKORTELSER = r"(?<![\wæøå])(fx|f\.eks\.|bl\.a\.|evt\.|ca\.|osv\.|mht\.|dvs\.)"  # læses forkert op af stemmen


def talt(manus):
    return re.sub(r"\[[^\]]*\]", " ", manus)


def ord(t):
    return re.findall(r"[\wæøåÆØÅ]+", t)


def sek(talt_tekst):
    """Anslået taletid. Tal læses som ord (4.000 = 'fire tusind'), derfor tæller et tal for 2 ord."""
    n = len(re.findall(r"[a-zA-ZæøåÆØÅéÉ]+", talt_tekst)) + 2 * len(re.findall(r"\d+(?:[.,]\d+)*", talt_tekst))
    return n / ORD_PR_SEK


KAMERA_KODE = re.compile(r"^\s*\[(TÆT|MEDIUM|UDE|FORSKUDT)\]", re.I)


def kamera_kode(beskrivelse):
    """Kamera-koden forrest i et beats billedbeskrivelse ([TÆT]/[MEDIUM]/[UDE]), eller None.
    [FORSKUDT] (gammel kode før 21/11-2026) læses som [UDE]."""
    m = KAMERA_KODE.match(beskrivelse or "")
    if not m:
        return None
    k = m.group(1).upper()
    return "UDE" if k == "FORSKUDT" else k


def look(beskrivelse):
    """Lookket fra "Look: …" i en billedbeskrivelse (til og med første punktum/parentes), eller None."""
    m = re.search(r"look:\s*([^.(\n]+)", beskrivelse or "", re.I)
    return m.group(1).strip().rstrip(",").lower() if m else None


def klip_fil(beskrivelse):
    m = re.search(r"([\w\-]+\.mp4)", beskrivelse or "")
    if not m:
        return None, False
    return m.group(1), any(os.path.exists(os.path.join(ROOT, d, m.group(1))) for d in KLIP_MAPPER)


def rytme(p):
    """Klip-rytme og B-roll: midter-beats ≤ ca. 4 sek.; KLIP/SIT-beats skal pege på en fil, der findes."""
    res = []
    beats = p.get("beats") or []
    if not beats:
        return [("Beats findes (klip-rytme kan tjekkes)", False, "ingen beats", "stop")]
    lange = [f"beat {i + 1}: {sek(b[2]):.1f} sek." for i, b in enumerate(beats)
             if 0 < i < len(beats) - 1 and sek(b[2]) > MAX_BEAT_SEK]
    res.append((f"Klip-rytme: midter-beats højst ca. 4 sek. (grænse {MAX_BEAT_SEK})", not lange, "; ".join(lange), "stop"))
    mangler, pladsh = [], []
    for i, b in enumerate(beats):
        typ, beskr = b[0], b[3] if len(b) > 3 else ""
        if typ in ("KLIP", "SIT"):
            fil, findes = klip_fil(beskr)
            if not findes:
                mangler.append(f"beat {i + 1}: {fil or 'intet .mp4 angivet'}")
        if re.search(PLADSHOLDER, beskr or "", re.I):
            pladsh.append(f"beat {i + 1}")
    res.append(("B-roll-klip findes i assets/ (broll eller situationer)", not mangler, "; ".join(mangler), "stop"))
    res.append(("Ingen pladsholdertekst i billedbeskrivelser", not pladsh, ", ".join(pladsh), "stop"))
    midt = beats[1:-1]
    ikke_av = sum(1 for b in midt if b[0] != "AV")
    res.append(("Midten er mest B-roll/grafik (Iman-stil)", ikke_av >= len(midt) / 2, f"{ikke_av} af {len(midt)} ikke-avatar", "advarsel"))
    # Kamera-koder (Hagbarth 21/11-2026): aldrig samme kode på to AV-beats lige efter hinanden.
    ens = []
    for i in range(1, len(beats)):
        a, b = beats[i - 1], beats[i]
        if a[0] == "AV" and b[0] == "AV":
            ka = kamera_kode(a[3] if len(a) > 3 else "")
            kb = kamera_kode(b[3] if len(b) > 3 else "")
            if ka and ka == kb:
                ens.append(f"beat {i} og {i + 1}: [{ka}]")
    res.append(("Kamera-kode skifter mellem AV-beats lige efter hinanden", not ens, "; ".join(ens), "advarsel"))
    # Maks. 2 lokationer/looks pr. video (Hagbarth 21/11-2026), læst fra "Look: …" i billedbeskrivelserne.
    looks = sorted({look(b[3]) for b in beats if b[0] == "AV" and len(b) > 3 and look(b[3])})
    res.append(("Maks. 2 looks pr. video", len(looks) <= 2, " · ".join(looks), "advarsel"))
    return res


def manuskript(p):
    """Manuskript som beat-liste ([TYPE | billede] tekst) — bygges af beats, hvis de findes."""
    if p.get("beats"):
        return " ".join(f"[{b[0]} | {b[3]}] {b[2]}" for b in p["beats"])
    return p.get("manuskript", "")


def tjek(p):
    """Returnerer liste af (navn, ok, info, alvor) — alvor er 'stop' eller 'advarsel'."""
    manus = manuskript(p)
    tale = talt(manus).strip()
    billedtekst = p.get("billedtekst", "")
    skaerm = p.get("skaermtekst", "")
    alt = (tale + " " + billedtekst).lower()
    res = []

    # --- Brand (Låste regler) ---
    hit = [w for w in FORBUDT if re.search(w, alt)]
    res.append(("Forbudte ord", not hit, ", ".join(hit), "stop"))
    hit = [w for w in FOERSTE_KONTAKT if re.search(w, alt)]
    res.append(("Metodeord i første kontakt (bundniveau/dårlige dage)", not hit, ", ".join(hit), "stop"))
    hit = [w for w in PRIS_KURSUS if re.search(w, alt)]
    res.append(("Pris/kursusnavn", not hit, ", ".join(hit), "stop"))
    res.append(("Keyword START i tale og billedtekst", KEYWORD in manus and KEYWORD in billedtekst, "", "stop"))
    ctas = len(re.findall(CTA_ORD, alt))
    res.append(("Én CTA (ingen stablede)", ctas <= 2, f"{ctas} CTA-ord (tale+billedtekst)", "stop"))

    # --- Teknik (produktion og Instagram) ---
    res.append(("AI-disclosure i billedteksten", DISCLOSURE in billedtekst, "", "stop"))
    fk = re.findall(FORKORTELSER, tale.lower())
    res.append(("Ingen forkortelser i talt tekst (stemmen læser dem forkert)", not fk, ", ".join(fk), "stop"))
    sk = re.sub(r"[*\"“”„«»]", "", skaerm).strip()
    res.append(("Skærmtekst udfyldt", bool(sk), "", "stop"))
    res.append(("Skærmtekst har ét accentord (*ord*) til gul markering", skaerm.count("*") == 2, skaerm, "advarsel"))
    res.append(("Skærmtekst = de første talte ord (Imans mekanik)",
                bool(sk) and re.sub(r"^[\"“”„«»\s]+", "", tale).lower().startswith(sk.rstrip("?").lower()),
                f"tale starter: '{tale[:40]}'", "advarsel"))
    n = len(ord(tale))
    res.append(("Længde ca. som Imans (højst ca. 120 ord)", n <= 120, f"{n} ord", "advarsel"))
    res += rytme(p)
    return res


def mark(ok, alvor):
    if ok:
        return "✅"
    return "❌" if alvor == "stop" else "⚠️"


if __name__ == "__main__":
    posts = json.load(open(sys.argv[1], encoding="utf-8"))
    stop = 0
    for p in posts:
        print(f"\n== {p.get('id', '?')} {p.get('titel', '')}")
        for navn, ok, info, alvor in tjek(p):
            if not ok and alvor == "stop":
                stop += 1
            print(f"  {mark(ok, alvor)} {navn} {('— ' + info) if info else ''}")
    print(f"\n{'OK' if stop == 0 else f'{stop} stop-fejl'}")
    sys.exit(1 if stop else 0)
