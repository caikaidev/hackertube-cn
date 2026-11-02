#!/usr/bin/env python3
"""Merge accepted sweep additions into data.json, re-classify ALL items in one LLM pass,
apply self_promo heuristic + politics blocklist, final name verification."""
import json, os, re, glob, subprocess
from collections import defaultdict

BASE = os.path.join(os.path.dirname(__file__), "..")
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
POLITICS = ["王志安", "王局拍案", "新官场", "星话大白", "柴静", "听床党", "政经鲁社长", "张召忠", "馆长"]
PROMO_CUE = re.compile(r"推荐(一下)?我?自己|自荐|我就是|本人|我的频道|我的视频|我做的")

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def main():
    topics = {}
    for p in glob.glob(os.path.join(BASE, "data", "parsed", "topic_*.json")):
        t = json.load(open(p, encoding="utf-8"))
        topics[t["topic_id"]] = t
    items = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
    additions = json.load(open(os.path.join(BASE, "data", "sweep", "additions.json"), encoding="utf-8"))
    added = 0
    for a in additions:
        if a["verdict"] == "rejected":
            continue
        t = topics[a["topic_id"]]
        hit = [f for f in t["floors"] if f["floor"] in a["floors"]]
        url = ""
        for f in hit:
            if f["links"]:
                url = f["links"][0]["url"]
                break
        items.append({
            "type": "creator", "platform": a.get("platform", "bilibili"), "name": a["name"],
            "url": url, "summary": a.get("summary", ""), "category": "其他",
            "mention_count": len(a["floors"]), "self_promo": False,
            "sources": [{"topic_id": a["topic_id"], "floors": a["floors"], "positive_floors": []}],
            "via_sweep": a["verdict"],
        })
        added += 1
    print("merged additions:", added)
    # summaries for auto_pass additions: borrow shortest positive-ish floor excerpt is risky; ask classify pass to also write summary
    rows = []
    for it in items:
        t = topics[it["sources"][0]["topic_id"]]
        rows.append({"name": it["name"], "platform": it["platform"], "category": it["category"],
                     "summary": it["summary"], "from_topic": t["title"]})
    prompt = """你是一个分类助手。下面是博主/频道清单（名字、平台、现有分类、推荐摘要、来源帖子标题）。请为每条重新判定 platform 和 category，并为 summary 为空的条目根据来源帖主题补一句≤40字的中性描述（只写它做什么内容，不编造评价）。
platform 只能是 bilibili、youtube、other。category 只能从 [编程, 科技数码, 财经, 科普, 历史人文, 影视, 音乐, 生活, 游戏, 其他] 选一个，按以下口径：编程=编程开发与技术教学；科技数码=数码产品、科技资讯、AI 工具；财经=投资理财、商业、经济；科普=科学知识普及；历史人文=历史、文化、人文社科；影视=电影剧集影评解说；音乐=音乐类；生活=vlog、美食、旅行、日常；游戏=游戏实况与游戏内容；其他=确实无法归入以上任何一类时才用。
只输出 JSON 对象：{"results": [{"name": "", "platform": "", "category": "", "summary": ""}]}，results 与输入同序，summary 有值时原样返回。

输入：
""" + json.dumps(rows, ensure_ascii=False)
    pf = os.path.join(BASE, "data", "sweep", "classify_prompt.txt")
    out = os.path.join(BASE, "data", "sweep", "classify_out.json")
    open(pf, "w", encoding="utf-8").write(prompt)
    r = subprocess.run(["python3", HELPER, "chat", pf, "gpt-4o-mini", out], capture_output=True, text=True, timeout=600)
    print("classify helper:", r.stdout.strip()[:200], r.stderr.strip()[:150])
    results = json.load(open(out, encoding="utf-8")).get("results", [])
    by_name = {}
    for res in results:
        by_name[norm(res.get("name", ""))] = res
    fixed = 0
    for it in items:
        res = by_name.get(norm(it["name"]))
        if res:
            if res.get("category") and res["category"] != it["category"]:
                it["category"] = res["category"]
                fixed += 1
            if res.get("platform"):
                it["platform"] = res["platform"]
            if not it["summary"] and res.get("summary"):
                it["summary"] = res["summary"]
    print("categories changed:", fixed)
    # self_promo heuristic + final checks
    for it in items:
        for s in it["sources"]:
            t = topics[s["topic_id"]]
            for f in t["floors"]:
                if f["floor"] in (s["floors"] or []) and it["name"] in f["content"] and PROMO_CUE.search(f["content"]):
                    it["self_promo"] = True
    excluded = json.load(open(os.path.join(BASE, "data", "excluded_politics.json"), encoding="utf-8"))
    final = []
    for it in items:
        if any(p in it["name"] for p in POLITICS):
            excluded.append({"topic_id": it["sources"][0]["topic_id"], "name": it["name"], "reason": "用户口径：时政类默认不收（复检后过滤）"})
        else:
            final.append(it)
    corpus = {tid: norm(t["title"] + t["content"] + " ".join(f["content"] for f in t["floors"])) for tid, t in topics.items()}
    final = [it for it in final if any(norm(it["name"]) in corpus[s["topic_id"]] for s in it["sources"])]
    final.sort(key=lambda x: -x["mention_count"])
    json.dump(final, open(os.path.join(BASE, "data", "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(excluded, open(os.path.join(BASE, "data", "excluded_politics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("FINAL:", len(final), "items | categories:", dict(Counter(i["category"] for i in final)), "| self_promo:", [i["name"] for i in final if i["self_promo"]])

if __name__ == "__main__":
    main()
