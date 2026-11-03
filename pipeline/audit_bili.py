#!/usr/bin/env python3
"""Audit every Bilibili space link in data.json against the live account.

For each entry whose url is a space.bilibili.com link, fetch the account
card (name / fans / archive_count). An account with archive_count == 0
has no content: per the user's rule (2026-11-03) such a match is void and
the entry must be re-matched. Results are cached in data/bili_audit.json
so reruns only fetch what is missing.
"""
import json
import os
import re
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "data.json")
OUT = os.path.join(BASE, "data", "bili_audit.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def card(mid):
    url = f"https://api.bilibili.com/x/web-interface/card?mid={mid}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    cache = {}
    if os.path.exists(OUT):
        cache = json.load(open(OUT, encoding="utf-8"))
    todo = []
    for e in data:
        m = re.search(r"space\.bilibili\.com/(\d+)", e.get("url") or "")
        if m:
            todo.append((e["name"], m.group(1)))
    print(f"entries with bilibili space links: {len(todo)}")
    for name, mid in todo:
        if mid in cache and cache[mid].get("ok"):
            continue
        for attempt in range(4):
            try:
                r = card(mid)
                if r.get("code") == 0:
                    d = r["data"]
                    c = d["card"]
                    cache[mid] = {
                        "ok": True,
                        "entry_name": name,
                        "card_name": c.get("name"),
                        "fans": c.get("fans"),
                        "archive_count": d.get("archive_count"),
                        "sign": (c.get("sign") or "")[:60],
                    }
                    break
                cache[mid] = {"ok": False, "entry_name": name, "code": r.get("code")}
                if r.get("code") == -412:
                    time.sleep(20 * (attempt + 1))
                    continue
                break
            except Exception as ex:  # noqa: BLE001
                cache[mid] = {"ok": False, "entry_name": name, "error": str(ex)[:80]}
                time.sleep(5 * (attempt + 1))
        time.sleep(1.1)
        json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = {m: v for m, v in cache.items() if v.get("ok") and (v.get("archive_count") or 0) == 0}
    print(f"audited ok: {sum(1 for v in cache.values() if v.get('ok'))}, empty accounts: {len(bad)}")
    for m, v in bad.items():
        print(f"  EMPTY mid={m} entry={v['entry_name']} card_name={v['card_name']} fans={v['fans']}")


if __name__ == "__main__":
    sys.exit(main())
