"""Mekaniske tjek — kun brand- og teknik-tjek (ja/nej, intet skøn).

Brug: python3 tools/mekaniske_tjek.py opslag.json   (liste af opslag; manuskript eller beats)

Beslutning 24/10-2026 (Hagbarth):
  - Skribenten skriver efter Imans opskrift (hensigt, mekanik, eksempler) og bruger skøn.
  - Gatekeeperen sikrer det danske sprog.
  - Formreglerne fra testkørsel 1-15 er parkeret. Den gamle version ligger i
    tools/arkiv/mekaniske_tjek_K15_2026-10-22.py og bruges ikke.

Tjekket her fanger kun det, der aldrig må slippe igennem (Låste regler i Notion),
plus det, produktionen teknisk afhænger af. ❌ = stop, ⚠️ = advarsel.
"""
import json, re, sys

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
