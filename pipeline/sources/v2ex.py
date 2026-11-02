"""V2EX adapter.

discover(): SOV2EX full-text search (sort=created desc). Caveats learned
2026-11-02: `size` max is 50 (100 -> HTTP 400), page with `from`; the
reply counts SOV2EX returns are badly stale for new topics, so every
candidate's reply_count/date is re-verified against the official API.

fetch(): orchestrates the existing V2EX tooling — fetch_topics.py (official
API -> data/raw) then parse_floors.py (raw -> unified corpus in
data/parsed, applying the #N > @user > "X楼" reply-edge rules) — and
returns the parsed topic via the corpus loader.
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from corpus import load_topics, topic_key  # noqa: E402
from sources.base import SourceAdapter  # noqa: E402

PIPE = os.path.join(os.path.dirname(__file__), "..")
UA = {"User-Agent": "Mozilla/5.0 (HackerTubeCN research)"}


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


class V2exAdapter(SourceAdapter):
    name = "v2ex"

    def discover(self, queries, min_replies=25, limit_per_query=50):
        seen = {}
        for q in queries:
            url = ("https://www.sov2ex.com/api/search?q=" + urllib.parse.quote(q)
                   + f"&size={min(limit_per_query, 50)}&sort=created&order=1&from=0")
            try:
                hits = _get_json(url).get("hits", [])
            except Exception as e:
                print(f"discover {q!r}: {e}", file=sys.stderr)
                continue
            for h in hits:
                tid = h.get("_source", {}).get("id") or h.get("_id")
                if tid and int(tid) not in seen:
                    seen[int(tid)] = {"topic_id": int(tid)}
        out = []
        for ref in seen.values():
            t = _get_json(f"https://www.v2ex.com/api/topics/show.json?id={ref['topic_id']}")
            if t and t[0].get("replies", 0) >= min_replies:
                ref["replies"] = t[0]["replies"]
                ref["title"] = t[0].get("title", "")
                out.append(ref)
        return out

    def fetch(self, topic_id):
        subprocess.run([sys.executable, os.path.join(PIPE, "fetch_topics.py"),
                        str(topic_id)], check=True)
        subprocess.run([sys.executable, os.path.join(PIPE, "parse_floors.py")],
                       check=True)
        topics = load_topics()
        return topics[topic_key(self.name, topic_id)]
