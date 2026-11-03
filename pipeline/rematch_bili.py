#!/usr/bin/env python3
"""Propose re-matches for entries whose Bilibili link is an empty account.

Reads data/bili_audit.json (archive_count == 0 and fans < 1000 = squatter),
searches Bilibili for each entry name, and proposes the best candidate
with actual content (videos > 0):
- exact-name candidate with content -> most fans wins;
- else a containing/near name that dominates (fans >= 30000 and >= 20x
  the voided account's fans);
- else no proposal (entry should fall back to search, not a dead link).
Writes data/rematch_plan.json; does NOT modify data.json.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_covers import bili_search, norm  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL = {"小鱼哥": 333010040}  # verified from the user's own screenshot (招财小瑜哥)


def main():
    audit = json.load(open(os.path.join(BASE, "data", "bili_audit.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
    by_name = {e["name"]: e for e in data}
    voided = []
    for mid, v in audit.items():
        if v.get("ok") and (v.get("archive_count") or 0) == 0 and (v.get("fans") or 0) < 1000:
            voided.append((v["entry_name"], int(mid), v.get("fans") or 0))
    print(f"voided squatter matches to re-match: {len(voided)}")
    plan = []
    for name, old_mid, old_fans in sorted(voided):
        rec = {"name": name, "old_mid": old_mid, "old_fans": old_fans}
        if name in MANUAL:
            rec.update({"action": "manual", "new_mid": MANUAL[name]})
            plan.append(rec)
            print(f"{name}: MANUAL -> {MANUAL[name]}")
            continue
        cands = [r for r in bili_search(name) if (r.get("videos") or 0) > 0]
        cands.sort(key=lambda r: -(r.get("fans") or 0))
        rec["top_candidates"] = [
            {"uname": r.get("uname"), "mid": r.get("mid"), "fans": r.get("fans"), "videos": r.get("videos")}
            for r in cands[:5]
        ]
        en = norm(name)
        exact = [r for r in cands if norm(r.get("uname", "")) == en]
        if exact:
            top = exact[0]
            rec.update({"action": "exact", "new_mid": top["mid"], "new_uname": top.get("uname"),
                        "new_fans": top.get("fans"), "new_videos": top.get("videos")})
        else:
            near = [r for r in cands
                    if en in norm(r.get("uname", "")) or norm(r.get("uname", "")) in en]
            top = near[0] if near else None
            if top and (top.get("fans") or 0) >= 30000 and (top.get("fans") or 0) >= 20 * max(old_fans, 1):
                rec.update({"action": "dominant_near", "new_mid": top["mid"], "new_uname": top.get("uname"),
                            "new_fans": top.get("fans"), "new_videos": top.get("videos")})
            else:
                rec.update({"action": "clear"})
        plan.append(rec)
        print(f"{name}: {rec['action']} -> {rec.get('new_uname', '-')} "
              f"(fans {rec.get('new_fans', '-')}, videos {rec.get('new_videos', '-')})")
        time.sleep(0.5)
    json.dump(plan, open(os.path.join(BASE, "data", "rematch_plan.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("plan written to data/rematch_plan.json")


if __name__ == "__main__":
    main()
