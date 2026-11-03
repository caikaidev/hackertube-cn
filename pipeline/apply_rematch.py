#!/usr/bin/env python3
"""Apply the reviewed re-match plan (2026-11-03).

- Accepted new matches: set url/avatar/fans from the account card.
- Merges: SCFR into 蜀犬吠日 (same account 蜀犬吠日SCFR), 赖导 AboutLai
  into 赖导 (same account), 落拓 into 落拓呀 (same account 是落拓呀).
- Clears (no credible account found): drop url/avatar/fans so the entry
  falls back to platform search instead of a dead squatter link.
Rejected by review: 叶落初冬 -> 魔兽世界叶落初冬 (gaming account, wrong
person), 朱志文 -> 朱志文漂游记 (namesake, unverifiable) -> cleared.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_covers import bili_card  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "data.json")

# name -> (new mid, aka or None)
ACCEPT = {
    "付鹏": (662660667, "付鹏的财经世界"),
    "小鱼哥": (333010040, "招财小瑜哥"),
    "李永乐老师": (None, None),  # mid from plan
    "无穷小亮": (None, "无穷小亮的科普日常"),
    "极客湾": (None, None),
    "盗月社": (None, "盗月社食遇记"),
    "小钟": (None, None),
    "小黑屋的貘": (None, None),
    "中队长": (None, "中队长同志"),
}
CLEAR = ["午夜狂暴哈士奇", "回形针", "女菩萨", "牛总", "老张啊", "视野环球财经", "叶落初冬", "朱志文"]
MERGES = [  # (donor, target, target aka)
    ("SCFR", "蜀犬吠日", "SCFR"),
    ("赖导 AboutLai", "赖导", "赖导AboutLai"),
    ("落拓", "落拓呀", "是落拓呀"),
]


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    plan = {r["name"]: r for r in json.load(open(os.path.join(BASE, "data", "rematch_plan.json"), encoding="utf-8"))}
    by = {e["name"]: e for e in data}

    def set_from_card(e, mid, aka):
        card = bili_card(str(mid))
        time.sleep(1.0)
        if not card:
            print("CARD FAILED", e["name"], mid)
            return
        e["url"] = f"https://space.bilibili.com/{mid}"
        e["avatar"] = card["face"]
        e["fans"] = card["fans"]
        e["cover"] = None
        e["resolved_via"] = "bili_rematch_2026-11-03"
        if aka:
            e["aka"] = aka
        print(f"set {e['name']} -> {card['name']} (fans {card['fans']})")

    for name, (mid, aka) in ACCEPT.items():
        mid = mid or plan[name]["new_mid"]
        set_from_card(by[name], mid, aka)

    for donor_name, target_name, aka in MERGES:
        donor, target = by[donor_name], by[target_name]
        mid = (plan.get(donor_name) or {}).get("new_mid") or (plan.get(target_name) or {}).get("new_mid")
        target["mention_count"] += donor["mention_count"]
        target["sources"] = target.get("sources", []) + donor.get("sources", [])
        target["aka"] = aka
        data.remove(donor)
        print(f"merged {donor_name} into {target_name} (mentions {target['mention_count']})")
        set_from_card(target, mid, aka)

    for name in CLEAR:
        e = by[name]
        e["url"] = None
        e["avatar"] = None
        e["fans"] = None
        e["cover"] = None
        e["resolved_via"] = None
        print(f"cleared {name} (back to search fallback)")

    json.dump(data, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("entries now:", len(data))


if __name__ == "__main__":
    main()
