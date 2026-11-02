#!/usr/bin/env python3
"""Build self-contained static index.html (+ feed.xml) from data.json.

v6 geek edition (external-review triage, user-approved 2026-11-02):
accepted: dark mode, keyboard-first nav, card/list dual view, real community
quotes as primary copy, local marks (fav/later/blocked, localStorage +
import/export), JSON/CSV export, RSS feed, Cmd+K palette — all in the same
single zero-dependency file.
rejected: iframe embeds (site stays pure-outlink by founding rule), 50%
thumbnail trick (no per-video data, no such API), React/Tailwind stack,
IndexedDB (localStorage is enough at this scale).
"""
import json, os, re, sys
from email.utils import formatdate
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(__file__))
from corpus import load_topics, source_of, topic_key

BASE = os.path.join(os.path.dirname(__file__), "..")
items = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
topics = load_topics()

URL_RE = re.compile(r"https?://\S+")

def clean_quote(text):
    t = URL_RE.sub("", text or "")
    t = re.sub(r"@([0-9A-Za-z_]+)", "", t)
    t = re.sub(r"\s+", " ", t).strip(" \t\r\n-—:：")
    return t

NEG_WORDS = ("难看", "不行", "太差", "很差", "抄袭", "抄的", "水分", "水了", "取关", "拉黑", "不好看", "没意思")

def pick_quote(it, t, s, by_floor):
    """Real community quote: earliest positive floor naming the creator; fall back
    to other positive floors, then to name-mentioning floors without negative words."""
    def grab(flnos, minlen):
        out = []
        for flno in flnos or []:
            f = by_floor.get(flno)
            if not f:
                continue
            txt = clean_quote(f.get("content"))
            if len(txt) >= minlen:
                out.append((f.get("created", 0), txt, f.get("username", "")))
        return out
    pos = grab(s.get("positive_floors"), 8)
    tiers = [
        [c for c in pos if it["name"] in c[1]],
        [c for c in pos if len(c[1]) >= 16],
        [c for c in grab(s.get("floors"), 12)
         if it["name"] in c[1] and not any(w in c[1] for w in NEG_WORDS)],
        pos,
    ]
    for pool in tiers:
        if pool:
            pool.sort(key=lambda c: c[0])
            _, txt, user = pool[0]
            if len(txt) > 88:
                txt = txt[:88] + "…"
            return {"text": txt, "by": user}
    return None

for it in items:
    srcs = []
    mention_ts = []
    quote = None
    for s in it["sources"]:
        t = topics.get(topic_key(source_of(s), s["topic_id"]))
        if not t:
            continue
        by_floor = {f["floor"]: f for f in t["floors"]}
        first_user = ""
        fl = sorted(s["floors"] or [])
        if fl and fl[0] in by_floor:
            first_user = by_floor[fl[0]]["username"]
        for flno in (s["floors"] or []) + (s.get("positive_floors") or []):
            if flno in by_floor and by_floor[flno].get("created"):
                mention_ts.append(by_floor[flno]["created"])
        srcs.append({"title": t["title"], "url": t["url"], "by": first_user, "source": source_of(s)})
        if not mention_ts and t["floors"]:
            mention_ts.append(min(f["created"] for f in t["floors"] if f.get("created")))
        if quote is None:
            quote = pick_quote(it, t, s, by_floor)
    it["source_topics"] = srcs
    if mention_ts:
        it["last_mention"] = max(mention_ts)
        it["first_mention"] = min(mention_ts)
    if quote:
        it["quote"] = quote
    it.pop("sources", None)

def out_link(d):
    if d.get("url"):
        return d["url"]
    kw = d["name"]
    from urllib.parse import quote as uq
    if d.get("platform") == "bilibili":
        return "https://search.bilibili.com/all?keyword=" + uq(kw)
    if d.get("platform") == "youtube":
        return "https://www.youtube.com/results?search_query=" + uq(kw)
    return "https://www.bing.com/search?q=" + uq(kw)

# ---- RSS feed (all entries, newest mention first) ----
feed_items = sorted(items, key=lambda d: -(d.get("last_mention") or 0))
rss = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<rss version="2.0"><channel>',
       '<title>HackerTube CN</title>',
       '<link>https://hackertube-cn.pages.dev/</link>',
       '<description>从 V2EX 高互动讨论里挖出来的视频与博主清单</description>',
       '<language>zh-cn</language>']
for d in feed_items:
    link = out_link(d)
    desc = (d.get("quote") or {}).get("text") or d.get("summary") or ""
    rss.append("<item>")
    rss.append(f"<title>{xesc(d['name'])}</title>")
    rss.append(f"<link>{xesc(link)}</link>")
    rss.append(f"<guid isPermaLink=\"false\">htcn-{xesc(d['name'])}</guid>")
    if d.get("last_mention"):
        rss.append(f"<pubDate>{formatdate(d['last_mention'])}</pubDate>")
    rss.append(f"<category>{xesc(d.get('category',''))}</category>")
    rss.append(f"<category>{xesc(d.get('platform',''))}</category>")
    rss.append(f"<description>{xesc(desc)}</description>")
    rss.append("</item>")
rss.append("</channel></rss>")
with open(os.path.join(BASE, "site", "feed.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(rss))

data_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
NTOPICS = len(topics)
NFLOORS = sum(len(t["floors"]) for t in topics.values())

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HackerTube CN — V2EX 网友筛选的视频与博主清单</title>
<meta name="description" content="从 V2EX 高互动讨论中提取、经多人认可的视频与博主推荐，只做外链索引，不托管视频。">
<link rel="alternate" type="application/rss+xml" title="HackerTube CN" href="feed.xml">
<script>(function(){try{var t=localStorage.getItem('ht-theme');if(!t)t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='light';}})();</script>
<style>
:root{--bg:#faf7f2;--card:#fff;--ink:#1c1917;--mut:#78716c;--line:#e7e0d6;--acc:#ea580c;--acc2:#fff3e8;--bili:#0aa6c2;--yt:#e03131}
[data-theme="dark"]{--bg:#141518;--card:#1d1f24;--ink:#e9e6e0;--mut:#9d968b;--line:#2e3038;--acc:#f0762b;--acc2:#33231a;--bili:#39bcd6;--yt:#ff6b6b}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.wrap{max-width:1080px;margin:0 auto;padding:28px 16px 60px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
header h1{font-size:30px;margin:0;letter-spacing:.5px}header h1 .cn{color:var(--acc)}
header p{color:var(--mut);margin:8px 0 0;font-size:14px;line-height:1.6}
.hbtns{display:flex;gap:8px;flex:none;padding-top:6px}
.hbtn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:6px 11px;font-size:13px;cursor:pointer}
.hbtn:hover{border-color:var(--acc);color:var(--acc)}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px;font-size:13px;color:var(--mut)}
.stats b{color:var(--ink);font-size:16px}
.controls{position:sticky;top:0;background:var(--bg);padding:14px 0 10px;z-index:5}
.search{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:12px;font-size:15px;background:var(--card);color:var(--ink);outline:none}
.search:focus{border-color:var(--acc)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:5px 12px;border-radius:999px;font-size:13px;cursor:pointer}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.chip .n{opacity:.55;font-size:12px;margin-left:3px}
.tabs{display:flex;gap:4px;background:var(--acc2);padding:3px;border-radius:10px}
.tabs button{border:0;background:transparent;padding:5px 14px;border-radius:8px;font-size:13px;cursor:pointer;color:var(--mut)}
.tabs button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.15)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:8px}
.coverwrap{height:96px;border-radius:10px;overflow:hidden;position:relative;background:var(--acc2);margin:-4px -4px 2px}
.coverblur{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:blur(16px) saturate(1.25);opacity:.5;transform:scale(1.25)}
.coverimg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.head{display:flex;gap:12px;align-items:flex-start}
.avaw{position:relative;width:52px;height:52px;flex:none}
.ava{width:52px;height:52px;border-radius:12px;display:block}
.ava.fb{display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;font-weight:600}
.ava.im{position:absolute;inset:0;object-fit:cover;background:var(--card)}
.head .tt{min-width:0;flex:1}
.card h3{margin:0;font-size:17px;line-height:1.35}
.card h3 a{color:var(--ink);text-decoration:none}.card h3 a:hover{color:var(--acc)}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px}
.b{font-size:11px;padding:2px 8px;border-radius:999px;background:transparent;color:var(--mut);border:1px solid var(--line)}


.quote{font-size:14.5px;line-height:1.65;margin:0;color:var(--ink)}
.ep{font-size:12.5px;line-height:1.6;margin:0;color:var(--mut)}.ep a{color:var(--ink);font-weight:500}
.quote .qby{color:var(--mut);font-size:12px;white-space:nowrap}
.sum{font-size:13px;color:var(--mut);line-height:1.6;margin:0;flex:1}
.foot{font-size:12px;color:var(--mut);border-top:1px dashed var(--line);padding-top:8px;line-height:1.7}
.foot a{color:var(--mut)}
.mks{display:flex;gap:6px;align-items:center}
.mk{font-size:12px;border:0;background:transparent;padding:2px 3px;cursor:pointer;color:var(--mut)}
.mk.on{color:var(--ink);font-weight:600}
.go{font-size:13px;color:var(--ink);text-decoration:none;border:1px solid var(--line);background:transparent;padding:5px 12px;border-radius:8px}
.cardbot{display:flex;justify-content:space-between;align-items:center;gap:8px}
.focused{outline:2px solid var(--acc);outline-offset:-2px}
.rows{margin-top:16px;border-bottom:1px solid var(--line)}
.rrow{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-bottom:0;background:var(--card)}
.rrow .up{flex:none;font-size:13px;color:var(--acc);min-width:34px;text-align:center}
.rrow .av2{width:28px;height:28px;border-radius:8px;flex:none;object-fit:cover}
.rrow .av2fb{width:28px;height:28px;border-radius:8px;flex:none;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;font-weight:600}
.rrow .main{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:14px}
.rrow .main a{color:var(--ink);text-decoration:none;font-weight:600}.rrow .main a:hover{color:var(--acc)}
.rrow .main .q{color:var(--mut);font-weight:400}
.rrow .meta{flex:none;display:flex;gap:6px;align-items:center;font-size:12px;color:var(--mut)}
.empty{text-align:center;color:var(--mut);padding:50px 0;font-size:14px}
footer{margin-top:44px;font-size:12.5px;color:var(--mut);line-height:1.9;border-top:1px solid var(--line);padding-top:16px}
footer .fbtn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:7px;padding:3px 10px;font-size:12px;cursor:pointer;margin-right:6px}
footer a{color:var(--mut)}
.pal-wrap{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;justify-content:center;align-items:flex-start;padding-top:12vh;z-index:50}
.pal{background:var(--card);width:min(560px,92vw);border-radius:12px;border:1px solid var(--line);overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.3)}
.pal input{width:100%;padding:13px 15px;font-size:15px;border:0;outline:none;background:transparent;color:var(--ink)}
.pal .it{padding:9px 15px;font-size:14px;cursor:pointer;display:flex;justify-content:space-between;gap:10px;color:var(--ink)}
.pal .it small{color:var(--mut)}
.pal .it.sel{background:var(--acc2)}
@media (max-width:640px){
header h1{font-size:19px;white-space:nowrap}header p{display:none}
.hbtn{padding:4px 7px;font-size:11px}.hbtns{padding-top:1px;gap:5px}
.stats{gap:6px;font-size:11px;margin-top:7px;flex-wrap:nowrap;white-space:nowrap;overflow:hidden}
.stats b{font-size:13px}
.wrap{padding:14px 12px 48px}
.controls{position:static;padding:10px 0 4px}
.search{padding:9px 12px;font-size:14px}
.controls .row{flex-wrap:nowrap;overflow-x:auto;margin-top:8px;padding-bottom:2px;scrollbar-width:none}
.controls .row::-webkit-scrollbar{display:none}
.chip{flex:none;padding:4px 10px;font-size:12px}
.tabs{flex:none}.tabs button{padding:4px 10px;font-size:12px}
.sortnote{display:none}
.card{padding:13px}.coverwrap{height:84px}
}
</style>
</head>
<body>
<div class="wrap">
<header>
<div>
<h1>HackerTube <span class="cn">CN</span></h1>
<p>从 V2EX 高互动讨论里挖出来的视频与博主清单——每一条都经过多位网友提及或认可。本站只做外链索引，不托管任何视频。</p>
<div class="stats" id="stats"></div>
</div>
<div class="hbtns">
<button class="hbtn" id="palBtn" title="命令面板">⌘K</button>
<button class="hbtn" id="viewBtn" title="切换卡片/列表视图">列表</button>
<button class="hbtn" id="themeBtn" title="切换暗黑/亮色" aria-label="切换暗黑/亮色"></button>
</div>
</header>
<div class="controls">
<input class="search" id="q" type="search" placeholder="搜博主名、关键词…（按 / 快速聚焦）">
<div class="row" id="cats"></div>
<div class="row">
<div class="tabs" id="typeTabs">
<button data-t="all" class="on">全部</button><button data-t="creator">博主</button><button data-t="video" id="videoTab">视频</button>
</div>
<div class="tabs" id="pfTabs">
<button data-p="all" class="on">全平台</button><button data-p="bilibili">B站</button><button data-p="youtube">YouTube</button><button data-p="other">其他</button>
</div>
</div>
<div class="row">
<span style="font-size:13px;color:var(--mut)">排序</span>
<div class="tabs" id="sortTabs">
<button data-s="mentions" class="on">提及次数</button><button data-s="fans">粉丝数</button><button data-s="recent">最近提及</button>
</div>
<span class="sortnote" style="font-size:12px;color:var(--mut)">默认优先级：提及次数 › 粉丝数 › 时间，均为倒序</span>
</div>
<div class="row">
<span style="font-size:13px;color:var(--mut)">标记</span>
<div class="tabs" id="markTabs">
<button data-m="all" class="on">全部</button><button data-m="fav">收藏</button><button data-m="later">稍后再看</button>
</div>
<button class="mk" id="blockedBtn" hidden></button>
</div>
</div>
<div class="grid" id="grid"></div>
<div class="rows" id="rows" hidden></div>
<div class="empty" id="empty" hidden>没有符合条件的条目，换个关键词试试。</div>
<footer>
灵感来源：Andrej Karpathy 的 <a href="https://hackertube.org" target="_blank" rel="noopener">HackerTube</a>（把 Hacker News 评论挖成视频站），本站是它的 V2EX 社区版，数据与口径独立。感谢原作者，也感谢每位在原帖里认真推荐过的网友。<br>
数据来源：V2EX 公开讨论帖（共 __NTOPICS__ 帖、__NFLOORS__ 个楼层），引言为网友原话摘录、均经原文校验；提及次数为粗略统计，仅作排序参考。<br>
收录口径：被多人独立提及或有正面佐证才入选；新闻时政类默认不收录。如需删除或纠正某条，请在 <a href="https://github.com/caikaidev/hackertube-cn" target="_blank" rel="noopener">GitHub 仓库</a> 开 issue，我们核对后处理。<br>
头像与粉丝数来自平台公开信息；主页链接经站方核对后补全，如有错误同样请联系纠正。<br>
数据与订阅：<a href="feed.xml">RSS 订阅</a> · <button class="fbtn" id="expJson">导出 JSON</button><button class="fbtn" id="expCsv">导出 CSV</button> 标记备份：<button class="fbtn" id="expMarks">导出标记</button><button class="fbtn" id="impMarksBtn">导入标记</button><input type="file" id="impMarks" accept=".json" hidden><br>
快捷键：<span class="mono">j</span>/<span class="mono">k</span> 上下移动 · <span class="mono">Enter</span> 打开 · <span class="mono">o</span> 新标签打开 · <span class="mono">/</span> 搜索 · <span class="mono">Cmd/Ctrl+K</span> 命令面板 · <span class="mono">Esc</span> 清除/关闭。收藏、稍后再看、屏蔽只存在你自己的浏览器里，不上传任何服务器。
</footer>
</div>
<div class="pal-wrap" id="palWrap" hidden>
<div class="pal">
<input id="palInput" type="text" placeholder="搜博主、分类，或输入命令…">
<div id="palList"></div>
</div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
var DATA = JSON.parse(document.getElementById('data').textContent);
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return (s == null ? '' : String(s)).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function outLink(d){
  if (d.url) return d.url;
  var kw = encodeURIComponent(d.name);
  if (d.platform === 'bilibili') return 'https://search.bilibili.com/all?keyword=' + kw;
  if (d.platform === 'youtube') return 'https://www.youtube.com/results?search_query=' + kw;
  return 'https://www.bing.com/search?q=' + kw;
}
function pfName(p){ return p === 'bilibili' ? 'B站' : (p === 'youtube' ? 'YouTube' : '其他'); }
function hueFor(s){ var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }
function fansFmt(n){ if (!n && n !== 0) return ''; if (n >= 10000) return (Math.round(n / 1000) / 10) + '万'; return '' + n; }
function fmtDate(ts){ if (!ts) return ''; var d = new Date(ts * 1000); function p(x){ return (x < 10 ? '0' : '') + x; } return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }
function mkey(d){ return d.name + '|' + d.platform; }

var state = { q: '', cat: 'all', type: 'all', pf: 'all', sort: 'mentions', mark: 'all', showBlocked: false };
var view = 'card';
try { view = localStorage.getItem('ht-view') || 'card'; } catch (e) {}
var marks = {};
try { marks = JSON.parse(localStorage.getItem('ht-marks') || '{}') || {}; } catch (e) { marks = {}; }
function saveMarks(){ try { localStorage.setItem('ht-marks', JSON.stringify(marks)); } catch (e) {} }
function getMark(d){ return marks[mkey(d)] || ''; }
function setMark(d, m){ var k = mkey(d); if (m) marks[k] = m; else delete marks[k]; saveMarks(); render(); }

var cats = {}; DATA.forEach(function(d){ cats[d.category] = (cats[d.category] || 0) + 1; });
$('stats').innerHTML = '<span><b class="mono">' + DATA.length + '</b> 条收录</span><span><b class="mono">__NTOPICS__</b> 个来源帖</span><span><b class="mono">__NFLOORS__</b> 个楼层</span>';
var catHtml = '<button class="chip on" data-c="all">全部 <span class="n">' + DATA.length + '</span></button>';
Object.keys(cats).sort(function(a, b){ return cats[b] - cats[a]; }).forEach(function(c){ catHtml += '<button class="chip" data-c="' + esc(c) + '">' + esc(c) + ' <span class="n">' + cats[c] + '</span></button>'; });
$('cats').innerHTML = catHtml;
if (!DATA.some(function(d){ return d.type === 'video'; })) $('videoTab').style.display = 'none';

function sortChain(list){
  var K = { mentions: function(d){ return d.mention_count || 0; }, fans: function(d){ return (d.fans == null ? -1 : d.fans); }, recent: function(d){ return d.last_mention || 0; } };
  var order = ['mentions', 'fans', 'recent']; order.splice(order.indexOf(state.sort), 1); order.unshift(state.sort);
  return list.slice().sort(function(a, b){ for (var i = 0; i < 3; i++) { var d0 = K[order[i]](b) - K[order[i]](a); if (d0) return d0; } return 0; });
}
function currentList(){
  var q = state.q.trim().toLowerCase();
  var list = DATA.filter(function(d){
    var mk = getMark(d);
    if (mk === 'blocked' && !state.showBlocked) return false;
    if (state.mark !== 'all' && mk !== state.mark) return false;
    if (state.cat !== 'all' && d.category !== state.cat) return false;
    if (state.type !== 'all' && d.type !== state.type) return false;
    if (state.pf !== 'all' && d.platform !== state.pf) return false;
    if (q && (d.name + ' ' + d.category + ' ' + ((d.quote || {}).text || '')).toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  return sortChain(list);
}
var lastList = [], focusIdx = -1;

function badges(d){
  var h = '<span class="b pf' + (d.platform === 'youtube' ? ' yt' : '') + '">' + pfName(d.platform) + '</span><span class="b">' + esc(d.category) + '</span>';
  if (d.fans != null) h += '<span class="b mono">' + fansFmt(d.fans) + ' 粉丝</span>';
  if (d.is_promotion) h += '<span class="b">自荐</span>';
  return h;
}
function markBtns(d){
  var mk = getMark(d);
  function b(act, label){ return '<button class="mk' + (mk === act ? ' on' : '') + '" data-act="' + act + '">' + label + '</button>'; }
  return '<div class="mks">' + b('fav', '收藏') + b('later', '稍后') + b('blocked', '屏蔽') + '</div>';
}
function quoteHtml(d){
  if (d.quote && d.quote.text) return '<p class="quote">“' + esc(d.quote.text) + '”' + (d.quote.by ? ' <span class="qby">—— 网友 @' + esc(d.quote.by) + '</span>' : '') + '</p>';
  return '';
}
function episodeHtml(d){
  if (d.episode && d.episode.url) return '<p class="ep">网友提到的单集：<a href="' + esc(d.episode.url) + '" target="_blank" rel="noopener">《' + esc(d.episode.title || '视频') + '》</a> ↗</p>';
  return '';
}
function footHtml(d){
  var src = (d.source_topics && d.source_topics[0]) || null;
  var h = '被提及 <span class="mono">' + d.mention_count + '</span> 次';
  if (d.first_mention) h += ' · 首提 <span class="mono">' + fmtDate(d.first_mention) + '</span>';
  if (src) h += ' · 来源：<a href="' + esc(src.url) + '" target="_blank" rel="noopener">' + esc(src.title) + '</a>' + (src.by ? '（首提 @' + esc(src.by) + '）' : '');
  return h;
}
function cardHTML(d){
  var link = outLink(d), direct = !!d.url, hue = hueFor(d.category + d.name);
  var avaFb = '<div class="ava fb" style="background:linear-gradient(135deg,hsl(' + hue + ',55%,55%),hsl(' + ((hue + 40) % 360) + ',55%,42%))">' + esc(d.name.slice(0, 1)) + '</div>';
  var ava = avaFb + (d.avatar ? '<img class="ava im" src="' + esc(d.avatar) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : '');
  var cover = d.cover ? '<div class="coverwrap"><img class="coverimg" src="' + esc(d.cover) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()"></div>' : '';
  return '<div class="card">' + cover
    + '<div class="head"><div class="avaw">' + ava + '</div><div class="tt"><h3><a href="' + esc(link) + '" target="_blank" rel="noopener">' + esc(d.name) + '</a></h3><div class="badges">' + badges(d) + '</div></div></div>'
    + quoteHtml(d)
    + episodeHtml(d)
    + '<div class="foot">' + footHtml(d) + '</div>'
    + '<div class="cardbot">' + markBtns(d) + '<a class="go" href="' + esc(link) + '" target="_blank" rel="noopener">' + (direct ? '直达主页 ↗' : '去平台搜 ↗') + '</a></div></div>';
}
function rowHTML(d){
  var link = outLink(d), hue = hueFor(d.category + d.name);
  var av = d.avatar ? '<img class="av2" src="' + esc(d.avatar) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML=\'<div class=&quot;av2fb&quot; style=&quot;background:hsl(' + hue + ',55%,50%)&quot;>' + esc(d.name.slice(0, 1)) + '</div>\'">'
    : '<div class="av2fb" style="background:hsl(' + hue + ',55%,50%)">' + esc(d.name.slice(0, 1)) + '</div>';
  var q = (d.quote && d.quote.text) ? ' <span class="q">“' + esc(d.quote.text) + '”</span>' : '';
  return '<div class="rrow"><span class="up mono">▲' + d.mention_count + '</span>' + av
    + '<div class="main"><a href="' + esc(link) + '" target="_blank" rel="noopener">' + esc(d.name) + '</a>' + q + '</div>'
    + '<div class="meta"><span>' + pfName(d.platform) + '</span><span>' + esc(d.category) + '</span>'
    + (d.fans != null ? '<span class="mono">' + fansFmt(d.fans) + ' 粉</span>' : '') + markBtns(d) + '</div></div>';
}
var nodeCache = {};
function cachedNode(kind, d, html){
  var k = kind + ':' + mkey(d);
  var n = nodeCache[k];
  if (!n) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    n = t.content.firstChild;
    nodeCache[k] = n;
  }
  var mk = getMark(d);
  var btns = n.querySelectorAll('.mk');
  for (var i = 0; i < btns.length; i++) btns[i].classList.toggle('on', btns[i].dataset.act === mk);
  return n;
}
function render(){
  lastList = currentList(); focusIdx = -1;
  var blockedN = DATA.filter(function(d){ return getMark(d) === 'blocked'; }).length;
  var bb = $('blockedBtn');
  if (blockedN) { bb.hidden = false; bb.textContent = state.showBlocked ? '隐藏屏蔽（' + blockedN + '）' : '已屏蔽 ' + blockedN + ' 条 · 显示'; } else bb.hidden = true;
  if (view === 'list') {
    $('grid').hidden = true; $('rows').hidden = false;
    $('rows').replaceChildren.apply($('rows'), lastList.map(function(d){ return cachedNode('r', d, rowHTML(d)); }));
  } else {
    $('rows').hidden = true; $('grid').hidden = false;
    $('grid').replaceChildren.apply($('grid'), lastList.map(function(d){ return cachedNode('c', d, cardHTML(d)); }));
  }
  $('empty').hidden = lastList.length > 0;
  $('viewBtn').textContent = view === 'list' ? '卡片' : '列表';
}
function bindTabs(id, attr, key){
  $(id).addEventListener('click', function(e){
    var b = e.target.closest('button'); if (!b) return;
    state[key] = b.dataset[attr];
    var bs = $(id).querySelectorAll('button'); for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('on', bs[i] === b);
    render();
  });
}
$('cats').addEventListener('click', function(e){ var b = e.target.closest('button'); if (!b) return; state.cat = b.dataset.c;
  var bs = $('cats').querySelectorAll('button'); for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('on', bs[i] === b); render(); });
bindTabs('typeTabs', 't', 'type'); bindTabs('pfTabs', 'p', 'pf'); bindTabs('sortTabs', 's', 'sort'); bindTabs('markTabs', 'm', 'mark');
$('q').addEventListener('input', function(e){ state.q = e.target.value; render(); });
$('blockedBtn').addEventListener('click', function(){ state.showBlocked = !state.showBlocked; render(); });
function onMarks(e){
  var b = e.target.closest('.mk'); if (!b || !b.dataset.act) return;
  var host = b.closest('.card') || b.closest('.rrow'); if (!host) return;
  var idx = Array.prototype.indexOf.call(host.parentNode.children, host);
  var d = lastList[idx]; if (!d) return;
  var act = b.dataset.act;
  setMark(d, getMark(d) === act ? '' : act);
}
$('grid').addEventListener('click', onMarks); $('rows').addEventListener('click', onMarks);

var ICON_MOON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
var ICON_SUN = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="display:block"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
function themeUI(t){ document.documentElement.dataset.theme = t; $('themeBtn').innerHTML = t === 'dark' ? ICON_SUN : ICON_MOON; }
function applyTheme(t){
  themeUI(t);
  try { localStorage.setItem('ht-theme', t); } catch (e) {}
}
$('themeBtn').addEventListener('click', function(){ applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); });
themeUI(document.documentElement.dataset.theme || 'light');
try { window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(){ var saved = null; try { saved = localStorage.getItem('ht-theme'); } catch (e) {} if (!saved) themeUI(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); }); } catch (e) {}
function applyView(v){ view = v; try { localStorage.setItem('ht-view', v); } catch (e) {} render(); }
$('viewBtn').addEventListener('click', function(){ applyView(view === 'list' ? 'card' : 'list'); });

function download(name, text, type){
  var a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: type || 'text/plain;charset=utf-8' }));
  a.download = name; a.click(); setTimeout(function(){ URL.revokeObjectURL(a.href); }, 2000);
}
function csvCell(s){ s = (s == null ? '' : String(s)); return '"' + s.replace(/"/g, '""') + '"'; }
$('expJson').addEventListener('click', function(){ download('hackertube-cn-data.json', JSON.stringify(DATA, null, 1), 'application/json'); });
$('expCsv').addEventListener('click', function(){
  var lines = ['name,platform,category,fans,mention_count,url,quote,summary'];
  DATA.forEach(function(d){ lines.push([d.name, d.platform, d.category, d.fans == null ? '' : d.fans, d.mention_count, d.url || '', (d.quote || {}).text || '', d.summary || ''].map(csvCell).join(',')); });
  download('hackertube-cn-data.csv', lines.join('\n'), 'text/csv');
});
$('expMarks').addEventListener('click', function(){ download('hackertube-cn-marks.json', JSON.stringify(marks, null, 1), 'application/json'); });
$('impMarksBtn').addEventListener('click', function(){ $('impMarks').click(); });
$('impMarks').addEventListener('change', function(e){
  var f = e.target.files[0]; if (!f) return;
  var r = new FileReader();
  r.onload = function(){ try { var o = JSON.parse(r.result); if (o && typeof o === 'object') { marks = o; saveMarks(); render(); alert('标记已导入'); } } catch (err) { alert('导入失败：不是有效的标记文件'); } };
  r.readAsText(f); e.target.value = '';
});

/* keyboard-first */
function focusables(){ return view === 'list' ? $('rows').children : $('grid').children; }
function setFocus(i){
  var els = focusables(); if (!els.length) return;
  focusIdx = Math.max(0, Math.min(i, els.length - 1));
  for (var j = 0; j < els.length; j++) els[j].classList.toggle('focused', j === focusIdx);
  els[focusIdx].scrollIntoView({ block: 'nearest' });
}
document.addEventListener('keydown', function(e){
  if (!$('palWrap').hidden) return;
  var tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea') {
    if (e.key === 'Escape') { e.target.value = ''; if (e.target.id === 'q') { state.q = ''; render(); } e.target.blur(); }
    return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPal(); return; }
  if (e.key === 'j') { setFocus(focusIdx + 1); }
  else if (e.key === 'k') { setFocus(focusIdx - 1); }
  else if (e.key === 'Enter') { if (focusIdx >= 0 && lastList[focusIdx]) location.href = outLink(lastList[focusIdx]); }
  else if (e.key === 'o') { if (focusIdx >= 0 && lastList[focusIdx]) window.open(outLink(lastList[focusIdx]), '_blank'); }
  else if (e.key === '/') { e.preventDefault(); $('q').focus(); }
  else if (e.key === 'Escape') { if (state.q) { state.q = ''; $('q').value = ''; render(); } }
});

/* command palette */
var palItems = [], palIdx = 0;
function palActions(){
  var acts = [
    { label: '切换暗黑/亮色', hint: '命令', run: function(){ $('themeBtn').click(); } },
    { label: '切换卡片/列表视图', hint: '命令', run: function(){ $('viewBtn').click(); } },
    { label: '导出数据 JSON', hint: '命令', run: function(){ $('expJson').click(); } },
    { label: '导出数据 CSV', hint: '命令', run: function(){ $('expCsv').click(); } }
  ];
  Object.keys(cats).forEach(function(c){ acts.push({ label: '只看分类：' + c, hint: '分类 · ' + cats[c] + ' 条', run: function(){ state.cat = c;
    var bs = $('cats').querySelectorAll('button'); for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('on', bs[i].dataset.c === c); render(); } }); });
  return acts;
}
function openPal(){ $('palWrap').hidden = false; $('palInput').value = ''; palRender(''); setTimeout(function(){ $('palInput').focus(); }, 10); }
function closePal(){ $('palWrap').hidden = true; }
function palRender(q){
  q = (q || '').trim().toLowerCase();
  var res = [];
  DATA.forEach(function(d){ if (!q || (d.name + ' ' + d.category + ' ' + (d.summary || '')).toLowerCase().indexOf(q) >= 0) res.push({ label: d.name, hint: pfName(d.platform) + ' · ' + d.category + ' · 提及 ' + d.mention_count, run: function(){ window.open(outLink(d), '_blank'); } }); });
  palActions().forEach(function(a){ if (!q || a.label.toLowerCase().indexOf(q) >= 0) res.push(a); });
  palItems = res.slice(0, 9); palIdx = 0;
  $('palList').innerHTML = palItems.map(function(it, i){ return '<div class="it' + (i === palIdx ? ' sel' : '') + '" data-i="' + i + '"><span>' + esc(it.label) + '</span><small>' + esc(it.hint || '') + '</small></div>'; }).join('') || '<div class="it"><span>没有匹配项</span></div>';
}
$('palBtn').addEventListener('click', openPal);
$('palInput').addEventListener('input', function(e){ palRender(e.target.value); });
$('palInput').addEventListener('keydown', function(e){
  if (e.key === 'ArrowDown') { e.preventDefault(); palIdx = Math.min(palIdx + 1, palItems.length - 1); palRender($('palInput').value); palIdx = Math.min(palIdx, palItems.length - 1);
    var els = $('palList').children; for (var i = 0; i < els.length; i++) els[i].classList.toggle('sel', i === palIdx); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); palIdx = Math.max(palIdx - 1, 0);
    var els2 = $('palList').children; for (var j = 0; j < els2.length; j++) els2[j].classList.toggle('sel', j === palIdx); }
  else if (e.key === 'Enter') { var it = palItems[palIdx]; if (it) { closePal(); it.run(); } }
  else if (e.key === 'Escape') { closePal(); }
});
$('palList').addEventListener('click', function(e){ var el = e.target.closest('.it'); if (!el) return; var it = palItems[+el.dataset.i]; if (it) { closePal(); it.run(); } });
$('palWrap').addEventListener('click', function(e){ if (e.target === $('palWrap')) closePal(); });

render();
</script>
</body>
</html>
"""

html = HTML.replace("__DATA__", data_json).replace("__NTOPICS__", str(NTOPICS)).replace("__NFLOORS__", format(NFLOORS, ","))
with open(os.path.join(BASE, "site", "index.html"), "w", encoding="utf-8") as f:
    f.write(html)
with open(os.path.join(BASE, "site", "data.json"), "w", encoding="utf-8") as f:
    f.write(data_json)
nq = sum(1 for i in items if i.get("quote"))
nc = sum(1 for i in items if i.get("cover"))
print(f"built site/index.html ({len(html)} bytes), site/data.json, site/feed.xml | quotes {nq}/{len(items)} covers {nc}/{len(items)}")
