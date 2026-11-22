#!/usr/bin/env python3
"""
Hent tal — henter Instagram-tal pr. reel og skriver dem i Notion Content Library.

Koeres af GitHub Actions (.github/workflows/hent-tal.yml) hver dag og ved push
til trigger/tal.txt. Bruges af marketingchefen (skill marketingchef, 22/11-2026).

Laeser hemmeligheder udelukkende fra miljoevariabler (GitHub Secrets). Noeglen
printes aldrig, og fejlbeskeder fra Meta gengives uden noeglen.

Env vars (GitHub Secrets):
  NOTION_API_KEY, NOTION_DATABASE_ID, IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID

Logik:
  1. Hent alle poster i Content Library med Status = "Published".
  2. Hent kontoens opslag fra Instagram (id, caption, tidspunkt).
  3. Match hver post: foerst paa "IG Media ID", ellers paa billedteksten
     (de foerste 80 tegn, uden mellemrumsforskelle). Usikkert match = spring over.
  4. Hent tallene pr. opslag (visninger, raekkevidde, visningstid, likes,
     kommentarer, gemt, delt) og taeller kommentarer, der indeholder postens
     Keyword. Et maalepunkt, Meta ikke leverer, springes over (gaettes aldrig).
  5. Skriv tallene i Notion-felterne "IG ..." og "IG Tal opdateret".
  6. Gem kontoens foelgertal med dato i trigger/foelgere.csv (historik).
  7. Kan noeglen ikke laese tal (manglende tilladelse), stopper scriptet med fejl.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ACCOUNT_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]

NOTION_VERSION = "2022-06-28"
GRAPH = "https://graph.instagram.com/v22.0"
DK = ZoneInfo("Europe/Copenhagen")

# Instagram-maalepunkt -> Notion-felt
METRICS = {
    "views": "IG Visninger",
    "reach": "IG Rækkevidde",
    "ig_reels_avg_watch_time": "IG Visningstid (sek)",  # leveres i millisekunder
    "likes": "IG Likes",
    "comments": "IG Kommentarer",
    "saved": "IG Gemt",
    "shares": "IG Delt",
}


def scrub(text):
    """Fjern noeglen fra en tekst, foer den printes."""
    return str(text).replace(IG_ACCESS_TOKEN, "***")


def http(method, url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": {"message": f"HTTP {e.code}"}}


def ig_get(path, **params):
    params["access_token"] = IG_ACCESS_TOKEN
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    return http("GET", url)


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def text_prop(props, name):
    prop = props.get(name) or {}
    t = prop.get("type")
    if t in ("rich_text", "title"):
        return "".join(p.get("plain_text", "") for p in prop.get(t, []))
    return ""


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()[:80]


def fetch_published():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    body = {"filter": {"property": "Status", "select": {"equals": "Published"}}, "page_size": 100}
    results = []
    while True:
        status, data = http("POST", url, notion_headers(), body)
        if status != 200:
            raise RuntimeError(f"Notion query fejlede ({status}): {data}")
        results += data.get("results", [])
        if not data.get("has_more"):
            return results
        body["start_cursor"] = data["next_cursor"]


def fetch_ig_media():
    media, after = [], None
    for _ in range(10):  # hoejst ca. 500 opslag
        params = {"fields": "id,caption,timestamp,media_type", "limit": 50}
        if after:
            params["after"] = after
        status, data = ig_get(f"{IG_BUSINESS_ACCOUNT_ID}/media", **params)
        if status != 200:
            raise RuntimeError(f"Kunne ikke hente opslag fra Instagram ({status}): {scrub(data)}")
        media += data.get("data", [])
        after = (data.get("paging") or {}).get("cursors", {}).get("after")
        if not after or not (data.get("paging") or {}).get("next"):
            return media
    return media


def fetch_metrics(media_id):
    """Hent alle maalepunkter; fejler kaldet samlet, hentes de enkeltvis."""
    out = {}
    status, data = ig_get(f"{media_id}/insights", metric=",".join(METRICS))
    if status == 200:
        items = data.get("data", [])
    else:
        msg = json.dumps(data)
        if "permission" in msg.lower() or (data.get("error") or {}).get("code") in (10, 190, 200):
            raise PermissionError(scrub(msg))
        items = []
        for m in METRICS:
            s, d = ig_get(f"{media_id}/insights", metric=m)
            if s == 200:
                items += d.get("data", [])
            else:
                print(f"  - {m} ikke leveret af Meta: {scrub((d.get('error') or {}).get('message', s))}")
    for item in items:
        name = item.get("name")
        values = item.get("values") or []
        value = values[0].get("value") if values else item.get("total_value", {}).get("value")
        if name in METRICS and isinstance(value, (int, float)):
            if name == "ig_reels_avg_watch_time":
                value = round(value / 1000, 1)
            out[METRICS[name]] = value
    return out


def count_keyword_comments(media_id, keyword):
    if not keyword:
        return None
    pattern = re.compile(rf"\b{re.escape(keyword.strip())}\b", re.IGNORECASE)
    count, after = 0, None
    for _ in range(20):
        params = {"fields": "text", "limit": 50}
        if after:
            params["after"] = after
        status, data = ig_get(f"{media_id}/comments", **params)
        if status != 200:
            print(f"  - kommentarer kunne ikke hentes: {scrub((data.get('error') or {}).get('message', status))}")
            return None
        count += sum(1 for c in data.get("data", []) if pattern.search(c.get("text") or ""))
        after = (data.get("paging") or {}).get("cursors", {}).get("after")
        if not after or not (data.get("paging") or {}).get("next"):
            break
    return count


def update_notion(page_id, values, media_id, now):
    props = {name: {"number": v} for name, v in values.items()}
    props["IG Media ID"] = {"rich_text": [{"text": {"content": media_id}}]}
    props["IG Tal opdateret"] = {"date": {"start": now.isoformat(timespec="minutes")}}
    status, data = http("PATCH", f"https://api.notion.com/v1/pages/{page_id}", notion_headers(), {"properties": props})
    if status != 200:
        raise RuntimeError(f"Notion-opdatering fejlede ({status}): {data}")


def save_followers(now):
    status, data = ig_get("me", fields="followers_count,media_count")
    if status != 200:
        print(f"Foelgertal kunne ikke hentes: {scrub((data.get('error') or {}).get('message', status))}")
        return
    path = os.path.join("trigger", "foelgere.csv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write("dato,foelgere,opslag\n")
        f.write(f"{now.date().isoformat()},{data.get('followers_count','')},{data.get('media_count','')}\n")
    print(f"Følgere: {data.get('followers_count')}")


TEST_STATS_URL = "https://bejewelled-dragon-5e69df.netlify.app/.netlify/functions/stats"


def save_test_stats(now):
    """Antal, der har taget testen (kun tal, aldrig navne), til trigger/testtal.csv."""
    try:
        with urllib.request.urlopen(TEST_STATS_URL, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Testens tal kunne ikke hentes: {e}")
        return
    if not data.get("ok"):
        print("Testens tal kunne ikke hentes (Brevo svarede ikke).")
        return
    path = os.path.join("trigger", "testtal.csv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write("dato,tests_i_alt,sidste_7_dage,sidste_30_dage,afmeldt\n")
        f.write(f"{now.date().isoformat()},{data['tests']},{data['sidste7']},{data['sidste30']},{data['afmeldt']}\n")
    print(f"Testen: {data['tests']} i alt, {data['sidste7']} de sidste 7 dage")


def main():
    now = datetime.now(DK)
    save_test_stats(now)
    posts = fetch_published()
    media = fetch_ig_media()
    by_id = {m["id"]: m for m in media}
    by_caption = {}
    for m in media:
        key = norm(m.get("caption"))
        if key:
            by_caption.setdefault(key, []).append(m)

    updated, unmatched = 0, []
    for page in posts:
        props = page["properties"]
        title = text_prop(props, "Titel") or page["id"]
        media_id = text_prop(props, "IG Media ID").strip()
        match = by_id.get(media_id) if media_id else None
        if not match:
            hits = by_caption.get(norm(text_prop(props, "Billedtekst")), [])
            if len(hits) == 1:
                match = hits[0]
        if not match:
            unmatched.append(title)
            continue
        print(f"{title}:")
        values = fetch_metrics(match["id"])
        kw = count_keyword_comments(match["id"], text_prop(props, "Keyword"))
        if kw is not None:
            values["IG Keyword-kommentarer"] = kw
        update_notion(page["id"], values, match["id"], now)
        print(f"  {values}")
        updated += 1

    save_followers(now)
    print(f"\nOpdateret: {updated} opslag. Uden sikkert match: {len(unmatched)}")
    for t in unmatched:
        print(f"  - {t}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"Noeglen maa ikke laese tal. Mangler tilladelsen instagram_business_manage_insights? {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Fejl: {scrub(e)}")
        sys.exit(1)
