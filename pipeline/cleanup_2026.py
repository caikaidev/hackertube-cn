#!/usr/bin/env python3
"""One-off cleanup of the 2026 merge (documented decisions, 2026-11-02):
1. Fold 老高和小茉 (platform mis-tagged bilibili in one thread) into 老高与小茉.
2. Politics purge: entries the user already voted to exclude （睡前消息/马督工/
   二爷故事/赵灵敏） plus new politics-milieu names from the 2026 commentary
   thread （立党/石国鹏 1972/王菊） -> excluded_politics.json, restorable.
3. Split list-lump entries per extraction rule D (list floors recommend each
   member): 面基、摸鱼早报、商业就是这样、十字路口 Crossing lump and the
   半拿铁|商业沉浮录 lump.
"""
import json, os, re

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data", "data.json")
EXC = os.path.join(BASE, "data", "excluded_politics.json")

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

items = json.load(open(DATA, encoding="utf-8"))
excluded = json.load(open(EXC, encoding="utf-8"))
ex_names = {norm(e["name"]) for e in excluded}

def add_excluded(name, reason, tid=None):
    if norm(name) not in ex_names:
        excluded.append({"topic_id": tid, "name": name, "reason": reason})
        ex_names.add(norm(name))

def find(name):
    for x in items:
        if x["name"] == name:
            return x
    return None

# 1. fold 老高和小茉
a, b = find("老高与小茉"), find("老高和小茉")
if a and b:
    tids = {s["topic_id"] for s in a["sources"]}
    for s in b["sources"]:
        if s["topic_id"] not in tids:
            a["sources"].append(s)
    a["mention_count"] += b["mention_count"]
    items.remove(b)
    print("folded 老高和小茉 -> 老高与小茉, mc now", a["mention_count"])

# 2. politics purge
PURGE = {
    "睡前消息": "用户已拍板不收（待定区 6 条之一），本次重提取又入选，维持原判",
    "马督工": "用户已拍板不收（待定区 6 条之一），本次重提取又入选，维持原判",
    "二爷故事": "用户已拍板不收（待定区 6 条之一），本次重提取又入选，维持原判",
    "赵灵敏（世界灵敏度）": "用户已拍板不收（待定区：赵灵敏），维持原判",
    "立党": "时政评论类，默认不收；且原帖评价褒贬不一，不合正面认可门槛",
    "石国鹏 1972": "历史、时政评论类，默认不收",
    "王菊": "2026 时政评论帖语境中被提及，默认不收（可恢复）",
}
for name, reason in PURGE.items():
    x = find(name)
    if x:
        tid = x["sources"][0]["topic_id"] if x["sources"] else None
        add_excluded("赵灵敏" if name.startswith("赵灵敏") else name, reason, tid)
        items.remove(x)
        print("purged to excluded:", name)

# 3a. split the list lump
lump = find("面基、摸鱼早报、商业就是这样、十字路口 Crossing")
if lump:
    items.remove(lump)
    src76 = [{"topic_id": 1185562, "floors": [76], "positive_floors": []}]
    items.append({"type": "creator", "platform": "other", "name": "摸鱼早报", "url": "",
                  "summary": "播客名单楼集中推荐之一", "category": "科技数码",
                  "mention_count": 1, "self_promo": False, "sources": src76})
    items.append({"type": "creator", "platform": "other", "name": "商业就是这样", "url": "",
                  "summary": "商业播客，楼主与名单楼两次推荐", "category": "财经",
                  "mention_count": 2, "self_promo": False,
                  "sources": [{"topic_id": 1185562, "floors": [1], "positive_floors": []}] + src76})
    for host_name in ("面基", "罗永浩的十字路口"):
        h = find(host_name)
        if h and all(s["topic_id"] != 1185562 or 76 not in (s.get("floors") or []) for s in h["sources"]):
            h["sources"].append({"topic_id": 1185562, "floors": [76], "positive_floors": []})
            h["mention_count"] += 1
    print("split lump -> 摸鱼早报 / 商业就是这样 (+sources for 面基/十字路口)")

# 3b. 半拿铁 lump
lump2 = find("半拿铁|商业沉浮录")
if lump2:
    items.remove(lump2)
    h = find("半拿铁")
    if h:
        h["sources"].append({"topic_id": 1185562, "floors": [66], "positive_floors": []})
        h["mention_count"] += 1
    print("dropped 半拿铁|商业沉浮录 lump (floor folded into 半拿铁)")

items.sort(key=lambda x: -x["mention_count"])
json.dump(items, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(excluded, open(EXC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"final items: {len(items)} | excluded: {len(excluded)}")
print("all names:", [x["name"] for x in items])
