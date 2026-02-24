import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";
import RunList from "../components/RunList.jsx";
import NewRunModal from "../components/NewRunModal.jsx";

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const data = await apiGet("/api/runs");
      setRuns(data.runs || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function createRun({ title, meta }) {
    const created = await apiPost("/api/runs", { title, meta });
    await refresh();
    return created.run_id;
  }

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>Studies</h1>
          <p className="muted">Start a new study run or resume an existing one.</p>
        </div>
        <button className="btn primary" onClick={() => setShowNew(true)}>
          + Start New Study
        </button>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="card">
        {loading ? <div className="muted">Loading runs…</div> : <RunList runs={runs} />}
      </div>

      <NewRunModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onCreate={createRun}
      />
    </div>
  );
}