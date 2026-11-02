"""Source registry. Add a new data source by implementing the contract in
base.py and registering its adapter here."""
from sources.v2ex import V2exAdapter

SOURCES = {
    "v2ex": V2exAdapter(),
}


def get_source(name):
    if name not in SOURCES:
        raise SystemExit(f"unknown source {name!r}; available: {', '.join(sorted(SOURCES))}")
    return SOURCES[name]
