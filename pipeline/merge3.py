#!/usr/bin/env python3
"""Cleanup v3: politics/borderline moves, containment dedupe, commenter-name junk drop,
evidence-based reclassification of remaining '其他' items (positional mapping)."""
import json, os, re, glob, subprocess
from collections import defaultdict, Counter

BASE = os.path.join(os.path.dirname(__file__), "..")
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
POLITICS_ADD = ["王局", "官场"]
BORDERLINE = ["户晨风", "X 调查", "X调查"]
STOPLIST = {"rust", "钓鱼", "长视频", "冰", "ak", "tim"}

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def main():
    topics = {}
    authors = set()
    for p in glob.glob(os.path.join(BASE, "data", "parsed", "topic_*.json")):
        t = json.load(open(p, encoding="utf-8"))
        topics[t["topic_id"]] = t
        for f in t["floors"]:
            authors.add(f["username"].lower())
    items = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
    excluded = json.load(open(os.path.join(BASE, "data", "excluded_politics.json"), encoding="utf-8"))

    kept = []
    for it in items:
        if it["name"] in POLITICS_ADD:
            excluded.append({"topic_id": it["sources"][0]["topic_id"], "name": it["name"], "reason": "用户口径：时政类默认不收（复检后过滤）"})
        elif it["name"] in BORDERLINE:
            excluded.append({"topic_id": it["sources"][0]["topic_id"], "name": it["name"], "reason": "社会新闻/时政相邻，待用户定（暂不收）"})
        else:
            kept.append(it)
    items = kept
    print("after politics/borderline moves:", len(items))

    # containment dedupe: shorter normalized name contained in longer -> merge into longer
    items.sort(key=lambda x: len(norm(x["name"])))
    merged_away = []
    alive = []
    for it in items:
        target = None
        for other in items:
            if other is it:
                continue
            if len(norm(other["name"])) > len(norm(it["name"])) and norm(it["name"]) in norm(other["name"]) and len(norm(it["name"])) >= 3:
                target = other
                break
        if target is not None:
            target["mention_count"] += it["mention_count"]
            target["sources"].extend(it["sources"])
            if not target["url"] and it["url"]:
                target["url"] = it["url"]
            merged_away.append(it["name"] + " -> " + target["name"])
        else:
            alive.append(it)
    items = alive
    print("containment merged:", merged_away)

    dropped = []
    kept = []
    for it in items:
        is_author = norm(it["name"]) in authors
        if norm(it["name"]) in STOPLIST:
            dropped.append(it["name"] + " (stoplist)")
        elif it.get("via_sweep") and not it["url"] and is_author:
            dropped.append(it["name"] + " (v2ex commenter name)")
        else:
            kept.append(it)
    items = kept
    print("junk dropped:", dropped, "| remaining:", len(items))

    # evidence-based reclassification for items still in 其他
    others = [it for it in items if it["category"] == "其他"]
    print("to reclassify:", len(others))
    PROMPT = """你是一个分类助手。下面每个博主/频道附了它在 V2EX 被提及的原文楼层节选。请只根据节选内容判定 category，只能从 [编程, 科技数码, 财经, 科普, 历史人文, 影视, 音乐, 生活, 游戏, 其他] 选一：编程=编程开发与技术教学；科技数码=数码产品、科技资讯、AI；财经=投资理财、商业、经济；科普=科学知识普及；历史人文=历史文化人文社科；影视=电影剧集影评解说；音乐=音乐类；生活=vlog、美食、旅行、日常；游戏=游戏内容；其他=节选也看不出领域时才用。
只输出 JSON 对象：{"categories": ["分类1", "分类2", ...]}，数组与输入条目同序同长，不要输出名字。

条目：
"""
    for b in range(0, len(others), 25):
        batch = others[b:b+25]
        lines = []
        for idx, it in enumerate(batch):
            ev = []
            for s in it["sources"][:2]:
                t = topics[s["topic_id"]]
                for f in t["floors"]:
                    if f["floor"] in (s["floors"] or []) and it["name"] in f["content"]:
                        ev.append(f["content"].replace("\n", " ")[:110])
                    if len(ev) >= 2:
                        break
                if len(ev) >= 2:
                    break
            lines.append("%d. %s（现摘要：%s）节选：%s" % (idx + 1, it["name"], it["summary"][:30], " / ".join(ev)))
        pf = os.path.join(BASE, "data", "sweep", "recls_prompt_%d.txt" % b)
        out = os.path.join(BASE, "data", "sweep", "recls_out_%d.json" % b)
        open(pf, "w", encoding="utf-8").write(PROMPT + "\n".join(lines))
        r = subprocess.run(["python3", HELPER, "chat", pf, "gpt-4o-mini", out], capture_output=True, text=True, timeout=600)
        try:
            cats = json.load(open(out, encoding="utf-8")).get("categories", [])
        except Exception as e:
            print("batch", b, "parse fail", e, flush=True)
            continue
        for it, c in zip(batch, cats):
            if c and c != "其他":
                it["category"] = c
        print("batch", b, "done", cats, flush=True)

    corpus = {tid: norm(t["title"] + t["content"] + " ".join(f["content"] for f in t["floors"])) for tid, t in topics.items()}
    items = [it for it in items if any(norm(it["name"]) in corpus[s["topic_id"]] for s in it["sources"])]
    items.sort(key=lambda x: -x["mention_count"])
    json.dump(items, open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(excluded, open(os.path.join(BASE, "data", "excluded_politics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("FINAL:", len(items), "| categories:", dict(Counter(i["category"] for i in items)))
    print("names:", [i["name"] for i in items])

if __name__ == "__main__":
    main()
