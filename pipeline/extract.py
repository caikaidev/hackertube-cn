#!/usr/bin/env python3
"""Topic-level LLM extraction via custom.openai chat helper (gpt-4o-mini), then cross-topic dedup merge."""
import json, os, re, glob, subprocess
from collections import defaultdict

BASE = os.path.join(os.path.dirname(__file__), "..")
PARSED = os.path.join(BASE, "data", "parsed")
EXTRACTED = os.path.join(BASE, "data", "extracted")
os.makedirs(EXTRACTED, exist_ok=True)
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
MODEL = "gpt-4o-mini"

PROMPT_HEAD = """你是一个严格的内容筛选助手。下面是一个 V2EX 主题的正文和全部回复楼层（平铺结构，楼层号即顺序）。每楼后面标注了系统解析出的信息：该楼包含的链接、哪些楼层回复了它（子楼层）。

【任务】从整个主题中提取被推荐的视频或博主，并为每条找到佐证。

【入选条件】满足任一：
A. 同一博主/视频被 ≥2 个不同用户独立提及；
B. 被提及后，有子楼层或后续楼层出现点名/引用它的正面评价（不错、推荐、好看、感谢、收藏、确实好等）；
C. 被求推荐帖的楼主在后续楼层确认采纳或点名感谢。

【硬规则】
1. url 只能填写原文或标注链接中真实出现的链接，禁止根据名字推断或拼接主页链接；没有就留空字符串。
2. 推荐人就是博主本人时 "self_promo": true。
3. 同一博主/视频在多楼出现时合并为一条，mention_count 累加（只算独立提及的楼层数）。
4. summary 只概括原文已有的推荐理由，不添加原文没有的评价，≤40字。
5. category 从 [编程, 科技数码, 财经, 科普, 历史人文, 影视, 音乐, 生活, 游戏, 其他] 中选一个。
6. 新闻时政类（时政评论、新闻政评、政治话题博主）不要放入 items，单独放入 excluded，name+一句话原因即可。

【输出】只输出一个 JSON 对象，不要其他文字：
{"items": [{"type": "video", "platform": "bilibili", "name": "博主名或视频标题", "url": "", "summary": "", "category": "", "mention_count": 1, "positive_floors": [], "source_floors": [], "self_promo": false}], "excluded": [{"name": "", "reason": ""}]}
type 可为 video 或 creator；platform 可为 bilibili、youtube、podcast 或 other（播客节目/有声音频填 podcast）。

"""

def build_prompt(topic):
    children = defaultdict(list)
    for f in topic["floors"]:
        if f["parent_floor"]:
            children[f["parent_floor"]].append(f["floor"])
    lines = [PROMPT_HEAD,
             "主题标题：" + topic["title"],
             "楼主：" + topic["op"],
             "主题正文：" + (topic["content"] or "（无正文）"),
             "回复楼层："]
    for f in topic["floors"]:
        line = "%d. [%s] %s" % (f["floor"], f["username"], f["content"])
        notes = []
        if f["links"]:
            notes.append("链接: " + ", ".join(l["url"] for l in f["links"]))
        if children.get(f["floor"]):
            notes.append("被这些楼层回复: " + ",".join(str(c) for c in children[f["floor"]]))
        if f["thanks"]:
            notes.append("感谢数: %d" % f["thanks"])
        if notes:
            line += "  〔" + "；".join(notes) + "〕"
        lines.append(line)
    return "\n".join(lines)

def norm_name(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def main():
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    merged = {}
    excluded_all = []
    for path in sorted(glob.glob(os.path.join(PARSED, "topic_*.json"))):
        topic = json.load(open(path, encoding="utf-8"))
        tid = topic["topic_id"]
        out_path = os.path.join(EXTRACTED, "topic_%d.json" % tid)
        if os.path.exists(out_path):
            result = json.load(open(out_path, encoding="utf-8"))
            print("%d: cached extraction" % tid, flush=True)
        else:
            prompt_file = os.path.join(EXTRACTED, "prompt_%d.txt" % tid)
            with open(prompt_file, "w", encoding="utf-8") as fh:
                fh.write(build_prompt(topic))
            raw_out = os.path.join(EXTRACTED, "raw_%d.json" % tid)
            r = subprocess.run(["python3", HELPER, "chat", prompt_file, MODEL, raw_out],
                               capture_output=True, text=True, timeout=600)
            print("%d: helper -> %s %s" % (tid, r.stdout.strip()[:300], r.stderr.strip()[:200]), flush=True)
            if r.returncode != 0 or not os.path.exists(raw_out):
                print("%d: EXTRACTION FAILED" % tid, flush=True)
                continue
            try:
                meta = json.loads(r.stdout)
                usage_total["prompt_tokens"] += meta["usage"].get("prompt_tokens", 0)
                usage_total["completion_tokens"] += meta["usage"].get("completion_tokens", 0)
            except Exception:
                pass
            result = json.load(open(raw_out, encoding="utf-8"))
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=1)
        items = result.get("items", [])
        excluded_all.extend(dict({"topic_id": tid}, **e) for e in result.get("excluded", []))
        print("%d: %d items, %d excluded" % (tid, len(items), len(result.get("excluded", []))), flush=True)
        for it in items:
            key = (it.get("platform", ""), norm_name(it.get("name", "")))
            if not key[1]:
                continue
            if key in merged:
                m = merged[key]
                m["mention_count"] += it.get("mention_count", 1)
                m["sources"].append({"topic_id": tid, "floors": it.get("source_floors", []),
                                     "positive_floors": it.get("positive_floors", [])})
                if not m["url"] and it.get("url"):
                    m["url"] = it["url"]
                m["self_promo"] = m["self_promo"] and bool(it.get("self_promo"))
            else:
                merged[key] = {
                    "type": it.get("type"), "platform": it.get("platform"), "name": it.get("name"),
                    "url": it.get("url", ""), "summary": it.get("summary", ""),
                    "category": it.get("category", "其他"),
                    "mention_count": it.get("mention_count", 1),
                    "self_promo": bool(it.get("self_promo")),
                    "sources": [{"topic_id": tid, "floors": it.get("source_floors", []),
                                 "positive_floors": it.get("positive_floors", [])}],
                }
    items = sorted(merged.values(), key=lambda x: -x["mention_count"])
    with open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(BASE, "data", "excluded_politics.json"), "w", encoding="utf-8") as fh:
        json.dump(excluded_all, fh, ensure_ascii=False, indent=1)
    print("MERGED: %d unique items, %d excluded, usage=%s" % (len(items), len(excluded_all), usage_total), flush=True)

if __name__ == "__main__":
    main()
