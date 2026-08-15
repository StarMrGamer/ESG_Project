# Prototype Build Spec — v2
**Quill & Candle · 14 Aug 2026 · supersedes v1 (Prototype_Build_Spec_Final).** Changes in v2: adds **Phase B** (the build steps that fire when CGSI's data lands, per the Data-Arrival Playbook) and replaces §7 with the **full blockchain implementation** — concrete enough to code from directly.

## Decisions log (unchanged, binding)
1. Persona: green-finance investor · green bonds as gauge · risk appetite as filter · Moderate demo default.
2. Three types answer: Green / Social / Sustainability; we target standard green use-of-proceeds bonds of listed issuers.
3. Quadrants: CGSI's names, full adoption + new fourth label.
4. Chatbot / In-Depth mode: **OUT** — roadmap line only.
5. Intangibles: **IN**, taxonomy-only (`digital_risk`, `platform_dominance`).
6. Risk appetite UI: 3-tier selector, Moderate default; sliders dropped.

---

# PHASE A — build now (Sprint 2, 17–23 Aug)

### A1. Config: quadrant labels (30 min)
```
labels:
  hidden_winners:     disagreement >= theta AND composite_confidence >= 0.5 AND signal_count >= 10
  future_leaders:     lseg_percentile >= 0.5 AND composite_momentum > 0
  value_traps:        lseg_percentile <  0.5 AND composite_momentum < 0
  overrated_leaders:  lseg_percentile >= 0.5 AND composite_momentum < 0     # NEW
  consensus:          everything else
theta: 0.30
```
`hidden_winners` takes precedence where conditions overlap. CGSI names appear in the legend, tooltips, evidence-trail headers, demo script. Labels reproducible from the stored record.

### A2. Config: DIGITAL subcomponents (1–2 hrs)
`digital_risk` — route existing cyber/breach/regtech signals (default direction −1; no duplicate records — add DIGITAL routing alongside existing G routing). `platform_dominance` — platform/marketplace/ecosystem language in filings & wires, weighted low like disclosure.
Sub-weights (config, disclosed, swept): patents .30 · ai_talent .25 · digital_capex .20 · digital_disclosure .10 · platform_dominance .05 · digital_risk .10.

### A3. Company metadata loader (2–3 hrs)
CSV header = frozen schema; join on `company_id`. Missing file/row must not break rendering. Ship a mock file with `is_provisional = TRUE` until real data lands; provisional badge mirrors the MOCK pattern.

### A4. UI: two badges (2–3 hrs)
Green-bond status (4 tiers + PROVISIONAL treatment) and profitability (3 states + traction pip on loss-makers). Badge click-through → `evidence_url` / `source_url_1`. Three-click rule holds.

### A5. UI: risk-tier selector (half day)
Conservative · **Balanced (default)** · Aggressive. Derived at runtime:
```
conservative: green_bond_status in {cbi_certified, labelled_reviewed} AND momentum > 0
              AND confidence >= 0.7 AND profitable
balanced:     disagreement >= theta AND confidence >= 0.5 AND profitable
              AND green_bond_status in {labelled_unreviewed, none}
aggressive:   disagreement >= theta AND confidence >= 0.3 AND loss_making
              AND traction_flag AND green_bond_status = none
```
Re-segments the matrix in <1s (precompute all three if slow). Non-matching companies dim, not hide. Thresholds in config.

### A6. UI: origination-pipeline filter (1 hr)
Toggle = the Balanced condition. On-screen counts: *N issuers (priced in) · M pipeline · K review list*, computed live.

### A7. Trust layer — full implementation (Jayden, ~1 day, slot Sat 22 Aug) — see PHASE C below.

### A8. Harness (Rai, rolling)
Golden-set expectations for the two new subcomponents · sensitivity sweeps report quadrant churn under the new names · **backtest cases = the five delivered 14 Aug** (Sembcorp cutoff 31 Aug 2021 · ACEN 30 Sep 2022 · Top Glove 30 Jun 2020 · Adaro 28 Feb 2023 · REE 31 Jul 2022; timelines and sources in `Backtest_Candidates_for_Rai.md`). Cutoff assertion `signal.published_at < case.cutoff_date` fails loudly.

### A9. Demo script v5 (30 min, after A5–A6)
Universe → matrix (CGSI names) → tier flip Conservative→Balanced→Aggressive (15s) → Hidden Winner → evidence trail → source URL → on-chain verify (15s). Chatbot line: *"Natural-language interrogation is on the roadmap — today every answer is a click, not a prompt."*

---

# PHASE B — fires when CGSI's data lands (see Data-Arrival Playbook for the team run-order)

### B1. Real metadata swap (Jayden, 1 hr)
Replace the mock CSV with the verified file (`is_provisional = FALSE`); badges, tiers and the pipeline filter go live on real names. **No code changes** — this is why the schema froze early.

### B2. N/M/K computation (Rai, 1 hr)
One script over labels + metadata → the three counts, frozen with a run ID and date, handed to Brina/Grace for the money slide. Counts must reproduce from the stored records.

### B3. The 17-pick validation run (Rai, ½ day — only if CGSI shares them)
Run the engine blind over the 52 → rank by composite momentum → compare our top quartile against CGSI's 17. Output: agreement %, and for every disagreement the evidence trail explaining why. Either result is a slide; disagreement with evidence is CGSI criterion 03 in its purest form.

### B4. Green-bond issuance backtest (Rai, ½ day)
For each high-momentum company at time t: did a green bond issuance or external review appear at t+1? Outcome dates from AsianBondsOnline / exchange filings. Public, free, precisely dated — validation that doesn't depend on the mocked LSEG baseline.

### B5. Anchor the verification table (Jayden, 15 min)
Include each CSV row's hash in the next scoring run's Merkle leaves (see C3). The green-bond evidence becomes independently verifiable like every other claim.

**Timing rule:** data before Thu 21 Aug → B1–B2 inside Sprint 2, B3–B4 early Sprint 3. After the 23 Aug freeze → run everything, but results go to slides and the eval report only; no new UI.

---

# PHASE C — the blockchain, concretely (the "suitable blockchain idea", fully scoped)

**What it is:** hash-anchored evidence provenance. One Merkle root per scoring run, one small transaction on the Sepolia public testnet, one verification page. **What it is not:** no token, no DAO, no on-chain scoring, no raw or licensed data on-chain, no "decentralised" claims. The chain stores a commitment, not a claim.

### C1. The contract (~20 lines of Solidity, deploy once on Sepolia)
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EvidenceAnchor {
    address public immutable signer;
    struct Anchor { bytes32 root; uint64 timestamp; }
    mapping(bytes32 => Anchor) public anchors;          // run_id => anchor
    event Anchored(bytes32 indexed runId, bytes32 root, uint64 timestamp);

    constructor() { signer = msg.sender; }

    function anchor(bytes32 runId, bytes32 root) external {
        require(msg.sender == signer, "not signer");
        require(anchors[runId].timestamp == 0, "run already anchored");   // append-only
        anchors[runId] = Anchor(root, uint64(block.timestamp));
        emit Anchored(runId, root, uint64(block.timestamp));
    }
}
```
Append-only by construction — a run can never be silently re-anchored, which *is* the tamper-evidence story. Deploy from a dedicated hackathon wallet; the wallet address is "the verifier's signature" in VeriESG terms. Sepolia ETH from a public faucet; gas ≈ 0. **Mainnet-equivalent cost for Sean's model: one ~80k-gas tx per run — a few cents to a few dollars depending on chain; hand him the measured number.**

### C2. Merkle construction (Python, ~40 lines, deterministic)
- **Leaf** = `sha256(signal_id | raw_text_hash | direction | materiality | confidence | model_version | prompt_version)` — canonical field order, fixed decimal formatting (e.g. 4 dp), UTF-8, `|` delimiter. Determinism is a hard requirement: same inputs → same root, twice, in the test suite.
- Sort leaves by `signal_id` before building (order-independence). Pair up, hash pairs, duplicate the last leaf on odd counts. Store per run: `run_id, root, leaf_count, engine_version` + the leaf list (off-chain, in the run record).
- **Leaves also include** one leaf per green-bond verification row: `sha256(company_id | green_bond_status | bond_isin | source_url_1 | as_of)` (B5).
- Anchor every run — including bad ones. Anchoring only favourable runs is misleading by omission; a visible run status (anchored/pending) enforces the comply-or-explain posture.

### C3. Anchoring step in the engine (30 min)
After a scoring run completes: compute root → call `anchor(run_id, root)` via web3.py → store the tx hash + block number on the run record. If the tx fails, the run is marked `anchor_pending` and visibly so in the UI — never silently unanchored.

### C4. The verification page (the 15-second demo moment)
Flow: user pastes (or clicks from any evidence trail) a company's evidence set → page recomputes each leaf hash → recomputes the root along the stored Merkle path → fetches the anchored root from Sepolia by `run_id` (public RPC, read-only, no wallet needed) → **MATCH / NO MATCH**, plus the block timestamp and signer address, plus an Etherscan link a judge can open on their own phone.
Also add a "tamper demo" button in rehearsal builds only: edit one character of an excerpt → verification fails → that's the point, made visually in five seconds. Remove or hide for the judged demo unless asked.

### C5. Definition of done
Deterministic root (tested twice-same) · deployed contract + ≥3 real anchored runs before 23 Aug · verification page passes the phone test (judge opens Etherscan link themselves) · nothing licensed or raw on-chain · per-anchor cost handed to Sean · one paragraph in Methodology §9 and Whitepaper §8 already written.
**Descope ladder if Gate 1 slips (unchanged):** full flow → verification page over one precomputed anchored root → roadmap slide. Cut here before cutting validation.

### C6. The one-sentence case (memorise)
*"A database's operator can silently rewrite history; anchoring each run's evidence hash on a public chain makes our evidence trail independently verifiable — tamper-evidence without trusting us. Proof on-chain, not data."* Precedents if pressed: BIS Project Genesis 2.0, HKSAR digital green bonds, Green Assets Wallet, MAS Project Guardian.

---

## OUT OF SCOPE (unchanged, binding)
Chatbot (both modes) · news-summary/forecast features · horizon sliders · satellite data · country-level scoring · OECD screen (roadmap unless Sprint 3 is calm) · Hyperledger Fabric for the demo (production roadmap only) · any token/DAO/on-chain scoring.

## Timing
A1–A2 Mon 17 · A3–A4 Tue–Wed 18–19 · A5–A6 Thu–Fri 20–21 · A7/C Sat 22 · A9 Sun 23 before the Gate 2 dry run · Phase B on data arrival per the playbook. Total Phase A+C ≈ 2.5–3 days across two people, inside existing Sprint 2 allocations.
