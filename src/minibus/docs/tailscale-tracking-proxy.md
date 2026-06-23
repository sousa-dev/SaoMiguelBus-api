# Tailscale home proxy for Eleven Systems AVL

Live minibus tracking pulls fleet positions from Eleven Systems:

- Upstream: `https://pdl.elevensystems.pt/publicapi/locations`
- Detail: `https://pdl.elevensystems.pt/publicapi/locations/{id}`

The Django gateway (`minibus/tracking_client.py` → `GET /api/v3/minibus/vehicles`) uses **`MINIBUS_TRACKING_BASE_URL`** as the root and appends `/locations` paths. Any compatible reverse proxy can sit in front of the upstream without code changes.

## Why a home Raspberry Pi proxy exists

Cloudflare in front of `pdl.elevensystems.pt` often **blocks datacenter egress IPs** (e.g. Hetzner Frankfurt). Symptoms on the API host:

- `curl https://pdl.elevensystems.pt/publicapi/locations` → **403** with HTML (`Attention Required! | Cloudflare`)
- SMB API logs: `tracking_unavailable` / `Upstream HTTP 403`
- `cf-ray` edge may show **FRA** (datacenter) vs **LIS** (residential Portugal) when it works

Residential IPs (home laptop, Raspberry Pi on ISP) typically get **200 JSON**.

**Proper long-term fix:** ask Eleven Systems / PDL to **allowlist** Hetzner (and prod) API egress IPs in Cloudflare for `/publicapi/*`.

**Interim fix:** run a small reverse proxy on a **home Raspberry Pi** on **Tailscale**, and point `MINIBUS_TRACKING_BASE_URL` at the Pi’s Tailscale address so Hetzner fetches AVL over the mesh instead of directly from Frankfurt.

## Architecture

```text
Expo app
  → GET /api/v3/minibus/vehicles (Hetzner SMB API)
       → requests.get(MINIBUS_TRACKING_BASE_URL + "/locations")
            → Tailscale mesh (100.x.x.x)
                 → RPi reverse proxy :8080
                      → https://pdl.elevensystems.pt/publicapi/...  (residential egress)
```

Traffic between Hetzner and the Pi stays on **Tailscale** (encrypted). The proxy should **not** be exposed on the public internet.

## API configuration (Hetzner / Dokploy)

In `src/src/.env` (Environment tab):

```env
# Point at the Pi proxy (Tailscale IP), not the public Eleven URL
MINIBUS_TRACKING_BASE_URL=http://100.x.y.z:8080/publicapi
# Same secret as on the Pi — sent as X-Tracking-Proxy-Key on every upstream request
MINIBUS_TRACKING_PROXY_KEY=your-proxy-secret

# Other tuning vars unchanged
MINIBUS_TRACKING_CACHE_TTL=10
MINIBUS_TRACKING_STALE_GRACE=60
MINIBUS_TRACKING_TIMEOUT=10
```

Restart the **web** container after changing these values.

The client builds URLs like:

- `{MINIBUS_TRACKING_BASE_URL}/locations`
- `{MINIBUS_TRACKING_BASE_URL}/locations/{tracking_id}`

So the proxy must forward `/publicapi/*` to `https://pdl.elevensystems.pt/publicapi/*` with the same path.

## Raspberry Pi proxy (operator notes)

The proxy itself is **not** in this repo — it runs on the Pi (Caddy, nginx, or similar). Typical requirements:

| Requirement | Detail |
|-------------|--------|
| Bind address | Pi **Tailscale IP** (`tailscale ip -4`), not `0.0.0.0` on LAN |
| Port | e.g. `8080` |
| Path | `/publicapi/*` → `https://pdl.elevensystems.pt/publicapi/*` |
| Boot | `systemd` unit, `systemctl enable` |
| Auth | Header `X-Tracking-Proxy-Key` — when enabled on the proxy, set `MINIBUS_TRACKING_PROXY_KEY` on the API to the same value |

Operator docs on the Pi often live at `~/smb-tracking-proxy/README.md` and env at `/etc/smb-tracking-proxy.env`.

### Verify from the Pi

```bash
tailscale ip -4
curl -sS -H "X-Tracking-Proxy-Key: $PROXY_SECRET" \
  "http://<TAILSCALE_IP>:8080/publicapi/locations" | head -c 200
# Expect: [{"id":
```

### Verify from Hetzner (over Tailscale)

```bash
curl -sS -H "X-Tracking-Proxy-Key: $PROXY_SECRET" \
  "http://<PI_TAILSCALE_IP>:8080/publicapi/locations" | head -c 200
```

### Verify SMB API after env change

```bash
curl -sS -H "X-Island: sao-miguel" \
  "https://staging.api.saomiguelhub.com/api/v3/minibus/vehicles" | head -c 300
```

Expect `vehicles` array, not `tracking_unavailable`.

## Related code and docs

| Path | Role |
|------|------|
| `minibus/tracking_client.py` | HTTP client; `MINIBUS_TRACKING_BASE_URL` + optional `MINIBUS_TRACKING_PROXY_KEY` |
| `minibus/services_tracking.py` | Redis cache-aside, stale fallback |
| `minibus/api_v3.py` | `vehicles_list_view`, `vehicle_detail_view` |
| `minibus/README.md` | Module overview + link here |
| `src/src/.env.example` | `MINIBUS_TRACKING_*` variables |
| `AGENTS.md` | Deploy env table |

## Mobile app

The Expo client only calls **`/api/v3/minibus/vehicles`** on the SMB API — it never talks to Eleven Systems or the Pi directly. No app changes are required when switching between direct upstream and Tailscale proxy; only `MINIBUS_TRACKING_BASE_URL` on the backend changes.

## When to remove the proxy

Once Eleven Systems allowlists Hetzner/prod egress IPs:

1. Set `MINIBUS_TRACKING_BASE_URL=https://pdl.elevensystems.pt/publicapi`
2. Confirm `curl` from the API container returns JSON
3. Optionally retire the Pi proxy service
