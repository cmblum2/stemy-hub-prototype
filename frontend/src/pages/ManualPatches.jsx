// frontend/src/pages/ManualPatches.jsx
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api";

function encodeRunId(runId) {
  return encodeURIComponent(runId || "");
}

function parseValueByType(raw, type) {
  const s = (raw ?? "").trim();

  if (!type) return s;

  // Normalize common catalog types
  const t = String(type).toLowerCase();

  if (t === "number" || t === "float" || t === "int" || t === "integer") {
    const n = Number(s);
    return Number.isFinite(n) ? n : s; // fallback to string if invalid
  }

  if (t === "boolean" || t === "bool") {
    if (s.toLowerCase() === "true") return true;
    if (s.toLowerCase() === "false") return false;
    return s; // fallback
  }

  if (t === "percent") {
    // allow "5" or "5%" -> store as number 5
    const cleaned = s.endsWith("%") ? s.slice(0, -1).trim() : s;
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : s;
  }

  if (t === "timestamp" || t === "datetime" || t === "date") {
    // keep as string; backend stores patch.value as Any
    return s;
  }

  // enum/string/default
  return s;
}

export default function ManualPatches() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");

  const [catalog, setCatalog] = useState(null);
  const [catalogError, setCatalogError] = useState("");

  const [section, setSection] = useState("All");
  const [search, setSearch] = useState("");

  const [selectedKey, setSelectedKey] = useState("");
  const [valueRaw, setValueRaw] = useState("");
  const [note, setNote] = useState("");

  const [patches, setPatches] = useState([]);
  const [state, setState] = useState(null);

  const [status, setStatus] = useState("");

  // Load runs
  useEffect(() => {
    (async () => {
      try {
        const r = await apiGet("/api/runs");
        const list = r?.runs || [];
        setRuns(list);
        if (!runId && list.length > 0) {
          setRunId(list[0].run_id);
        }
      } catch (e) {
        setStatus(`Failed to load runs: ${e?.message || String(e)}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load catalog
  useEffect(() => {
    (async () => {
      try {
        const c = await apiGet("/api/catalog");
        setCatalog(c);
        setCatalogError(c?.error || "");
      } catch (e) {
        setCatalog(null);
        setCatalogError(e?.message || String(e));
      }
    })();
  }, []);

  async function refreshRunData(rid) {
    if (!rid) return;
    setStatus("");

    try {
      const p = await apiGet(`/api/runs/${encodeRunId(rid)}/patches?min_conf=0.0`);
      setPatches(p?.patches || []);
    } catch (e) {
      setStatus(`Failed to load patches: ${e?.message || String(e)}`);
    }

    try {
      const s = await apiGet(`/api/runs/${encodeRunId(rid)}/state?min_conf=0.0`);
      setState(s?.state || null);
    } catch (e) {
      setStatus((prev) => prev || `Failed to load state: ${e?.message || String(e)}`);
    }
  }

  // Refresh patches/state when run changes
  useEffect(() => {
    refreshRunData(runId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const variables = useMemo(() => (catalog?.variables || []).filter((v) => v && v.id), [catalog]);

  const sections = useMemo(() => {
    const s = new Set();
    variables.forEach((v) => {
      if (v.section) s.add(v.section);
    });
    return ["All", ...Array.from(s).sort()];
  }, [variables]);

  const filteredVars = useMemo(() => {
    const q = search.trim().toLowerCase();

    return variables
      .filter((v) => (section === "All" ? true : v.section === section))
      .filter((v) => {
        if (!q) return true;
        const hay = `${v.id} ${v.label || ""} ${(v.synonyms || []).join(" ")}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => {
        const aa = a.label || a.id;
        const bb = b.label || b.id;
        return aa.localeCompare(bb);
      });
  }, [variables, section, search]);

  const selectedVar = useMemo(() => {
    if (!selectedKey) return null;
    return variables.find((v) => v.id === selectedKey) || null;
  }, [variables, selectedKey]);

  useEffect(() => {
    // If selectedKey disappears due to filtering/section change, keep it but ensure it exists
    if (selectedKey && !variables.find((v) => v.id === selectedKey)) {
      setSelectedKey("");
    }
  }, [variables, selectedKey]);

  async function onCreatePatch() {
    setStatus("");

    if (!runId) return setStatus("Pick a run first.");
    if (!selectedKey) return setStatus("Pick a variable from the catalog.");
    if (!valueRaw.trim()) return setStatus("Enter a value.");

    const typedValue = parseValueByType(valueRaw, selectedVar?.type);

    try {
      await apiPost(`/api/runs/${encodeRunId(runId)}/patches/manual`, {
        key: selectedKey,
        value: typedValue,
        actor: "researcher",
        source: "manual",
        note: note?.trim() ? note.trim() : null,
      });

      setValueRaw("");
      setNote("");
      await refreshRunData(runId);
      setStatus("✅ Patch created (append-only).");
    } catch (e) {
      setStatus(`❌ Failed to create patch: ${e?.message || String(e)}`);
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <h2 style={{ marginBottom: 4 }}>Manual Patch Creator</h2>
      <div style={{ opacity: 0.8, marginBottom: 12 }}>
        Catalog → select variable → create append-only patch → view patches/state
      </div>

      {catalogError ? (
        <div style={{ padding: 12, border: "1px solid #e11", borderRadius: 8, marginBottom: 12 }}>
          <b>Catalog error:</b> {catalogError}
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* LEFT: Create patch */}
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 10 }}>
          <h3 style={{ marginTop: 0 }}>Create Patch</h3>

          <label style={{ display: "block", marginBottom: 6 }}>Run</label>
          <select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 12 }}
          >
            {runs.length === 0 ? <option value="">(no runs yet)</option> : null}
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id} ({r.patch_count ?? 0} patches)
              </option>
            ))}
          </select>

          <label style={{ display: "block", marginBottom: 6 }}>Section</label>
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 12 }}
          >
            {sections.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <label style={{ display: "block", marginBottom: 6 }}>Search</label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by id / label / synonyms..."
            style={{ width: "100%", padding: 8, marginBottom: 12 }}
          />

          <label style={{ display: "block", marginBottom: 6 }}>
            Variable <span style={{ opacity: 0.7 }}>({filteredVars.length} shown)</span>
          </label>
          <select
            value={selectedKey}
            onChange={(e) => setSelectedKey(e.target.value)}
            style={{ width: "100%", padding: 8, marginBottom: 10 }}
          >
            <option value="">— select —</option>
            {filteredVars.map((v) => (
              <option key={v.id} value={v.id}>
                {(v.label || v.id)} [{v.id}]
              </option>
            ))}
          </select>

          {selectedVar ? (
            <div style={{ fontSize: 13, opacity: 0.85, marginBottom: 12, lineHeight: 1.35 }}>
              <div>
                <b>id:</b> {selectedVar.id}
              </div>
              {selectedVar.label ? (
                <div>
                  <b>label:</b> {selectedVar.label}
                </div>
              ) : null}
              <div>
                <b>type:</b> {selectedVar.type || "string"}
                {selectedVar.unit ? ` (${selectedVar.unit})` : ""}
              </div>
              {selectedVar.section ? (
                <div>
                  <b>section:</b> {selectedVar.section}
                </div>
              ) : null}
              {selectedVar.phase ? (
                <div>
                  <b>phase:</b> {selectedVar.phase}
                </div>
              ) : null}
            </div>
          ) : (
            <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 12 }}>
              Pick a variable to see its details.
            </div>
          )}

          <label style={{ display: "block", marginBottom: 6 }}>Value</label>
          <input
            value={valueRaw}
            onChange={(e) => setValueRaw(e.target.value)}
            placeholder={
              (selectedVar?.type || "").toLowerCase() === "number"
                ? "e.g. 5"
                : (selectedVar?.type || "").toLowerCase() === "percent"
                ? "e.g. 5 or 5%"
                : "e.g. text"
            }
            style={{ width: "100%", padding: 8, marginBottom: 12 }}
          />

          <label style={{ display: "block", marginBottom: 6 }}>Note (optional)</label>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="context / why you're setting this"
            style={{ width: "100%", padding: 8, marginBottom: 12 }}
          />

          <button onClick={onCreatePatch} style={{ padding: "10px 14px", cursor: "pointer" }}>
            Create Patch
          </button>

          {status ? <div style={{ marginTop: 12 }}>{status}</div> : null}
        </div>

        {/* RIGHT: State */}
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 10 }}>
          <h3 style={{ marginTop: 0 }}>Derived State</h3>
          <div style={{ fontSize: 13, opacity: 0.75, marginBottom: 8 }}>
            This is reconstructed from patches (append-only).
          </div>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: 560,
              overflow: "auto",
              background: "#fafafa",
              padding: 12,
              borderRadius: 8,
              border: "1px solid #eee",
            }}
          >
            {JSON.stringify(state, null, 2)}
          </pre>
        </div>
      </div>

      {/* PATCHES */}
      <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 10, marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Patches</h3>
        <div style={{ fontSize: 13, opacity: 0.75, marginBottom: 8 }}>
          Showing {patches.length} patches (min_conf=0.0)
        </div>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 420,
            overflow: "auto",
            background: "#fafafa",
            padding: 12,
            borderRadius: 8,
            border: "1px solid #eee",
          }}
        >
          {JSON.stringify(patches, null, 2)}
        </pre>
      </div>
    </div>
  );
}