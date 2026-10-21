"""Storyboard afsnit 6 — mekaniske tjek, kørt som kode (fra tørsvømning 21/10-2026).
Brug: python3 tools/mekaniske_tjek.py opslag.json   (liste af opslag; manuskript eller beats)
Regler afskrevet fra Notion: Storyboard-værktøj — krav, Scripting Framework, Den røde tråd."""
import json, re, sys

FORBUDT = [r"diagnos\w*", r"\bvaner?\w*", r"\bbasic\b", r"t-kryds\w*", r"\breview\b", r"check-in",
           r"\bmatch\b", r"to-do", r"selvindsigt", r"selvforståelse", r"\btændt\b", r"selvtilfredshed"]
FOERSTE_KONTAKT = [r"bundniveau\w*", r"dårlige? dag\w*"]
ABSTRAKT = [r"\bsystem\w*", r"\bintention\w*", r"\bproces\w*", r"\bbeslut\w*", r"\bprincip\w*"]
PRIS_KURSUS =[r"\bkr\.?\b", r"4\.?995", r"bliv ceo"]
DISCLOSURE = "🤖 Skabt med AI (avatar, stemme og video)."
KEYWORD = "START"

def talt(manus):
    return re.sub(r"\[[^\]]*\]", " ", manus)

def ord(t):
    return re.findall(r"[\wæøåÆØÅ]+", t)

def manuskript(p):
    """Manuskript som beat-liste ([TYPE | billede] tekst) — bygges af beats, hvis de findes."""
    if p.get("beats"):
        return " ".join(f"[{b[0]} | {b[3]}] {b[2]}" for b in p["beats"])
    return p["manuskript"]

def tjek(p):
    p = dict(p, manuskript=manuskript(p))
    res = []
    tale = talt(p["manuskript"]).strip()
    n = len(ord(tale))
    res.append(("Højst 100–120 ord", n <= 120, f"{n} ord"))
    sk = p["skaermtekst"].replace("*", "")
    skn = len(ord(sk))
    res.append(("Skærmtekst 2–5 ord", 2 <= skn <= 5, f"{skn} ord"))
    res.append(("Ét accentord", p["skaermtekst"].count("*") == 2, p["skaermtekst"]))
    res.append(("Skærmtekst = første talte ord", tale.lower().startswith(sk.lower()), f"tale starter: '{tale[:40]}'"))
    # Situation først (Scripting Framework, tilføjet 21/10-2026 efter SOP-kørsel 2)
    sit = re.search(r"Situation:\s*\S", p.get("noter", "") + " " + p.get("situation", ""))
    res.append(("Situation-linje skrevet før manuskript", bool(sit), "mangler 'Situation: sted · tid · handling'" if not sit else ""))
    foerste = re.split(r"(?<=[.!?])\s", tale, maxsplit=1)[0].lower() + " " + sk.lower()
    hit = [w for w in ABSTRAKT if re.search(w, foerste)]
    res.append(("Ingen abstrakte ord i skærmtekst/første sætning", not hit, ", ".join(hit)))
    res.append(("Ét udbytte i CTA", not re.search(r"igennem, og |, og om du", tale), ""))
    alt = (tale + " " + p["billedtekst"]).lower()
    res.append(("Keyword START", KEYWORD in p["manuskript"] and KEYWORD in p["billedtekst"], ""))
    ctas = len(re.findall(r"\bkommenter\b|følg mig|link i bio|del (den|det|opslaget) med|\bgem (den|det|opslaget)\b", alt))
    res.append(("Én CTA (ingen stablede)", ctas <= 2, f"{ctas} CTA-ord (tale+billedtekst)"))
    hit = [w for w in FORBUDT if re.search(w, alt)]
    res.append(("Forbudte ord", not hit, ", ".join(hit)))
    hit = [w for w in FOERSTE_KONTAKT if re.search(w, alt)]
    res.append(("Metodeord i første kontakt", not hit, ", ".join(hit)))
    hit = [w for w in PRIS_KURSUS if re.search(w, alt)]
    res.append(("Pris/kursusnavn", not hit, ", ".join(hit)))
    res.append(("Disclosure-linje", p["billedtekst"].strip().endswith(DISCLOSURE), ""))
    linjer = [l for l in p["billedtekst"].split("\n\n") if l.strip()]
    res.append(("Billedtekst 3 linjer + disclosure", len(linjer) == 4, f"{len(linjer)} blokke"))
    emojis = len(re.findall(r"[\U0001F300-\U0001FAFF]", p["billedtekst"] + p["manuskript"]))
    res.append(("Højst én emoji", emojis <= 1, f"{emojis}"))
    return res

def uge(posts):
    res = []
    for a, b in zip(posts, posts[1:]):
        res.append((f"{a['id']}→{b['id']} ikke samme indholdstype", a["indholdstype"] != b["indholdstype"],
                    f"{a['indholdstype']} / {b['indholdstype']}"))
        res.append((f"{a['id']}→{b['id']} ikke samme hook-vinkel", a["hook_vinkel"] != b["hook_vinkel"], ""))
    return res

if __name__ == "__main__":
    posts = json.load(open(sys.argv[1], encoding="utf-8"))
    for p in posts:
        print(f"\n== {p['id']} {p['titel']} (format {p['videoformat']})")
        for navn, ok, info in tjek(p):
            print(f"  {'✅' if ok else '❌'} {navn} {('— ' + info) if info else ''}")
    print("\n== Ugen / variation")
    for navn, ok, info in uge(posts):
        print(f"  {'✅' if ok else '❌'} {navn} {('— ' + info) if info else ''}")
