"""
core.py — FROZEN shared foundation for the ASEAN ESG Momentum Radar.
=====================================================================
Everything that touches the LLM provider or the on-disk sample data lives here, so the
three stage modules stay provider-agnostic and never fabricate. Per CLAUDE.md HARD RULES:
  - LLM access ONLY through call_llm()      (provider isolation, rule 6)
  - API key ONLY from the environment       (never hard-coded, rule 5)
  - live fetch ONLY through http_get()      (external-I/O isolation; rule 1 — see note)

RULE 1 UPDATE (production, sign-off 2026-06-23): the tool now performs LIVE RETRIEVAL (RAG)
for real external context. ALL outbound HTTP is isolated in http_get() exactly as the LLM is
isolated in call_llm(). Fetch is best-effort by contract: a blocked/slow network degrades to
"no external context" so the relay never hard-crashes. We STILL never fabricate (rule 2) —
retrieved sources carry their real URLs, and a missing company fact is "unknown", never
invented. The structured company dataset remains local; the web only adds grounding context.

THE RELAY MODEL: each pipeline stage that reasons gets a FRESH agent — its own system
prompt and its own message list passed into call_llm(). Stages never share conversation
history. The only thing that travels down the pipe is the verified contract output (the
baton). Stage 2 sees the NarrowedQuestion, NOT Stage 1's interrogation transcript.

DO NOT edit without sign-off (frozen contract surface).
"""

import json
import os


def _env_float(name, default):
    """Read a float env var, falling back to `default` on a missing OR non-numeric value.
    A typo'd tunable (e.g. ESG_HTTP_TIMEOUT='8s') must never crash `import core`."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _env_int(name, default):
    """Read an int env var, falling back to `default` on a missing OR non-numeric value."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


# --------------------------------------------------------------------------- #
#  CONFIG
# --------------------------------------------------------------------------- #
BASE_URL = "https://api.deepseek.com"
# CLAUDE.md specifies deepseek-v4-flash. Overridable via env so a wrong default name is a
# one-line fix, not a code change (e.g. export DEEPSEEK_MODEL=deepseek-chat).
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_QUESTIONS = 5  # Stage 1 interrogation cap.

# --- live-fetch / RAG config (rule 1 now permits live retrieval via http_get) ----------- #
HTTP_TIMEOUT = _env_float("ESG_HTTP_TIMEOUT", 10)  # per-request seconds (default 10s)
# Synchronous LLM calls run inside the Streamlit script-run; cap them so a stalled endpoint
# can't freeze the UI for the SDK default (~600s × retries). Tunable via ESG_LLM_TIMEOUT.
LLM_TIMEOUT = _env_float("ESG_LLM_TIMEOUT", 30)
USER_AGENT = os.environ.get(
    "ESG_USER_AGENT",
    "ASEAN-ESG-Momentum-Radar/1.0 (research demo; live ESG context retrieval)",
)

_DATA_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "data", "hero_company.json")


class LLMConfigError(RuntimeError):
    """Raised when the LLM cannot be called (e.g. missing API key)."""


class FetchError(RuntimeError):
    """Raised when an external fetch fails (network, timeout, non-200). Callers treat it as
    'no external context available' and degrade gracefully — never a hard crash (rule 1)."""


# --------------------------------------------------------------------------- #
#  THE ONE LLM ENTRY POINT  (provider isolation — swap providers only here)
# --------------------------------------------------------------------------- #
def call_llm(messages, system, *, max_tokens=600, temperature=0.6, json_mode=False,
             stream=False, on_delta=None):
    """Call DeepSeek. The ONLY place that imports the SDK / reads the API key.

    A fresh agent per call: ``system`` is this stage's system prompt and ``messages`` is
    this stage's own conversation — nothing is shared between stages.

    Args:
        messages:   list of {"role", "content"} turns (NO system role — pass via `system`).
        system:     the stage-specific system prompt string.
        json_mode:  ask the API to guarantee valid-JSON output. Falls back to a plain call
                    if the configured model/endpoint rejects it.
        stream:     consume the response incrementally (added 2026-06-17 with sign-off).
        on_delta:   optional callback(delta, accumulated) fired per streamed chunk so the UI
                    can narrate progress. ADDITIVE only — the FULL assistant string is still
                    returned in every mode, so JSON callers parse exactly as before.
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

    # timeout + max_retries=0 so a connected-but-stalled endpoint degrades quickly (callers catch
    # and fall back) instead of hanging the Streamlit run for the SDK default (~600s × 2 retries).
    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=LLM_TIMEOUT, max_retries=0)
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "system", "content": system}] + list(messages),
    )
    if json_mode:  # OpenAI-style JSON mode; DeepSeek supports it (prompt must say "json").
        kwargs["response_format"] = {"type": "json_object"}
    if stream:
        kwargs["stream"] = True
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        if "response_format" in kwargs:  # model/endpoint rejected JSON mode — retry plain.
            kwargs.pop("response_format")
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    if stream:  # accumulate chunks; surface each via on_delta, still return the full text.
        parts, reasoning_parts = [], []
        for chunk in resp:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            piece = getattr(delta, "content", "") or ""
            if piece:
                parts.append(piece)
                if on_delta is not None:
                    on_delta(piece, "".join(parts))
            else:  # some (reasoning) models stream chain-of-thought as reasoning_content
                rpiece = getattr(delta, "reasoning_content", "") or ""
                if rpiece:
                    reasoning_parts.append(rpiece)
        return "".join(parts) or "".join(reasoning_parts)
    msg = resp.choices[0].message
    # Prefer content; fall back to reasoning_content so a reasoning model never returns "".
    return (getattr(msg, "content", None) or getattr(msg, "reasoning_content", "") or "")


# --------------------------------------------------------------------------- #
#  THE ONE EXTERNAL-FETCH ENTRY POINT  (live-retrieval isolation — like call_llm)
# --------------------------------------------------------------------------- #
def http_get(url, *, params=None, headers=None, timeout=None, retries=1):
    """GET a URL and return the response text. The ONLY place that does outbound HTTP.

    Isolated exactly like call_llm so the stages stay I/O-agnostic and testable (tests
    monkeypatch this one function). Best-effort by contract: every failure is normalised to
    FetchError, which callers swallow into "no external context" (rule 1 graceful fallback).
    Retries transient blips (timeout / reset) ``retries`` times before giving up.

    Args:
        url:      the absolute URL to fetch.
        params:   optional querystring dict.
        headers:  optional extra headers (merged over the default User-Agent).
        timeout:  per-request seconds (defaults to HTTP_TIMEOUT).
        retries:  extra attempts on failure (so 1 = up to 2 tries total).
    Returns:
        the response body as text. Raises FetchError after the last attempt fails.
    """
    import requests  # lazy: offline paths (selftest) never import it.

    hdrs = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    if headers:
        hdrs.update(headers)
    last = None
    for _attempt in range(max(retries, 0) + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout or HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.text or ""
        except Exception as e:  # noqa: BLE001 — transient blips often clear on a retry.
            last = e
    raise FetchError(
        f"GET {url} failed after {max(retries, 0) + 1} attempt(s): {type(last).__name__}: {last}"
    ) from last


# --------------------------------------------------------------------------- #
#  DEFENSIVE JSON PARSE  (DeepSeek sometimes wraps JSON in prose — rule 6)
# --------------------------------------------------------------------------- #
def _extract_json_object(s):
    """First BALANCED {...} block in s, scanning with a brace-depth counter that respects JSON
    strings/escapes. So braces or ``` fences inside a string VALUE are preserved, and trailing
    prose after the object (which may itself contain a '}') is ignored. None if no object."""
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def parse_json(raw):
    """Best-effort parse of a model response into a dict.

    Extracts the first balanced {...} object (so a code fence inside a string value isn't stripped,
    and trailing prose with a stray '}' can't defeat the parse), then json.loads it. Falls back to
    the legacy fence-strip + outermost slice. Returns a dict, or None if nothing parseable is found.
    """
    if not raw:
        return None
    block = _extract_json_object(raw)
    if block is not None:
        try:
            obj = json.loads(block)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
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
