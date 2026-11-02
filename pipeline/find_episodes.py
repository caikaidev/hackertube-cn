#!/usr/bin/env python3
"""Collect every video link mentioned in the 14 topics, resolve each video's
REAL author/title via platform APIs (Bilibili view API / YouTube oEmbed),
and match the author against catalog entries by mid or exact name.
No inference: a link is attributed only when the platform itself says the
video's author is that entry. Output: data/episodes_report.json + updates
data/data.json with an `episode` field on matched entries."""
import json, re, subprocess, sys, time

sys.path.insert(0, "/home/hatch/workspace/hackertube-cn/pipeline")
from corpus import load_topics

ROOT = "/home/hatch/workspace/hackertube-cn"
BV = re.compile(r'https?://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]+)')
YTV = re.compile(r'https?://(?:www\.)?youtube\.com/watch\?v=([0-9A-Za-z_-]{6,})')
YTS = re.compile(r'https?://youtu\.be/([0-9A-Za-z_-]{6,})')

def curl_json(url):
    r = subprocess.run(["curl", "-s", "--max-time", "25", url],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

# ---- 1. collect links with floor context ----
occurrences = {}  # video key -> list of {source, topic_id, floor, username, text}
for (tsrc, tid), t in sorted(load_topics().items()):
    spots = [(0, t.get("op", ""), (t.get("content") or ""))]
    for fl in t["floors"]:
        spots.append((fl["floor"], fl.get("username", ""), fl.get("content") or ""))
    for flno, user, txt in spots:
        for m in BV.finditer(txt):
            occurrences.setdefault(("bili", m.group(1)), []).append(
                {"source": tsrc, "topic_id": tid, "floor": flno, "by": user, "text": txt[:200]})
        for m in YTV.finditer(txt):
            occurrences.setdefault(("yt", m.group(1)), []).append(
                {"source": tsrc, "topic_id": tid, "floor": flno, "by": user, "text": txt[:200]})
        for m in YTS.finditer(txt):
            occurrences.setdefault(("yt", m.group(1)), []).append(
                {"source": tsrc, "topic_id": tid, "floor": flno, "by": user, "text": txt[:200]})

print(f"unique videos: {len(occurrences)}", file=sys.stderr)

# ---- 2. resolve authors via platform APIs ----
resolved = {}
for (plat, vid), occs in sorted(occurrences.items()):
    if plat == "bili":
        d = curl_json(f"https://api.bilibili.com/x/web-interface/view?bvid={vid}")
        if d and d.get("code") == 0:
            v = d["data"]
            resolved[(plat, vid)] = {"title": v.get("title", ""),
                                     "author": v["owner"]["name"],
                                     "mid": v["owner"]["mid"]}
        else:
            resolved[(plat, vid)] = {"error": (d or {}).get("message", "fetch failed")}
    else:
        d = curl_json("https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v="
                      + vid + "&format=json")
        if d and d.get("author_name"):
            resolved[(plat, vid)] = {"title": d.get("title", ""),
                                     "author": d["author_name"], "mid": None}
        else:
            resolved[(plat, vid)] = {"error": "oembed failed"}
    time.sleep(0.4)

# ---- 3. match author -> entry ----
data = json.load(open(f"{ROOT}/data/data.json", encoding="utf-8"))
by_mid, by_name, by_norm = {}, {}, {}
def norm(s):
    return re.sub(r"[\s｜|·・_-]+", "", s).lower()
for d in data:
    m = re.search(r"space\.bilibili\.com/(\d+)", d.get("url") or "")
    if m:
        by_mid[int(m.group(1))] = d
    by_name[d["name"]] = d
    by_norm[norm(d["name"])] = d

report = []
attached = {}
for (plat, vid), occs in sorted(occurrences.items()):
    r = resolved[(plat, vid)]
    row = {"video": f"{plat}:{vid}", "occurrences": occs, "resolved": r,
           "matched_entry": None, "match_via": None}
    if "error" not in r:
        entry, via = None, None
        if r.get("mid") and r["mid"] in by_mid:
            entry, via = by_mid[r["mid"]], "mid"
        elif r["author"] in by_name:
            entry, via = by_name[r["author"]], "exact_name"
        elif norm(r["author"]) in by_norm:
            entry, via = by_norm[norm(r["author"])], "normalized_name"
        if entry is not None:
            row["matched_entry"], row["match_via"] = entry["name"], via
            url = (f"https://www.bilibili.com/video/{vid}" if plat == "bili"
                   else f"https://www.youtube.com/watch?v={vid}")
            occ = occs[0]
            ep = {"url": url, "title": r["title"], "source": occ["source"],
                  "topic_id": occ["topic_id"], "floor": occ["floor"], "by": occ["by"]}
            # prefer an occurrence whose floor text also names the entry
            for o in occs:
                if entry["name"] in o["text"]:
                    ep.update({"source": o["source"], "topic_id": o["topic_id"], "floor": o["floor"], "by": o["by"]})
                    break
            cur = attached.get(entry["name"])
            if cur is None:
                attached[entry["name"]] = ep
    report.append(row)

for d in data:
    if d["name"] in attached:
        d["episode"] = attached[d["name"]]
    elif "episode" in d:
        del d["episode"]

json.dump(data, open(f"{ROOT}/data/data.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(report, open(f"{ROOT}/data/episodes_report.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
ok = sum(1 for r in report if r["matched_entry"])
print(f"videos={len(report)} matched={ok} entries_with_episode={len(attached)}")
for r in report:
    rr = r["resolved"]
    print(f"- {r['video']} | {rr.get('author', rr.get('error', ''))} | 《{rr.get('title', '')[:40]}》 -> {r['matched_entry']} ({r['match_via']})")
