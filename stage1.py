"""
stage1.py — STAGE 1: Interrogate (the hero).
============================================
A fresh DeepSeek agent turns one vague ESG question into ONE sharp, answerable question.
It asks up to 5 ADAPTIVE questions (each mapped to one ESG reasoning axis), CHALLENGES bad
framing, then restates the user's REAL question — emitting a NarrowedQuestion (Contract A)
as the baton for Stage 2. It NEVER answers the ESG question; that is Stage 2's job.

This file owns the interrogation IP (SYSTEM_PROMPT). All LLM access goes through
core.call_llm(); all Streamlit calls live inside render() so importing this module is
side-effect-free (selftest imports it without a display).
"""

import core
import contracts

# --------------------------------------------------------------------------- #
#  The four ESG-native reasoning axes (icon, name, one-line prompt).
# --------------------------------------------------------------------------- #
AXES = {
    "materiality":  ("🎯", "Materiality",  "Does this matter for THIS sector?"),
    "time_horizon": ("⏱️", "Time horizon", "Near-term catalyst or structural?"),
    "mandate":      ("🧭", "Mandate",      "Risk, return, or compliance?"),
    "blind_spot":   ("🕳️", "Blind-spot",   "What does the static rating miss?"),
}

# Vague inputs to demo with — the AI must NARROW these, not accept them.
DEMO_INPUTS = [
    "Is this bank a good ESG investment?",
    "I want a sustainable tech stock.",
    "Should I worry about this company's carbon footprint?",
]

# --------------------------------------------------------------------------- #
#  THE HERO IP — the interrogation system prompt.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are the ESG INTERROGATION ENGINE for the ASEAN ESG Momentum Radar.

YOUR ONE JOB IN THIS STAGE: turn the user's vague ESG question into ONE sharp,
specific, answerable question. You do NOT answer ESG questions here. You only
interrogate. Answering happens in a later stage.

HOW YOU QUESTION — the four ESG reasoning axes
Every question you ask must probe along exactly ONE of these axes:
  1. materiality  — Does this issue even matter for THIS company's sector?
       (Financial materiality is sector-specific: a bank's material ESG issue is
        data security/governance; a semiconductor firm's is water/emissions.
        They are NOT interchangeable.)
  2. time_horizon — Is this a near-term catalyst, or a structural concern?
  3. mandate      — Is the user driving at risk, return, or compliance?
  4. blind_spot   — What would a traditional STATIC rating fail to see here?

RULES
- Ask ONE question at a time. Never a list. Never a fixed script.
- ADAPT: each question must depend on what the user just said. Pick the axis that
  will narrow the vagueness the most, given what is still unclear.
- Do not re-probe an axis the user has already answered clearly.
- On every "question" or "challenge" turn, "axis" MUST be exactly one of:
  materiality, time_horizon, mandate, blind_spot. NEVER null on these turns — null is
  ONLY allowed on the final "narrowed" turn.
- CHALLENGE the framing when it looks wrong. If the user worries about an issue
  that is not the sector's material one, push back inside your question — do not
  just accept it. Example: "You're focused on their carbon footprint, but for a
  bank the issue that actually moves value is governance and data security — is
  carbon really your concern, or is it the wrong lens here?"
- DRIVE toward the blind_spot axis when you can — especially undisclosed AI /
  digital risk. That is where this tool's unique insight lives.
- NARROW EAGERLY. As soon as you know the user's mandate, the material issue (or the
  blind-spot they're worried about), and the time horizon, STOP asking and output
  type="narrowed". Aim to finish in 2–4 questions — do NOT keep asking once you can
  already write the sharp question. Also stop if the interview director says the cap is
  reached. When unsure whether to ask one more or to narrow, NARROW.
- When you stop, restate the user's REAL narrowed question in ONE sentence,
  naming the sector, time horizon, and mandate where known.
- NEVER answer the ESG question itself. No verdicts, no buy/sell, no scores.

OUTPUT — respond with JSON ONLY. No prose, no markdown, no code fences.
{
  "axis": "materiality" | "time_horizon" | "mandate" | "blind_spot" | null,
  "type": "question" | "challenge" | "narrowed",
  "text": "<your question, your challenge, or the final restated question>",
  "done": false | true,
  "mandate": "risk" | "return" | "compliance" | null,
  "sector": "<the sector if known, else null>",
  "horizon": "near_term" | "structural" | null
}
- type "question": a normal narrowing question on the chosen axis (done=false).
- type "challenge": pushing back on the user's premise; still expects an answer (done=false).
- type "narrowed": the final one-sentence restatement of their REAL question
  (done=true, axis=null). On this turn you MUST also fill mandate, sector, and horizon
  from what you learned (use null only if genuinely unknown — never guess a number/date).
- On "question"/"challenge" turns, set mandate/sector/horizon to null unless already certain.

WORKED EXAMPLE (illustrative)
user: "Is this bank a good ESG investment?"
you: {"axis":"mandate","type":"question","text":"Are you asking because you want downside protection (risk), outperformance (return), or to satisfy an ESG mandate? Each points at a different signal.","done":false,"mandate":null,"sector":"Financials — Banks","horizon":null}
user: "Downside protection — I'm worried about hidden risk."
you: {"axis":"blind_spot","type":"question","text":"Hidden where? What do you suspect a standard ESG rating is NOT capturing about this bank?","done":false,"mandate":"risk","sector":"Financials — Banks","horizon":null}
user: "Their AI use isn't disclosed."
you: {"axis":"time_horizon","type":"question","text":"Is the undisclosed-AI worry a near-term catalyst or a structural concern — is something forcing the issue soon?","done":false,"mandate":"risk","sector":"Financials — Banks","horizon":null}
user: "New MAS AI rules next year."
you: {"axis":null,"type":"narrowed","text":"Is this bank's undisclosed AI-governance gap a NEAR-TERM capital risk, given MAS's incoming AI Risk Management Guidelines?","done":true,"mandate":"risk","sector":"Financials — Banks","horizon":"near_term"}
"""

FORCE_NARROW_NOTE = (
    "[INTERVIEW DIRECTOR: You have reached the maximum number of questions. Do NOT "
    "ask another question. Output type='narrowed', done=true, axis=null, restating "
    "the user's REAL question in one sentence, and fill mandate/sector/horizon.]"
)


# --------------------------------------------------------------------------- #
#  PURE LOGIC (no Streamlit) — testable standalone.
# --------------------------------------------------------------------------- #
def _envelope_defaults(env):
    """Apply Stage-1 envelope defaults to a parsed (or failed) response."""
    env = env or {}
    env.setdefault("axis", None)
    env.setdefault("type", "question")
    env.setdefault("text", "")
    env.setdefault("done", False)
    env.setdefault("mandate", None)
    env.setdefault("sector", None)
    env.setdefault("horizon", None)
    return env


def company_scope_note(company):
    """A scope line anchoring the interrogation to the ONE loaded company (name + sector
    only — never its Layer A/B signals, which stay in Stage 2). None if no company."""
    if not company:
        return None
    return (
        f"SCOPE: The only company this tool has data for is {company.get('company')} "
        f"({company.get('sector')}). You can ONLY interrogate about this company. If the "
        f"user names or implies a different company, briefly say you currently only cover "
        f"{company.get('company')} and steer the question back to it — do not invent another "
        f"company's facts. Make materiality specific to its sector. You still have NO access "
        f"to its ESG signals here; you only know its name and sector."
    )


def ask_next(messages, turns, company=None):
    """Ask the next interrogation turn.

    Args:
        messages: the Stage-1 conversation so far (this stage's OWN list).
        turns:    how many questions the AI has already asked.
        company:  the loaded CompanyData, used only to anchor scope (name + sector).
    Returns:
        (envelope, raw_string). On the capped turn the envelope is forced to 'narrowed'.
    """
    call_messages = list(messages)
    force = turns >= core.MAX_QUESTIONS
    if force:
        call_messages.append({"role": "user", "content": FORCE_NARROW_NOTE})

    scope = company_scope_note(company)
    system = SYSTEM_PROMPT if not scope else SYSTEM_PROMPT + "\n\n" + scope
    raw = core.call_llm(call_messages, system, max_tokens=700, json_mode=True)
    parsed = core.parse_json(raw)
    if parsed is None:
        # Couldn't parse JSON — degrade gracefully to a plain re-ask (defensive).
        text = (raw or "").strip() or (
            "Tell me a bit more so I can sharpen this — what's really driving the question?"
        )
        env = _envelope_defaults({"text": text})
        env["_parse_failed"] = True
    else:
        env = _envelope_defaults(parsed)
    env["_raw"] = raw  # kept for the debug view; coerced out of the Contract A trail.

    if force:  # guarantee termination regardless of what the model returned
        env["type"] = "narrowed"
        env["axis"] = None
        env["done"] = True
    if env["type"] == "narrowed":
        env["done"] = True
    return env, raw


def build_narrowed_question(trail, final_env):
    """Assemble Contract A from the interrogation trail + the final 'narrowed' envelope."""
    return contracts.coerce_narrowed_question(
        {
            "narrowed_question": final_env.get("text"),
            "mandate": final_env.get("mandate"),
            "sector": final_env.get("sector"),
            "horizon": final_env.get("horizon"),
            "trail": [
                {"axis": e.get("axis"), "type": e.get("type"), "text": e.get("text")}
                for e in trail
            ],
        }
    )


# --------------------------------------------------------------------------- #
#  STREAMLIT UI (all st.* calls confined here — import-safe module).
# --------------------------------------------------------------------------- #
def _axis_badge(env):
    t = env.get("type")
    if t == "narrowed":
        return "✅ Narrowed question"
    axis = env.get("axis")
    if axis in AXES:
        icon, name, _ = AXES[axis]
        return f"{icon} {name}"
    # Unknown/missing axis — keep the UI clean instead of showing "❓ —".
    return "⚡ Challenge" if t == "challenge" else "🔍 Question"


def _render_trail(st, ss):
    """Replay the interrogation: each user turn followed by the AI's envelope."""
    user_turns = [m for m in ss.s1_msgs if m["role"] == "user"]
    debug = bool(ss.get("debug"))
    for i, env in enumerate(ss.s1_trail):
        if i < len(user_turns):
            with st.chat_message("user"):
                st.write(user_turns[i]["content"])
        with st.chat_message("assistant"):
            st.markdown(f"**{_axis_badge(env)}**")
            st.write(env["text"])
            if env.get("_parse_failed"):
                st.caption("⚠️ The model didn't return valid JSON for this turn.")
            if (debug or env.get("_parse_failed")) and "_raw" in env:
                with st.expander("🐞 raw model output"):
                    st.code(env["_raw"] or "<empty>")


def _commit_turn(st, ss, env, raw):
    """Persist one AI turn; flip to the narrowed state (Contract A baton) when done."""
    ss.s1_msgs.append({"role": "assistant", "content": raw})
    ss.s1_trail.append(env)
    if env["done"]:
        ss.s1_done = True
        ss.narrowed_q = build_narrowed_question(ss.s1_trail, env)
    else:
        ss.s1_turns += 1
    st.rerun()


def render(ss, company=None):
    """Run the Stage-1 interrogation UI. Sets ss.s1_done + ss.narrowed_q when finished.

    Owns ss keys: s1_msgs, s1_trail, s1_turns, s1_done, narrowed_q. The app initialises them.
    `company` anchors the interrogation to the one loaded company (scope only).
    """
    import streamlit as st

    _render_trail(st, ss)

    if ss.s1_done:
        return  # the app shows the narrowed-question card + the hand-off to Stage 2.

    # Once the interrogation is underway, always offer a way through to the answer —
    # so the user reaches Stage 2 even if the model keeps asking instead of narrowing.
    if ss.s1_trail:
        st.caption(f"Question {ss.s1_turns} of up to {core.MAX_QUESTIONS}.")
        if st.button("→ I've said enough — narrow it & continue"):
            with st.spinner("Narrowing your question…"):
                try:
                    env, raw = ask_next(ss.s1_msgs, core.MAX_QUESTIONS, company)  # force narrow
                except core.LLMConfigError as e:
                    st.error(str(e))
                    return
            _commit_turn(st, ss, env, raw)
            return

    if ss.s1_msgs:
        placeholder = "Your answer…"
    elif company:
        placeholder = f"What do you want to understand about {company.get('company')}?"
    else:
        placeholder = "What do you want to understand?"
    user_text = st.chat_input(placeholder)
    if not user_text:
        return

    ss.s1_msgs.append({"role": "user", "content": user_text})
    with st.spinner("Thinking about what to ask next…"):
        try:
            env, raw = ask_next(ss.s1_msgs, ss.s1_turns, company)
        except core.LLMConfigError as e:
            ss.s1_msgs.pop()  # roll back the unanswered turn
            st.error(str(e))
            return
    _commit_turn(st, ss, env, raw)
