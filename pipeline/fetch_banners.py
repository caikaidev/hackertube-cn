#!/usr/bin/env python3
"""Fetch creator cover images (user-approved simple version, 2026-11-02).

No video embeds anywhere (founding rule). Covers are just images:
- bilibili: space top_photo via x/space/acc/info (public, no signing needed).
  A top_photo shared by >3 entries is the platform default banner -> dropped.
- youtube: channel banner (=w2120 fcrop URL) scraped from the channel page,
  downscaled to w1060.
Entries without a real banner get no `cover` field; the site falls back to an
avatar-derived band. Idempotent: skips entries that already have `cover`
unless --force.
"""
import json, os, re, sys, time, urllib.request
from collections import Counter

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data", "data.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
      "Referer": "https://space.bilibili.com/", "Cookie": "buvid3=ABCDEF1234567890infoc"}
FORCE = "--force" in sys.argv

def get(url, binary=False):
    # acc/info rate-limits hard (code -799 under fast pacing): retry with backoff.
    for attempt in range(3):
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            b = r.read()
        if binary:
            return b
        d = json.loads(b.decode("utf-8"))
        if d.get("code") in (0, None) or attempt == 2:
            return d
        print(f"  api code {d.get('code')} ({d.get('message')}), backing off...", flush=True)
        time.sleep(8 * (attempt + 1))
    return d

def main():
    items = json.load(open(DATA, encoding="utf-8"))
    only = {s for s in (os.environ.get("HT_ONLY") or "").split(",") if s}
    raw = {}
    todo = []
    for it in items:
        if only and it["name"] not in only:
            continue
        if it.get("cover") and not FORCE:
            continue
        m = re.search(r"space\.bilibili\.com/(\d+)", it.get("url") or "")
        if m:
            todo.append((it, "bili", int(m.group(1))))
        elif it.get("platform") == "youtube" and it.get("url"):
            todo.append((it, "yt", it["url"]))
    print(f"to fetch: {len(todo)}")
    for it, kind, key in todo:
        try:
            if kind == "bili":
                d = get(f"https://api.bilibili.com/x/space/acc/info?mid={key}")
                tp = ((d.get("data") or {}).get("top_photo") or "").strip()
                if tp:
                    raw[it["name"]] = "https://i0.hdslb.com/" + tp.lstrip("/")
            else:
                req = urllib.request.Request(key, headers=UA)
                with urllib.request.urlopen(req, timeout=25) as r:
                    html = r.read().decode("utf-8", "replace")
                m = re.search(r"https://yt3\.googleusercontent\.com/[A-Za-z0-9_\-]+=[A-Za-z0-9\-=,]+", html)
                hits = re.findall(r"https://yt3\.googleusercontent\.com/[A-Za-z0-9_\-]+=w2120[^\"\\ ]*", html)
                if hits:
                    raw[it["name"]] = hits[0].replace("=w2120", "=w1060", 1)
        except Exception as e:
            print(f"  {it['name']}: FAIL {e}")
        time.sleep(2.2)
    freq = Counter(raw.values())
    defaults = {u for u, n in freq.items() if n > 3}
    got = 0
    for it in items:
        u = raw.get(it["name"])
        if u and u not in defaults:
            it["cover"] = u
            got += 1
        elif u in defaults:
            print(f"  default banner dropped: {it['name']}")
    json.dump(items, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"covers set: {got}; total with cover: {sum(1 for i in items if i.get('cover'))}/{len(items)}")

if __name__ == "__main__":
    main()
