#!/usr/bin/env python3
"""Merge a fresh extract_chunked run with the enriched backup.

The extractor overwrites data.json with raw output (no enrichment, no
Day-1 sweep entries, no curation). This restores, per the standing
recovery recipe:
- enrichment + curated fields (url/avatar/fans/cover/episode/aka/
  resolved_via/confidence/category/platform) from the backup for
  shared names;
- backup-only entries appended whole;
- the three 2026-11-03 merges re-applied if donors reappear;
- curated excluded_politics.json restored (done by caller via cp).
Prints the genuinely-new names as the curation queue.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = json.load(open("/tmp/data_backup_v103.json", encoding="utf-8"))
NEW = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
FIELDS = ["url", "avatar", "fans", "cover", "episode", "aka", "resolved_via",
          "confidence", "category", "platform"]
MERGES = [("SCFR", "蜀犬吠日"), ("赖导 AboutLai", "赖导"), ("落拓", "落拓呀")]


def main():
    bk = {e["name"]: e for e in BK}
    # The extractor can emit the same name twice (different topics,
    # different categories): collapse first.
    dedup = {}
    for e in NEW:
        if e["name"] in dedup:
            d = dedup[e["name"]]
            d["mention_count"] += e["mention_count"]
            d["sources"] = d.get("sources", []) + e.get("sources", [])
        else:
            dedup[e["name"]] = e
    new_items = list(dedup.values())
    merged, new_only = [], []
    for e in new_items:
        b = bk.get(e["name"])
        if b:
            for f in FIELDS:
                if b.get(f) is not None:
                    e[f] = b[f]
            merged.append(e)
        else:
            new_only.append(e)
    shared = {e["name"] for e in new_items}
    restored = [e for n, e in bk.items() if n not in shared]
    out = merged + new_only + restored
    by = {e["name"]: e for e in out}
    for donor_name, target_name in MERGES:
        if donor_name in by and target_name in by:
            d, t = by[donor_name], by[target_name]
            t["mention_count"] += d["mention_count"]
            t["sources"] = t.get("sources", []) + d.get("sources", [])
            out.remove(d)
            print(f"re-merged {donor_name} -> {target_name}")
    json.dump(out, open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"total: {len(out)} (shared {len(merged)}, backup-only restored {len(restored)})")
    print(f"NEW curation queue ({len(new_only)}):")
    for e in sorted(new_only, key=lambda x: -x["mention_count"]):
        print(f"  {e['name']} | mentions {e['mention_count']} | {e.get('category')} | {e.get('platform')}")


if __name__ == "__main__":
    main()
