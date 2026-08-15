"""Load + validate the demo company roster (data/demo_config.json)."""
import json, os
import esg_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "demo_config.json")
_REQUIRED = ("name", "country", "sector", "real_world_basis", "ticker", "exchange")


def load_config(path=CONFIG):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    companies = raw.get("companies") if isinstance(raw, dict) else raw
    if not isinstance(companies, list) or not companies:
        raise ValueError("demo_config: 'companies' must be a non-empty list")
    valid_countries = set(esg_data.COUNTRIES.values())
    seen = set()
    for c in companies:
        missing = [k for k in _REQUIRED if k not in c]
        if missing:
            raise ValueError(f"demo_config: {c.get('name','?')} missing {missing}")
        if c["country"] not in valid_countries:
            raise ValueError(f"demo_config: unknown country {c['country']}")
        if c["ticker"] in seen:
            raise ValueError(f"demo_config: duplicate ticker {c['ticker']}")
        seen.add(c["ticker"])
    return companies
