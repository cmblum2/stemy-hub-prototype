import os
import time
import json
import uuid
import random
from datetime import datetime, timezone

import requests

# -----------------------
# CONFIG (edit these)
# -----------------------
BASE_URL = os.getenv("STEMY_BASE_URL", "https://stemy-hub.fly.dev")
API_KEY  = os.getenv("STEMY_API_KEY", "89310a35-6420-433b-9bc5-226955510fae0d649592-61e6-4ef1-b435-8bc5003b47e3")
RUN_ID   = os.getenv("STEMY_RUN_ID", "RUN_DEMO_001")

INTERVAL_SEC = float(os.getenv("STEMY_INTERVAL_SEC", "2.0"))
DURATION_SEC = float(os.getenv("STEMY_DURATION_SEC", "120"))  # 2 minutes demo by default

# -----------------------
# Helpers
# -----------------------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def post_patch(patch: dict) -> dict:
    url = f"{BASE_URL}/api/runs/{RUN_ID}/patch"
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, data=json.dumps(patch), timeout=20)
    r.raise_for_status()
    return r.json()

def make_value(v, t, src="sensor", q="measured"):
    return {"v": v, "t": t, "src": src, "q": q}

# -----------------------
# Simulation state
# -----------------------
# Incubator targets
o2_target = 5.0         # e.g., hypoxia incubator
co2_target = 5.0
temp_target = 37.0

# Current readings
o2 = o2_target
co2 = co2_target
temp = temp_target

# Differentiation progression (0..1)
prog = 0.0

# Stage machine
# 0: hPSC maintenance
# 1: primitive streak / mesoderm induction
# 2: cardiac mesoderm
# 3: immature cardiomyocyte
# 4: mature cardiomyocyte (not reached in short demo)
stage = 0
stage_names = [
    "maintenance.hpsc",
    "diff.primitive_streak",
    "diff.cardiac_mesoderm",
    "diff.immature_cardiomyocyte",
    "diff.mature_cardiomyocyte",
]

# We'll "advance stage" at certain progression values
stage_thresholds = [0.0, 0.20, 0.45, 0.75, 1.00]  # demo-friendly

# Occasionally inject an "O2 disturbance"
disturbance_timer = 0

def maybe_disturb_o2():
    global disturbance_timer, o2
    # every ~30-50 seconds create a transient dip or spike lasting ~10 seconds
    if disturbance_timer <= 0 and random.random() < 0.05:
        disturbance_timer = random.randint(5, 7)  # 5-7 ticks at 2s => 10-14s
        # dip or spike
        o2 += random.choice([-1.2, -0.8, 0.8, 1.2])

def update_env():
    """Random-walk dynamics toward targets."""
    global o2, co2, temp, disturbance_timer

    # O2: more drift, slower control
    # small random walk
    o2 += random.uniform(-0.12, 0.12)
    # pull back toward target
    o2 += (o2_target - o2) * 0.05

    # CO2: tighter control
    co2 += random.uniform(-0.05, 0.05)
    co2 += (co2_target - co2) * 0.10

    # Temp: very tight control
    temp += random.uniform(-0.02, 0.02)
    temp += (temp_target - temp) * 0.20

    # Disturbance handling
    if disturbance_timer > 0:
        disturbance_timer -= 1
    else:
        maybe_disturb_o2()

    # clamp plausible values
    o2 = max(0.1, min(21.0, o2))
    co2 = max(0.1, min(10.0, co2))
    temp = max(35.0, min(39.0, temp))

def update_progress(elapsed_sec: float):
    """Progress from 0→1 over demo duration; also stage transitions."""
    global prog, stage
    prog = min(1.0, elapsed_sec / DURATION_SEC)

    # update stage based on thresholds
    for i in range(len(stage_thresholds) - 1, -1, -1):
        if prog >= stage_thresholds[i]:
            stage = i
            break

def stage_event_if_needed(prev_stage: int, new_stage: int):
    """Generate step events on stage change."""
    events = []
    if new_stage != prev_stage:
        if prev_stage >= 0:
            events.append({"type": "step_completed", "step_key": stage_names[prev_stage]})
        events.append({"type": "step_started", "step_key": stage_names[new_stage]})
    return events

def build_patch(elapsed_sec: float, events):
    """Create a patch with env readings + progression markers."""
    # A couple "biological" markers that move with prog:
    # progenitor transition marker rises early, then plateaus
    progenitor_score = min(1.0, (prog / 0.55) ** 0.9)
    # cardiac marker rises later
    cardiac_score = max(0.0, (prog - 0.35) / 0.55)

    kv = {
        # environment sensors
        "env.incubator.o2_measured_percent": make_value(round(o2, 2), "float"),
        "env.incubator.co2_measured_percent": make_value(round(co2, 2), "float"),
        "env.incubator.temp_measured_C": make_value(round(temp, 2), "float"),

        # differentiation progression
        "process.diff.stage": make_value(stage_names[stage], "string", src="inferred", q="derived"),
        "process.diff.progress_0_1": make_value(round(prog, 3), "float", src="inferred", q="derived"),

        # “progenitor transition” emphasis
        "process.progenitor.transition_score_0_1": make_value(round(progenitor_score, 3), "float", src="inferred", q="derived"),
        "process.cardiac.marker_score_0_1": make_value(round(cardiac_score, 3), "float", src="inferred", q="derived"),
    }

    patch = {
        "run_id": RUN_ID,
        "patch_id": str(uuid.uuid4()),
        "ts": iso_now(),
        "kv": kv,
        "events": events,
    }
    return patch

def main():
    print("=== SteMy Real-Time Simulator ===")
    print("Base URL:", BASE_URL)
    print("Run ID:", RUN_ID)
    print("Interval (sec):", INTERVAL_SEC)
    print("Duration (sec):", DURATION_SEC)
    print("Posting to:", f"{BASE_URL}/api/runs/{RUN_ID}/patch")
    print("Tip: In another terminal, watch SSE:")
    print(f'  curl.exe -N -H \'X-API-Key: <KEY>\' "{BASE_URL}/api/stream/patches?run_id={RUN_ID}"')
    print("================================")

    start = time.time()
    prev_stage = stage

    # start with a stage_started event
    init_events = [{"type": "step_started", "step_key": stage_names[stage]}]
    patch = build_patch(0.0, init_events)
    resp = post_patch(patch)
    print("Sent init patch:", resp)

    while True:
        elapsed = time.time() - start
        if elapsed > DURATION_SEC:
            # send final completion event
            final_events = [{"type": "step_completed", "step_key": stage_names[stage]}]
            patch = build_patch(elapsed, final_events)
            resp = post_patch(patch)
            print("Sent final patch:", resp)
            break

        update_env()
        update_progress(elapsed)

        events = stage_event_if_needed(prev_stage, stage)
        prev_stage = stage

        patch = build_patch(elapsed, events)
        resp = post_patch(patch)
        print(f"Sent patch {patch['patch_id'][:8]}... ok={resp.get('ok')}")

        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()