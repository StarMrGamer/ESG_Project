"""
ASEAN ESG Momentum Radar — STAGE 1: The Interrogation Loop (the hero)
=====================================================================
A bare-page reasoning loop. User types one vague ESG question; the AI asks up to
5 ADAPTIVE questions (each mapped to one ESG reasoning axis), CHALLENGES the
framing when it looks off, then restates the user's REAL narrowed question.
It does NOT answer the ESG question — that is Stage 2.

This file is owned by Person 1 (AI Reasoning Lead). The SYSTEM_PROMPT below is
the IP — tune it freely. The loop logic underneath should rarely need to change.

RUN
---
    pip install streamlit anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."      # Windows: set ANTHROPIC_API_KEY=...
    streamlit run stage1_interrogation.py

Swapping LLM provider: only edit call_llm(). Everything else is provider-agnostic.
"""

import json
import streamlit as st

# ----------------------------------------------------------------------------- #
#  CONFIG
# ----------------------------------------------------------------------------- #
MODEL = "deepseek-chat"       # DeepSeek V3. swap to "deepseek-reasoner" for R1.
MAX_QUESTIONS = 5             # the cap. The AI may narrow earlier than this.

# The four ESG-native reasoning axes (from the Part 1 concept page).
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

# ----------------------------------------------------------------------------- #
#  THE HERO IP — the interrogation system prompt
# ----------------------------------------------------------------------------- #
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
- CHALLENGE the framing when it looks wrong. If the user worries about an issue
  that is not the sector's material one, push back inside your question — do not
  just accept it. Example: "You're focused on their carbon footprint, but for a
  bank the issue that actually moves value is governance and data security — is
  carbon really your concern, or is it the wrong lens here?"
- DRIVE toward the blind_spot axis when you can — especially undisclosed AI /
  digital risk. That is where this tool's unique insight lives.
- STOP when the question is sharp enough to answer with specific company data,
  OR after the interview director tells you the cap is reached — whichever first.
- When you stop, restate the user's REAL narrowed question in ONE sentence,
  naming the sector, time horizon, and mandate where known.
- NEVER answer the ESG question itself. No verdicts, no buy/sell, no scores.

OUTPUT — respond with JSON ONLY. No prose, no markdown, no code fences.
{
  "axis": "materiality" | "time_horizon" | "mandate" | "blind_spot" | null,
  "type": "question" | "challenge" | "narrowed",
  "text": "<your question, your challenge, or the final restated question>",
  "done": false | true
}
- type "question": a normal narrowing question on the chosen axis (done=false)
- type "challenge": pushing back on the user's premise; still expects an answer (done=false)
- type "narrowed": the final one-sentence restatement of their REAL question (done=true, axis=null)

WORKED EXAMPLE (illustrative)
user: "Is this bank a good ESG investment?"
you: {"axis":"mandate","type":"question","text":"Are you asking because you want downside protection (risk), outperformance (return), or to satisfy an ESG mandate? Each points at a different signal.","done":false}
user: "Downside protection — I'm worried about hidden risk."
you: {"axis":"blind_spot","type":"question","text":"Hidden where? What do you suspect a standard ESG rating is NOT capturing about this bank?","done":false}
user: "Their AI use isn't disclosed."
you: {"axis":"time_horizon","type":"question","text":"Is the undisclosed-AI worry a near-term catalyst or a structural concern — is something forcing the issue soon?","done":false}
user: "New MAS AI rules next year."
you: {"axis":null,"type":"narrowed","text":"Your real question: is this bank's undisclosed AI-governance gap a NEAR-TERM capital risk, given MAS's incoming AI Risk Management Guidelines?","done":true}
"""

FORCE_NARROW_NOTE = (
    "[INTERVIEW DIRECTOR: You have reached the maximum number of questions. Do NOT "
    "ask another question. Output type='narrowed', done=true, axis=null, restating "
    "the user's REAL question in one sentence.]"
)

# ----------------------------------------------------------------------------- #
#  LLM CALL  — the only provider-specific code. Swap this to change providers.
# ----------------------------------------------------------------------------- #
def call_llm(messages):
    """messages: list of {"role","content"} turns. Returns raw string response."""
    from openai import OpenAI
    import os
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        temperature=0.6,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )
    return resp.choices[0].message.content


def parse_envelope(raw):
    """Defensive JSON parse. Falls back to treating raw text as a plain question."""
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        start, end = cleaned.index("{"), cleaned.rindex("}") + 1
        env = json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"axis": None, "type": "question", "text": raw.strip(), "done": False}
    env.setdefault("axis", None)
    env.setdefault("type", "question")
    env.setdefault("text", "")
    env.setdefault("done", False)
    return env

# ----------------------------------------------------------------------------- #
#  STREAMLIT APP
# ----------------------------------------------------------------------------- #
st.set_page_config(page_title="ESG Interrogation — Stage 1", page_icon="🛰️")

ss = st.session_state
if "stage" not in ss:
    ss.stage = "start"      # start -> interrogating -> narrowed
    ss.msgs = []            # the LLM conversation (real turns only)
    ss.trail = []           # list of parsed envelopes — the visible reasoning trail
    ss.turns = 0            # how many questions the AI has asked
    ss.narrowed = ""

# ---- Sidebar: axis legend, demo inputs, reset --------------------------------
with st.sidebar:
    st.subheader("The four axes")
    for icon, name, desc in AXES.values():
        st.markdown(f"{icon} **{name}** — {desc}")
    st.divider()
    st.subheader("Demo inputs (vague on purpose)")
    for d in DEMO_INPUTS:
        st.markdown(f"- _{d}_")
    st.divider()
    if st.button("↺ Reset"):
        for k in ("stage", "msgs", "trail", "turns", "narrowed"):
            ss.pop(k, None)
        st.rerun()

# ---- Header ------------------------------------------------------------------
st.title("🛰️ ESG Interrogation — Stage 1")
st.caption("It asks before it answers. Vague question in → sharp question out. "
           "(It does NOT answer here — that's Stage 2.)")

def axis_badge(env):
    if env.get("type") == "narrowed":
        return "✅ Narrowed question"
    if env.get("type") == "challenge":
        return "⚡ Challenge"
    icon, name, _ = AXES.get(env.get("axis"), ("❓", "—", ""))
    return f"{icon} {name}"

# ---- Render the conversation so far ------------------------------------------
i = 0
for env in ss.trail:
    # the user's seed/answer that PRECEDED this AI turn
    user_turns = [m for m in ss.msgs if m["role"] == "user"]
    if i < len(user_turns):
        with st.chat_message("user"):
            st.write(user_turns[i]["content"])
    i += 1
    with st.chat_message("assistant"):
        st.markdown(f"**{axis_badge(env)}**")
        st.write(env["text"])

# ---- Narrowed: show the handoff to Stage 2 -----------------------------------
if ss.stage == "narrowed":
    st.success("**Narrowed question (Stage 1 output):**\n\n" + ss.narrowed)
    st.info("➡️ **Stage 2** will reason over Layer A (stale baseline) + Layer B "
            "(live signal) to ANSWER this exact question in the four-line shape.")
    st.stop()

# ---- Input: seed question, then answers --------------------------------------
placeholder = ("What do you want to understand?"
               if ss.stage == "start" else "Your answer…")
user_text = st.chat_input(placeholder)

if user_text:
    ss.msgs.append({"role": "user", "content": user_text})
    if ss.stage == "start":
        ss.stage = "interrogating"

    force = ss.turns >= MAX_QUESTIONS
    call_messages = list(ss.msgs)
    if force:
        call_messages.append({"role": "user", "content": FORCE_NARROW_NOTE})

    with st.spinner("Thinking about what to ask next…"):
        raw = call_llm(call_messages)
    env = parse_envelope(raw)

    ss.msgs.append({"role": "assistant", "content": raw})
    ss.trail.append(env)

    if env.get("done") or force or env.get("type") == "narrowed":
        ss.stage = "narrowed"
        ss.narrowed = env["text"]
    else:
        ss.turns += 1

    st.rerun()
