"""Data-source adapter contract.

To add a new source (Hacker News, RSS, a forum, ...):

1. Create pipeline/sources/<name>.py with a class implementing:
     name: str                       # short id, e.g. "v2ex"
     discover(queries) -> list[dict] # candidate topic refs {"topic_id": ...}
     fetch(topic_id) -> dict         # ONE topic in the unified corpus schema
                                     # (see pipeline/corpus.py), with
                                     # "source" set to this adapter's name
2. Register it in pipeline/sources/__init__.py SOURCES.
3. Run the fetch CLI for the new source, then extraction + build as usual.
   Extraction, enrichment (avatars / fans / episodes) and the site build are
   source-agnostic: they read only the unified corpus via corpus.load_topics()
   and entry sources keyed by (source, topic_id).

Rules every adapter must honor:
- Floors are 1-based, in posting order; floor 0 / parent_floor 0 = topic body.
- `created` is a Unix timestamp (seconds).
- Reply structure goes in parent_floor; how it is derived is the adapter's
  own business (V2EX uses the #N > @user > "X楼" edge rules).
- fetch() must be idempotent and cache-friendly (skip work already on disk).
"""


class SourceAdapter:
    name = ""

    def discover(self, queries):
        raise NotImplementedError

    def fetch(self, topic_id):
        raise NotImplementedError
