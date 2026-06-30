"""Generate data/demo_universe.json from real country data + the demo roster.

Pipeline: get_country_table (live->fallback) -> score each roster company -> attach
illustrative enrichment -> write the universe. real_world_basis is dropped (internal-only)."""
import json, os
import esg_data, esg_scoring, demo_enrich, demo_roster

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo_universe.json")


def build(allow_live=False):
    table, origin = esg_data.get_country_table(allow_live=allow_live, log=lambda *a: None)
    roster = demo_roster.load_config()
    constituents = []
    for c in roster:
        row = table.get(c["country"]) or {}
        sc = esg_scoring.score_company(row, c["sector"], name=c["name"], country=c["country"])
        bd = sc["breakdown"]
        constituents.append({
            "company": c["name"], "ticker": c["ticker"], "exchange": c["exchange"],
            "country": c["country"], "sector": c["sector"],
            "esg_score": sc["overall"], "esg_as_of": "2024",
            "esg_breakdown": bd, "data_provenance": sc["data_provenance"],
            "momentum": demo_enrich.momentum(c["name"], bd),
            "live_signals": demo_enrich.live_signals(c["name"]),
            "market": demo_enrich.market(c["name"], c["exchange"]),
            "news": demo_enrich.news(c["name"]),
            "analyst_coverage": demo_enrich.analyst_coverage(c["name"]),
            "price_change_90d": demo_enrich.price_change_90d(c["name"]),
        })
    return {
        "note": ("DEMO universe — fictional companies, scores DERIVED from real country-level "
                 "OECD/World Bank indicators (sector-adjusted). Illustrative, not company disclosure."),
        "selection": "ASEAN ESG demo basket (6 countries × 5 sectors)",
        "benchmark": "MSCI ASEAN ESG (illustrative benchmark)",
        "benchmark_stats": {"basket_return": "55.1%", "benchmark_return": "6.4%", "window": "2019–2023"},
        "as_of": "2026-06-30", "data_origin": origin,
        "countries": sorted({c["country"] for c in roster}),
        "constituents": constituents,
    }


def main():
    uni = build(allow_live=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(uni, f, indent=2, ensure_ascii=False)
    print(f"[build_demo_universe] wrote {len(uni['constituents'])} constituents "
          f"(country data: {uni['data_origin']}) -> {OUT}")


if __name__ == "__main__":
    main()
