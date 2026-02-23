🧬 SteMy Hub
Level 1 → Level 3 Real-Time Experimental Telemetry
🔎 Overview

This repository implements the Level 1 experimental telemetry hub for SteMy.

It provides:

✅ Real-time streaming of experimental state updates (“patches”)

✅ Persistent storage

✅ Run isolation

✅ Idempotent ingestion

✅ Replay / recovery capability

Level 3 can subscribe to a live stream and immediately begin modeling.

This system is deployed using:

FastAPI

Fly.io

SQLite (persistent volume)

Server-Sent Events (SSE)

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
1️⃣ Researcher / Sensor Generates Update

A change occurs:

O₂ reading

Differentiation stage transition

Purification metric

Manual parameter input

2️⃣ Level 1 Sends a PATCH to the Hub
POST /api/runs/{run_id}/patch
3️⃣ FastAPI Hub Performs

Authentication validation

patch_id deduplication

SQLite persistence

Snapshot update

Real-time broadcast to subscribers

4️⃣ Level 3 Subscribes to Stream
GET /api/stream/patches?run_id=RUN_DEMO_001
5️⃣ Recovery (If Stream Drops)
GET /api/runs/{run_id}/export_events?since_ts=<timestamp>

Then reconnect to stream.

📦 Patch Format (Data Contract)

Each patch is incremental and append-only.

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
🔬 Design Principles

Incremental updates (only changed keys sent)

Append-only event architecture

Idempotent ingestion via patch_id

Time-stamped for replay and modeling

Structured metadata for downstream feature engineering

🌐 Deployment (Fly.io)
Why Fly.io?

Supports long-lived SSE connections

Provides persistent volumes

Simple Docker-based deployment

Stable HTTPS endpoints

Deployment Model

Single Fly machine

SQLite database stored at /data

In-memory subscriber list for broadcasting

Required fly.toml Configuration
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

Store API key securely:

fly secrets set STEMY_API_KEY="YOUR_SECRET"

Deploy:

fly deploy
🔐 Authentication

All endpoints require:

X-API-Key: YOUR_SECRET
📡 API Endpoints

Base URL:

https://stemy-hub.fly.dev
Ingest Patch
POST /api/runs/{run_id}/patch
Stream Patches (SSE)
GET /api/stream/patches?run_id=RUN_DEMO_001
Get Current Snapshot
GET /api/runs/{run_id}/state
Backfill Missed Events
GET /api/runs/{run_id}/export_events?since_ts=<ISO8601>
🚀 2-Minute Live Demo

The demo simulates:

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

You should see:

event: hello
data: {}
Step 2 – Run Simulator
$env:STEMY_BASE_URL="https://stemy-hub.fly.dev"
$env:STEMY_API_KEY="YOUR_SECRET"
$env:STEMY_RUN_ID="RUN_DEMO_001"
python .\simulate_stream.py

Patches will appear in real time in the stream window.

🧠 Level 3 Integration Logic
Maintain State
for key, value in patch["kv"].items():
    state[key] = value
Track

patch_id (dedupe)

last_ts (for recovery)

Recovery Flow

Call backfill endpoint with since_ts

Apply missed updates

Reconnect to SSE stream

📊 What This Enables

Level 3 can now:

Build baseline manifolds

Compute Z-score deviations

Rank variable importance

Detect anomalies

Generate intervention recommendations

Without modifying Level 1 transport.

⚠️ MVP Constraints

Single-machine deployment

SQLite persistence

In-memory broadcast

Future scaling:

Replace SQLite with Postgres

Add Redis pub/sub for horizontal scaling

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
