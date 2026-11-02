#!/usr/bin/env python3
"""Recall sweep: per chunk, list ALL mentioned creator names (no quality gate),
diff against current data.json, verify new candidates with floor evidence."""
import json, os, re, glob, subprocess
from collections import defaultdict

BASE = os.path.join(os.path.dirname(__file__), "..")
EXT = os.path.join(BASE, "data", "extracted_v2")
SWEEP = os.path.join(BASE, "data", "sweep")
os.makedirs(SWEEP, exist_ok=True)
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.openai/bin/openai_api.py")
POS = re.compile(r"不错|推荐|好看|感谢|收藏|确实|值得|厉害|优质|宝藏|良心|干货|必看|关注了|订阅|强推|很好|喜欢")

SWEEP_HEAD = """下面是一个 V2EX 主题的部分回复楼层。请列出这段楼层中出现的每一个被推荐、被提及或被讨论的博主/UP主/频道/视频名字，逐字抄写原文写法，不要改写、不要补全、不要判断质量好坏，不要遗漏名单楼层里列出的名字。只输出 JSON 对象：{"names": ["名字1", "名字2"]}

"""

VERIFY_HEAD = """你是一个严格的内容筛选助手。下面是某个 V2EX 主题中，与一位候选博主相关的全部楼层（含回复它的子楼层）。请判断该博主是否满足入选条件：被≥2个不同用户独立推荐/提及并认可，或被1人推荐且有其他楼层正面佐证（不错、好看、感谢、收藏、确实好等），或出现在带正面总评的推荐名单楼层中。只输出 JSON 对象：{"pass": true, "summary": "≤40字推荐理由，只用原文信息", "platform": "bilibili 或 youtube 或 other"}

候选博主：%s
相关楼层：
%s
"""

def norm(s):
    return re.sub(r"[\s\-_·・'']", "", (s or "").lower())

def call_chat(prompt_text, tag):
    pf = os.path.join(SWEEP, tag + ".txt")
    out = os.path.join(SWEEP, tag + ".json")
    if os.path.exists(out):
        return json.load(open(out, encoding="utf-8"))
    open(pf, "w", encoding="utf-8").write(prompt_text)
    r = subprocess.run(["python3", HELPER, "chat", pf, "gpt-4o-mini", out], capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(out):
        print("FAIL", tag, r.stdout[:150], r.stderr[:150], flush=True)
        return {}
    return json.load(open(out, encoding="utf-8"))

def main():
    topics = {}
    for p in glob.glob(os.path.join(BASE, "data", "parsed", "topic_*.json")):
        t = json.load(open(p, encoding="utf-8"))
        topics[t["topic_id"]] = t
    current = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
    cur_norm = [norm(i["name"]) for i in current]

    def covered(name):
        n = norm(name)
        return any(n == c or n in c or c in n for c in cur_norm if len(c) >= 2 and len(n) >= 2)

    additions = []
    for prompt_path in sorted(glob.glob(os.path.join(EXT, "prompt_t*_c*.txt"))):
        tag = os.path.basename(prompt_path).replace("prompt_", "sweep_").replace(".txt", "")
        tid = int(re.search(r"t(\d+)_", tag).group(1))
        text = open(prompt_path, encoding="utf-8").read()
        floors_text = text.split("回复楼层：", 1)[1] if "回复楼层：" in text else text
        res = call_chat(SWEEP_HEAD + floors_text, tag)
        names = res.get("names", [])
        topic = topics[tid]
        children = defaultdict(list)
        for f in topic["floors"]:
            if f["parent_floor"]:
                children[f["parent_floor"]].append(f["floor"])
        by_floor = {f["floor"]: f for f in topic["floors"]}
        for name in names:
            name = (name or "").strip()
            if not name or len(name) > 30 or covered(name):
                continue
            hit_floors = [f for f in topic["floors"] if name in f["content"]]
            if not hit_floors:
                continue
            users = {f["username"] for f in hit_floors}
            entry = {"name": name, "topic_id": tid, "floors": [f["floor"] for f in hit_floors],
                     "users": len(users), "verdict": None}
            if len(users) >= 2:
                entry["verdict"] = "auto_pass_multi_user"
                additions.append(entry)
            else:
                ev_lines = []
                for f in hit_floors:
                    ev_lines.append("%d. [%s] %s" % (f["floor"], f["username"], f["content"]))
                    for c in children.get(f["floor"], []):
                        cf = by_floor[c]
                        ev_lines.append("  子楼 %d. [%s] %s" % (c, cf["username"], cf["content"]))
                v = call_chat(VERIFY_HEAD % (name, "\n".join(ev_lines)), "verify_%d_%s" % (tid, norm(name)[:12]))
                if v.get("pass"):
                    entry["verdict"] = "llm_verified"
                    entry["summary"] = v.get("summary", "")
                    entry["platform"] = v.get("platform", "other")
                    additions.append(entry)
                else:
                    entry["verdict"] = "rejected"
                    additions.append(entry)
        print(tag, "done", flush=True)
    json.dump(additions, open(os.path.join(SWEEP, "additions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    acc = [a for a in additions if a["verdict"] != "rejected"]
    print("SWEEP: %d candidates checked, %d accepted, %d rejected" % (len(additions), len(acc), len(additions) - len(acc)))
    for a in additions:
        print(" ", a["verdict"], a["topic_id"], a["name"], "users=", a["users"], "floors=", a["floors"])

if __name__ == "__main__":
    main()
