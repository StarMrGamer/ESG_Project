"""
signals.py — deterministic signal extraction (the engine's input layer).
========================================================================
Turns what we ALREADY STORE about a company (its `esg_basis` evidence text, its live-signal
block, its dated news rows, or an explicit event list from the backtest harness) into a list of
atomic, dated, directional **signal records** — the unit the engine scores and the Merkle tree
anchors (Build Spec §C2).

Three properties this module is built around:

* **Deterministic.** Pure functions over the stored text: no network, no LLM, no clock, no RNG.
  The same company record yields byte-identical signals every run — Gate 1's hard requirement.
  `model_version` therefore records the RULES extractor ("rules-v1"), not a sampled model; when
  an LLM extractor is swapped in later it fills the same two fields and nothing downstream moves.
* **Never fabricates** (HARD RULE 2). Every signal carries the verbatim `raw_text` it was read
  from and the stored `source_url`. A date the text doesn't state is NOT invented — the record
  falls back to the dataset's `as_of` and says so in `date_basis`, so the harness can tell a real
  publication date from an inherited one.
* **Discounts talk.** Announcement/target language has its materiality halved, and company-PR
  sources are capped at 0.5 confidence by config. That is the Adaro lesson from
  `D/Backtest_Candidates_for_Rai.md` case 4 encoded as arithmetic rather than as a caveat.

Signal record (also the Merkle leaf's source — see anchor.py):
    signal_id, company_id, routes[{component, subcomponent}], direction (+1/-1),
    materiality (0..1), confidence (0..1), published_at (ISO date), date_basis,
    source_url, source_type, raw_text, raw_text_hash, rationale,
    model_version, prompt_version

`routes` is a LIST because A2 requires a cyber/breach signal to reach DIGITAL/digital_risk
*alongside* its existing G routing — one record, two routes, no duplicate records.
"""

import hashlib
import re

import engine_config

EXTRACTOR_VERSION = "rules-v1"
PROMPT_VERSION = "n/a-rules"          # filled by a real prompt hash if an LLM extractor lands

# --------------------------------------------------------------------------- #
#  TAXONOMY — pattern -> where the signal lands, which way it points, how much
#  it matters. Ordered: the FIRST match wins as the primary route, so put the
#  specific patterns above the generic ones.
#  (component, subcomponent, direction, materiality, extra_routes)
# --------------------------------------------------------------------------- #
_T = [
    # --- DIGITAL / intangibles (A2) -----------------------------------------
    (r"\b(cyber(?:security)?|data breach|breach|ransomware|hacking|outage|"
     r"personal data protection|pdpa|regtech)\b",
     "DIGITAL", "digital_risk", -1, 0.55, [("G", "controversy")]),
    (r"\b(ai governance|ai ethics|responsible ai|model risk)\b",
     "DIGITAL", "digital_disclosure", +1, 0.50, [("G", "board")]),
    (r"\b(ai (?:talent|hiring|lead|head)|chief (?:data|ai) officer|data scientist"
     r"|ai team|ai capability)\b",
     "DIGITAL", "ai_talent", +1, 0.55, []),
    (r"\b(patent|patents|intellectual property|r&d centre|r&d center)\b",
     "DIGITAL", "patents", +1, 0.60, []),
    (r"\b(digital (?:capex|investment|transformation|infrastructure)|cloud migration"
     r"|data cent(?:re|er))\b",
     "DIGITAL", "digital_capex", +1, 0.50, []),
    (r"\b(platform|marketplace|ecosystem|super ?app|network effect)\b",
     "DIGITAL", "platform_dominance", +1, 0.35, []),
    (r"\b(digital disclosure|technology disclosure|ai disclosure)\b",
     "DIGITAL", "digital_disclosure", +1, 0.40, []),
    (r"\b(ai\b|artificial intelligence|machine learning|automation)\b",
     "DIGITAL", "digital_capex", +1, 0.35, []),

    # --- G ------------------------------------------------------------------
    (r"\b(withhold release order|wro|forced labour finding|sanction|fine[ds]?|penalt"
     r"|investigation|probe|lawsuit|misconduct|fraud|greenwash)\w*",
     "G", "controversy", -1, 0.90, []),
    (r"\b(djsi|dow jones sustainability|ftse4good|msci esg|sustainalytics|cdp\b|gresb"
     r"|vnsi|sri index|esg index|esg rating)\b",
     "G", "index_membership", +1, 0.70, []),
    (r"\b(governance (?:&|and) transparency index|cg scorecard|corporate governance"
     r"|board (?:independence|diversity|oversight)|audit committee|whistleblow)\w*",
     "G", "board", +1, 0.60, []),
    (r"\b(sustainability report|integrated report|tcfd|issb|gri\b|assurance|externally"
     r" (?:reviewed|verified)|second[- ]party opinion|spo\b|public disclosure|transparency"
     r" score|spott)\b",
     "G", "transparency", +1, 0.55, []),

    # --- S ------------------------------------------------------------------
    (r"\b(forced labour|forced labor|recruitment fee|debt bondage|child labour"
     r"|modern slavery|strike|wage theft)\b",
     "S", "labour", -1, 0.90, [("G", "controversy")]),
    (r"\b(fatalit|injur|lost[- ]time|safety incident|accident rate)\w*",
     "S", "safety", -1, 0.70, []),
    (r"\b(worker (?:welfare|remediation)|living wage|upskilling|reskilling|training hours"
     r"|employee engagement|diversity|gender)\b",
     "S", "human_capital", +1, 0.50, []),
    (r"\b(community|financial inclusion|affordable housing|healthcare access"
     r"|smallholder)\b",
     "S", "community", +1, 0.45, []),

    # --- E ------------------------------------------------------------------
    (r"\b(coal (?:exit|retirement|divest|sale)|early retirement|energy transition"
     r" mechanism|etm\b|coal[- ]to[- ]clean)\b",
     "E", "transition", +1, 0.85, []),
    (r"\b(captive coal|new coal|coal[- ]fired|expansion of coal|thermal coal)\b",
     "E", "transition", -1, 0.85, []),
    (r"\b(green bond|sustainability[- ]linked (?:bond|loan)|slb\b|green loan|green finance"
     r"|sustainable financ\w*|climate bond|cbi[- ]certified)\b",
     "E", "green_finance", +1, 0.70, []),
    (r"\b(renewable|solar|wind|hydro|geothermal|clean energy|gw\b|mwp?\b)\b",
     "E", "renewables", +1, 0.60, []),
    (r"\b(net[- ]?zero|emission[s]? (?:reduction|intensity)|scope [123]|carbon neutral"
     r"|decarbonis\w*|decarboniz\w*|sbti)\b",
     "E", "emissions", +1, 0.60, []),
    (r"\b(pollution|spill|deforestation|haze|effluent|waste violation|emissions? (?:rose|"
     r"increased))\b",
     "E", "emissions", -1, 0.75, []),
    (r"\b(leed|green (?:building|mark)|circular|recycl\w*|water (?:stewardship|intensity)"
     r"|climate disclosure|environmental disclosure|climate score)\b",
     "E", "disclosure_e", +1, 0.45, []),
]
TAXONOMY = [(re.compile(p, re.I), c, s, d, m, extra) for p, c, s, d, m, extra in _T]

# Forward-looking / announcement language — materiality x forward_looking_discount.
_FORWARD = re.compile(
    r"\b(target\w*|aims?|plans?|intends?|commits?|commitment|pledge\w*|will |to be |expected"
    r"|announc\w*|roadmap|ambition|by 20[2-9]\d)\b", re.I)

# Dates the text actually states. Order matters: most specific first.
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH_NUM = {m: i + 1 for i, m in enumerate(_MONTHS)}
_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\w*\s+(20\d{2})\b", re.I),   # 15 Jul 2020
    re.compile(r"\b(" + "|".join(_MONTHS) + r")\w*\s+(\d{1,2}),?\s+(20\d{2})\b", re.I),  # Jul 15, 2020
    re.compile(r"\b(" + "|".join(_MONTHS) + r")\w*[- ](20\d{2})\b", re.I),               # Jul 2020
    re.compile(r"\b(?:end|since|through|by|in|from)[- ](20\d{2})\b", re.I),              # end-2022
    re.compile(r"\b(20\d{2})\b"),                                                        # 2022
)

# Source type from the stored URL. Longest/most specific host fragments first.
_SOURCE_HOSTS = (
    (("cbp.gov", "dol.gov", ".gov", "europa.eu", "mas.gov.sg", "sec.gov"), "regulator"),
    (("sgx.com", "bursamalaysia", "idx.co.id", "pse.com.ph", "set.or.th", "hsx.vn"),
     "exchange_filing"),
    (("msci.com", "spglobal.com", "ftserussell", "sustainalytics", "cdp.net", "gresb",
      "djsi", "robecosam"), "index_provider"),
    (("sustainalytics.com", "iss-corporate", "vigeo", "moodys.com", "issgovernance"),
     "external_reviewer"),
    (("mongabay", "banktrack", "marketforces", "greenpeace", "amnesty", "ilo.org"), "ngo"),
    (("reuters", "bloomberg", "theguardian", "malaymail", "straitstimes", "businesstimes",
      "theedge", "nikkei", "channelnewsasia", "saigontimes", "theinvestor"), "news"),
)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_source(url, fallback="unknown"):
    """Source type for a stored URL — drives the confidence multiplier (company PR capped .5)."""
    low = (url or "").lower()
    if not low:
        return fallback
    for hosts, kind in _SOURCE_HOSTS:
        if any(h in low for h in hosts):
            return kind
    return "company_pr"          # a company's own domain is the residual case, and the capped one


def extract_date(text, *, fallback, year_month=6, year_day=30):
    """The date the TEXT states, ISO. Returns (iso_date, basis) where basis is 'stated' or
    'dataset_as_of' — a date the source doesn't give is never invented (HARD RULE 2). A bare
    year resolves to a mid-year date so ordering is stable and never claims false precision."""
    t = text or ""
    m = _DATE_PATTERNS[0].search(t)
    if m:
        return f"{m.group(3)}-{_MONTH_NUM[m.group(2)[:3].lower()]:02d}-{int(m.group(1)):02d}", "stated"
    m = _DATE_PATTERNS[1].search(t)
    if m:
        return f"{m.group(3)}-{_MONTH_NUM[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}", "stated"
    m = _DATE_PATTERNS[2].search(t)
    if m:
        return f"{m.group(2)}-{_MONTH_NUM[m.group(1)[:3].lower()]:02d}-15", "stated"
    for pattern in _DATE_PATTERNS[3:]:
        m = pattern.search(t)
        if m:
            return f"{m.group(1)}-{year_month:02d}-{year_day:02d}", "stated_year"
    return _as_iso(fallback), "dataset_as_of"


def _as_iso(value, *, month=12, day=31):
    """'2023' -> '2023-12-31'; passthrough for a full ISO date; '' -> '' (unknown)."""
    v = str(value or "").strip()
    if re.fullmatch(r"20\d{2}", v):
        return f"{v}-{month:02d}-{day:02d}"
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", v):
        return v
    if re.fullmatch(r"20\d{2}-\d{2}", v):
        return f"{v}-01"
    return v


def split_clauses(text):
    """Evidence text -> atomic clauses. Splits on ; and . , on the arrow used in event
    timelines, and on the em/en-dash asides these sources love, keeping clauses long enough to
    carry their own date and meaning."""
    parts = re.split(r"[;.]\s+|\s+→\s+|\s*\|\s*|\s+[—–]\s+|\s+plus\s+|,\s+while\s+", text or "")
    return [p.strip(" .;·") for p in parts if len(p.strip(" .;·")) >= 12]


def _matchable(text):
    """Lower-cased, dash-flattened copy used ONLY for pattern matching — 'sustainable-finance'
    and 'AI-governance' must read the same as the spaced forms. `raw_text` stays verbatim so the
    evidence trail (and the Merkle leaf) always shows the source's own words."""
    return re.sub(r"\s+", " ", re.sub(r"[-–—]", " ", (text or "").lower()))


def _rationale(subcomponent, component, direction, source_type, date_basis, forward):
    """The one-line justification stored on EVERY signal and surfaced in the evidence trail
    (INSTRUCTIONS step 5). Deterministic prose — it explains the routing, not the company."""
    way = "raises" if direction > 0 else "lowers"
    bits = [f"Reads as {component}/{subcomponent}; {way} momentum",
            f"source graded {source_type.replace('_', ' ')}"]
    if forward:
        bits.append("forward-looking language — materiality halved")
    if date_basis == "dataset_as_of":
        bits.append("no date in source — dataset as-of used")
    return "; ".join(bits) + "."


def make_signal(*, company_id, text, source_url, published_at=None, source_type=None,
                fallback_date="", config=None):
    """One clause -> one signal record, or None when nothing in the taxonomy matches.

    A record carries EVERY route the clause belongs to (primary first) so a cyber event reaches
    DIGITAL/digital_risk *and* G/controversy without being counted as two signals (A2)."""
    cfg = config or engine_config.load()
    clause = (text or "").strip()
    if not clause:
        return None

    haystack = _matchable(clause)
    primary = None
    routes = []
    seen = set()
    for pattern, comp, sub, direction, materiality, extra in TAXONOMY:
        if not pattern.search(haystack):
            continue
        if primary is None:
            primary = (comp, sub, direction, materiality)
            for c, s in [(comp, sub)] + list(extra):
                if (c, s) not in seen:
                    seen.add((c, s))
                    routes.append({"component": c, "subcomponent": s})
        elif (comp, sub) not in seen:
            # a second family in the same clause rides as an extra route, not a second record
            seen.add((comp, sub))
            routes.append({"component": comp, "subcomponent": sub})
    if primary is None:
        return None

    comp, sub, direction, materiality = primary
    forward = bool(_FORWARD.search(haystack))
    if forward:
        materiality *= cfg["forward_looking_discount"]

    stype = source_type or classify_source(source_url)
    quality = cfg["source_quality"].get(stype, cfg["source_quality"]["unknown"])
    date_iso, basis = (published_at, "stated") if published_at else \
        extract_date(clause, fallback=fallback_date)
    confidence = round(quality * (1.0 if basis in ("stated", "stated_year") else 0.85), 4)

    raw_hash = _sha256(clause)
    signal_id = _sha256(f"{company_id}|{comp}|{sub}|{raw_hash}")[:16]
    return {
        "signal_id": signal_id,
        "company_id": company_id,
        "routes": routes,
        "component": comp,                  # primary route, denormalised for readability
        "subcomponent": sub,
        "direction": direction,
        "materiality": round(materiality, 4),
        "confidence": confidence,
        "published_at": date_iso,
        "date_basis": basis,
        "source_url": source_url or "",
        "source_type": stype,
        "raw_text": clause,
        "raw_text_hash": raw_hash,
        "rationale": _rationale(sub, comp, direction, stype, basis, forward),
        "model_version": EXTRACTOR_VERSION,
        "prompt_version": PROMPT_VERSION,
    }


# --------------------------------------------------------------------------- #
#  Demo-universe blocks: numeric live signals + pillar momentum. These are
#  DATASET-origin (source_quality 0.6) and, in the demo file, fictional — the
#  record says so via source_type/source_url so nothing masquerades as fetched.
# --------------------------------------------------------------------------- #
_LIVE_SIGNAL_MAP = {
    "ai_hiring_surge":    ("DIGITAL", "ai_talent", +1, 0.60),
    "board_ai_policy":    ("DIGITAL", "digital_disclosure", +1, 0.45),
    "carbon_disclosure":  ("E", "disclosure_e", +1, 0.50),
    "green_patents":      ("DIGITAL", "patents", +1, 0.65),
    "controversy_flags":  ("G", "controversy", -1, 0.85),
}
_PILLAR_MAP = {"environment": ("E", "emissions"), "social": ("S", "human_capital"),
               "governance": ("G", "board"), "digital_ai": ("DIGITAL", "digital_capex")}


def _numeric(value):
    """'+218%' / 12 / True -> float or None. Booleans read as 1/0 (a policy exists or doesn't)."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else None


def _dataset_signal(company_id, comp, sub, direction, materiality, text, date_iso, confidence):
    raw_hash = _sha256(text)
    return {
        "signal_id": _sha256(f"{company_id}|{comp}|{sub}|{raw_hash}")[:16],
        "company_id": company_id,
        "routes": [{"component": comp, "subcomponent": sub}],
        "component": comp, "subcomponent": sub,
        "direction": direction, "materiality": round(materiality, 4),
        "confidence": round(confidence, 4),
        "published_at": date_iso, "date_basis": "dataset_as_of",
        "source_url": "", "source_type": "dataset",
        "raw_text": text, "raw_text_hash": raw_hash,
        "rationale": _rationale(sub, comp, direction, "dataset", "dataset_as_of", False),
        "model_version": EXTRACTOR_VERSION, "prompt_version": PROMPT_VERSION,
    }


def from_company(company, *, config=None):
    """Every signal a stored company record supports, deduped by signal_id and sorted by id.

    Reads whichever blocks are present — real names carry `esg_basis` text only; demo names carry
    momentum/live_signals/news too. Nothing is synthesised for a company that has no evidence: an
    empty list is a valid, honest answer (it becomes 'low confidence' downstream, the REE case)."""
    cfg = config or engine_config.load()
    c = company if isinstance(company, dict) else {}
    cid = c.get("ticker") or c.get("company_id") or c.get("company") or "unknown"
    as_of = c.get("esg_as_of") or c.get("as_of") or ""
    url = c.get("source_url", "")
    out = {}

    def _add(sig):
        if sig and sig["signal_id"] not in out:
            out[sig["signal_id"]] = sig

    for clause in split_clauses(c.get("esg_basis", "")):
        _add(make_signal(company_id=cid, text=clause, source_url=url,
                         fallback_date=as_of, config=cfg))

    for item in c.get("events") or []:                      # harness / event-timeline input
        if not isinstance(item, dict):
            continue
        _add(make_signal(company_id=cid, text=item.get("text", ""),
                         source_url=item.get("source_url", ""),
                         published_at=item.get("published_at"),
                         source_type=item.get("source_type"),
                         fallback_date=as_of, config=cfg))

    for item in c.get("news") or []:                        # dated headlines (demo set)
        if not isinstance(item, dict):
            continue
        _add(make_signal(company_id=cid, text=item.get("title", ""),
                         source_url=item.get("url", ""),
                         published_at=_as_iso(item.get("date", "")) or None,
                         source_type="news", fallback_date=as_of, config=cfg))

    quality = cfg["source_quality"]["dataset"]
    live = c.get("live_signals") if isinstance(c.get("live_signals"), dict) else {}
    for key, raw in live.items():
        route = _LIVE_SIGNAL_MAP.get(key)
        if not route:
            continue
        comp, sub, direction, materiality = route
        value = _numeric(raw)
        if value is None or value == 0:
            continue                                        # 0 controversy flags = no signal
        # The VALUE's sign decides direction, composed with the family's own polarity: carbon
        # disclosure at -12% is a deterioration, not a positive, while a controversy count is a
        # positive number that always points down. Reading only the family's polarity would
        # score a falling metric as if it were rising.
        signed = direction * (1 if value > 0 else -1)
        _add(_dataset_signal(cid, comp, sub, signed, materiality,
                             f"live signal {key}={raw}", _as_iso(as_of), quality))

    mom = c.get("momentum") if isinstance(c.get("momentum"), dict) else {}
    for key, raw in mom.items():
        route = _PILLAR_MAP.get(key)
        value = _numeric(raw)
        if not route or value is None or value == 0:
            continue
        comp, sub = route
        materiality = min(1.0, abs(value) / 30.0)           # 30% move = fully material
        _add(_dataset_signal(cid, comp, sub, 1 if value > 0 else -1, materiality,
                             f"stored {key} momentum {raw:+g}%", _as_iso(as_of), quality))

    return sorted(out.values(), key=lambda s: s["signal_id"])
