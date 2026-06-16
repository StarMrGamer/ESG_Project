"""
debug_llm.py — one-shot probe of the DeepSeek endpoint.
=======================================================
Run it with your venv + key set, to see EXACTLY what the model returns (this is what
Stage 1/2 must parse as JSON):

    set -x DEEPSEEK_API_KEY "sk-..."      # fish
    .venv/bin/python debug_llm.py

What the output tells you:
  - "CALL FAILED: NotFoundError ..."  -> the model name is wrong; set DEEPSEEK_MODEL.
  - RAW REPR: ''                       -> the model returned empty content.
  - RAW REPR: '...prose...'            -> the model ignored JSON-only; PARSED will be None.
  - PARSED: {...}                      -> JSON works; the app should too.
"""

import core

PROMPT = 'Reply with JSON only, no prose: {"ok": true, "note": "hello"}'


def main():
    print("MODEL    :", core.MODEL, "   (override with env DEEPSEEK_MODEL)")
    print("BASE_URL :", core.BASE_URL)
    print("KEY SET  :", bool(__import__("os").environ.get("DEEPSEEK_API_KEY")))
    print("-" * 60)
    try:
        raw = core.call_llm(
            [{"role": "user", "content": PROMPT}],
            "You output JSON only.",
            json_mode=True,
        )
    except Exception as e:  # noqa: BLE001 — this probe must report any failure verbatim
        print("CALL FAILED:", type(e).__name__, "->", e)
        return
    print("RAW REPR :", repr(raw))
    print("PARSED   :", core.parse_json(raw))


if __name__ == "__main__":
    main()
