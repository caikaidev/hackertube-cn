#!/usr/bin/env python3
"""Discover 2026 V2EX creator-recommendation threads via SOV2EX, verified by API.

Recall: SOV2EX api/search with sort=created (newest first; size capped at 50,
paginate with `from`), walking each query back to 2026-01-01.
Filters: title looks like a recommendation thread; politics titles excluded
(user rule). SOV2EX's own reply counts are stale for recent threads, so every
surviving candidate is verified against the V2EX API (created + replies>=20).
"""
import json, os, re, time, urllib.request, urllib.parse, datetime

BASE = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(BASE, "data", "discovery_2026b.json")
SEEDS = {723217, 893469, 840328, 1094836, 1176867, 1205371, 1171199, 326698}
QUERIES = ["求推荐 up", "关注列表", "播客 推荐", "信息茧房 推荐", "宝藏 up主",
           "订阅的频道", "看哪些频道", "优质博主", "扩充关注", "宝藏频道"]
UA = {"User-Agent": "Mozilla/5.0 (HackerTubeCN research)"}
SUBJECT = re.compile(r"博主|up主|UP主|youtuber|YouTuber|油管|B站|bilibili|主播|频道|播客")
INTENT = re.compile(r"推荐|求|分享|关注|收藏|宝藏|安利|哪些|几个|有没有|值得|订阅|长期")
POLITICS = re.compile(r"时政|新闻博主|国际局势|军事博主|政论|地缘")

def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def sov2ex_walk(q):
    out = []
    for frm in range(0, 300, 50):
        url = "https://www.sov2ex.com/api/search?" + urllib.parse.urlencode(
            {"q": q, "size": 50, "from": frm, "sort": "created"}, quote_via=urllib.parse.quote)
        try:
            hits = get_json(url).get("hits", [])
        except Exception as e:
            print(f"  {q!r} from={frm} failed: {e}")
            break
        if not hits:
            break
        out.extend(hits)
        last = (hits[-1].get("_source", {}).get("created") or "")[:10]
        if last < "2026-01-01":
            break
        time.sleep(0.4)
    return out

def main():
    cand = {}
    for q in QUERIES:
        for h in sov2ex_walk(q):
            s = h.get("_source", {})
            tid, created = s.get("id"), (s.get("created") or "")[:10]
            if not tid or tid in SEEDS or tid in cand:
                continue
            if not created.startswith("2026"):
                continue
            cand[tid] = {"topic_id": tid, "title": s.get("title", ""),
                         "created": created, "found_by": q}
    print(f"2026 candidates by title-date: {len(cand)}")
    kept, dropped = [], []
    for c in cand.values():
        t = c["title"]
        if POLITICS.search(t):
            dropped.append({**c, "why": "politics_title"})
        elif not (SUBJECT.search(t) and INTENT.search(t)):
            dropped.append({**c, "why": "title_not_recommendation"})
        else:
            kept.append(c)
    print(f"title filter kept: {len(kept)}, dropped: {len(dropped)}; verifying via V2EX API...")
    verified, too_small = [], []
    for c in kept:
        try:
            d = get_json(f"https://www.v2ex.com/api/topics/show.json?id={c['topic_id']}")
            t = d[0]
            c["title"] = t.get("title", c["title"])
            c["replies"] = t.get("replies", 0)
            c["created"] = datetime.datetime.fromtimestamp(
                t["created"], datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
            c["node"] = (t.get("node") or {}).get("name", "")
        except Exception as e:
            c["verify_error"] = str(e)[:120]
        (verified if c.get("replies", 0) >= 20 and c["created"].startswith("2026")
         else too_small).append(c)
        time.sleep(0.3)
    verified.sort(key=lambda c: -c["replies"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"kept": verified, "dropped": dropped, "too_small": too_small},
                  f, ensure_ascii=False, indent=1)
    print(f"VERIFIED kept: {len(verified)}  (verified-out: {len(too_small)})")
    tot = 0
    for c in verified:
        tot += c["replies"]
        print(f"  {c['created']}  {c['replies']:>4} replies  t/{c['topic_id']}  [{c.get('node','')}] {c['title']}")
    print(f"total replies to fetch: {tot}")

if __name__ == "__main__":
    main()
