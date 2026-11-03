#!/usr/bin/env python3
"""Curation for the 2023 backfill batch (adjudicated 2026-11-03).

- Name variants merge into their canonical entries.
- Podcast guests praised on 罗永浩's show (刘谦/何小鹏/李想/宋方金,
  all from t/1175341) are dropped: guests, not recommended creators.
- Current-affairs commentators move to excluded_politics.json.
- Telegram channel names, junk and non-creators are dropped.
- Horror-story podcasts get platform=podcast, category=生活.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "data.json")
EXCL = os.path.join(BASE, "data", "excluded_politics.json")

MERGE = {
    "罗永浩": "罗永浩的十字路口",
    "商业访谈录": "张小珺",
    "老高与小沫": "老高与小茉",
    "老高与小莫": "老高与小茉",
    "老高和小茉": "老高与小茉",
    "李永乐": "李永乐老师",
    "乔·罗根 Joe Rogan": "Joe Rogan",
    "半拿铁|商业沉浮录": "半拿铁",
    "半拿铁·周刊": "半拿铁",
}
POLITICS = ["立党", "五岳散人", "王局", "躺平叔", "文昭谈古论今", "陈破空纵论天下",
            "江峰时刻", "二爷故事", "赵灵敏（世界灵敏度）", "睡前消息", "马督工",
            "王菊", "小岛大浪吹", "中指通"]
DROP = ["刘谦", "何小鹏", "李想", "宋方金", "CCTV", "AtlasOS", "Solidot",
        "APPDO 数字生活指南", "巨魔商店", "阿里云盘盘 - 📣通知频道",
        "科技圈🎗在花频道📮", "Digital Immigrants 丨 Want Want Channel",
        "https://space.bilibili.com/485642308/video", "阿喵的小生活永劫无间",
        "面基、摸鱼早报、商业就是这样、十字路口 Crossing"]
PODCAST_FIX = ["张震讲故事", "黑水怪谈", "机核网--中元夜话", "硬核说（硬核电台）"]
CAT_FIX = {"脑洞乌托邦": "科普"}


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    excl = json.load(open(EXCL, encoding="utf-8"))
    by = {e["name"]: e for e in data}
    for donor_name, target_name in MERGE.items():
        if donor_name in by and target_name in by:
            d, t = by[donor_name], by[target_name]
            t["mention_count"] += d["mention_count"]
            t["sources"] = t.get("sources", []) + d.get("sources", [])
            data.remove(d)
            print(f"merged {donor_name} -> {target_name} (now {t['mention_count']})")
    excl_names = {r["name"] for r in excl}
    for name in POLITICS:
        if name in by:
            data.remove(by[name])
            if name not in excl_names:
                excl.append({"name": name, "mention_count": by[name]["mention_count"],
                             "category": by[name].get("category"), "platform": by[name].get("platform"),
                             "sources": by[name].get("sources", []),
                             "note": "时政评论类，按既定规则不收录（2023 回补策展）"})
            print(f"politics: {name}")
    for name in DROP:
        if name in by:
            data.remove(by[name])
            print(f"dropped: {name}")
    by = {e["name"]: e for e in data}
    for name in PODCAST_FIX:
        if name in by:
            by[name]["platform"] = "podcast"
            by[name]["category"] = "生活"
    for name, cat in CAT_FIX.items():
        if name in by:
            by[name]["category"] = cat
    json.dump(data, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(excl, open(EXCL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"entries: {len(data)}, excluded: {len(excl)}")


if __name__ == "__main__":
    main()
