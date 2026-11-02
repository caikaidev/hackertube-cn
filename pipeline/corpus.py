"""Unified corpus layer.

Every data source (see pipeline/sources/) produces topics in ONE schema:

    {
      "source": "v2ex",            # adapter name
      "topic_id": 893469,          # id within that source
      "title": "...", "url": "https://...", "op": "username",
      "content": "topic body text",
      "reply_count": 123,
      "floors": [
        {"floor": 1, "username": "...", "content": "...",
         "content_rendered": "...", "created": 1660000000,
         "parent_floor": 0, "links": [{"kind": "...", "url": "..."}]}
      ]
    }

Stored as data/parsed/topic_<id>.json today; the loader keys topics by
(source, topic_id) so two sources may reuse numeric ids without collision.
All consumers (extraction, site build, episode matching) read topics ONLY
through load_topics() — never by globbing files themselves. Legacy files
without a "source" field default to DEFAULT_SOURCE.
"""
import glob
import json
import os

BASE = os.path.join(os.path.dirname(__file__), "..")
PARSED = os.path.join(BASE, "data", "parsed")
DEFAULT_SOURCE = "v2ex"


def topic_key(source, topic_id):
    return (source or DEFAULT_SOURCE, topic_id)


def source_of(ref):
    """Source name of an entry-source ref or topic dict (legacy -> default)."""
    return (ref or {}).get("source") or DEFAULT_SOURCE


def load_topics():
    """Return {(source, topic_id): topic dict} for every parsed topic."""
    topics = {}
    for path in sorted(glob.glob(os.path.join(PARSED, "topic_*.json"))):
        t = json.load(open(path, encoding="utf-8"))
        t.setdefault("source", DEFAULT_SOURCE)
        topics[topic_key(t["source"], t["topic_id"])] = t
    return topics
