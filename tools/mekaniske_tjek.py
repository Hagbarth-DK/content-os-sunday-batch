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
    sk = re.sub(r"[*\"“”„«»]", "", p["skaermtekst"]).strip()
    skn = len(ord(sk))
    res.append(("Skærmtekst 2–5 ord", 2 <= skn <= 5, f"{skn} ord"))
    res.append(("Ét accentord", p["skaermtekst"].count("*") == 2, p["skaermtekst"]))
    res.append(("Skærmtekst = første talte ord", tale.lower().startswith(sk.lower()), f"tale starter: '{tale[:40]}'"))
    # Situation først (Scripting Framework, tilføjet 21/10-2026 efter SOP-kørsel 2)
    sit = re.search(r"Situation:\s*\S", p.get("noter", "") + " " + p.get("situation", ""))
    res.append(("Situation-linje skrevet før manuskript", bool(sit), "mangler 'Situation: sted · tid · handling'" if not sit else ""))
    # Kørsel 3: situationen skal have tre dele, og handlingen skal være konkret (ikke "intet"/"noget")
    m = re.search(r"Situation:\s*(.+)", p.get("noter", ""))
    dele = [d.strip() for d in m.group(1).split("·")] if m else []
    vag = bool(dele) and len(dele) == 3 and re.search(r"\b(intet|ingenting|noget)\b", dele[2].lower())
    res.append(("Situation har sted · tid · konkret handling", len(dele) == 3 and not vag,
                f"{len(dele)} dele" + (", handlingen er vag" if vag else "")))
    foerste_ord = re.split(r"(?<=[.!?])\s", tale, maxsplit=1)[0]
    res.append(("Spørgsmål i hook = spørgsmålstegn i skærmtekst",
                not foerste_ord.strip().endswith("?") or p["skaermtekst"].strip().endswith("?"), ""))
    tretal = re.findall(r"\b\w+, \w+ og \w+\b", tale)
    res.append(("Ingen tretals-opremsning som pynt", not tretal, ", ".join(tretal)))
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
    res += tjek_k5(p, tale, sk, foerste_ord, dele, linjer)
    return res


# Kørsel 5: reglerne fandtes, men skribenten fulgte dem ikke. Derfor felter, der tvinger
# reglen frem, i stedet for flere regler: "emne" (den konkrete ting, der ligger stille)
# og "idebank_soejle" (søjlen, som idébanken angiver).
VAG_EKSTRA = r"\b(planer|planlagt|ting|tingene|det hele|alt det)\b"
MORAL = r"resten af dit liv|det er der,|det handler om|sådan er livet|det er det, der"


def stamme(o):
    o = o.lower().strip(".,!?*")
    return o[:5] if len(o) > 5 else o


def tjek_k5(p, tale, sk, foerste, dele, linjer):
    res = []
    emne = p.get("emne", "").strip()
    res.append(("Emne-felt udfyldt (den ting, der ligger stille)", bool(emne), ""))
    if emne:
        st = stamme(emne.split()[-1])
        res.append(("Emneordet står i skærmteksten", st in sk.lower(), f"emne '{emne}' / skærmtekst '{sk}'"))
        res.append(("Emneordet står i første sætning", st in foerste.lower(), foerste[:60]))
        res.append(("Emneordet står i billedtekstens linje 1", bool(linjer) and st in linjer[0].lower(), ""))
        res.append(("Emneordet står i situationens handling", len(dele) == 3 and st in dele[2].lower(), ""))
    if len(dele) == 3:
        v = re.search(VAG_EKSTRA, dele[2].lower())
        res.append(("Handlingen er ikke 'planer'/'ting'", not v, v.group(0) if v else ""))
    saet = [s for s in re.split(r"(?<=[.!?])\s+", tale) if s.strip()]
    foer_cta = [s for s in saet if "START" not in s]
    sidste = foer_cta[-1] if foer_cta else ""
    m = re.search(MORAL, sidste.lower())
    res.append(("Ingen moralsk afrunding før CTA", not m, sidste[:60] if m else ""))
    n_ikke = len(re.findall(r"\bikke\b", tale.lower()))
    res.append(("Højst to 'ikke' (ingen dobbelt ikke-X-kontrast)", n_ikke <= 2, f"{n_ikke}"))
    # Etiketter følger indholdet (kontrolleret, ikke deklareret)
    hv, it, f1 = p["hook_vinkel"], p["indholdstype"], foerste.lower()
    ok, why = True, ""
    if hv == "Observation":
        ok = bool(re.search(r"\b(du|dig|din|dit)\b", f1)) and not re.search(r"\bjeg\b", f1); why = "Observation kræver du-form i første sætning"
    elif hv == "Sætningen de selv siger":
        ok = bool(re.search(r"\b(jeg|min|mit|mig|siger du)\b", (sk + " " + foerste).lower())); why = "kræver seerens egen sætning (jeg-form)"
    elif hv == "Regnestykke":
        to = " ".join(saet[:2]).lower()
        ok = bool(re.search(r"\d|\b(to|tre|fire|fem|seks|syv|otte|ti|tyve|femten|halvdelen)\b", to)); why = "kræver et tal i de to første sætninger"
    elif hv == "Billede":
        ok = bool(re.search(r"huset|speedbåd|vandstand", tale.lower())); why = "Billede = kun huset, speedbåden, vandstanden"
    elif hv == "Modsigelse":
        ok = bool(re.search(r"\b(men|hjælper ikke|tværtimod|sjældent)\b", " ".join(saet[:3]).lower())); why = "kræver en modsigelse i de tre første sætninger"
    res.append((f"Hook-vinkel '{hv}' passer til indholdet", ok, "" if ok else why))
    if it == "Historie":
        res.append(("Historie: hook er ikke Observation", hv != "Observation", hv))
        res.append(("Historie: billedtekst linje 1 er emnet, ikke 'Jeg …'", bool(linjer) and not linjer[0].strip().startswith("Jeg"), linjer[0][:50] if linjer else ""))
    ib = p.get("idebank_soejle", "")
    res.append(("Søjle = idébankens søjle", bool(ib) and ib[:1] == p["soejle"][:1], f"{p['soejle']} / idébank {ib or 'mangler'}"))
    res += tjek_k6(p, tale, emne, dele, saet)
    return res


# Kørsel 6: gatekeeperen dømte efter kriterier, skribenten ikke tjekkede. Det, der kan
# måles, måles nu her; resten står i skribentens selvtjek (SOP trin 2b).
FYLD = r"det har du vidst længe|det, der virker, er|det er det hele|sådan er det bare|det ved du godt"
LED4 = ["også når konsulenten er kørt hjem", "selv stået præcis dér"]


def tjek_k6(p, tale, emne, dele, saet):
    res = []
    acc = re.findall(r"\*([^*]+)\*", p["skaermtekst"])
    if emne:
        res.append(("Accentordet er emneordet", bool(acc) and stamme(emne.split()[-1]) in acc[0].lower(), f"accent '{acc[0] if acc else ''}' / emne '{emne}'"))
    if len(dele) == 3:
        sted = stamme(dele[0].split()[-1])
        res.append(("Situationens sted står i teksten", sted in tale.lower(), f"sted '{dele[0]}'"))
    res.append(("Jobbet vs. resten af livet er med ('jobbet')", "jobbet" in tale.lower() or "arbejdet" in tale.lower(), ""))
    f = re.search(FYLD, tale.lower())
    res.append(("Ingen fyldsætninger", not f, f.group(0) if f else ""))
    if p["hook_vinkel"] == "Sætningen de selv siger":
        res.append(("Seerens egen sætning står i anførselstegn i skærmteksten", bool(re.search(r"[\"“„«]", p["skaermtekst"])), p["skaermtekst"]))
    if p["indholdstype"] == "Tilbud" or "30 år" in tale:
        n = len(re.findall(r"\btest\w*|\bviser\b", tale.lower())) - 1
        res.append(("Testens udbytte loves kun én gang (i CTA)", n <= 1, f"{n} løfter"))
        res.append(("Bevis = Den røde tråd led 4 ordret", all(s in tale for s in LED4), "brug led 4's ordlyd"))
    # Problemordet: situationen og jobsammenligningen skal handle om det samme problem.
    prob = p.get("problem", "").strip().lower()
    beats = p.get("beats", [])
    job = [b[2].lower() for b in beats if "jobbet" in b[2].lower() or "arbejdet" in b[2].lower()]
    if prob:
        ps = stamme(prob)
        ok = bool(beats) and ps in beats[0][2].lower() and any(ps in j for j in job)
        res.append(("Problemordet står i genkendelsen OG i jobsammenligningen", ok, f"problem '{prob}'"))
    else:
        res.append(("Problem-felt udfyldt (ét ord: hvorfor ligger det stille?)", False, ""))
    st = p.get("selvtjek", {})
    res.append(("Skribentens selvtjek udfyldt (AI-markører ≤1, send-til)",
                isinstance(st, dict) and st.get("ai_markoerer", 9) <= 1 and bool(st.get("send_til")), str(st)))
    klip_trin = [b[1] for b in p.get("beats", []) if b[0] == "KLIP"]
    res.append(("KLIP kun i Forståelse (klippene viser Twin, ikke seerens situation)", all(t == "Forståelse" for t in klip_trin), ", ".join(klip_trin)))
    return res

def uge(posts):
    res = []
    # Kørsel 4: samme klip i alle opslag. Maks. 2 gange pr. uge og aldrig to dage i træk.
    klip = [set(re.findall(r"([\w\-]+\.mp4)", " ".join(b[3] for b in p.get("beats", [])))) for p in posts]
    alle = [k for s in klip for k in s]
    for k in sorted(set(alle)):
        res.append((f"Klip {k} højst 2 gange i ugen", alle.count(k) <= 2, f"{alle.count(k)} gange"))
    for a, b, ka, kb in zip(posts, posts[1:], klip, klip[1:]):
        res.append((f"{a['id']}→{b['id']} ikke samme klip", not (ka & kb), ", ".join(ka & kb)))
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
