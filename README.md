# SteMy Hub Prototype (Level 1 → Level 3 Real-Time Patch Stream)

This repo is a minimal working prototype that proves Level 1 can deliver real-time experimental updates ("patches") to Level 3.

## What this server does
- Accepts incremental JSON patches:
  - `POST /api/runs/{run_id}/patch`
- Stores:
  - append-only event history (`run_kv_events`)
  - latest snapshot per key (`run_kv_current`)
- Streams accepted patches in real time via SSE:
  - `GET /api/stream/patches?run_id=...`
- Supports recovery/backfill:
  - `GET /api/runs/{run_id}/export_events?since_ts=...`

## Patch format
```json
{
  "run_id": "RUN_TEST_001",
  "patch_id": "PATCH_1",
  "ts": "2026-02-23T17:12:00Z",
  "kv": {
    "example.key": { "v": 123, "t": "float", "src": "human", "q": "measured" }
  },
  "events": []
}