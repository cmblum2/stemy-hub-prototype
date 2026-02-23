**🧬 SteMy Hub**
Level 1 → Level 3 Real-Time Experimental Telemetry
Overview

This repository implements the Level 1 experimental telemetry hub for SteMy.

It provides:

    Real-time streaming of experimental state updates ("patches")

    Persistent storage

    Run isolation

    Idempotent ingestion

    Replay and recovery capability

Level 3 can subscribe to a live stream and immediately begin modeling.

  Deployment stack:

    FastAPI

    Fly.io

    SQLite (persistent volume)

    Server-Sent Events (SSE)


**Full Workflow**
_1. Researcher or Sensor Generates Update_

         Examples:

            O₂ reading
        
            Differentiation stage transition
    
            Purification metric

            Manual parameter input

_ 2. Level 1 Sends a PATCH_
        POST /api/runs/{run_id}/patch

_4. FastAPI Hub_

    The Hub performs:

        Authentication validation

        patch_id deduplication

        SQLite persistence

        Snapshot update

        Real-time broadcast to subscribers

_4. Level 3 Subscribes to Stream_
GET /api/stream/patches?run_id=RUN_DEMO_001
_

_5. Recovery If Stream Drops_
GET /api/runs/{run_id}/export_events?since_ts=<timestamp>

Recommended recovery flow for level 3 deployment:

    Store last_ts

    Call backfill endpoint

    Resume stream

**Patch Format (Data Contract)**

Each patch is incremental and append-only.

    {
      "run_id": "RUN_DEMO_001",
      "patch_id": "unique-id",
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
**
API Endpoints**

_Base URL:_
        https://stemy-hub.fly.dev
_Ingest Patch_
        POST /api/runs/{run_id}/patch
_Stream Patches (SSE)_
        GET /api/stream/patches?run_id=RUN_DEMO_001
_Get Current Snapshot_
        GET /api/runs/{run_id}/state
_Backfill Missed Events_
        GET /api/runs/{run_id}/export_events?since_ts=<ISO8601>

**Authentication**

_All endpoints require:_

    X-API-Key: YOUR_SECRET

    The secret is stored securely in Fly.io and is not committed to this repository.

    Deployment Details (Fly.io)

The hub is deployed using:

    Single Fly machine

    SQLite stored on mounted volume /data

    In-memory broadcast for SSE

**Required fly.toml configuration:**

        [mounts]
          source = "stemy_data"
          destination = "/data"
        
        [http_service]
          internal_port = 8080
          force_https = true
          auto_start_machines = true
          auto_stop_machines = false
          min_machines_running = 1


**2-Minute Live Demo**

This demo simulates:

    O₂ drift

    CO₂ drift

    Temperature control

    Differentiation stage progression

    Progenitor transition scoring

    Cardiac marker scoring

    Stage boundary events

A patch is emitted every 2 seconds.

    Step 1 — Start Stream Listener
    curl.exe -N -H "X-API-Key: YOUR_SECRET" `
    "https://stemy-hub.fly.dev/api/stream/patches?run_id=RUN_DEMO_001"
    
    You should see:
    
    event: hello
    data: {}
    Step 2 — Run Simulator
    $env:STEMY_BASE_URL="https://stemy-hub.fly.dev"
    $env:STEMY_API_KEY="YOUR_SECRET"
    $env:STEMY_RUN_ID="RUN_DEMO_001"
    python .\simulate_stream.py
    
    You will now see real-time patches streaming.

**Level 3 Integration Summary**

  Level 3 should:

    Subscribe to SSE stream

    Apply incremental kv updates

    Track patch_id for deduplication

    Store last_ts

    Use backfill endpoint if disconnected

**Summary**

Level 1 provides a real-time, authenticated, append-only experimental telemetry backbone.

Level 3 can immediately subscribe, ingest, model, and recover.

The 2-minute demo proves:

Continuous ingestion

Real-time streaming

Persistent storage

Recovery capability

Clean separation of concerns
