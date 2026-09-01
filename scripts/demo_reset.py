"""Put the running app into a known state for a recording take.

Retakes are the whole reason this exists. A screen recording is shot several times, and every
take has to start from the same board — same pinned names, same focused company, and above all
a Stage-2 answer already computed, because a cold Compete takes forty to seventy seconds and
that is death on camera.

    python server.py &                       # in a shell that has DEEPSEEK_API_KEY
    python -m scripts.demo_reset             # prep the demo universe
    python -m scripts.demo_reset --no-warm   # skip the billable Stage-2 calls

It prints a one-line localStorage blob to paste into the browser console, because the UI half of
the state (level, theme, filters, whether setup has run) lives in the browser and nothing on the
server can set it.

On the HTTP here: this is a developer tool driving our OWN api on localhost, not the app
fetching external context, so it is outside what HARD RULE 1 isolates in core.http_get — and it
needs POST, which core.http_get does not do. It never contacts an external host.
"""
import argparse
import json
import sys
import time

import requests

BASE = "http://localhost:8000"

# The two names the script is built around: the strongest disagreement in each direction. Pearl
# Savings rides along as the opening focus because it is the friendliest first read on the board.
HERO = "KLSE:KLCT"          # KLCC Towers — Hidden Winner, rated bottom 9%, strongest momentum
FOIL = "HOSE:RRRE"          # Red River Renewables — Overrated Leader, rated top 11%, falling
OPENER = "PSE:PRLS"         # Pearl Savings — the level-1 focus
# Present mode's demo subject (web/src/components/present/tour.ts). Chosen over the HERO because
# its evidence CONTESTS itself — one emissions signal points down — and "we show you the one
# that disagrees" is a claim the walkthrough stops on and points at.
TOUR = "IDX:SATB"           # SatBank — Hidden Winner, 11 signals, dissenting emissions signal

# What the browser should hold when recording starts.
# The RECORDING state. Every UI flag is spelled out, including the ones that default the other
# way, because anything omitted here falls back to the app's DEFAULTS — and the defaults are
# written for a first-time visitor, not for take three. `tourDone` is the one that bit: leaving it
# out armed the first-run tutorial, so a coach-mark overlay could appear mid-take on the exact
# screen this script exists to make identical.
UI_STATE = {
    "demo": True, "dark": True, "simplified": True, "level": 1, "setupDone": True,
    "tourDone": True, "tourDeck": "",
    "extras": [], "focus": "",
    "profile": {"mandate": "risk", "goal": "screen",
                "label": "protect the downside across ASEAN"},
    "filters": {"country": "All", "sector": "All"},
    "leftOpen": False, "rightOpen": False, "ragEnabled": True, "ragTopK": 5,
    "tier": "balanced", "horizon": "long", "pipelineOnly": False,
    # The PPP lens and which argument the matrix is making. Spelled out for the same reason
    # everything else here is: an omitted key falls back to the app's default, and a take that
    # opens on a different plot from the last one is a take that has to be re-shot.
    "ppp": "balanced", "greenFocus": False,
}

# The FIRST-RUN state: what a judge handed the laptop should meet. Setup has not run and the
# tutorial has not been seen, so the app opens on its one question and walks the board afterwards.
FIRST_RUN_STATE = {
    "demo": True, "dark": True, "setupDone": False, "tourDone": False, "tourDeck": "",
    "extras": [], "focus": "",
}


def _post(path, body=None, timeout=240):
    r = requests.post(f"{BASE}{path}", json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _get(path, timeout=30):
    r = requests.get(f"{BASE}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _resolve(ticker, fallback_name):
    """Confirm a ticker exists in the demo universe, or find it by name."""
    import universe
    if universe.get(ticker, universe.DEMO_FILE):
        return ticker
    for c in universe.load_universe(universe.DEMO_FILE)["constituents"]:
        if fallback_name.lower() in c["company"].lower():
            return c["ticker"]
    return None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--first-run", action="store_true",
                    help="print the FIRST-RUN blob instead: setup unrun and the tutorial armed, "
                         "which is what a judge meeting the app should see. The recording blob "
                         "deliberately suppresses both.")
    ap.add_argument("--no-warm", action="store_true",
                    help="skip pre-computing Stage 2 (saves billable calls, but the take waits)")
    a = ap.parse_args(argv)

    try:
        health = _get("/api/health")
    except Exception as e:  # noqa: BLE001
        print(f"server not reachable at {BASE} — start it first ({type(e).__name__})")
        return 1
    print(f"server ok · llm_configured={health['llm_configured']}")

    hero = _resolve(HERO, "KLCC")
    foil = _resolve(FOIL, "Red River")
    opener = _resolve(OPENER, "Pearl Savings")
    tour = _resolve(TOUR, "SatBank")
    picks = [t for t in (opener, hero, foil, tour) if t]
    if len(picks) < 4:
        print("  WARNING: could not resolve every hero ticker — check the demo universe")

    print("\nclearing the watchlist…")
    for row in _get("/api/watchlist").get("tickers", []):
        requests.delete(f"{BASE}/api/monitor/{row}", timeout=30)

    print("pinning:")
    for tk in picks:
        entry = _post("/api/monitor", {"ticker": tk, "demo": True})
        print(f"  {tk:<12} {entry['entry']['company']['company']}")

    if not a.no_warm:
        if not health["llm_configured"]:
            print("\n  SKIPPING warm-up: no DEEPSEEK_API_KEY on the server. Start it from a shell "
                  "that has the key, or the Compete will run cold on camera.")
        else:
            print("\npre-computing Stage 2 so no take waits on it (this bills)…")
            for tk in (hero, foil, tour):
                if not tk:
                    continue
                t0 = time.time()
                try:
                    _post("/api/stage2/quick", {"ticker": tk, "use_rag": True, "top_k": 5})
                    print(f"  {tk:<12} warm in {time.time() - t0:.0f}s")
                except Exception as e:  # noqa: BLE001
                    print(f"  {tk:<12} FAILED after {time.time() - t0:.0f}s — {type(e).__name__}. "
                          f"Raise ESG_LLM_TIMEOUT and retry.")

    state = FIRST_RUN_STATE if a.first_run else UI_STATE
    print("\nPaste this into the browser console, then reload:\n")
    print(f"  localStorage.setItem('esg-radar-settings', '{json.dumps(state)}')\n")
    if a.first_run:
        print("Opens on: the one-question setup, then the first-run tutorial — what a judge sees.")
        print("Or skip the console entirely: open  http://localhost:8000/?fresh=1")
    else:
        print("Opens on: level 1, dark, demo data, all ASEAN, both rails closed, analyst view.")
        print("No tutorial: `tourDone` is set, so no overlay can appear mid-take.")
        print("For the first-time experience instead, re-run with --first-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
