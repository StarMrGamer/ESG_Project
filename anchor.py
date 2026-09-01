"""
anchor.py — C2/C3: deterministic Merkle construction + the anchoring step.
==========================================================================
Turns a scoring run's evidence into ONE 32-byte commitment, records it locally, and (when a
chain is configured) writes it to the `EvidenceAnchor` contract on Sepolia.

    leaves = one per signal + one per green-bond verification row (B5)
    root   = merkle_root(sorted(leaves))
    chain  = anchor(run_id, root)  -> tx hash + block number on the run record

**Determinism is the hard requirement** (C2): canonical field order, fixed 4-decimal formatting,
UTF-8, `|` delimiter, leaves sorted by id before pairing, last leaf duplicated on odd counts.
Same inputs → same root, twice, in the test suite (`harness.py --merkle`).

**Every run is anchored, including bad ones.** Anchoring only the flattering runs would be
misleading by omission, so a run that cannot reach the chain is recorded `anchor_pending` and
says so on screen — never silently unanchored.

Chain access is optional and best-effort, exactly like retrieval: no RPC configured, no web3
installed, or a failed transaction all degrade to `anchor_pending`. The demo never depends on a
network being reachable. Secrets come from the environment only (HARD RULE 5):

    ESG_ANCHOR_RPC        https://sepolia.infura.io/v3/...   (or any Sepolia RPC)
    ESG_ANCHOR_CONTRACT   0x...                              (deployed EvidenceAnchor)
    ESG_ANCHOR_KEY        0x...                              (hackathon wallet private key)
    ESG_ANCHOR_EXPLORER   https://sepolia.etherscan.io       (default)
"""

import hashlib
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#: Files whose CONTENT is an input to a published gap, hashed into every run's tree (leaf-v2).
#: Order is fixed; leaves sort by id afterwards, so it only has to be deterministic.
BENCHMARK_FILES = (
    os.path.join(BASE_DIR, "data", "oecd_sector_benchmark.csv"),
    os.path.join(BASE_DIR, "data", "oecd_industry_benchmark.csv"),
)
ANCHOR_DIR = os.path.join(BASE_DIR, "data", "anchors")
CONTRACT_FILE = os.path.join(BASE_DIR, "contracts", "EvidenceAnchor.sol")
DEFAULT_EXPLORER = "https://sepolia.etherscan.io"
CHAIN_NAME = "sepolia"

LEAF_VERSION = "leaf-v2"          # bump ONLY with sign-off: it changes every historical root
#: v2 (2026-08-21) adds the BENCHMARK leaf below. Signed off in `Prototype_Build_Notes.md` §7:
#: "even the yardstick can't be quietly swapped." Adding a leaf kind moves every root, which is
#: why the version moves with it — a v1 anchor stays verifiable as a v1 anchor.


# --------------------------------------------------------------------------- #
#  leaf encoding — the canonical, byte-stable preimage
# --------------------------------------------------------------------------- #
def signal_preimage(signal):
    """`signal_id|raw_text_hash|direction|materiality|confidence|model_version|prompt_version`.

    Fixed 4-dp decimals so 0.5 and 0.50000001 can never collide into "the same" evidence, and so
    a float repr difference between machines can never move the root."""
    return "|".join([
        str(signal.get("signal_id", "")),
        str(signal.get("raw_text_hash", "")),
        f"{int(signal.get('direction', 0)):+d}",
        f"{float(signal.get('materiality', 0.0)):.4f}",
        f"{float(signal.get('confidence', 0.0)):.4f}",
        str(signal.get("model_version", "")),
        str(signal.get("prompt_version", "")),
    ])


def metadata_preimage(row, as_of=""):
    """B5: `company_id|green_bond_status|bond_isin|source_url_1|as_of` — the green-bond
    verification row becomes independently verifiable like every other claim."""
    return "|".join([
        str(row.get("company_id", "")),
        str(row.get("green_bond_status", "")),
        str(row.get("bond_isin", "")),
        str(row.get("source_url_1", "")),
        str(row.get("as_of") or as_of or ""),
    ])


def benchmark_preimage(path):
    """`benchmark|filename|sha256(file bytes)|byte length` — the yardstick itself, as a leaf.

    Hashing the FILE rather than the parsed rows is deliberate: a comment line, a reference
    year or a fallback flag edited in place all change the meaning of a published gap, and all
    of them would survive a row-level digest.

    Returns "" when the file is absent, and an absent benchmark contributes NO leaf rather than
    a leaf hashing the empty string — otherwise "we had no yardstick" and "our yardstick was an
    empty file" would anchor to the same root."""
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return ""
    return "|".join(["benchmark", os.path.basename(path),
                     hashlib.sha256(blob).hexdigest(), str(len(blob))])


def _leaf_hash(preimage):
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def leaves_for_run(run, metadata=None):
    """Every leaf in a run, sorted by `leaf_id` so the tree is independent of input order.

    Returns `[{leaf_id, kind, hash, preimage, company_id}]`. A signal that appears for two
    companies is still one leaf per (company, signal) pair because `signal_id` already hashes the
    company id in."""
    leaves = []
    for record in run.get("records", []):
        for sig in record.get("signals", []):
            preimage = signal_preimage(sig)
            leaves.append({"leaf_id": str(sig.get("signal_id", "")), "kind": "signal",
                           "company_id": record.get("company_id", ""),
                           "hash": _leaf_hash(preimage), "preimage": preimage})
    for cid, row in sorted((metadata or {}).items()):
        row = dict(row or {})
        row.setdefault("company_id", cid)
        preimage = metadata_preimage(row, as_of=run.get("as_of", ""))
        leaves.append({"leaf_id": f"gb:{cid}", "kind": "green_bond", "company_id": cid,
                       "hash": _leaf_hash(preimage), "preimage": preimage})
    for path in BENCHMARK_FILES:
        preimage = benchmark_preimage(path)
        if not preimage:
            continue
        leaves.append({"leaf_id": "bm:%s" % os.path.basename(path), "kind": "benchmark",
                       "company_id": "", "hash": _leaf_hash(preimage), "preimage": preimage})
    leaves.sort(key=lambda leaf: (leaf["leaf_id"], leaf["hash"]))
    return leaves


# --------------------------------------------------------------------------- #
#  tree
# --------------------------------------------------------------------------- #
def _pair(left, right):
    return hashlib.sha256(bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def merkle_root(leaf_hashes):
    """Root over an ORDERED list of hex leaf hashes. Odd level -> duplicate the last node.
    An empty tree is the hash of the empty string — a run with no evidence still commits to
    "no evidence", which is itself a claim worth being unable to rewrite."""
    level = list(leaf_hashes)
    if not level:
        return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_path(leaf_hashes, index):
    """Sibling path for one leaf: `[{position: 'left'|'right', hash}]`, bottom-up. `position` is
    where the SIBLING sits, so verification concatenates in the right order."""
    level = list(leaf_hashes)
    if not level or not 0 <= index < len(level):
        return []
    path = []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = index + 1 if index % 2 == 0 else index - 1
        path.append({"position": "right" if index % 2 == 0 else "left",
                     "hash": level[sibling]})
        level = [_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        index //= 2
    return path


def verify_path(leaf_hash, path, root):
    """Recompute the root from one leaf + its path. The verification page's whole job."""
    node = leaf_hash
    for step in path or []:
        node = (_pair(node, step["hash"]) if step.get("position") == "right"
                else _pair(step["hash"], node))
    return node == root


# --------------------------------------------------------------------------- #
#  the run record  (off-chain; the chain only ever holds run_id -> root)
# --------------------------------------------------------------------------- #
def build_anchor_record(run, metadata=None):
    """`{run_id, root, leaf_count, engine_version, config_hash, as_of, leaf_version, chain,
    status, leaves}` — everything needed to re-verify without re-running the engine."""
    leaves = leaves_for_run(run, metadata)
    return {
        "run_id": run["run_id"],
        "root": merkle_root([leaf["hash"] for leaf in leaves]),
        "leaf_count": len(leaves),
        "engine_version": run.get("engine_version", ""),
        "config_hash": run.get("config_hash", ""),
        "as_of": run.get("as_of", ""),
        "leaf_version": LEAF_VERSION,
        "chain": CHAIN_NAME,
        "status": "anchor_pending",
        "tx_hash": "",
        "block_number": None,
        "block_timestamp": None,
        "signer": "",
        "contract": os.environ.get("ESG_ANCHOR_CONTRACT", ""),
        "leaves": leaves,
    }


def record_path(run_id):
    return os.path.join(ANCHOR_DIR, f"{run_id}.json")


def save_record(record):
    try:
        os.makedirs(ANCHOR_DIR, exist_ok=True)
        with open(record_path(record["run_id"]), "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, sort_keys=True)
        return True
    except OSError:
        return False


def load_record(run_id):
    try:
        with open(record_path(run_id), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def list_records():
    """Every anchor record on disk, newest `as_of` first — the run-status list in the UI."""
    out = []
    try:
        names = sorted(os.listdir(ANCHOR_DIR))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        rec = load_record(name[:-5])
        if rec:
            out.append({k: v for k, v in rec.items() if k != "leaves"})
    out.sort(key=lambda r: (r.get("as_of", ""), r.get("run_id", "")), reverse=True)
    return out


# --------------------------------------------------------------------------- #
#  chain I/O — optional, best-effort, never a hard failure
# --------------------------------------------------------------------------- #
def chain_config():
    """What the environment gives us. `ready` means an anchoring WRITE is possible."""
    rpc = os.environ.get("ESG_ANCHOR_RPC", "").strip()
    contract = os.environ.get("ESG_ANCHOR_CONTRACT", "").strip()
    key = os.environ.get("ESG_ANCHOR_KEY", "").strip()
    return {
        "rpc": rpc, "contract": contract, "has_key": bool(key), "chain": CHAIN_NAME,
        "explorer": os.environ.get("ESG_ANCHOR_EXPLORER", DEFAULT_EXPLORER).rstrip("/"),
        "ready": bool(rpc and contract and key),
        "readable": bool(rpc and contract),
    }


def _web3():
    """web3.py if it is installed AND an RPC is configured, else None. Import is local so the
    app runs — and the demo works — with no web3 dependency at all."""
    cfg = chain_config()
    if not cfg["rpc"]:
        return None, cfg, "no ESG_ANCHOR_RPC configured"
    try:
        from web3 import Web3
    except ImportError:
        return None, cfg, "web3.py not installed (pip install web3)"
    try:
        w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            return None, cfg, "RPC unreachable"
        return w3, cfg, ""
    except Exception as exc:                                   # noqa: BLE001 - best-effort
        return None, cfg, f"RPC error: {exc}"


_ABI = json.loads("""[
 {"inputs":[{"internalType":"bytes32","name":"runId","type":"bytes32"},
            {"internalType":"bytes32","name":"root","type":"bytes32"}],
  "name":"anchor","outputs":[],"stateMutability":"nonpayable","type":"function"},
 {"inputs":[{"internalType":"bytes32","name":"runId","type":"bytes32"}],
  "name":"getAnchor","outputs":[{"internalType":"bytes32","name":"root","type":"bytes32"},
                                {"internalType":"uint64","name":"timestamp","type":"uint64"}],
  "stateMutability":"view","type":"function"},
 {"inputs":[],"name":"signer","outputs":[{"internalType":"address","name":"","type":"address"}],
  "stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],
  "name":"anchors","outputs":[{"internalType":"bytes32","name":"root","type":"bytes32"},
                              {"internalType":"uint64","name":"timestamp","type":"uint64"}],
  "stateMutability":"view","type":"function"}]""")


def _0x(value):
    """A hex identifier as a block explorer expects it: `0x`-prefixed, lower case.

    Stored records are not consistent about this and were never required to be — `contract` and
    `signer` come back from web3 already prefixed, while `tx_hash` is stored bare. Concatenating
    the bare hash into an explorer URL produced
    `https://sepolia.etherscan.io/tx/41065825…`, which Etherscan does not resolve, so the one
    button that lets a reader check the chain for themselves led nowhere. Normalised at the point
    of USE rather than by rewriting the records, because the records are the anchored artefact and
    a display bug is no reason to touch them.
    """
    v = str(value or "").strip()
    if not v:
        return ""
    return v if v.lower().startswith("0x") else "0x" + v


def _run_id_bytes32(run_id):
    """The 16-hex-char run id, right-padded into bytes32 — stable and collision-free."""
    return bytes.fromhex(run_id.encode("utf-8").hex().ljust(64, "0")[:64])


def push_to_chain(record):
    """Send `anchor(run_id, root)`. Returns the updated record; on ANY failure the record stays
    `anchor_pending` with `anchor_note` explaining why — the run is never silently unanchored."""
    w3, cfg, why = _web3()
    if not w3:
        record["anchor_note"] = why
        return record
    if not cfg["ready"]:
        record["anchor_note"] = "read-only: no ESG_ANCHOR_KEY set"
        return record
    try:
        from eth_account import Account
        account = Account.from_key(os.environ["ESG_ANCHOR_KEY"])
        contract = w3.eth.contract(address=w3.to_checksum_address(cfg["contract"]), abi=_ABI)
        tx = contract.functions.anchor(
            _run_id_bytes32(record["run_id"]), bytes.fromhex(record["root"])
        ).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 120000,
            "maxFeePerGas": w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": w3.to_wei(1, "gwei"),
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        record.update(status="anchored", tx_hash=receipt["transactionHash"].hex(),
                      block_number=receipt["blockNumber"], signer=account.address,
                      contract=cfg["contract"], gas_used=receipt.get("gasUsed"),
                      anchor_note="")
        block = w3.eth.get_block(receipt["blockNumber"])
        record["block_timestamp"] = int(block["timestamp"])
    except Exception as exc:                                   # noqa: BLE001 - best-effort
        record["anchor_note"] = f"anchor tx failed: {exc}"
    return record


def fetch_from_chain(run_id):
    """Read the anchor for `run_id` — public RPC, read-only, no wallet. Returns
    `{ok, root, timestamp, signer, contract, explorer_url, note}`; `ok=False` simply means the
    chain could not be reached or the run is not anchored yet."""
    w3, cfg, why = _web3()
    base = {"ok": False, "root": "", "timestamp": None, "signer": "",
            "contract": cfg["contract"], "explorer": cfg["explorer"], "note": why}
    if not w3 or not cfg["readable"]:
        base["note"] = why or "no ESG_ANCHOR_CONTRACT configured"
        return base
    try:
        contract = w3.eth.contract(address=w3.to_checksum_address(cfg["contract"]), abi=_ABI)
        run_key = _run_id_bytes32(run_id)
        # Two ways to read the same slot, and the deployed contract may only offer one. The
        # Sepolia deployment (2026-08-25) has no `getAnchor` — it exposes only the getter Solidity
        # generates for `mapping(bytes32 => Anchor) public anchors`. Calling the missing wrapper
        # reverts with "no data", which `--verify` reported as NO MATCH on a run whose root was
        # on chain and correct: a false tamper alarm, which is the one failure this module must
        # never produce. `anchors` exists on every version of this contract, so it is tried first.
        try:
            root, timestamp = contract.functions.anchors(run_key).call()
        except Exception:                                      # noqa: BLE001 - try the wrapper
            root, timestamp = contract.functions.getAnchor(run_key).call()
        if int(timestamp) == 0:
            base["note"] = "run not anchored on chain yet"
            return base
        base.update(ok=True, root=root.hex(), timestamp=int(timestamp), note="",
                    signer=contract.functions.signer().call())
    except Exception as exc:                                   # noqa: BLE001 - best-effort
        base["note"] = f"chain read failed: {exc}"
    return base


def anchor_run(run, metadata=None, *, push=True):
    """C3: build the record, try the chain, persist either way. Idempotent — an already-anchored
    run returns its stored record untouched (the contract is append-only, so re-sending would
    revert anyway)."""
    existing = load_record(run["run_id"])
    if existing and existing.get("status") == "anchored":
        return existing
    record = build_anchor_record(run, metadata)
    if existing:
        record["leaves"] = record["leaves"] or existing.get("leaves", [])
    if push:
        record = push_to_chain(record)
    save_record(record)
    return record


# --------------------------------------------------------------------------- #
#  verification (C4's engine — the page is a thin skin over this)
# --------------------------------------------------------------------------- #
def verify_company(run_id, company_id, *, evidence=None, check_chain=True):
    """Recompute one company's evidence leaves, walk each Merkle path to the root, and compare
    that root with the anchored one.

    `evidence` optionally overrides the stored preimages — that is the tamper demo: change one
    character and the leaf hash, the root, and the verdict all move. Returns a payload the page
    renders directly."""
    record = load_record(run_id)
    if not record:
        return {"ok": False, "status": "unknown_run",
                "note": f"No anchor record for run {run_id}."}

    leaf_hashes = [leaf["hash"] for leaf in record["leaves"]]
    supplied = {item.get("leaf_id"): item.get("preimage") for item in (evidence or [])}
    rows, recomputed_hashes = [], list(leaf_hashes)
    for index, leaf in enumerate(record["leaves"]):
        if leaf.get("company_id") != company_id and company_id:
            continue
        preimage = supplied.get(leaf["leaf_id"], leaf["preimage"])
        digest = _leaf_hash(preimage)
        recomputed_hashes[index] = digest
        rows.append({
            "leaf_id": leaf["leaf_id"], "kind": leaf["kind"], "preimage": preimage,
            "stored_hash": leaf["hash"], "recomputed_hash": digest,
            "leaf_ok": digest == leaf["hash"],
            "path_ok": verify_path(digest, merkle_path(leaf_hashes, index), record["root"]),
            "index": index,
        })

    if company_id and not rows:
        # No leaves for this company: recomputing an untouched tree would trivially "MATCH" and
        # show a green verdict for a company we hold no evidence about. Say so instead.
        return {"ok": False, "status": "no_evidence", "run_id": run_id, "company_id": company_id,
                "stored_root": record["root"], "recomputed_root": record["root"],
                "leaf_count": record["leaf_count"], "rows": [],
                "anchor_status": record.get("status", "anchor_pending"),
                "note": f"No evidence leaves for {company_id} in run {run_id} — nothing to verify."}

    recomputed_root = merkle_root(recomputed_hashes)
    local_match = recomputed_root == record["root"]
    payload = {
        "ok": local_match,
        "status": "MATCH" if local_match else "NO MATCH",
        "run_id": run_id,
        "company_id": company_id,
        "stored_root": record["root"],
        "recomputed_root": recomputed_root,
        "leaf_count": record["leaf_count"],
        "rows": rows,
        "anchor_status": record.get("status", "anchor_pending"),
        "tx_hash": record.get("tx_hash", ""),
        "block_number": record.get("block_number"),
        "block_timestamp": record.get("block_timestamp"),
        "signer": record.get("signer", ""),
        "contract": record.get("contract", ""),
        "chain": record.get("chain", CHAIN_NAME),
        "explorer_url": "",
        "chain_checked": False,
        "chain_match": None,
        "note": record.get("anchor_note", ""),
    }
    cfg = chain_config()
    if record.get("tx_hash"):
        payload["explorer_url"] = f"{cfg['explorer']}/tx/{_0x(record['tx_hash'])}"
    elif record.get("contract"):
        payload["explorer_url"] = f"{cfg['explorer']}/address/{_0x(record['contract'])}"

    if check_chain and cfg["readable"]:  # noqa: PLR0915 - one branch, kept with its payload
        chain = fetch_from_chain(run_id)
        payload["chain_checked"] = True
        payload["chain_match"] = bool(chain["ok"]) and chain["root"].lower().lstrip("0x") == \
            record["root"].lower()
        if chain["ok"]:
            payload.update(block_timestamp=chain["timestamp"], signer=chain["signer"] or
                           payload["signer"])
        else:
            payload["note"] = chain["note"] or payload["note"]
        payload["ok"] = local_match and bool(payload["chain_match"])
        payload["status"] = "MATCH" if payload["ok"] else "NO MATCH"
    return payload


# --------------------------------------------------------------------------- #
#  CLI — build and anchor runs (C5 wants >= 3 real anchored runs before 23 Aug)
# --------------------------------------------------------------------------- #
def _cli(argv):
    import company_metadata
    import engine
    import engine_config
    import universe

    if "--list" in argv:
        rows = list_records()
        cfg = chain_config()
        print(f"anchored runs ({len(rows)}) · chain {cfg['chain']} · "
              f"{'RPC configured' if cfg['readable'] else 'no RPC configured'}")
        for row in rows:
            print(f"  {row['run_id']}  {row.get('status','?'):14s} root {row['root'][:20]}…  "
                  f"{row['leaf_count']:4d} leaves  as_of {row.get('as_of','')}"
                  + (f"  tx {row['tx_hash'][:14]}…" if row.get("tx_hash") else ""))
        return 0

    if "--verify" in argv:
        i = argv.index("--verify")
        run_id = argv[i + 1] if len(argv) > i + 1 else ""
        company = argv[i + 2] if len(argv) > i + 2 else ""
        payload = verify_company(run_id, company)
        print(f"{payload['status']} — run {run_id} · {company}")
        print(f"  stored root      {payload.get('stored_root','')}")
        print(f"  recomputed root  {payload.get('recomputed_root','')}")
        print(f"  leaves checked   {len(payload.get('rows', []))} of {payload.get('leaf_count',0)}")
        if payload.get("note"):
            print(f"  note             {payload['note']}")
        return 0 if payload.get("ok") else 1

    push = "--no-push" not in argv
    # Every horizon is anchored, not just the default. The Short and Long views are different
    # runs over the same evidence, so a judge who flips the toggle and clicks Verify must get a
    # real answer either way — an unanchored half of the product is worse than no toggle. It is
    # also the same rule as 9b: anchor every run, including the ones that do not flatter us.
    horizons = sorted(engine_config.horizons()) or [engine_config.DEFAULT_HORIZON]
    for demo in (True, False):
        source = universe.active_file(demo)
        # Metadata follows the universe — the mock rows key on the fictional tickers, the
        # verified CSV on the real 52. Loading one set for both anchors a tree whose green-bond
        # leaves belong to companies that are not in the run.
        metadata = company_metadata.load(demo=demo)
        # The board merges harvested evidence for the real basket, so this MUST too. Anchoring a
        # run built from different inputs would produce a root the verification page can never
        # reproduce — it recomputes leaves from the run the user is looking at, and would report
        # NO MATCH on evidence nobody had tampered with.
        cons = universe.constituents(source)
        if not demo:
            import harvest
            cons = harvest.apply_overlay(
                cons, as_of=universe.load_universe(source).get("as_of") or "")
        for name in horizons:
            cfg = engine_config.for_horizon(name)
            run = engine.run_engine(cons, metadata=metadata, config=cfg)
            record = anchor_run(run, metadata, push=push)
            scope = ("demo (fictional)" if demo else "real ASEAN base DB") + f" · {name}"
            print(f"{scope:26s} run {record['run_id']}  root {record['root'][:20]}…  "
                  f"{record['leaf_count']} leaves  -> {record['status']}")
            if record.get("anchor_note"):
                print(f"{'':26s} note: {record['anchor_note']}")
    cfg = chain_config()
    if not cfg["ready"]:
        print("\nRecords stored locally and marked `anchor_pending` — they are NEVER silently "
              "unanchored.\nTo write them to Sepolia, set ESG_ANCHOR_RPC, ESG_ANCHOR_CONTRACT and "
              "ESG_ANCHOR_KEY\nand re-run `python anchor.py` (the contract is append-only, so "
              "re-running is safe).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
