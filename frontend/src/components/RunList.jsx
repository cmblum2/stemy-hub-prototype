import { Link } from "react-router-dom";

export default function RunList({ runs }) {
  if (!runs?.length) return <div className="muted">No runs yet. Click “Start New Study”.</div>;

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Run</th>
          <th>Status</th>
          <th>Stage</th>
          <th>Updated</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.run_id}>
            <td><code>{r.run_id}</code></td>
            <td><span className="chip">{r.status}</span></td>
            <td>{r.stage ? <span className="chip">{r.stage}</span> : <span className="muted">—</span>}</td>
            <td className="muted">{r.updated_at}</td>
            <td style={{ textAlign: "right" }}>
              <Link className="btn" to={`/runs/${r.run_id}`}>Resume</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}