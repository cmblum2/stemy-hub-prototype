import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api";
import { useSSE } from "../hooks/useSSE";
import StatusBadge from "../components/StatusBadge.jsx";
import PatchFeed from "../components/PatchFeed.jsx";
import StateTable from "../components/StateTable.jsx";
import StageTimeline from "../components/StageTimeline.jsx";

export default function RunDashboard() {
  const { runId } = useParams();
  const { connected, feed, mergedState } = useSSE(runId);

  const [snapshot, setSnapshot] = useState(null);
  const [tab, setTab] = useState("live");
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      setError("");
      try {
        const data = await apiGet(`/api/runs/${runId}/state`);
        setSnapshot(data.state || {});
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [runId]);

  const combinedState = useMemo(() => {
    const base = snapshot ? { ...snapshot } : {};
    Object.entries(mergedState || {}).forEach(([k, v]) => {
      base[k] = v; // overwrite with live state
    });
    return base;
  }, [snapshot, mergedState]);

  const stage = combinedState?.["process.diff.stage"]?.value?.v;

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>{runId}</h1>
          <div className="row">
            <StatusBadge connected={connected} />
            <span className="chip">{stage ? `Stage: ${stage}` : "Stage: —"}</span>
          </div>
        </div>

        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          {/* Home + Patch History Nav */}
          <Link className="btn" to="/runs">
            Home
          </Link>
          <Link className="btn" to={`/runs/${encodeURIComponent(runId)}/patches`}>
            View Patches
          </Link>

          {/* Existing tabs */}
          <button
            className={`btn ${tab === "live" ? "primary" : ""}`}
            onClick={() => setTab("live")}
          >
            Live Feed
          </button>
          <button
            className={`btn ${tab === "state" ? "primary" : ""}`}
            onClick={() => setTab("state")}
          >
            Current State
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <StageTimeline stage={stage} />

      {tab === "live" ? (
        <div className="grid2">
          <div className="card">
            <h2>Live Patch Feed</h2>
            <PatchFeed feed={feed} />
          </div>
          <div className="card">
            <h2>Key Metrics</h2>
            <StateTable state={combinedState} compact />
          </div>
        </div>
      ) : (
        <div className="card">
          <h2>Current State</h2>
          <StateTable state={combinedState} />
        </div>
      )}
    </div>
  );
}