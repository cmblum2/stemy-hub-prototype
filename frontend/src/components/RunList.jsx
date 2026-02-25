import { Link } from "react-router-dom";

export default function RunList({ runs }) {
  if (!runs || runs.length === 0) {
    return <div className="muted">No runs yet.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {runs.map((r) => (
        <div
          key={r.run_id}
          className="row"
          style={{
            justifyContent: "space-between",
            alignItems: "center",
            padding: 12,
            border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 12,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700 }}>
              {r.title ? r.title : r.run_id}
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              <span>{r.run_id}</span>
              {" • "}
              <span>Status: {r.status}</span>
              {" • "}
              <span>Stage: {r.stage ?? "—"}</span>
            </div>
          </div>

          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <Link className="btn" to={`/runs/${encodeURIComponent(r.run_id)}`}>
              Open Live
            </Link>

            <Link className="btn" to={`/runs/${encodeURIComponent(r.run_id)}/patches`}>
              View Patches
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}