"""
core.py — FROZEN shared foundation for the ASEAN ESG Momentum Radar.
=====================================================================
Everything that touches the LLM provider or the on-disk sample data lives here, so the
three stage modules stay provider-agnostic and never fabricate. Per CLAUDE.md HARD RULES:
  - LLM access ONLY through call_llm()      (provider isolation, rule 6)
  - API key ONLY from the environment       (never hard-coded, rule 5)
  - one local JSON file only                (no live data / DB / web fetch, rule 1)

THE RELAY MODEL: each pipeline stage that reasons gets a FRESH agent — its own system
prompt and its own message list passed into call_llm(). Stages never share conversation
history. The only thing that travels down the pipe is the verified contract output (the
baton). Stage 2 sees the NarrowedQuestion, NOT Stage 1's interrogation transcript.

DO NOT edit without sign-off (frozen contract surface).
"""

import json
import os

# --------------------------------------------------------------------------- #
#  CONFIG
# --------------------------------------------------------------------------- #
BASE_URL = "https://api.deepseek.com"
# CLAUDE.md specifies deepseek-v4-flash. Overridable via env so a wrong default name is a
# one-line fix, not a code change (e.g. export DEEPSEEK_MODEL=deepseek-chat).
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_QUESTIONS = 5  # Stage 1 interrogation cap.

_DATA_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "data", "hero_company.json")


class LLMConfigError(RuntimeError):
    """Raised when the LLM cannot be called (e.g. missing API key)."""


# --------------------------------------------------------------------------- #
#  THE ONE LLM ENTRY POINT  (provider isolation — swap providers only here)
# --------------------------------------------------------------------------- #
def call_llm(messages, system, *, max_tokens=600, temperature=0.6, json_mode=False):
    """Call DeepSeek. The ONLY place that imports the SDK / reads the API key.

    A fresh agent per call: ``system`` is this stage's system prompt and ``messages`` is
    this stage's own conversation — nothing is shared between stages.

    Args:
        messages:   list of {"role", "content"} turns (NO system role — pass via `system`).
        system:     the stage-specific system prompt string.
        json_mode:  ask the API to guarantee valid-JSON output. Falls back to a plain call
                    if the configured model/endpoint rejects it.
    Returns:
        the raw assistant string ("" if empty; parse defensively with parse_json).
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise LLMConfigError(
            'DEEPSEEK_API_KEY is not set. Export it before running:\n'
            '  export DEEPSEEK_API_KEY="sk-..."   '
            '(Windows: $env:DEEPSEEK_API_KEY="sk-...")'
        )
    from openai import OpenAI  # lazy import: non-LLM paths (e.g. selftest) need no SDK.

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "system", "content": system}] + list(messages),
    )
    if json_mode:  # OpenAI-style JSON mode; DeepSeek supports it (prompt must say "json").
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        if "response_format" in kwargs:  # model/endpoint rejected JSON mode — retry plain.
            kwargs.pop("response_format")
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
#  DEFENSIVE JSON PARSE  (DeepSeek sometimes wraps JSON in prose — rule 6)
# --------------------------------------------------------------------------- #
def parse_json(raw):
    """Best-effort parse of a model response into a dict.

    Strips ``` fences, slices the outermost {...}, and json.loads it.
    Returns a dict, or None if nothing parseable is found (caller decides the fallback).
    """
    if not raw:
        return None
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        start, end = cleaned.index("{"), cleaned.rindex("}") + 1
    except ValueError:
        return None
    try:
        obj = json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# --------------------------------------------------------------------------- #
#  THE ONE DATA SOURCE  (one local JSON, no live data — rule 1)
# --------------------------------------------------------------------------- #
def load_company_data(path=None):
    """Load the single local CompanyData JSON (Contract B)."""
    path = path or _DATA_PATH_DEFAULT
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
