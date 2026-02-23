🧬 SteMy Hub (Level 1 → Level 3 Integration)
Real-Time Experimental Telemetry via FastAPI + Fly.io + SQLite + SSE
🔎 Overview

This repository implements the Level 1 experimental telemetry hub for SteMy.

It provides:

Real-time streaming of experimental state updates (“patches”)

Persistent storage

Run isolation

Idempotent ingestion

Replay / recovery capability

Level 3 can subscribe to a live stream and immediately begin modeling.

This is a production-style deployment hosted on Fly.io.

🏗 System Architecture
(UI / Sensors / Simulator)
          |
          |  HTTPS POST (patch JSON)
          v
     FastAPI Hub (Fly.io)
          |
          |  Persistent SQLite (/data volume)
          |
          +--> SSE Stream Broadcast
                    |
                    v
            Level 3 Modeling System
🔁 Full Workflow (End-to-End)
1️⃣ Researcher / Sensor generates update

A change occurs (e.g., O₂ reading, stage transition, purification metric).

2️⃣ Level 1 sends a PATCH to the Hub
POST /api/runs/{run_id}/patch
3️⃣ FastAPI Hub:

Authenticates request

Deduplicates using patch_id

Stores patch in SQLite

Updates current state snapshot

Broadcasts patch in real time to stream subscribers

4️⃣ Level 3 subscribes to live stream
GET /api/stream/patches?run_id=RUN_DEMO_001
5️⃣ If stream drops

Level 3 calls:

GET /api/runs/{run_id}/export_events?since_ts=<timestamp>

Then resumes streaming.

📦 Patch Format (Data Contract)

Each update is incremental and append-only.

{
  "run_id": "RUN_DEMO_001",
  "patch_id": "uuid-v4",
  "ts": "2026-02-23T17:12:00Z",
  "kv": {
    "env.incubator.o2_measured_percent": {
      "v": 5.02,
      "t": "float",
      "src": "sensor",
      "q": "measured"
    },
    "process.diff.stage": {
      "v": "diff.cardiac_mesoderm",
      "t": "string",
      "src": "inferred",
      "q": "derived"
    }
  },
  "events": [
    {
      "type": "step_started",
      "step_key": "diff.primitive_streak"
    }
  ]
}
Design Principles

Incremental (only changed keys sent)

Append-only

Idempotent (safe to resend)

Timestamped

Structured metadata

🌐 Deployment Details (Fly.io)
Why Fly.io?

Supports long-lived SSE connections

Provides persistent volumes

Simple Docker-based deployment

Stable HTTPS endpoints

Deployment Model

Single Fly machine

SQLite database stored on mounted volume /data

In-memory subscriber list for broadcasting

Critical Fly Configuration

fly.toml must include:

[mounts]
  source = "stemy_data"
  destination = "/data"

[http_service]
  internal_port = 8080
  force_https = true
  auto_start_machines = true
  auto_stop_machines = false
  min_machines_running = 1

⚠️ Do NOT scale to multiple machines while using SQLite.

Secrets

API key stored as Fly secret:

fly secrets set STEMY_API_KEY="YOUR_SECRET"

Deploy:

fly deploy
🔐 Authentication

All endpoints require:

X-API-Key: YOUR_SECRET
📡 Endpoints

Base URL:

https://stemy-hub.fly.dev
Ingest patch
POST /api/runs/{run_id}/patch
Stream patches (SSE)
GET /api/stream/patches?run_id=RUN_DEMO_001
Get current state snapshot
GET /api/runs/{run_id}/state
Backfill missed events
GET /api/runs/{run_id}/export_events?since_ts=<ISO8601>
🚀 2-Minute Live Demo

This demo simulates:

O₂ drift

CO₂ drift

Temperature control

Differentiation stage progression

Progenitor transition scoring

Cardiac marker scoring

Stage boundary events

A patch is emitted every 2 seconds.

Step 1 – Start Stream Listener
curl.exe -N -H 'X-API-Key: YOUR_SECRET' "https://stemy-hub.fly.dev/api/stream/patches?run_id=RUN_DEMO_001"

You should immediately see:

event: hello
data: {}
Step 2 – Run Simulator
$env:STEMY_BASE_URL="https://stemy-hub.fly.dev"
$env:STEMY_API_KEY="YOUR_SECRET"
$env:STEMY_RUN_ID="RUN_DEMO_001"
python .\simulate_stream.py

You will see patches being sent every 2 seconds.

The stream window will update live.

🧠 How Level 3 Should Consume Data
1️⃣ Subscribe to SSE

Keep connection open and parse patch events.

2️⃣ Maintain State

Apply incremental updates:

for key, value in patch["kv"].items():
    state[key] = value
3️⃣ Track patch_id

Avoid double processing.

4️⃣ Store last_ts

Use for recovery.

5️⃣ Recovery Logic

If stream disconnects:

Call /export_events?since_ts=last_ts

Apply missing updates

Reconnect stream

📊 What This Enables for Level 3

You can now:

Build baseline manifolds

Compute Z-score deviations

Rank variable importance

Detect anomalies

Generate intervention recommendations

All without modifying Level 1 transport.

⚠️ MVP Limitations

Single-machine deployment

SQLite persistence

In-memory broadcast

Future scaling:

Replace SQLite with Postgres

Add Redis pub/sub for multi-machine broadcasting

Architecture contract remains unchanged.

🧬 Summary

Level 1 provides:

A real-time, authenticated, append-only experimental telemetry backbone.

Level 3 can immediately subscribe, ingest, model, and recover.

The 2-minute demo proves:

Continuous ingestion

Real-time streaming

Persistent storage

Recovery capability

Clean separation of concerns