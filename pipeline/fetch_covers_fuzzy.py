#!/usr/bin/env python3
"""Fuzzy pass for Bilibili creators the exact-name pass could not match.

User-approved 2026-11-02: score candidates 1-10, accept only score > 8.
Scoring (deterministic, auditable; full detail lands in data/cover_report.json):
- name: exact +6 / one contains the other +5 / edit-ratio >=0.8 +4,
  >=0.65 +3, >=0.5 +1.5
- fans: >=5M +2.5 / >=1M +2 / >=300k +1.5 / >=100k +1 / >=30k +0.5
- corroboration +1: entry name appears in the candidate's signature or in
  one of its video titles returned by search
- rank +0.5: candidate is the #1 hit for the plain-name query
- handle bonus +1.5: entry name is a latin/digit handle AND exact match
- short-name guard: entry names of <=2 chars halve the name points unless
  corroboration is present (generic words attract squatters)
Accepted entries get avatar + fans + backfilled space URL, with
resolved_via=bili_fuzzy_scored and confidence=<score> stored in the data.
TESTV-style verified mismatches are not touched (not Bilibili-labelled, and
this pass only processes platform=bilibili entries that still lack avatars).
"""
import difflib, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_covers import bili_card, bili_search, norm, BASE, DATA, REPORT

def score(entry_name, cand, rank_idx):
    en, cn = norm(entry_name), norm(cand.get("uname", ""))
    detail = {}
    if en == cn:
        pts = 6.0
    elif en in cn or cn in en:
        pts = 5.0
    else:
        r = difflib.SequenceMatcher(None, en, cn).ratio()
        pts = 4.0 if r >= 0.8 else 3.0 if r >= 0.65 else 1.5 if r >= 0.5 else 0.0
    detail["name"] = pts
    fans = cand.get("fans") or 0
    detail["fans"] = 2.5 if fans >= 5_000_000 else 2.0 if fans >= 1_000_000 else \
        1.5 if fans >= 300_000 else 1.0 if fans >= 100_000 else 0.5 if fans >= 30_000 else 0.0
    corro = en in norm(cand.get("usign", "")) or \
        any(en in norm(v.get("title", "")) for v in (cand.get("res") or []))
    detail["corroboration"] = 1.0 if corro else 0.0
    if len(en) <= 2 and not corro:
        detail["name"] = detail["name"] / 2
        detail["short_name_guard"] = True
    detail["rank"] = 0.5 if rank_idx == 0 else 0.0
    detail["handle"] = 1.5 if (en == cn and re.fullmatch(r"[a-z0-9_\-]+", en)) else 0.0
    return round(sum(v for k, v in detail.items() if isinstance(v, float)), 1), detail

def main():
    items = json.load(open(DATA, encoding="utf-8"))
    targets = [it for it in items if it.get("platform") == "bilibili" and not it.get("avatar")]
    print(f"targets: {len(targets)}")
    fuzzy_report = []
    for it in targets:
        name = it["name"]
        variants = {name, re.sub(r"[+\s]+", "", name)}
        parts = re.split(r"[+\s]+", name)
        if len(parts) > 1:
            variants.add(parts[0])
        pool = {}
        first_page_order = []
        for v in variants:
            for idx, r in enumerate(bili_search(v)):
                mid = str(r["mid"])
                if mid not in pool:
                    pool[mid] = r
                    if v == name and idx < 20:
                        first_page_order.append(mid)
                time.sleep(0.2)
        scored = []
        for mid, cand in pool.items():
            rank_idx = first_page_order.index(mid) if mid in first_page_order else -1
            s, detail = score(name, cand, rank_idx)
            scored.append({"mid": mid, "uname": cand.get("uname"), "fans": cand.get("fans"),
                           "score": s, "detail": detail})
        scored.sort(key=lambda x: -x["score"])
        best = scored[0] if scored else None
        rec = {"name": name, "best": best, "runner_up": scored[1] if len(scored) > 1 else None,
               "accepted": False}
        if best and best["score"] > 8:
            card = bili_card(best["mid"])
            if card:
                face = card["face"]
                if face.startswith("http://"):
                    face = "https://" + face[7:]
                if "hdslb.com" in face and "@" not in face:
                    face += "@128w_128h_1c"
                it["avatar"] = face
                if card["fans"] is not None:
                    it["fans"] = card["fans"]
                it["url"] = f"https://space.bilibili.com/{best['mid']}"
                it["resolved_via"] = "bili_fuzzy_scored"
                it["confidence"] = best["score"]
                rec["accepted"] = True
        fuzzy_report.append(rec)
        print(("ACCEPT " if rec["accepted"] else "skip   ") + name +
              (f" -> {best['uname']} ({best['score']})" if best else " -> no candidates"))
        time.sleep(0.4)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    report = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {"entries": []}
    report["fuzzy_pass"] = fuzzy_report
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("avatars:", sum(1 for i in items if i.get("avatar")),
          "/ urls:", sum(1 for i in items if i.get("url")))

if __name__ == "__main__":
    main()
