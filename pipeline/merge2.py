#!/usr/bin/env python3
"""Merge v2: dedupe sweep additions, re-filter by recomputed evidence (distinct users + positive signal),
merge into data.json, batch-classify (40/call), self_promo + politics + name verification."""
import json, os, re, glob, subprocess
from collections import defaultdict, Counter

BASE = os.path.join(os.path.dirname(__file__), "..")
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
POLITICS = ["王志安", "王局拍案", "新官场", "星话大白", "柴静", "听床党", "政经鲁社长", "张召忠", "馆长"]
POS = re.compile(r"不错|推荐|好看|感谢|收藏|确实|值得|厉害|优质|宝藏|良心|干货|必看|关注了|订阅|强推|很好|喜欢|必读|精彩|硬核")
PROMO_CUE = re.compile(r"推荐(一下)?我?自己|自荐|我就是|本人|我的频道|我的视频|我做的")

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def main():
    topics = {}
    for p in glob.glob(os.path.join(BASE, "data", "parsed", "topic_*.json")):
        t = json.load(open(p, encoding="utf-8"))
        topics[t["topic_id"]] = t
    children = {}
    for tid, t in topics.items():
        ch = defaultdict(list)
        for f in t["floors"]:
            if f["parent_floor"]:
                ch[f["parent_floor"]].append(f["floor"])
        children[tid] = ch
    by_floor = {tid: {f["floor"]: f for f in t["floors"]} for tid, t in topics.items()}

    items = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
    cur_norm = {norm(i["name"]) for i in items}
    additions = json.load(open(os.path.join(BASE, "data", "sweep", "additions.json"), encoding="utf-8"))

    # dedupe candidates by normalized name, keep any llm summary
    cand = {}
    for a in additions:
        if a["verdict"] == "rejected":
            continue
        k = norm(a["name"])
        if k in cur_norm:
            continue
        if k not in cand:
            cand[k] = {"name": a["name"], "summary": a.get("summary", ""), "platform": a.get("platform", "")}
    print("unique new candidates:", len(cand))

    accepted, dropped = [], []
    for k, c in cand.items():
        name = c["name"]
        hit = []  # (tid, floor_dict)
        for tid, t in topics.items():
            for f in t["floors"]:
                if name in f["content"]:
                    hit.append((tid, f))
        if not hit:
            dropped.append((name, "no_floor_hit"))
            continue
        users = {f["username"] for _, f in hit}
        pos = False
        for tid, f in hit:
            if POS.search(f["content"]):
                pos = True
                break
            for cf_no in children[tid].get(f["floor"], []):
                if POS.search(by_floor[tid][cf_no]["content"]):
                    pos = True
                    break
            if pos:
                break
        if (len(users) >= 2 and pos) or len(users) >= 5:
            src = defaultdict(list)
            for tid, f in hit:
                src[tid].append(f["floor"])
            url = ""
            for tid, f in hit:
                if f["links"]:
                    url = f["links"][0]["url"]
                    break
            accepted.append({
                "type": "creator", "platform": c["platform"] or "bilibili", "name": name,
                "url": url, "summary": c["summary"], "category": "其他",
                "mention_count": len(hit), "self_promo": False,
                "sources": [{"topic_id": tid, "floors": fl, "positive_floors": []} for tid, fl in src.items()],
                "via_sweep": "users=%d pos=%s" % (len(users), pos),
            })
        else:
            dropped.append((name, "users=%d pos=%s" % (len(users), pos)))
    print("accepted additions:", len(accepted), "| dropped:", len(dropped))
    items.extend(accepted)

    # batch classification, 40 per call
    CATPROMPT = """你是一个分类助手。为下面每个博主/频道判定 platform 与 category；summary 为空的，根据来源帖主题补一句≤40字中性描述（只写做什么内容，不编造评价）。
platform 只能是 bilibili、youtube、podcast、other（播客节目/有声音频用 podcast）。category 只能从 [编程, 科技数码, 财经, 科普, 历史人文, 影视, 音乐, 生活, 游戏, 其他] 选一：编程=编程开发与技术教学；科技数码=数码产品、科技资讯、AI；财经=投资理财、商业、经济；科普=科学知识普及；历史人文=历史文化人文社科；影视=电影剧集影评解说；音乐=音乐类；生活=vlog、美食、旅行、日常；游戏=游戏内容；其他=确实无法归类才用。
只输出 JSON 对象：{"results": [{"name": "", "platform": "", "category": "", "summary": ""}]}，与输入同序，summary 已有值时原样返回。
输入：
"""
    for b in range(0, len(items), 40):
        batch = items[b:b+40]
        rows = [{"name": it["name"], "platform": it["platform"], "category": it["category"],
                 "summary": it["summary"], "from_topic": topics[it["sources"][0]["topic_id"]]["title"]} for it in batch]
        pf = os.path.join(BASE, "data", "sweep", "cls_prompt_%d.txt" % b)
        out = os.path.join(BASE, "data", "sweep", "cls_out_%d.json" % b)
        open(pf, "w", encoding="utf-8").write(CATPROMPT + json.dumps(rows, ensure_ascii=False))
        r = subprocess.run(["python3", HELPER, "chat", pf, "gpt-4o-mini", out], capture_output=True, text=True, timeout=600)
        try:
            results = json.load(open(out, encoding="utf-8")).get("results", [])
        except Exception as e:
            print("batch", b, "classify parse failed, keeping old:", e, flush=True)
            continue
        by_name = {norm(x.get("name", "")): x for x in results}
        for it in batch:
            res = by_name.get(norm(it["name"]))
            if res:
                if res.get("category"):
                    it["category"] = res["category"]
                if res.get("platform"):
                    it["platform"] = res["platform"]
                if not it["summary"] and res.get("summary"):
                    it["summary"] = res["summary"]
        print("batch", b, "classified", len(results), flush=True)

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
    print("FINAL:", len(final), "| categories:", dict(Counter(i["category"] for i in final)))
    print("self_promo:", [i["name"] for i in final if i["self_promo"]])
    print("added names:", [a["name"] for a in accepted])

if __name__ == "__main__":
    main()
