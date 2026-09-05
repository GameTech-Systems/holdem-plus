# Container image for the Hold'em Plus demo API.
#
# Works as-is for Fly.io and Railway (both detect and build a root-level
# Dockerfile automatically) and for Render's "Docker" runtime (Render's
# native Python runtime, used by render.yaml in this repo, does NOT need
# this file at all -- see render.yaml / DEPLOYMENT.md for that path).
#
# Single-worker by design: TABLES/GUESTS in api.py are module-level
# in-memory dicts (see api.py's own module docstring and HANDOFF.md
# Section 3). Running more than one worker/process/machine against the
# same table would split that state across processes that can't see each
# other -- silently breaking gameplay, not just failing loudly. Do not
# raise --workers or run multiple instances/replicas without first
# replacing that in-memory state with something shared (Redis/DB).

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached across rebuilds
# that only change application code, not requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Most platforms (Render, Railway) inject $PORT and expect the app to
# bind to it; Fly.io is told the port explicitly via fly.toml's
# internal_port instead and does not require $PORT to be set, so this
# defaults to 8000 to match fly.toml when it isn't.
EXPOSE 8000
ENV PORT=8000

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT} --workers 1"]
