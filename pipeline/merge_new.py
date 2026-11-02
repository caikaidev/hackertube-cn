#!/usr/bin/env python3
"""Merge a fresh extract_chunked run into the curated, enriched data.json.

extract_chunked.py overwrites data/data.json with raw extraction output (no
avatar/fans/cover/resolved_via). This script unions it with the curated backup:
- matched entries keep curated enrichment + summary/category; sources come
  from the fresh run; mention_count is recomputed from per-chunk extraction
  files (ground truth across all topics);
- fresh-only entries are appended as new;
- curated-only entries are kept untouched (sweep/manual additions);
- excluded_politics.json is unioned by name.
Run AFTER extract_chunked.py, with the curated backup path as argv[1].
"""
import json, os, re, sys, glob
from collections import defaultdict

BASE = os.path.join(os.path.dirname(__file__), "..")
BACKUP = sys.argv[1]
NEW_TOPICS = {1221758, 1246722, 1183414, 1184310, 1185562, 1182763}

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

curated = json.load(open(BACKUP, encoding="utf-8"))
fresh = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))

# per-(key, topic) mention counts straight from chunk extraction files
per_topic = defaultdict(lambda: defaultdict(int))
for p in glob.glob(os.path.join(BASE, "data", "extracted_v2", "t*_c*.json")):
    m = re.search(r"t(\d+)_c\d+\.json$", os.path.basename(p))
    tid = int(m.group(1))
    for it in json.load(open(p, encoding="utf-8")).get("items", []):
        per_topic[(it.get("platform", ""), norm(it.get("name", "")))][tid] += it.get("mention_count", 1)

cur_idx = {(c.get("platform", ""), norm(c["name"])): c for c in curated}
out, new_entries, updated = [], [], []
matched = set()
for f in fresh:
    key = (f.get("platform", ""), norm(f["name"]))
    total = sum(per_topic.get(key, {}).values()) or f.get("mention_count", 1)
    if key in cur_idx:
        c = dict(cur_idx[key])
        matched.add(key)
        old_src_topics = {s["topic_id"] for s in c.get("sources", [])}
        c["sources"] = f["sources"]
        c["mention_count"] = total
        if not c.get("url") and f.get("url"):
            c["url"] = f["url"]
        if {s["topic_id"] for s in f["sources"]} - old_src_topics:
            updated.append(f["name"])
        out.append(c)
    else:
        f = dict(f)
        f["mention_count"] = total
        new_entries.append(f["name"])
        out.append(f)
kept_only = []
for key, c in cur_idx.items():
    if key not in matched:
        kept_only.append(c["name"])
        out.append(c)
out.sort(key=lambda x: -x["mention_count"])
json.dump(out, open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# excluded union
ex_cur = json.load(open(os.path.join(BASE, "data", "excluded_politics.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(BASE, "data", "excluded_politics.json")) else []
ex_bak = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else []
by_name = {}
for e in ex_bak + ex_cur:
    by_name.setdefault(e["name"], e)
new_ex = [e["name"] for e in ex_cur if e["name"] not in {x["name"] for x in ex_bak}]
json.dump(list(by_name.values()), open(os.path.join(BASE, "data", "excluded_politics.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print(f"merged total: {len(out)} (curated {len(curated)} + fresh {len(fresh)})")
print(f"NEW entries ({len(new_entries)}): {new_entries}")
print(f"entries gaining 2026 sources ({len(updated)}): {updated}")
print(f"curated-only kept ({len(kept_only)}): {kept_only}")
print(f"excluded total: {len(by_name)}; newly excluded: {new_ex}")
