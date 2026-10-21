#!/usr/bin/env python3
"""Bygger Notion-felter til Content Library og Storyboard-beats ud fra opslag.json.

Brug:
  python3 tools/til_notion.py opslag.json opslag "<kørsel-tekst>"        -> JSON til Content Library
  python3 tools/til_notion.py opslag.json beats <mappe> id=PAGEID ...    -> JSON til Storyboard-beats

Feltnavnene er Content Librarys/Storyboard-beats' egne (læs skemaet i Notion,
hvis det ændres). Værktøjet laver kun JSON; oprettelsen sker via Notion.
"""
import json, sys

RAW = "https://raw.githubusercontent.com/Hagbarth-DK/content-os-sunday-batch/main/"


def manus(p):
    return "\n".join(f"[{b[0]} | {b[3]}] {b[2]}" for b in p["beats"])


def opslag(P, korsel):
    out = []
    for p in P:
        noter = (f"{korsel}\n{p.get('noter', '')}\nEmne (det, der ligger stille): {p.get('emne', '')}\n"
                 f"Kildens søjle: {p.get('idebank_soejle', '')}\nVideoformat: {p['videoformat']} · Talking head med KLIP fra assets/broll\n"
                 f"Indholdstype: {p['indholdstype']}\nHook-vinkel: {p['hook_vinkel']}\nLyd: {p['lyd']}\nStemning: {p['stemning']}")
        out.append({"properties": {
            "Titel": p["titel"], "Status": "Draft", "Format": "Talking Head", "Søjle": p["soejle"],
            "Job i tragten": p["tragt"], "Hook": p["beats"][0][2], "Hook-kilde": "Egen",
            "Billedtekst": p["billedtekst"], "Keyword": "START", "Platform": '["Instagram"]', "Account": "Hagbarth",
            "date:Publiceringsdato:start": p["dato"], "date:Publiceringsdato:is_datetime": 0,
            "Manuskript": manus(p), "Skærmtekst (hook)": p["skaermtekst"],
            "Kilde-materiale": p["ide"], "Noter": noter, "Gatekeeper": "Ikke kørt",
            "Tjek": "OK (tools/mekaniske_tjek.py)"}})
    return out


def beats(P, mappe, ids):
    rows = []
    for p in P:
        for i, b in enumerate(p["beats"]):
            url = f"{RAW}{mappe}/{p['id'].lower()}_beat{i + 1:02d}.jpg"
            pr = {"Beat": f"{p['id']} · beat {i + 1}", "Nr": i + 1, "Beat-type": b[0], "Trin": b[1],
                  "Talt tekst": b[2], "Billede-beskrivelse": b[3], "Note": "Skitse: " + url,
                  "Opslag": json.dumps(["https://app.notion.com/p/" + ids[p["id"]]])}
            if i == 0:
                pr["Skærmtekst"] = p["skaermtekst"]
            rows.append({"properties": pr})
    return rows


if __name__ == "__main__":
    P = json.load(open(sys.argv[1], encoding="utf-8"))
    if sys.argv[2] == "opslag":
        print(json.dumps(opslag(P, sys.argv[3]), ensure_ascii=False))
    else:
        ids = dict(a.split("=", 1) for a in sys.argv[4:])
        print(json.dumps(beats(P, sys.argv[3], ids), ensure_ascii=False))
