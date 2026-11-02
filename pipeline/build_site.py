#!/usr/bin/env python3
"""Build self-contained static index.html from data.json (+ parsed topics for provenance)."""
import json, os, glob

BASE = os.path.join(os.path.dirname(__file__), "..")
items = json.load(open(os.path.join(BASE, "data", "data.json"), encoding="utf-8"))
topics = {}
for p in glob.glob(os.path.join(BASE, "data", "parsed", "topic_*.json")):
    t = json.load(open(p, encoding="utf-8"))
    topics[t["topic_id"]] = t

for it in items:
    srcs = []
    for s in it["sources"]:
        t = topics.get(s["topic_id"])
        if not t:
            continue
        first_user = ""
        fl = sorted(s["floors"] or [])
        if fl:
            by_floor = {f["floor"]: f for f in t["floors"]}
            if fl[0] in by_floor:
                first_user = by_floor[fl[0]]["username"]
        srcs.append({"title": t["title"], "url": t["url"], "by": first_user})
    it["source_topics"] = srcs
    it.pop("sources", None)

data_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HackerTube CN — V2EX 网友筛选的视频与博主清单</title>
<meta name="description" content="从 V2EX 高互动讨论中提取、经多人认可的视频与博主推荐，只做外链索引，不托管视频。">
<style>
:root{--bg:#faf7f2;--card:#fff;--ink:#1c1917;--mut:#78716c;--line:#e7e0d6;--acc:#ea580c;--acc2:#fff3e8;--bili:#0aa6c2;--yt:#e03131}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 16px 60px}
header h1{font-size:30px;margin:0;letter-spacing:.5px}header h1 .cn{color:var(--acc)}
header p{color:var(--mut);margin:8px 0 0;font-size:14px;line-height:1.6}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px;font-size:13px;color:var(--mut)}
.stats b{color:var(--ink);font-size:16px}
.controls{position:sticky;top:0;background:var(--bg);padding:14px 0 10px;z-index:5}
.search{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:12px;font-size:15px;background:#fff;outline:none}
.search:focus{border-color:var(--acc)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{border:1px solid var(--line);background:#fff;color:var(--ink);padding:5px 12px;border-radius:999px;font-size:13px;cursor:pointer}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.chip .n{opacity:.55;font-size:12px;margin-left:3px}
.tabs{display:flex;gap:4px;background:#efe9df;padding:3px;border-radius:10px}
.tabs button{border:0;background:transparent;padding:5px 14px;border-radius:8px;font-size:13px;cursor:pointer;color:var(--mut)}
.tabs button.on{background:#fff;color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.08)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:8px}
.head{display:flex;gap:12px;align-items:flex-start}
.avaw{position:relative;width:52px;height:52px;flex:none}
.ava{width:52px;height:52px;border-radius:12px;display:block}
.ava.fb{display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;font-weight:600}
.ava.im{position:absolute;inset:0;object-fit:cover;background:#fff}
.head .tt{min-width:0;flex:1}
.card h3{margin:0;font-size:17px;line-height:1.35}
.card h3 a{color:var(--ink);text-decoration:none}.card h3 a:hover{color:var(--acc)}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.b{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--acc2);color:var(--acc);border:1px solid #f3ddc9}
.b.pf{background:#eef7fa;color:var(--bili);border-color:#d3ecf2}.b.pf.yt{background:#fdeeee;color:var(--yt);border-color:#f6dede}
.b.promo{background:#fff7db;color:#94700a;border-color:#efe3ae}
.sum{font-size:13.5px;color:#44403c;line-height:1.65;margin:0;flex:1}
.foot{font-size:12px;color:var(--mut);border-top:1px dashed var(--line);padding-top:8px;line-height:1.7}
.foot a{color:var(--mut)}
.go{align-self:flex-start;font-size:13px;color:var(--acc);text-decoration:none;border:1px solid #f3ddc9;background:var(--acc2);padding:5px 12px;border-radius:8px}
.empty{text-align:center;color:var(--mut);padding:50px 0;font-size:14px}
footer{margin-top:44px;font-size:12.5px;color:var(--mut);line-height:1.8;border-top:1px solid var(--line);padding-top:16px}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>HackerTube <span class="cn">CN</span></h1>
<p>从 V2EX 高互动讨论里挖出来的视频与博主清单——每一条都经过多位网友提及或认可。本站只做外链索引，不托管任何视频。</p>
<div class="stats" id="stats"></div>
</header>
<div class="controls">
<input class="search" id="q" type="search" placeholder="搜博主名、关键词…">
<div class="row" id="cats"></div>
<div class="row">
<div class="tabs" id="typeTabs">
<button data-t="all" class="on">全部</button><button data-t="creator">博主</button><button data-t="video">视频</button>
</div>
<div class="tabs" id="pfTabs">
<button data-p="all" class="on">全平台</button><button data-p="bilibili">B站</button><button data-p="youtube">YouTube</button><button data-p="other">其他</button>
</div>
</div>
</div>
<div class="grid" id="grid"></div>
<div class="empty" id="empty" hidden>没有符合条件的条目，换个关键词试试。</div>
<footer>
数据来源：V2EX 公开讨论帖（共 8 帖、1,049 个楼层），摘要为机器整理、经原文校验；提及次数为粗略统计，仅作排序参考。<br>
收录口径：被多人独立提及或有正面佐证才入选；新闻时政类默认不收录。如需删除或纠正某条，请通过原帖联系我们核对后处理。<br>
头像与粉丝数来自平台公开信息；标有「同名核对补全」的主页链接，是站方按平台同名账号精确核对后补上的，如有错误同样请联系纠正。
</footer>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const state = {q:'', cat:'全部', type:'all', pf:'all'};
const PFNAME = {bilibili:'B站', youtube:'YouTube', other:'其他平台'};
const cats = ['全部', ...new Set(DATA.map(d=>d.category))];
document.getElementById('stats').innerHTML =
 '<span><b>'+DATA.length+'</b> 条收录</span><span><b>'+DATA.filter(d=>d.type!=='video').length+'</b> 位博主</span><span><b>'+DATA.filter(d=>d.url).length+'</b> 条带直达链接</span><span>来源 <b>8</b> 个 V2EX 讨论帖</span>';
const catsEl = document.getElementById('cats');
cats.forEach(c=>{
  const n = c==='全部'?DATA.length:DATA.filter(d=>d.category===c).length;
  const b=document.createElement('button'); b.className='chip'+(c==='全部'?' on':'');
  b.innerHTML=c+'<span class="n">'+n+'</span>';
  b.onclick=()=>{state.cat=c; [...catsEl.children].forEach(x=>x.classList.remove('on')); b.classList.add('on'); render();};
  catsEl.appendChild(b);
});
function tabWire(id, key, attr){
  const el=document.getElementById(id);
  el.addEventListener('click',e=>{
    const btn=e.target.closest('button'); if(!btn) return;
    state[key]=btn.dataset[attr];
    [...el.children].forEach(x=>x.classList.remove('on')); btn.classList.add('on'); render();
  });
}
tabWire('typeTabs','type','t'); tabWire('pfTabs','pf','p');
document.getElementById('q').addEventListener('input',e=>{state.q=e.target.value.trim().toLowerCase(); render();});
function outLink(d){
  if(d.url) return d.url;
  const kw=encodeURIComponent(d.name);
  if(d.platform==='bilibili') return 'https://search.bilibili.com/all?keyword='+kw;
  if(d.platform==='youtube') return 'https://www.youtube.com/results?search_query='+kw;
  return 'https://www.bing.com/search?q='+kw;
}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function hue(s){let h=0;for(const c of (s||''))h=(h*31+c.charCodeAt(0))%360;return h}
function fansFmt(n){if(n>=10000){const v=n/10000;return (v>=100?Math.round(v):v.toFixed(1).replace(/\.0$/,''))+'万'}return ''+n}
function render(){
  const list = DATA.filter(d=>
    (state.cat==='全部'||d.category===state.cat)&&
    (state.type==='all'||d.type===state.type)&&
    (state.pf==='all'||d.platform===state.pf)&&
    (!state.q||(d.name+' '+d.summary+' '+d.category).toLowerCase().includes(state.q)));
  const grid=document.getElementById('grid');
  document.getElementById('empty').hidden=list.length>0;
  grid.innerHTML=list.map(d=>{
    const src=(d.source_topics||[]).map(s=>'<a href="'+esc(s.url)+'" target="_blank" rel="noopener">《'+esc(s.title)+'》</a>'+(s.by?' · 首提 @'+esc(s.by):'')).join('；');
    const h=hue(d.category);
    const fb='<div class="ava fb" style="background:linear-gradient(135deg,hsl('+h+' 55% 55%),hsl('+((h+40)%360)+' 55% 42%))">'+esc((d.name||'').trim().charAt(0))+'</div>';
    const ava='<div class="avaw">'+fb+(d.avatar?'<img class="ava im" src="'+esc(d.avatar)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">':'')+'</div>';
    return '<div class="card"><div class="head">'+ava+'<div class="tt"><h3><a href="'+esc(outLink(d))+'" target="_blank" rel="noopener">'+esc(d.name)+'</a></h3>'+
    '<div class="badges"><span class="b pf'+(d.platform==='youtube'?' yt':'')+'">'+PFNAME[d.platform]+'</span><span class="b">'+esc(d.category)+'</span>'+
    (d.fans?'<span class="b">'+fansFmt(d.fans)+' 粉丝</span>':'')+
    (d.resolved_via==='bili_search_exact'?'<span class="b">主页·同名核对补全</span>':'')+
    (d.self_promo?'<span class="b promo">自荐</span>':'')+'</div></div></div>'+
    '<p class="sum">'+esc(d.summary||'')+'</p>'+
    '<a class="go" href="'+esc(outLink(d))+'" target="_blank" rel="noopener">'+(d.url?'直达主页/视频':'去'+PFNAME[d.platform]+'搜索')+' ↗</a>'+
    '<div class="foot">被提及 '+d.mention_count+' 次 · 来源 V2EX：'+src+'</div></div>';
  }).join('');
}
render();
</script>
</body>
</html>
"""
html = HTML.replace("__DATA__", data_json)
out = os.path.join(BASE, "site", "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
with open(os.path.join(BASE, "site", "data.json"), "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=1)
print("built", out, len(html), "bytes,", len(items), "items")
