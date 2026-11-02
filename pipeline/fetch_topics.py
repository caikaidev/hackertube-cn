#!/usr/bin/env python3
"""Fetch V2EX topics + all replies via public API v1 (generic fetch_seeds).

Usage: python3 fetch_topics.py <topic_id> [more ids...]
       python3 fetch_topics.py --from-discovery data/discovery_2026.json
Saves data/raw/topic_<id>.json, skipping files that already exist.
"""
import json, time, urllib.request, os, sys

BASE = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(BASE, "data", "raw")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (HackerTubeCN-MVP research)"}

def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  retry {i+1} {url}: {e}", flush=True)
            time.sleep(2 * (i + 1))
    return None

def main(ids):
    for tid in ids:
        path = os.path.join(OUT, f"topic_{tid}.json")
        if os.path.exists(path):
            print(f"{tid}: cached, skip", flush=True)
            continue
        topic = get(f"https://www.v2ex.com/api/topics/show.json?id={tid}")
        if not topic:
            print(f"{tid}: TOPIC FETCH FAILED", flush=True)
            continue
        topic = topic[0]
        replies, seen = [], set()
        for page in range(1, 16):
            batch = get(f"https://www.v2ex.com/api/replies/show.json?topic_id={tid}&page={page}&page_size=100")
            if not batch:
                break
            new = [r for r in batch if r["id"] not in seen]
            for r in new:
                seen.add(r["id"])
            replies.extend(new)
            if len(new) == 0 or len(replies) >= (topic.get("replies") or 0):
                break
            time.sleep(1)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"topic": topic, "replies": replies}, f, ensure_ascii=False)
        print(f"{tid}: saved {len(replies)} replies, title={topic.get('title')!r}", flush=True)
        time.sleep(1)
    print("DONE")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--from-discovery":
        d = json.load(open(os.path.join(BASE, args[1]), encoding="utf-8"))
        main([c["topic_id"] for c in d["kept"]])
    else:
        main([int(a) for a in args])
