# INSTRUCTIONS — Rai (Prototype)

**Your one job:** a reproducible engine and a 90-second demo path a judge can walk unaided. Our own competitive read says the prototype lens is where we're weakest — and neither rival team has working software at all. A live build wins this category.

**Your files:** `Prototype_Build_Spec_v2.md` (the coding list) · `Backtest_Candidates_for_Rai.md` (harness cases, chosen and sourced) · `green_bond_verification_template.csv` (the header row = the frozen metadata schema).

## Steps, in order

### This week (before Sunday)
1. **Gate 1 — Sunday 16 Aug. Nothing else matters until this passes.** `run_engine(company_list)` → identical score records twice, cached, seeded, golden set passing. If it's shaky, cut S-items, not this.
2. Safe to do pre-Gate (config only, ~2 hrs total): **Build Spec items A1–A2** — rename quadrants to CGSI's names (incl. the NEW `overrated_leaders` label: high baseline + negative momentum) and add the two DIGITAL subcomponents (`digital_risk` routed from existing cyber/breach signals with direction −1; `platform_dominance`).

### Sprint 2 (Mon 17 – Sun 23), in this order
3. **A3** — metadata loader: read the CSV (header is the frozen contract, join on `company_id`); missing file/row must not break rendering; ship a mock file with `is_provisional = TRUE` until real data arrives. *(Tue)*
4. **A4** — two badges: green-bond status (4 tiers + PROVISIONAL treatment) and profitability (+ traction pip). Click-through to `evidence_url`. *(Tue–Wed)*
5. **Surface the `rationale` field** in every evidence-trail row — 30 min. We already store the AI's one-line justification per signal; showing it beats GreenSightAI's "explanation layer" claim. *(Wed)*
6. **A5** — risk-tier selector: Conservative / **Balanced (default)** / Aggressive, formulas in the spec, derived at runtime, thresholds in config, matrix re-segments <1s (precompute if slow). *(Thu)*
7. **A6** — origination-pipeline filter + live N/M/K counts on screen. *(Fri)*
8. **If Jayden says "add horizon":** second toggle, Short 45d / Long 180d half-life — config swap + precompute, ~2 hrs. If he doesn't, skip. *(Fri)*
9. **A8 — harness:** load the five backtest cases from `Backtest_Candidates_for_Rai.md` (cutoff dates in its first table); cutoff assertion must fail loudly; golden-set expectations updated for the new subcomponents; sensitivity sweep reports quadrant churn under the NEW names. *(rolling)*
10. **Measure and send Sean one number: LLM cost per company** (tokens/signal × signals/company × price, off the golden set). One message. *(by Fri 21)*

### When CGSI's data lands (Playbook Phase B — Jayden will trigger)
11. Real CSV swap (no code — that's why the schema froze) · N/M/K script · the 17-pick blind validation run · the green-bond issuance backtest. Details: Build Spec §B.

### Do NOT build
Chatbot (both modes) · forecasts/news-summary · satellite · country scoring · OECD screen (unless Sprint 3 is calm) · anything not in the spec. Scope-change protocol applies.

**Done when:** a judge walks universe → matrix (CGSI names) → tier flip → Hidden Winner → evidence (with rationale) → source URL → on-chain verify, unaided, under 90 seconds — twice in a row, identically.
