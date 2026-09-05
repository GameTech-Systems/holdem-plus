# Deploying the Hold'em Plus demo

This repo now has ready-to-use config for all three platforms HANDOFF.md
names (Render, Fly.io, Railway): `render.yaml`, `fly.toml` + `Dockerfile`,
and `Procfile` + `Dockerfile` respectively. Pick one -- you don't need all
three, they just coexist harmlessly since each platform only looks for its
own file.

**Important, before you pick one:** this backend keeps every table, guest,
and hand in plain in-memory Python dicts (`TABLES`/`GUESTS` in `api.py`).
That means:
- **Exactly one worker, one instance, always.** All three configs below
  already pin this (`--workers 1`, one Render/Railway service, one Fly
  machine). Don't turn on autoscaling or add a second instance/replica --
  two processes each get their own empty copy of `TABLES`, so a player
  could hit a different instance mid-hand and find their table "doesn't
  exist." This isn't a rate-limit tuning knob, it's a correctness
  requirement until someone replaces that in-memory state with Redis/DB
  (see HANDOFF.md Section 4).
- **A restart wipes every table.** Deploys, crashes, and (on free tiers)
  idle-timeout scale-to-zero all restart the process, which loses
  everything. Fine for a demo link people click into fresh; not fine if
  you need tables to survive a redeploy.

## Why I (the assistant) can't just deploy this myself

I don't have credentials for Render, Fly.io, or Railway, and this
sandbox's network access is restricted to a fixed allowlist of domains
(package registries, GitHub, Anthropic's own API) that doesn't include any
of those three services -- so even with credentials I couldn't reach them
from here. Everything below is written so you can run it yourself in a
few minutes; I've verified the actual commands each config runs (the pip
install and the exact `uvicorn` invocation) against a real venv in this
session, just not the platform-specific build/deploy step itself.

---

## Option A -- Render (simplest, no Docker needed)

1. Push this repo to GitHub (it already needs to be there for Render to
   see it).
2. In the Render dashboard: **New -> Blueprint**, point it at this repo.
   Render reads `render.yaml` automatically and provisions the service.
3. Confirm the health check passes (`render.yaml` points it at `/health`,
   which just returns `{"status": "ok"}`).
4. Your URL will look like `https://holdem-plus-demo.onrender.com` (or
   whatever name you gave the service). Test it via
   `https://<your-url>/health` first, then `/app/` for the demo client.
5. Free-tier services spin down after a period of no traffic and cold-start
   on the next request -- see the in-memory caveat above. Upgrade to a paid
   plan (no scale-to-zero) if you need it to stay warm.

No Dockerfile involved in this path -- `render.yaml` uses Render's native
Python runtime and just runs `pip install -r requirements.txt` then the
`uvicorn` command directly.

## Option B -- Fly.io

1. Install `flyctl` if you don't have it:
   `curl -L https://fly.io/install.sh | sh` (see fly.io's own docs if
   that URL changes).
2. `fly auth login`.
3. **Rename the app first** -- `fly.toml`'s `app = "holdem-plus-demo"` is a
   placeholder; Fly app names are globally unique, so change it to
   something like `holdem-plus-demo-yourname` before continuing, or
   `fly launch` will reject it if that name's taken.
4. From the repo root: `fly launch --no-deploy` (it will detect the
   existing `fly.toml` and `Dockerfile` and ask to reuse them -- say yes),
   then `fly deploy`.
5. `fly.toml` sets `min_machines_running = 1` specifically so the table
   state doesn't vanish between requests -- see the comment in that file
   for the tradeoff if you'd rather allow scale-to-zero.
6. Your URL will be `https://<your-app-name>.fly.dev`.

## Option C -- Railway

1. In the Railway dashboard: **New Project -> Deploy from GitHub repo**,
   pick this repo.
2. Railway auto-detects `requirements.txt` and the `Procfile` and builds
   without any extra config (it can also just build the `Dockerfile`
   directly if you prefer -- either works, they run the same command).
3. Railway sets `$PORT` automatically; the `Procfile`'s command
   (`uvicorn api:app --host 0.0.0.0 --port $PORT --workers 1`) already
   reads it.
4. Generate a public domain for the service from Railway's dashboard
   (Settings -> Networking -> Generate Domain) to get your shareable URL.
5. Railway's free tier is usage-metered rather than idle-scale-to-zero by
   default, but confirm your plan's actual sleep behavior before treating
   the link as always-on.

---

## After it's live

- Sanity-check exactly like the earlier Codespaces verification did:
  `GET /health`, then open `/app/` in two separate browser tabs (or one
  normal + one incognito, so they get different guest ids) and play a
  full hand across both.
- Specifically re-check **Bug 1** (the `/app` redirect) on the real public
  URL, not just locally -- request `https://<your-url>/app` (no trailing
  slash) directly and confirm it redirects correctly rather than to
  `localhost`. This is exactly the failure mode the fix targets, and a
  real reverse-proxied deployment is the only way to see it for real
  rather than by simulating a non-default `Host` in a test.
- If you're using a platform's free tier and the link goes cold between
  demos, the first request after idle will be slow (cold start) and any
  tables that existed before the sleep will be gone -- both expected,
  given the in-memory-only design documented above and in HANDOFF.md.
