# Deploying the ASEAN ESG Momentum Radar

Written for a **publicly reachable** personal server. Read the security section before you
expose anything — the app has **no authentication on any endpoint**, and several of them spend
money or make outbound requests from your IP.

---

## The two things that most often go wrong

**1. There is no UI in a fresh clone.** `web/dist` is git-ignored, and `server.py` mounts it only
if the directory exists. Clone + run gives you a working API and a **404 on `/`**. You must build
it, or copy a build up:

```bash
./deploy/build.sh                      # needs Node 18+ on the server
# …or build locally and ship the output:
cd web && npm install && npm run build
rsync -a web/dist/ user@server:/srv/esg-radar/web/dist/
```

**2. The app port stays reachable behind your proxy** unless you bind it to loopback. Set
`HOST=127.0.0.1` — otherwise anyone can skip nginx (and its auth) by hitting `:8000` directly.

---

## Install

```bash
sudo useradd --system --home /srv/esg-radar --shell /usr/sbin/nologin esg
sudo git clone https://github.com/StarMrGamer/ESG_Project.git /srv/esg-radar
sudo chown -R esg:esg /srv/esg-radar

sudo -u esg /srv/esg-radar/deploy/build.sh     # venv + npm build + harness + selftest

sudo cp /srv/esg-radar/deploy/esg-radar.service /etc/systemd/system/
sudo cp /srv/esg-radar/deploy/esg-radar.env.example /etc/esg-radar.env
sudo chmod 600 /etc/esg-radar.env && sudo nano /etc/esg-radar.env
sudo systemctl daemon-reload && sudo systemctl enable --now esg-radar

curl -s localhost:8000/api/health
journalctl -u esg-radar -f
```

`build.sh` runs the harness and the selftest and refuses to pretend a broken build is fine. It
also anchors the current runs so the verification page works on first load.

---

## Security — read this before exposing it

There is **no auth on any endpoint**. CORS is set to dev origins, which constrains browsers and
does nothing to `curl`. These are the endpoints that matter:

| endpoint | what an anonymous caller gets |
|---|---|
| `/api/stage1/ask`, `/api/stage2/run`, `/api/stage2/quick` | DeepSeek calls **billed to your key** |
| `/api/monitor` (free text) | live outbound web fetches **from your server's IP** |
| `/api/upload` | file parsing, and an LLM extraction call for `.csv`/`.txt` |

Pick one of these three postures.

### A. Demo instance, no API key (simplest, zero money risk)

Leave `DEEPSEEK_API_KEY` unset. You lose **only** the Stage 1→2→3 deep dive. Everything the
Build Spec demo walks through still works: the universe, the disagreement matrix, tier flips,
N/M/K, badges, the evidence trail with per-signal rationale, and on-chain verification.
`/api/health` reports `llm_configured: false` rather than failing obscurely.

This is the right default for a link you hand to judges.

### B. Basic auth at the proxy (full functionality)

```nginx
server {
    listen 443 ssl http2;
    server_name esg.example.org;
    # ssl_certificate ... (certbot)

    auth_basic           "ESG Radar";
    auth_basic_user_file /etc/nginx/.htpasswd;   # htpasswd -c /etc/nginx/.htpasswd you

    client_max_body_size 6m;                     # mirror ESG_MAX_UPLOAD_MB

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # /api/stage2/run is Server-Sent Events — buffering breaks the progress stream
        proxy_buffering    off;
        proxy_read_timeout 300s;
    }
}
```

With auth in front, setting `DEEPSEEK_API_KEY` is reasonable. Keep `HOST=127.0.0.1`.

### C. VPN / Tailscale only

Bind to the tailnet address and skip the proxy. Safest, least convenient to share.

### Regardless of posture

- `ESG_MAX_UPLOAD_MB` caps in-memory uploads (default 5). Mirror it in `client_max_body_size`.
- Add a rate limit if the instance is public and keyed — `limit_req_zone` on `/api/stage1|stage2`
  is enough to stop a scripted wallet drain.
- `ESG_ANCHOR_KEY` is a **wallet private key**. Use a throwaway hackathon wallet holding only
  testnet ETH. Never a real one. `/etc/esg-radar.env` should be `chmod 600`.
- Outbound HTTP is required by design (retrieval, DeepSeek, the Sepolia RPC), so don't firewall
  egress to nothing — retrieval degrades gracefully, but the deep dive needs the API.

---

## Runtime paths that must be writable

The systemd unit runs with `ProtectSystem=strict` and grants exactly these:

| path | why |
|---|---|
| `.cache/` | RAG retrieval cache + the engine's per-run cache |
| `data/watchlist.json` | pinned tickers (runtime state, git-ignored) |
| `data/anchors/` | anchor records; `/api/verify` writes one on demand if missing |

---

## Updating

```bash
cd /srv/esg-radar
sudo -u esg git pull
sudo -u esg ./deploy/build.sh          # re-installs deps, rebuilds UI, re-runs the checks
sudo systemctl restart esg-radar
```

If `harness.py` reports drift after a pull, **do not paper over it**: a changed `config_hash`
with no per-company drift is a safe re-freeze (`python harness.py --update-golden`); per-company
drift means the engine's numbers moved and someone should know why.

---

## Anchoring from the server (Build Spec C3/C5)

Runs are recorded `anchor_pending` until a chain is configured, and the UI says so — a run is
never silently unanchored. To anchor for real:

```bash
sudo -u esg /srv/esg-radar/venv/bin/pip install web3
# set ESG_ANCHOR_RPC / ESG_ANCHOR_CONTRACT / ESG_ANCHOR_KEY in /etc/esg-radar.env
sudo -u esg --preserve-env /srv/esg-radar/venv/bin/python anchor.py
sudo -u esg /srv/esg-radar/venv/bin/python anchor.py --list
```

The contract is append-only, so re-running is safe: an already-anchored run returns its stored
record untouched.

---

## Health check

```bash
curl -s localhost:8000/api/health
# {"ok":true,"llm_configured":false,"model":"deepseek-v4-flash",...}
```

`llm_configured: false` is expected and correct under posture A — it means the deep-dive relay
is off, not that the app is broken.
