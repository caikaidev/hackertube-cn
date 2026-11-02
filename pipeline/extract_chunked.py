#!/usr/bin/env python3
"""Chunked extraction v2: split each topic's floors into ~55-floor chunks, extract per chunk,
merge all chunks+topics by normalized name, then verify names against source corpus and
apply the politics blocklist (user decision: politics excluded by default)."""
import json, os, re, subprocess, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from corpus import load_topics, source_of, topic_key

BASE = os.path.join(os.path.dirname(__file__), "..")
EXT = os.path.join(BASE, "data", "extracted_v2")
os.makedirs(EXT, exist_ok=True)
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
MODEL = "gpt-4o-mini"
CHUNK = 55

HEAD = """你是一个严格的内容筛选助手。下面是一个在线论坛主题的部分回复楼层（楼层号是全帖统一编号）。每楼后面标注了该楼包含的链接、哪些楼层回复了它。

【任务】从这段楼层中提取被推荐的视频或博主，并为每条找到佐证。

【入选条件】满足任一：
A. 同一博主/视频在这段楼层中被 ≥2 个不同用户独立提及；
B. 被提及后，有子楼层或后续楼层出现点名/引用它的正面评价（不错、推荐、好看、感谢、收藏、确实好等）；
C. 被楼主确认采纳或点名感谢；
D. 某个楼层以名单形式集中推荐了多位博主（例如一楼列出多个名字并给出正面总评），名单中的博主也可入选，source_floors 填该名单楼层号，mention_count 填 1。

【硬规则】
1. 名字必须逐字来自原文，禁止改写、补全或猜测博主名。
2. url 只能填写原文或标注链接中真实出现的链接，禁止推断或拼接；没有就留空字符串。
3. 推荐人就是博主本人时 "self_promo": true。
4. summary 只概括原文已有的推荐理由，≤40字。
5. category 从 [编程, 科技数码, 财经, 科普, 历史人文, 影视, 音乐, 生活, 游戏, 其他] 中选一个。
6. 新闻时政类不要放入 items，单独放入 excluded。

【输出】只输出一个 JSON 对象：
{"items": [{"type": "creator", "platform": "bilibili", "name": "", "url": "", "summary": "", "category": "", "mention_count": 1, "positive_floors": [], "source_floors": [], "self_promo": false}], "excluded": [{"name": "", "reason": ""}]}
type 可为 video 或 creator；platform 可为 bilibili、youtube 或 other。

"""

POLITICS = ["王志安", "王局拍案", "新官场", "星话大白", "柴静", "听床党", "政经鲁社长", "张召忠", "馆长"]

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def main():
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    merged = {}
    excluded = []
    corpus = {}
    for (tsrc, tid), topic in sorted(load_topics().items()):
        corpus[(tsrc, tid)] = norm(topic["title"] + topic["content"] + " ".join(f["content"] for f in topic["floors"]))
        children = defaultdict(list)
        for f in topic["floors"]:
            if f["parent_floor"]:
                children[f["parent_floor"]].append(f["floor"])
        floors = topic["floors"]
        chunks = [floors[i:i+CHUNK] for i in range(0, len(floors), CHUNK)] or [[ ]]
        for ci, chunk in enumerate(chunks):
            out_path = os.path.join(EXT, "%s_t%d_c%d.json" % (tsrc, tid, ci))
            if os.path.exists(out_path):
                result = json.load(open(out_path, encoding="utf-8"))
            else:
                lines = [HEAD, "主题标题：" + topic["title"], "楼主：" + topic["op"],
                         "主题正文：" + (topic["content"] or "（无正文）"), "回复楼层："]
                for f in chunk:
                    line = "%d. [%s] %s" % (f["floor"], f["username"], f["content"])
                    notes = []
                    if f["links"]:
                        notes.append("链接: " + ", ".join(l["url"] for l in f["links"]))
                    if children.get(f["floor"]):
                        notes.append("被这些楼层回复: " + ",".join(str(c) for c in children[f["floor"]]))
                    if notes:
                        line += "  〔" + "；".join(notes) + "〕"
                    lines.append(line)
                pf = os.path.join(EXT, "prompt_%s_t%d_c%d.txt" % (tsrc, tid, ci))
                open(pf, "w", encoding="utf-8").write("\n".join(lines))
                raw = os.path.join(EXT, "raw_%s_t%d_c%d.json" % (tsrc, tid, ci))
                r = subprocess.run(["python3", HELPER, "chat", pf, MODEL, raw], capture_output=True, text=True, timeout=600)
                if r.returncode != 0 or not os.path.exists(raw):
                    print("FAIL", tid, ci, r.stdout[:150], r.stderr[:150], flush=True)
                    continue
                try:
                    meta = json.loads(r.stdout)
                    usage["prompt_tokens"] += meta["usage"].get("prompt_tokens", 0)
                    usage["completion_tokens"] += meta["usage"].get("completion_tokens", 0)
                except Exception:
                    pass
                result = json.load(open(raw, encoding="utf-8"))
                json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            for e in result.get("excluded", []):
                excluded.append(dict({"source": tsrc, "topic_id": tid}, **e))
            for it in result.get("items", []):
                key = (it.get("platform", ""), norm(it.get("name", "")))
                if not key[1]:
                    continue
                if key in merged:
                    m = merged[key]
                    m["mention_count"] += it.get("mention_count", 1)
                    m["sources"].append({"source": tsrc, "topic_id": tid, "floors": it.get("source_floors", []), "positive_floors": it.get("positive_floors", [])})
                    if not m["url"] and it.get("url"):
                        m["url"] = it["url"]
                    m["self_promo"] = m["self_promo"] and bool(it.get("self_promo"))
                else:
                    merged[key] = {"type": it.get("type"), "platform": it.get("platform"), "name": it.get("name"),
                                   "url": it.get("url", ""), "summary": it.get("summary", ""),
                                   "category": it.get("category", "其他"), "mention_count": it.get("mention_count", 1),
                                   "self_promo": bool(it.get("self_promo")),
                                   "sources": [{"source": tsrc, "topic_id": tid, "floors": it.get("source_floors", []), "positive_floors": it.get("positive_floors", [])}]}
            print("%s t%d c%d: %d items" % (tsrc, tid, ci, len(result.get("items", []))), flush=True)
    # verify names against corpus of their source topics; drop fabrications
    verified, dropped = [], []
    for it in merged.values():
        ok = any(norm(it["name"]) in corpus[topic_key(source_of(s), s["topic_id"])] for s in it["sources"])
        (verified if ok else dropped).append(it if ok else it["name"])
    # politics blocklist
    final, moved = [], []
    for it in verified:
        if any(p in it["name"] for p in POLITICS):
            moved.append(it["name"])
            excluded.append({"source": source_of(it["sources"][0]), "topic_id": it["sources"][0]["topic_id"], "name": it["name"], "reason": "用户口径：时政类默认不收（管线后过滤）"})
        else:
            final.append(it)
    final.sort(key=lambda x: -x["mention_count"])
    json.dump(final, open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(excluded, open(os.path.join(BASE, "data", "excluded_politics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("V2 MERGED: %d items | dropped_fabricated=%s | politics_moved=%s | usage=%s" % (len(final), dropped, moved, usage), flush=True)

if __name__ == "__main__":
    main()
