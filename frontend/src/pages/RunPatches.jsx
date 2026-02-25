import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_BASE;
const UI_TOKEN = import.meta.env.VITE_UI_TOKEN;

function fmtTs(ts) {
  // keep it simple + readable
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export default function RunPatches() {
  const { runId } = useParams();

  const [patches, setPatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState(null);

  // UI controls
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());

  // Paging controls (works with your backend limit/offset/order)
  const [order, setOrder] = useState("desc");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [count, setCount] = useState(0);

  async function load() {
    setLoading(true);
    setErr("");
    setStatus(null);

    try {
      if (!API_BASE) throw new Error("VITE_API_BASE is not set.");

      const url =
        `${API_BASE}/api/runs/${encodeURIComponent(runId)}/patches` +
        `?limit=${limit}&offset=${offset}&order=${order}`;

      const res = await fetch(url, {
        headers: {
          "X-UI-Token": UI_TOKEN,
        },
      });

      setStatus(res.status);

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Request failed (${res.status}). ${text}`);
      }

      const data = await res.json();
      setPatches(data.patches || []);
      setCount(typeof data.count === "number" ? data.count : (data.patches || []).length);
    } catch (e) {
      setErr(String(e));
      setPatches([]);
      setCount(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, order, limit, offset]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return patches;

    return patches.filter((p) => {
      const patch = p.patch || {};
      const kv = patch.kv || {};
      const keys = Object.keys(kv);

      const stage = kv["process.diff.stage"]?.v ?? kv["process.diff.stage"]?.value?.v;
      const progress = kv["process.diff.progress_0_1"]?.v ?? kv["process.diff.progress_0_1"]?.value?.v;

      return (
        String(p.patch_id || "").toLowerCase().includes(q) ||
        String(p.ts || "").toLowerCase().includes(q) ||
        String(stage ?? "").toLowerCase().includes(q) ||
        String(progress ?? "").toLowerCase().includes(q) ||
        keys.some((k) => k.toLowerCase().includes(q))
      );
    });
  }, [patches, query]);

  function toggleExpanded(patchId) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(patchId)) next.delete(patchId);
      else next.add(patchId);
      return next;
    });
  }

  async function copyJson(obj) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
    } catch {
      // no-op
    }
  }

  const canPrev = offset > 0;
  const canNext = patches.length === limit; // simple heuristic

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1 style={{ marginBottom: 6 }}>Patch History</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            <span style={{ fontWeight: 600 }}>{runId}</span>
            {status !== null ? <span>{" • "}HTTP {status}</span> : null}
          </div>
        </div>

        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <Link className="btn" to="/runs">
            Home
          </Link>
          <Link className="btn" to={`/runs/${encodeURIComponent(runId)}`}>
            Back to Live
          </Link>
          <button className="btn" onClick={() => load()}>
            Refresh
          </button>
        </div>
      </header>

      {err && <div className="alert">{err}</div>}

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row" style={{ justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search patch id, stage, or key name (e.g. env.incubator)"
              style={{
                width: 420,
                maxWidth: "100%",
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.12)",
                background: "rgba(0,0,0,0.25)",
                color: "inherit",
                outline: "none",
              }}
            />
            <span className="chip">
              Showing {filtered.length} / {patches.length} (page size {limit})
            </span>
          </div>

          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <label className="row" style={{ gap: 8 }}>
              <span className="muted" style={{ fontSize: 12 }}>Order</span>
              <select
                value={order}
                onChange={(e) => { setOffset(0); setOrder(e.target.value); }}
                style={{
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: "rgba(0,0,0,0.25)",
                  color: "inherit",
                }}
              >
                <option value="desc">Newest → Oldest</option>
                <option value="asc">Oldest → Newest</option>
              </select>
            </label>

            <label className="row" style={{ gap: 8 }}>
              <span className="muted" style={{ fontSize: 12 }}>Limit</span>
              <select
                value={limit}
                onChange={(e) => { setOffset(0); setLimit(Number(e.target.value)); }}
                style={{
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: "rgba(0,0,0,0.25)",
                  color: "inherit",
                }}
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={250}>250</option>
              </select>
            </label>

            <button
              className="btn"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Prev
            </button>
            <button
              className="btn"
              disabled={!canNext}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="muted">Loading patches…</div>
      ) : filtered.length === 0 ? (
        <div className="card">
          <div className="muted">No patches match your search.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {filtered.map((p) => {
            const patch = p.patch || {};
            const kv = patch.kv || {};
            const events = patch.events || [];
            const kvKeys = Object.keys(kv);

            const stage = kv["process.diff.stage"]?.v ?? kv["process.diff.stage"]?.value?.v;
            const progress = kv["process.diff.progress_0_1"]?.v ?? kv["process.diff.progress_0_1"]?.value?.v;

            const isOpen = expanded.has(p.patch_id);

            return (
              <div key={p.patch_id} className="card" style={{ padding: 14 }}>
                <div className="row" style={{ justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 16, wordBreak: "break-all" }}>
                      {p.patch_id}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {fmtTs(p.ts)}
                    </div>
                  </div>

                  <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                    <span className="chip">{kvKeys.length} keys</span>
                    <span className="chip">{events.length} events</span>
                    <span className="chip">Stage: {stage ?? "—"}</span>
                    <span className="chip">Progress: {typeof progress === "number" ? progress.toFixed(2) : (progress ?? "—")}</span>

                    <button className="btn" onClick={() => toggleExpanded(p.patch_id)}>
                      {isOpen ? "Hide JSON" : "Show JSON"}
                    </button>
                    <button className="btn" onClick={() => copyJson(patch)}>
                      Copy JSON
                    </button>
                  </div>
                </div>

                {/* small key preview (top few keys) */}
                <div style={{ marginTop: 10, fontSize: 13 }}>
                  <div className="muted" style={{ marginBottom: 6 }}>Key preview</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {kvKeys.slice(0, 8).map((k) => (
                      <span
                        key={k}
                        className="chip"
                        title={k}
                        style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}
                      >
                        {k}
                      </span>
                    ))}
                    {kvKeys.length > 8 && <span className="chip">+{kvKeys.length - 8} more</span>}
                  </div>
                </div>

                {isOpen && (
                  <pre
                    style={{
                      marginTop: 12,
                      fontSize: 12,
                      lineHeight: 1.4,
                      background: "rgba(0,0,0,0.25)",
                      border: "1px solid rgba(255,255,255,0.10)",
                      borderRadius: 12,
                      padding: 12,
                      overflowX: "auto",
                      maxHeight: 420,
                    }}
                  >
                    {JSON.stringify(patch, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}