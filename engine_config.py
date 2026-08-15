"""
engine_config.py — the single place the engine's numbers come from.
===================================================================
Loads `data/engine_config.json` (Build Spec v2: A1 labels, A2 sub-weights, A5 tier formulas)
and hands back a plain dict. Nothing in `engine.py` / `signals.py` hard-codes a threshold —
the harness sweeps this file and reports the quadrant churn (A8), which only works if every
knob really does live here.

`config_hash` is part of every score record's identity: change a weight and the run id changes,
so two records can never silently disagree about which config produced them.
"""

import copy
import hashlib
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "data", "engine_config.json")

_CACHE = {}          # path -> {"mtime", "data"} : re-read only when the file actually changes


def load(path=None, *, overrides=None):
    """The config dict, mtime-cached. `overrides` is a deep-merged patch (the sweep's lever) and
    always returns a fresh copy, so a caller can never mutate another caller's config."""
    path = path or CONFIG_FILE
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    hit = _CACHE.get(path)
    if not hit or hit["mtime"] != mtime:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["config_hash"] = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        _CACHE[path] = {"mtime": mtime, "data": data}
        hit = _CACHE[path]
    cfg = copy.deepcopy(hit["data"])
    if overrides:
        cfg = merge(cfg, overrides)
        cfg["config_hash"] = hashlib.sha256(
            json.dumps({k: v for k, v in cfg.items() if k != "config_hash"},
                       sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    return cfg


def merge(base, patch):
    """Recursive dict merge — `patch` wins at the leaves. Used by the sensitivity sweep."""
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def threshold(cfg, value):
    """Resolve a threshold that may be the literal string "theta" (the spec writes tier and
    label rules in terms of theta so one number moves them all together)."""
    return cfg["theta"] if value == "theta" else value


def label_order(cfg):
    """Label keys in evaluation order — `hidden_winners` first, per A1's precedence rule."""
    order = [k for k in cfg["labels"].get("_order", []) if k in cfg["labels"]]
    return order or [k for k in cfg["labels"] if not k.startswith("_")]


def display(cfg, label_key):
    """CGSI display name for a label key ('hidden_winners' -> 'Hidden Winners')."""
    entry = cfg["labels"].get(label_key) or {}
    return entry.get("display", label_key.replace("_", " ").title())
