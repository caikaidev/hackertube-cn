#!/usr/bin/env python3
"""Resolve creator avatars (+ Bilibili fans) and backfill homepage URLs.

Rules (user-approved 2026-11-02, option B):
- Bilibili entries that already have a space URL: avatar/fans from the official
  card API by mid. URL is trusted (it came from source text); if the card name
  differs from the entry name we only report it.
- Bilibili entries without a URL: search the platform's own user search.
  Accept ONLY an exact normalized-name match; if several exact matches exist,
  take the one with the most fans and flag it in the report. On acceptance,
  backfill url=https://space.bilibili.com/<mid> and resolved_via=bili_search_exact.
- YouTube entries with an @handle URL: avatar scraped from the channel page.
- Everything else: no avatar (site renders a designed initial tile).
Images stay on the platforms' CDNs; we only store URLs.
"""
import json, os, re, sys, time, urllib.request, urllib.parse, uuid

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data", "data.json")
REPORT = os.path.join(BASE, "data", "cover_report.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
BUVID = uuid.uuid4().hex.upper()

def http_get(url, referer=None, want_json=True):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer or "https://www.bilibili.com/",
        "Cookie": f"buvid3={BUVID}infoc",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if want_json else raw

def norm(name):
    name = re.sub(r"<[^>]+>", "", name or "")
    return re.sub(r"\s+", "", name).lower()

def bili_card(mid):
    # Bilibili risk control intermittently returns non-zero codes (e.g. -412)
    # under burst traffic; retry with backoff before giving up.
    for attempt in range(3):
        try:
            d = http_get(f"https://api.bilibili.com/x/web-interface/card?mid={mid}")
            if d.get("code") == 0:
                c = d["data"]["card"]
                return {"face": c.get("face", ""), "fans": c.get("fans"), "name": c.get("name", "")}
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None

def bili_search(name):
    # Scan up to 3 result pages for an exact-name match.
    q = urllib.parse.quote(name)
    out = []
    for page in (1, 2, 3):
        try:
            d = http_get(f"https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword={q}&page={page}",
                         referer="https://search.bilibili.com/")
        except Exception:
            break
        if d.get("code") != 0:
            break
        res = d.get("data", {}).get("result") or []
        out.extend(res)
        if len(res) < 20:
            break
        time.sleep(0.3)
    return out

def yt_avatar(url):
    html = http_get(url, referer="https://www.youtube.com/", want_json=False)
    m = re.search(r'"avatar":\{"thumbnails":\[(.*?)\]', html)
    if not m:
        return ""
    urls = re.findall(r'"url":"(https://yt3\.googleusercontent\.com/[^"]+)"', m.group(1))
    if not urls:
        return ""
    return re.sub(r"=s\d+", "=s176", urls[-1])

def main():
    missing_only = "--missing-only" in sys.argv
    items = json.load(open(DATA, encoding="utf-8"))
    report = []
    stats = {"card_api": 0, "search_exact": 0, "search_multi": 0, "yt": 0,
             "no_match": 0, "name_mismatch_on_url": 0, "errors": 0}
    for it in items:
        name, plat = it["name"], it.get("platform")
        rec = {"name": name, "platform": plat, "outcome": ""}
        if missing_only and it.get("avatar"):
            rec["outcome"] = "already_done"
            report.append(rec)
            continue
        try:
            if plat == "bilibili":
                mid = None
                m = re.search(r"space\.bilibili\.com/(\d+)", it.get("url") or "")
                if m:
                    mid = m.group(1)
                    card = bili_card(mid)
                    if not card:
                        rec["outcome"] = "card_api_failed"
                    if card:
                        if norm(card["name"]) != norm(name):
                            stats["name_mismatch_on_url"] += 1
                            rec["note"] = f"card name differs: {card['name']}"
                        it["avatar"] = card["face"]
                        if card["fans"] is not None:
                            it["fans"] = card["fans"]
                        it["resolved_via"] = "source_url"
                        stats["card_api"] += 1
                        rec["outcome"] = "card_api"
                else:
                    results = bili_search(name)
                    exact = [r for r in results if norm(r.get("uname", "")) == norm(name)]
                    # Empty accounts (no videos) are name squatters, not matches:
                    # ignore them and re-match (user rule, 2026-11-03).
                    exact = [r for r in exact if (r.get("videos") or 0) > 0]
                    if exact:
                        exact.sort(key=lambda r: -(r.get("fans") or 0))
                        top = exact[0]
                        mid = str(top["mid"])
                        card = bili_card(mid)
                        face = (card or {}).get("face") or ("https:" + top["upic"] if str(top.get("upic", "")).startswith("//") else top.get("upic", ""))
                        fans = (card or {}).get("fans", top.get("fans"))
                        it["avatar"] = face
                        if fans is not None:
                            it["fans"] = fans
                        it["url"] = f"https://space.bilibili.com/{mid}"
                        it["resolved_via"] = "bili_search_exact"
                        if len(exact) > 1:
                            stats["search_multi"] += 1
                            rec["note"] = f"{len(exact)} exact matches, picked most fans mid={mid}"
                        stats["search_exact"] += 1
                        rec["outcome"] = "search_exact_backfilled"
                        rec["mid"] = mid
                    else:
                        stats["no_match"] += 1
                        rec["outcome"] = "no_exact_match"
            elif plat == "youtube" and it.get("url"):
                av = yt_avatar(it["url"])
                if av:
                    it["avatar"] = av
                    it["resolved_via"] = "yt_channel_page"
                    stats["yt"] += 1
                    rec["outcome"] = "yt_avatar"
                else:
                    rec["outcome"] = "yt_no_avatar_found"
            else:
                rec["outcome"] = "skipped"
        except Exception as e:
            stats["errors"] += 1
            rec["outcome"] = "error"
            rec["note"] = str(e)[:200]
        report.append(rec)
        time.sleep(0.45)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    if missing_only and os.path.exists(REPORT):
        old = json.load(open(REPORT, encoding="utf-8"))
        old_by_name = {e["name"]: e for e in old.get("entries", [])}
        for e in report:
            if e["outcome"] == "already_done" and e["name"] in old_by_name:
                e.update(old_by_name[e["name"]])
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "entries": report}, f, ensure_ascii=False, indent=1)
    have_avatar = sum(1 for i in items if i.get("avatar"))
    have_url = sum(1 for i in items if i.get("url"))
    print("stats:", json.dumps(stats, ensure_ascii=False))
    print(f"avatars: {have_avatar}/{len(items)}  urls: {have_url}/{len(items)}")

if __name__ == "__main__":
    main()
