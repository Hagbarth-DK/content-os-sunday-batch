#!/usr/bin/env python3
"""
Sondagsbatch — automatisk Instagram-publicering fra Notion Content Library.

Koeres af GitHub Actions hver soendag (se .github/workflows/sunday-batch.yml).
Laeser hemmeligheder udelukkende fra miljovariabler (GitHub Secrets) — ingen
tokens er nogensinde skrevet ind i denne fil.

Env vars (sat som GitHub Secrets):
  NOTION_API_KEY        - Notion internal integration secret
  NOTION_DATABASE_ID    - Content Library database id
  IG_ACCESS_TOKEN       - Instagram Graph API access token
  IG_BUSINESS_ACCOUNT_ID- Instagram-scoped account id for dette token (fra
                           graph.instagram.com/v21.0/me, ikke det gamle
                           Facebook Page-linked id)

Logik (spejler "Sondagsbatch — opskrift" i Claude Operating Manual):
  1. Hent alle poster med Status = "Scheduled" og Publiceringsdato <= i dag.
  2. Valider at alle paakraevede felter er udfyldt. Mangler et felt: spring
     over og log det — gaet det aldrig faerdigt.
  3. Opret Instagram media-container fra Videolink (media_type=REELS).
  4. Poll indtil status_code = FINISHED.
  5. Publicer containeren (media_publish).
  6. Skriv Status -> "Published" i Notion foerst naar Meta har bekraeftet.
  7. Print en opsummering (ses i GitHub Actions-loggen).
"""

import os
import sys
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ACCOUNT_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]

NOTION_VERSION = "2022-06-28"
GRAPH_VERSION = "v21.0"

REQUIRED_FIELDS = [
    "Videolink", "Billedtekst", "Keyword", "Platform", "Account", "Publiceringsdato",
]


def http(method, url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_scheduled_posts():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    body = {
        "filter": {
            "and": [
                {"property": "Status", "select": {"equals": "Scheduled"}},
                {"property": "Publiceringsdato", "date": {"on_or_before": datetime.now(timezone.utc).date().isoformat()}},
            ]
        }
    }
    status, data = http("POST", url, notion_headers(), body)
    if status != 200:
        raise RuntimeError(f"Notion query fejlede ({status}): {data}")
    return data.get("results", [])


def get_prop_text(props, name):
    prop = props.get(name)
    if not prop:
        return None
    t = prop.get("type")
    if t == "url":
        return prop.get("url")
    if t == "rich_text":
        parts = prop.get("rich_text", [])
        return "".join(p.get("plain_text", "") for p in parts) or None
    if t == "title":
        parts = prop.get("title", [])
        return "".join(p.get("plain_text", "") for p in parts) or None
    if t == "select":
        return (prop.get("select") or {}).get("name")
    if t == "status":
        return (prop.get("status") or {}).get("name")
    if t == "multi_select":
        vals = [o.get("name") for o in prop.get("multi_select", [])]
        return vals or None
    if t == "date":
        d = prop.get("date")
        return d.get("start") if d else None
    return None


def validate(props):
    missing = []
    for field in REQUIRED_FIELDS:
        val = get_prop_text(props, field)
        if not val:
            missing.append(field)
    platforms = get_prop_text(props, "Platform") or []
    if "Instagram" not in platforms:
        missing.append("Platform (Instagram)")
    return missing


def create_media_container(video_url, caption):
    url = (
        f"https://graph.instagram.com/{GRAPH_VERSION}/{IG_BUSINESS_ACCOUNT_ID}/media"
        f"?media_type=REELS"
        f"&video_url={urllib.parse.quote(video_url, safe='')}"
        f"&caption={urllib.parse.quote(caption, safe='')}"
        f"&access_token={IG_ACCESS_TOKEN}"
    )
    status, data = http("POST", url)
    if status != 200:
        raise RuntimeError(f"Kunne ikke oprette media-container ({status}): {data}")
    return data["id"]


def wait_for_container(container_id, timeout_seconds=600, interval_seconds=10):
    url = (
        f"https://graph.instagram.com/{GRAPH_VERSION}/{container_id}"
        f"?fields=status_code&access_token={IG_ACCESS_TOKEN}"
    )
    waited = 0
    while waited < timeout_seconds:
        status, data = http("GET", url)
        if status != 200:
            raise RuntimeError(f"Kunne ikke tjekke container-status ({status}): {data}")
        code = data.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"HeyGen/Meta rapporterede fejl for container {container_id}: {data}")
        time.sleep(interval_seconds)
        waited += interval_seconds
    raise TimeoutError(f"Container {container_id} blev ikke klar inden for {timeout_seconds}s")


def publish_container(container_id):
    url = (
        f"https://graph.instagram.com/{GRAPH_VERSION}/{IG_BUSINESS_ACCOUNT_ID}/media_publish"
        f"?creation_id={container_id}&access_token={IG_ACCESS_TOKEN}"
    )
    status, data = http("POST", url)
    if status != 200:
        raise RuntimeError(f"Kunne ikke publicere ({status}): {data}")
    return data["id"]


def mark_published(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    today = datetime.now(timezone.utc).date().isoformat()
    body = {
        "properties": {
            "Status": {"select": {"name": "Published"}},
            "Publiceringsdato": {"date": {"start": today}},
        }
    }
    status, data = http("PATCH", url, notion_headers(), body)
    if status != 200:
        raise RuntimeError(f"Kunne ikke opdatere Notion ({status}): {data}")


def main():
    posts = fetch_scheduled_posts()
    if not posts:
        print("Ingen poster klar til publicering i dag.")
        return

    published, skipped, failed = [], [], []

    for page in posts:
        page_id = page["id"]
        props = page["properties"]
        title = get_prop_text(props, "Titel") or page_id

        missing = validate(props)
        if missing:
            skipped.append((title, f"mangler felter: {', '.join(missing)}"))
            continue

        video_url = get_prop_text(props, "Videolink")
        caption = get_prop_text(props, "Billedtekst")

        try:
            container_id = create_media_container(video_url, caption)
            wait_for_container(container_id)
            publish_container(container_id)
            mark_published(page_id)
            published.append(title)
        except Exception as e:
            failed.append((title, str(e)))

    print("=== Sondagsbatch — opsummering ===")
    print(f"Publiceret ({len(published)}):")
    for t in published:
        print(f"  - {t}")
    print(f"Sprunget over ({len(skipped)}):")
    for t, reason in skipped:
        print(f"  - {t}: {reason}")
    print(f"Fejlet ({len(failed)}):")
    for t, reason in failed:
        print(f"  - {t}: {reason}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
