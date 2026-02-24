import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function NewRunModal({ open, onClose, onCreate }) {
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [incubatorId, setIncubatorId] = useState("");
  const [protocol, setProtocol] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const runId = await onCreate({
        title: title || null,
        meta: {
          incubator_id: incubatorId || null,
          protocol_version: protocol || null,
          notes: notes || null,
        },
      });
      onClose();
      nav(`/runs/${runId}`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modalBackdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Start New Study</h2>
        <p className="muted">Create a new run and begin streaming updates.</p>

        {err && <div className="alert">{err}</div>}

        <label>Title (optional)</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g., iPSC → progenitor demo" />

        <label>Incubator ID (optional)</label>
        <input value={incubatorId} onChange={(e) => setIncubatorId(e.target.value)} placeholder="e.g., INC_07" />

        <label>Protocol version (optional)</label>
        <input value={protocol} onChange={(e) => setProtocol(e.target.value)} placeholder="e.g., v1.2" />

        <label>Notes (optional)</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any context for Level 3…" />

        <div className="row right">
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "Creating…" : "Create Run"}
          </button>
        </div>
      </div>
    </div>
  );
}