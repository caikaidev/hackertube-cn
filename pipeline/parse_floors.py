#!/usr/bin/env python3
"""Parse raw topics into floors: extract links + build reply edges.

Edge rules (decided 2026-11-02, schools 1+2 combined, hit-and-stop):
0. All floors loaded first; floor no = API order (1-based).
1. #N explicit: N exists and < current floor; skip hex-color-like (#a1b2c3 / long hex) and URL fragments.
   Wins over @ on conflict.
2. @user: first mentioned user (from rendered /member/ links, fallback plain @name) who spoke earlier
   -> that user's most recent earlier floor. If user is OP and OP never replied -> parent 0 (topic body).
3. Textual 'X楼' incl. Chinese numerals, only when 1-2 miss; target must exist and be earlier.
4. Otherwise parent = None (top level).
"""
import json, os, re, glob
from collections import Counter

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "parsed")
os.makedirs(OUT, exist_ok=True)

LINK_PATTERNS = [
    ("bilibili_video", re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]+)")),
    ("bilibili_space", re.compile(r"https?://space\.bilibili\.com/(\d+)")),
    ("youtube_watch", re.compile(r"https?://(?:www\.)?youtube\.com/watch\?v=([0-9A-Za-z_-]{6,})")),
    ("youtube_short", re.compile(r"https?://youtu\.be/([0-9A-Za-z_-]{6,})")),
    ("youtube_handle", re.compile(r"https?://(?:www\.)?youtube\.com/(@[0-9A-Za-z_.-]+)")),
    ("youtube_channel", re.compile(r"https?://(?:www\.)?youtube\.com/channel/(UC[0-9A-Za-z_-]+)")),
]
CN_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
          "十一":11,"十二":12,"十三":13,"十四":14,"十五":15,"十六":16,"十七":17,"十八":18,"十九":19,
          "二十":20,"二十一":21,"二十二":22,"二十三":23,"二十四":24,"二十五":25,"三十":30,"四十":40,"五十":50}
MENTION_HTML = re.compile(r'href="/member/([0-9A-Za-z_]+)"')
MENTION_TXT = re.compile(r"@([0-9A-Za-z_]{2,})")
FLOOR_HASH = re.compile(r"#(\d{1,4})(?!\d)")
FLOOR_TXT_NUM = re.compile(r"(\d{1,4})\s*楼")
FLOOR_TXT_CN = re.compile(r"(" + "|".join(sorted(CN_NUM, key=len, reverse=True)) + r")楼")

def extract_links(text):
    out = []
    for kind, pat in LINK_PATTERNS:
        for m in pat.finditer(text or ""):
            out.append({"kind": kind, "id": m.group(1), "url": m.group(0)})
    return out

def build_edges(floors, op_user):
    """floors: list of dicts with username/content/content_rendered. Sets parent_floor + edge_via."""
    last_floor_by_user = {}
    stats = Counter()
    for f in floors:
        cur = f["floor"]
        content = f["content"] or ""
        parent, via = None, None
        # 1) #N — strip URLs first so fragments don't count; skip hex colors
        scrubbed = re.sub(r"https?://\S+", "", content)
        scrubbed = re.sub(r"#[0-9a-fA-F]{6}\b", "", scrubbed)
        for m in FLOOR_HASH.finditer(scrubbed):
            n = int(m.group(1))
            if 1 <= n < cur:
                parent, via = n, "floor_ref"
                break
        # 2) @user
        if parent is None:
            mentions = MENTION_HTML.findall(f["content_rendered"] or "") or MENTION_TXT.findall(content)
            for u in mentions:
                if u == f["username"]:
                    continue
                if u in last_floor_by_user:
                    parent, via = last_floor_by_user[u], "mention"
                    break
                if u == op_user:
                    parent, via = 0, "mention_op"
                    break
        # 3) textual X楼
        if parent is None:
            m = FLOOR_TXT_NUM.search(scrubbed)
            n = int(m.group(1)) if m else None
            if n is None:
                m2 = FLOOR_TXT_CN.search(content)
                n = CN_NUM.get(m2.group(1)) if m2 else None
            if n is not None and 1 <= n < cur:
                parent, via = n, "floor_text"
        f["parent_floor"] = parent
        f["edge_via"] = via
        stats[via or "none"] += 1
        last_floor_by_user[f["username"]] = cur
    return stats

total_stats = Counter()
for path in sorted(glob.glob(os.path.join(RAW, "topic_*.json"))):
    data = json.load(open(path, encoding="utf-8"))
    topic, replies = data["topic"], data["replies"]
    op_user = topic["member"]["username"]
    floors = []
    for i, r in enumerate(replies, start=1):
        floors.append({
            "floor": i,
            "reply_id": r["id"],
            "username": r["member"]["username"],
            "thanks": r.get("thanks", 0),
            "created": r.get("created"),
            "content": r.get("content", ""),
            "content_rendered": r.get("content_rendered", ""),
            "links": extract_links(r.get("content", "")),
        })
    stats = build_edges(floors, op_user)
    total_stats.update(stats)
    out = {
        "topic_id": topic["id"],
        "title": topic["title"],
        "url": topic["url"],
        "op": op_user,
        "content": topic.get("content", ""),
        "reply_count": topic.get("replies"),
        "floors": floors,
    }
    with open(os.path.join(OUT, f"topic_{topic['id']}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    n_links = sum(len(f["links"]) for f in floors)
    print(f"{topic['id']}: {len(floors)} floors, {n_links} links, edges={dict(stats)}")
print("TOTAL edges:", dict(total_stats))
