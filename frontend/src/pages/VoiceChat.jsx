// frontend/src/pages/VoiceChat.jsx
import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost, sseRunStreamUrl } from "../api";
import { Link } from "react-router-dom";

export default function VoiceChat() {
  // --- Run selection gate ---
  const [runId, setRunId] = useState("");
  const [runLocked, setRunLocked] = useState(false);
  const [runs, setRuns] = useState([]);
  const [runPickerOpen, setRunPickerOpen] = useState(true);
  const [newRunId, setNewRunId] = useState("");

  // confidence filtering
  const [minConf, setMinConf] = useState(0.75);

  // chat state
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState({});
  const [patches, setPatches] = useState([]);

  // UX/debug state
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);

  // Voice state (existing Web Speech hold-to-talk)
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef(null);

  // Voice state (record -> transcribe -> reason flow)
  const [voiceReasoning, setVoiceReasoning] = useState(null);
  const [assistantVoiceText, setAssistantVoiceText] = useState("");
  const [voicePatchCandidates, setVoicePatchCandidates] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [lastTranscript, setLastTranscript] = useState("");
  const [voiceError, setVoiceError] = useState("");

  // Universe drawer
  const [universeOpen, setUniverseOpen] = useState(false);
  const [universeSelectedRun, setUniverseSelectedRun] = useState(null);
  const [universeState, setUniverseState] = useState({});
  const [universePatches, setUniversePatches] = useState([]);
  const [universeError, setUniverseError] = useState("");
  const [liveOn, setLiveOn] = useState(true);
  const esRef = useRef(null);

  // Active run live updates (SSE)
  const activeEsRef = useRef(null);
  const [activeLiveOn, setActiveLiveOn] = useState(true);

  function setErr(msg) {
    setError(msg || "");
    if (msg) console.error(msg);
  }

  function closeActiveStream() {
    if (activeEsRef.current) {
      activeEsRef.current.close();
      activeEsRef.current = null;
    }
  }

  function closeUniverseStream() {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }

  function resetRunScopedUi() {
    setMessages([]);
    setPatches([]);
    setState({});
    setInput("");
    setInterim("");
    setErr("");
    setVoiceError("");
    setLastTranscript("");
    setVoiceReasoning(null);
    setAssistantVoiceText("");
    setVoicePatchCandidates([]);
  }

  // -------------------------
  // Run list + selection
  // -------------------------
  async function refreshRuns() {
    try {
      const res = await apiGet("/api/runs");
      setRuns(res?.runs || []);
      return res?.runs || [];
    } catch (e) {
      setErr(`GET /api/runs FAILED: ${e?.message || String(e)}`);
      return [];
    }
  }

  useEffect(() => {
    (async () => {
      await refreshRuns();
      setRunPickerOpen(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeRun() {
    closeActiveStream();
    setRunLocked(false);
    setRunId("");
    resetRunScopedUi();
    setRunPickerOpen(true);
  }

  async function selectExistingRun(id) {
    if (!id) return;
    setErr("");

    closeActiveStream();
    resetRunScopedUi();

    setRunId(id);
    setRunLocked(true);
    setRunPickerOpen(false);

    try {
      await Promise.all([loadStateFor(id), loadPatchesFor(id)]);
    } catch (e) {
      setErr(`Load run failed: ${e?.message || String(e)}`);
    }
  }

  async function createNewRun() {
    const id = (newRunId || "").trim();
    if (!id) {
      setErr("Please enter a new Run ID.");
      return;
    }

    setErr("");
    setIsSending(true);

    closeActiveStream();
    resetRunScopedUi();

    setRunId(id);
    setRunLocked(true);
    setRunPickerOpen(false);
    setNewRunId("");

    try {
      await apiPost("/api/runs", { run_id: id });
      await refreshRuns();
      await Promise.all([loadStateFor(id), loadPatchesFor(id)]);
    } catch (e) {
      setRunLocked(false);
      setRunPickerOpen(true);
      setErr(`Create run failed: ${e?.message || String(e)}`);
    } finally {
      setIsSending(false);
    }
  }

  // -------------------------
  // Backend calls (current run)
  // -------------------------
  async function ingestText(text) {
    if (!runLocked || !runId) {
      setErr("Select or create a Run ID first.");
      return;
    }

    const payload = { run_id: runId, text };
    const res = await apiPost("/api/voice/ingest", payload);

    if (res?.assistant_message) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.assistant_message, ts: Date.now() },
      ]);
    }

    if (res?.state) setState(res.state);
    if (Array.isArray(res?.committed_patches)) {
      setPatches((prev) => [...prev, ...res.committed_patches]);
    }

    refreshRuns().catch(() => {});
    return res;
  }

  async function processExperimentUpdate(transcriptText) {
    const API_BASE = import.meta.env.VITE_API_BASE || "";
    const UI_TOKEN = import.meta.env.VITE_UI_TOKEN || "";

    const reasonRes = await fetch(`${API_BASE}/api/voice/reason`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-UI-Token": UI_TOKEN,
      },
      body: JSON.stringify({
        run_id: runId,
        transcript: transcriptText,
      }),
    });

    const reasonRaw = await reasonRes.text();

    let reasonData = null;
    try {
      reasonData = JSON.parse(reasonRaw);
    } catch {
      throw new Error(
        `Reason returned non-JSON (${reasonRes.status}): ${reasonRaw}`
      );
    }

    if (!reasonRes.ok || !reasonData.ok) {
      throw new Error(
        reasonData?.error || `Reason failed with status ${reasonRes.status}`
      );
    }

    const reasoning = reasonData.reasoning || null;
    setVoiceReasoning(reasoning);
    setAssistantVoiceText(reasoning?.assistant_text || "");
    setVoicePatchCandidates(reasoning?.patch_candidates || []);

    // ALWAYS call commit — backend may be holding pending confirmation
    const commitRes = await fetch(`${API_BASE}/api/voice/commit_candidates`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-UI-Token": UI_TOKEN,
      },
      body: JSON.stringify({
        run_id: runId,
        transcript: transcriptText,
        patch_candidates: reasoning?.patch_candidates || [],
      }),
    });

    const commitRaw = await commitRes.text();

    let commitData = null;
    try {
      commitData = JSON.parse(commitRaw);
    } catch {
      throw new Error(
        `Commit returned non-JSON (${commitRes.status}): ${commitRaw}`
      );
    }

    if (!commitRes.ok || !commitData.ok) {
      throw new Error(
        commitData?.error || `Commit failed with status ${commitRes.status}`
      );
    }

    if (Array.isArray(commitData.committed_patches)) {
      setPatches((prev) => [...prev, ...commitData.committed_patches]);
    }

    if (commitData.state) {
      setState(commitData.state);
    }

    if (commitData.assistant) {
      setAssistantVoiceText(commitData.assistant);
    }

    await Promise.all([loadPatchesFor(runId), loadStateFor(runId)]).catch(
      () => {}
    );
    await refreshRuns().catch(() => {});

    setMessages((prev) => {
      const next = [
        ...prev,
        { role: "researcher", text: transcriptText, ts: Date.now() },
      ];

      const assistantText =
        commitData?.assistant || reasoning?.assistant_text;

      if (assistantText) {
        next.push({
          role: "assistant",
          text: assistantText,
          ts: Date.now() + 1,
        });
      }

      return next;
    });
  }

  async function startRecording() {
    try {
      if (!runLocked || !runId) {
        setVoiceError("Select or create a Run ID first.");
        return;
      }

      setVoiceError("");
      setLastTranscript("");
      setVoiceReasoning(null);
      setAssistantVoiceText("");
      setVoicePatchCandidates([]);

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
        },
      });

      let mimeType = "";
      if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      }

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      const chunks = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = async () => {
        try {
          const blob = new Blob(chunks, {
            type: recorder.mimeType || "audio/webm",
          });

          const formData = new FormData();
          formData.append("audio", blob, "recording.webm");

          const API_BASE = import.meta.env.VITE_API_BASE || "";
          const UI_TOKEN = import.meta.env.VITE_UI_TOKEN || "";

          const transcribeRes = await fetch(`${API_BASE}/api/voice/transcribe`, {
            method: "POST",
            headers: {
              "X-UI-Token": UI_TOKEN,
            },
            body: formData,
          });

          const transcribeRaw = await transcribeRes.text();

          let transcribeData = null;
          try {
            transcribeData = JSON.parse(transcribeRaw);
          } catch {
            throw new Error(
              `Transcribe returned non-JSON (${transcribeRes.status}): ${transcribeRaw}`
            );
          }

          if (!transcribeRes.ok || !transcribeData.ok) {
            throw new Error(
              transcribeData?.error ||
                `Transcribe failed with status ${transcribeRes.status}`
            );
          }

          const transcriptText = transcribeData.transcript || "";
          setLastTranscript(transcriptText);

          await processExperimentUpdate(transcriptText);
        } catch (err) {
          setVoiceError(err.message || "Voice pipeline failed");
        } finally {
          stream.getTracks().forEach((track) => track.stop());
        }
      };

      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
    } catch (err) {
      setVoiceError(err.message || "Microphone access failed");
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    setIsRecording(false);
  }

  async function loadPatchesFor(id) {
    const rid = id || runId;
    if (!rid) return;
    const res = await apiGet(
      `/api/runs/${encodeURIComponent(rid)}/patches?min_conf=${encodeURIComponent(
        minConf
      )}`
    );
    setPatches(res?.patches || []);
  }

  async function loadStateFor(id) {
    const rid = id || runId;
    if (!rid) return;
    const res = await apiGet(
      `/api/runs/${encodeURIComponent(rid)}/state?min_conf=${encodeURIComponent(
        minConf
      )}`
    );
    setState(res?.state || {});
  }

  async function loadPatches() {
    try {
      setErr("");
      await loadPatchesFor();
    } catch (e) {
      setErr(`Load patches failed: ${e?.message || String(e)}`);
    }
  }

  async function loadState() {
    try {
      setErr("");
      await loadStateFor();
    } catch (e) {
      setErr(`Load state failed: ${e?.message || String(e)}`);
    }
  }

  async function send() {
    setErr("");
    setVoiceError("");

    if (!runLocked || !runId) {
      setErr("Select or create a Run ID first.");
      return;
    }

    if (!input.trim()) return;

    const text = input.trim();
    setInput("");
    setLastTranscript(text);
    setVoiceReasoning(null);
    setAssistantVoiceText("");
    setVoicePatchCandidates([]);

    setIsSending(true);
    try {
      await processExperimentUpdate(text);
    } catch (e) {
      setErr(`Typed reasoning failed: ${e?.message || String(e)}`);
    } finally {
      setIsSending(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter") send();
  }

  // -------------------------
  // Active-run SSE
  // -------------------------
  useEffect(() => {
    closeActiveStream();

    if (!runLocked || !runId || !activeLiveOn) return;

    const url = sseRunStreamUrl(runId);
    const es = new EventSource(url);
    activeEsRef.current = es;

    es.onmessage = () => {
      Promise.all([loadPatchesFor(runId), loadStateFor(runId)])
        .then(() => refreshRuns())
        .catch(() => {});
    };

    es.onerror = () => {};

    return () => {
      closeActiveStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runLocked, runId, activeLiveOn, minConf]);

  // -------------------------
  // Voice (Web Speech API)
  // -------------------------
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onstart = () => {
      setIsListening(true);
      setErr("");
    };
    rec.onend = () => {
      setIsListening(false);
      setInterim("");
    };
    rec.onerror = (event) => {
      setErr(`Voice error: ${event?.error || "unknown"}`);
      setIsListening(false);
    };
    rec.onresult = async (event) => {
      let interimText = "";
      let finalText = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0]?.transcript || "";
        if (result.isFinal) finalText += transcript;
        else interimText += transcript;
      }

      setInterim(interimText);

      if (finalText.trim()) {
        if (!runLocked) {
          setErr("Select or create a Run ID first.");
          return;
        }

        const spoken = finalText.trim();
        setIsSending(true);
        try {
          await processExperimentUpdate(spoken);
        } catch (e) {
          setErr(`POST FAILED (voice): ${e?.message || String(e)}`);
        } finally {
          setIsSending(false);
        }
      }
    };

    recognitionRef.current = rec;
    return () => {
      try {
        rec.stop();
      } catch {}
    };
  }, [runLocked, runId]);

  function startListening() {
    setErr("");
    if (!runLocked) {
      setErr("Select or create a Run ID first.");
      return;
    }
    const rec = recognitionRef.current;
    if (!rec) {
      setErr("Web Speech API not available (try Chrome/Edge).");
      return;
    }
    try {
      rec.start();
    } catch {}
  }

  function stopListening() {
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      rec.stop();
    } catch {}
  }

  // -------------------------
  // Universe drawer
  // -------------------------
  async function universeLoadRuns() {
    setUniverseError("");
    try {
      const res = await apiGet("/api/runs");
      setRuns(res?.runs || []);
      if (!universeSelectedRun && (res?.runs || []).length > 0) {
        setUniverseSelectedRun(res.runs[0].run_id);
      }
    } catch (e) {
      setUniverseError(`GET /api/runs FAILED: ${e?.message || String(e)}`);
    }
  }

  async function universeLoadSelected(rid) {
    if (!rid) return;
    setUniverseError("");
    try {
      const [pRes, sRes] = await Promise.all([
        apiGet(
          `/api/runs/${encodeURIComponent(
            rid
          )}/patches?min_conf=${encodeURIComponent(minConf)}`
        ),
        apiGet(
          `/api/runs/${encodeURIComponent(
            rid
          )}/state?min_conf=${encodeURIComponent(minConf)}`
        ),
      ]);
      setUniversePatches(pRes?.patches || []);
      setUniverseState(sRes?.state || {});
    } catch (e) {
      setUniverseError(`Universe load FAILED: ${e?.message || String(e)}`);
    }
  }

  useEffect(() => {
    if (!universeOpen) return;
    universeLoadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeOpen]);

  useEffect(() => {
    if (!universeOpen || !universeSelectedRun) return;
    universeLoadSelected(universeSelectedRun);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeOpen, universeSelectedRun, minConf]);

  useEffect(() => {
    closeUniverseStream();
    if (!universeOpen || !universeSelectedRun || !liveOn) return;

    const url = sseRunStreamUrl(universeSelectedRun);
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = () => {
      universeLoadSelected(universeSelectedRun);
    };

    es.onerror = () => {};

    return () => {
      closeUniverseStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeOpen, universeSelectedRun, liveOn, minConf]);

  useEffect(() => {
    if (!universeOpen) closeUniverseStream();
  }, [universeOpen]);

  // -------------------------
  // UI
  // -------------------------
  return (
    <div style={{ padding: 30, maxWidth: 950 }}>
      <h2 style={{ marginBottom: 8 }}>StemY Conversational Assistant</h2>

      {error ? (
        <div
          style={{
            marginTop: 10,
            marginBottom: 10,
            padding: 10,
            borderRadius: 8,
            background: "rgba(255,0,0,0.08)",
            border: "1px solid rgba(255,0,0,0.25)",
          }}
        >
          <b>Error:</b> {error}
        </div>
      ) : null}

      <Link to="/manual" style={{ display: "inline-block", marginBottom: 12 }}>
        Go to Manual Patch Creator
      </Link>

      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <div style={{ fontSize: 12, opacity: 0.85 }}>
          Active run: <b>{runLocked ? runId : "none selected"}</b>
        </div>

        <button type="button" onClick={() => setRunPickerOpen(true)}>
          Select / Create Run
        </button>

        {runLocked ? (
          <button type="button" onClick={changeRun}>
            Change Run
          </button>
        ) : null}

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 12, opacity: 0.85 }}>live:</span>
          <input
            type="checkbox"
            checked={activeLiveOn}
            onChange={(e) => setActiveLiveOn(e.target.checked)}
            disabled={!runLocked}
          />
        </div>

        <div
          style={{
            marginLeft: 10,
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 12, opacity: 0.85 }}>min conf:</span>
          <input
            type="number"
            step="0.05"
            min="0"
            max="1"
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            style={{ width: 80 }}
            disabled={!runLocked}
          />
        </div>

        <button onClick={loadState} type="button" disabled={!runLocked}>
          Load State
        </button>
        <button onClick={loadPatches} type="button" disabled={!runLocked}>
          Load Patches
        </button>

        <button type="button" onClick={() => setUniverseOpen(true)}>
          Universe
        </button>

        <div style={{ marginLeft: "auto", opacity: 0.8, fontSize: 12 }}>
          {isSending ? "Sending..." : ""}
        </div>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 10 }}>
        <button
          type="button"
          onMouseDown={startListening}
          onMouseUp={stopListening}
          onTouchStart={startListening}
          onTouchEnd={stopListening}
          disabled={!runLocked}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            cursor: runLocked ? "pointer" : "not-allowed",
            opacity: runLocked ? 1 : 0.6,
          }}
        >
          {isListening ? "🎙️ Listening… (release to stop)" : "Hold to Talk"}
        </button>

        <button
          type="button"
          onClick={() => setMessages([])}
          disabled={!runLocked}
        >
          Clear Chat
        </button>

        <button
          type="button"
          onClick={() => setPatches([])}
          disabled={!runLocked}
        >
          Clear Patches
        </button>
      </div>

      <div
        style={{
          marginTop: 16,
          padding: 12,
          border: "1px solid #ccc",
          borderRadius: 8,
        }}
      >
        <h3>Voice Transcription Test</h3>

        {!isRecording ? (
          <button onClick={startRecording} disabled={!runLocked}>
            Start Recording
          </button>
        ) : (
          <button onClick={stopRecording}>Stop Recording</button>
        )}

        {lastTranscript ? (
          <p style={{ marginTop: 12 }}>
            <strong>Transcript:</strong> {lastTranscript}
          </p>
        ) : null}

        {voiceError ? (
          <p style={{ marginTop: 12, color: "red" }}>
            <strong>Error:</strong> {voiceError}
          </p>
        ) : null}
      </div>

      {voiceReasoning ? (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            border: "1px solid #ccc",
            borderRadius: 8,
          }}
        >
          <h3>Voice Reasoning Result</h3>

          {assistantVoiceText ? (
            <p>
              <strong>Assistant:</strong> {assistantVoiceText}
            </p>
          ) : null}

          <div style={{ marginTop: 10 }}>
            <strong>Patch Candidates:</strong>
            <pre
              style={{
                marginTop: 8,
                padding: 10,
                borderRadius: 8,
                border: "1px solid rgba(255,255,255,0.12)",
                overflowX: "auto",
              }}
            >
              {JSON.stringify(voicePatchCandidates, null, 2)}
            </pre>
          </div>

          <div style={{ marginTop: 10 }}>
            <strong>Follow-up:</strong>
            <pre
              style={{
                marginTop: 8,
                padding: 10,
                borderRadius: 8,
                border: "1px solid rgba(255,255,255,0.12)",
                overflowX: "auto",
              }}
            >
              {JSON.stringify(
                {
                  followup_mode: voiceReasoning.followup_mode,
                  pending_followup: voiceReasoning.pending_followup,
                },
                null,
                2
              )}
            </pre>
          </div>
        </div>
      ) : null}

      {interim ? (
        <div style={{ marginTop: 10, opacity: 0.8 }}>
          <b>Interim:</b> {interim}
        </div>
      ) : null}

      <div
        style={{
          marginTop: 18,
          padding: 16,
          borderRadius: 12,
          border: "1px solid rgba(255,255,255,0.12)",
          minHeight: 180,
          opacity: runLocked ? 1 : 0.6,
        }}
      >
        {!runLocked ? (
          <div style={{ opacity: 0.8 }}>Select or create a Run ID to begin.</div>
        ) : messages.length === 0 ? (
          <div style={{ opacity: 0.7 }}>
            Say or type an update (e.g., “CHIR was 8 µM for 24 hours, started
            9am.”)
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <b style={{ textTransform: "lowercase" }}>{m.role}:</b> {m.text}
            </div>
          ))
        )}
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            runLocked
              ? "Describe your experiment update..."
              : "Select a Run ID first..."
          }
          style={{ flex: 1, minWidth: 300 }}
          disabled={!runLocked}
        />
        <button onClick={send} disabled={!runLocked || isSending}>
          Send
        </button>
      </div>

      <div style={{ marginTop: 26 }}>
        <h3 style={{ marginBottom: 6 }}>Derived State</h3>
        <pre
          style={{
            padding: 12,
            borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.12)",
            overflowX: "auto",
          }}
        >
          {JSON.stringify(state || {}, null, 2)}
        </pre>
      </div>

      <div style={{ marginTop: 18 }}>
        <h3 style={{ marginBottom: 6 }}>Committed Patches</h3>
        <pre
          style={{
            padding: 12,
            borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.12)",
            overflowX: "auto",
            maxHeight: 260,
            overflowY: "auto",
          }}
        >
          {JSON.stringify(patches || [], null, 2)}
        </pre>
      </div>

      {runPickerOpen ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
          onMouseDown={() => {
            if (runLocked) setRunPickerOpen(false);
          }}
        >
          <div
            style={{
              width: 700,
              maxWidth: "95vw",
              background: "#0b0f1a",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 16,
              padding: 16,
            }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h3 style={{ margin: 0 }}>Select or Create a Run</h3>
              <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <button type="button" onClick={refreshRuns} disabled={isSending}>
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => setRunPickerOpen(false)}
                  disabled={!runLocked}
                  title={!runLocked ? "Select or create a run first" : ""}
                >
                  Close
                </button>
              </div>
            </div>

            <div style={{ display: "flex", gap: 14, marginTop: 14 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>
                  Existing runs
                </div>
                <div
                  style={{
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 12,
                    overflow: "hidden",
                    maxHeight: 340,
                    overflowY: "auto",
                  }}
                >
                  {runs.length === 0 ? (
                    <div style={{ padding: 12, opacity: 0.75 }}>
                      No runs found yet.
                    </div>
                  ) : (
                    runs.map((r) => (
                      <button
                        key={r.run_id}
                        type="button"
                        onClick={() => selectExistingRun(r.run_id)}
                        disabled={isSending}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          padding: 12,
                          border: "none",
                          borderBottom: "1px solid rgba(255,255,255,0.08)",
                          background: "transparent",
                          color: "white",
                          cursor: isSending ? "not-allowed" : "pointer",
                          opacity: isSending ? 0.6 : 1,
                        }}
                      >
                        <div style={{ fontWeight: 700 }}>
                          {r.title ? r.title : r.run_id}
                        </div>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          {(r.patch_count ?? 0) + " patches"} • updated{" "}
                          {r.updated_ts ?? r.last_ts ?? ""}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>

              <div style={{ width: 280 }}>
                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>
                  Create a new run
                </div>

                <input
                  value={newRunId}
                  onChange={(e) => setNewRunId(e.target.value)}
                  placeholder="e.g., run_2026_03_03_A"
                  style={{ width: "100%", padding: 10, borderRadius: 10 }}
                  disabled={isSending}
                />
                <button
                  type="button"
                  onClick={createNewRun}
                  disabled={isSending}
                  style={{ marginTop: 10, width: "100%" }}
                >
                  {isSending ? "Creating..." : "Create + Select"}
                </button>

                <div style={{ marginTop: 10, fontSize: 12, opacity: 0.75 }}>
                  You must select or create a run before adding patches.
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {universeOpen ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.55)",
            display: "flex",
            justifyContent: "flex-end",
            zIndex: 9999,
          }}
          onMouseDown={() => setUniverseOpen(false)}
        >
          <div
            style={{
              width: 640,
              height: "100%",
              background: "#0b0f1a",
              borderLeft: "1px solid rgba(255,255,255,0.12)",
              padding: 16,
              overflow: "auto",
            }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h3 style={{ margin: 0 }}>Universe</h3>
              <label style={{ marginLeft: 10, fontSize: 12, opacity: 0.85 }}>
                live:
              </label>
              <input
                type="checkbox"
                checked={liveOn}
                onChange={(e) => setLiveOn(e.target.checked)}
              />
              <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <button type="button" onClick={universeLoadRuns}>
                  Refresh
                </button>
                <button type="button" onClick={() => setUniverseOpen(false)}>
                  Close
                </button>
              </div>
            </div>

            {universeError ? (
              <div
                style={{
                  marginTop: 10,
                  marginBottom: 10,
                  padding: 10,
                  borderRadius: 8,
                  background: "rgba(255,0,0,0.08)",
                  border: "1px solid rgba(255,0,0,0.25)",
                }}
              >
                <b>Error:</b> {universeError}
              </div>
            ) : null}

            <div style={{ marginTop: 12, display: "flex", gap: 12 }}>
              <div style={{ width: 240 }}>
                <div style={{ opacity: 0.8, fontSize: 12, marginBottom: 6 }}>
                  Runs ({runs.length})
                </div>
                <div
                  style={{
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 10,
                    overflow: "hidden",
                  }}
                >
                  {runs.length === 0 ? (
                    <div style={{ padding: 10, opacity: 0.7 }}>No runs yet.</div>
                  ) : (
                    runs.map((r) => (
                      <button
                        key={r.run_id}
                        type="button"
                        onClick={() => setUniverseSelectedRun(r.run_id)}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          padding: "10px",
                          border: "none",
                          borderBottom: "1px solid rgba(255,255,255,0.08)",
                          background:
                            r.run_id === universeSelectedRun
                              ? "rgba(255,255,255,0.08)"
                              : "transparent",
                          color: "white",
                          cursor: "pointer",
                        }}
                      >
                        <div style={{ fontWeight: 700 }}>
                          {r.title ? r.title : r.run_id}
                        </div>
                        <div style={{ fontSize: 12, opacity: 0.75 }}>
                          {r.patch_count ?? 0} patches • updated{" "}
                          {r.updated_ts ?? ""}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>

              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, opacity: 0.8 }}>
                  Selected: <b>{universeSelectedRun || "—"}</b>
                </div>

                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>
                    State (filtered)
                  </div>
                  <pre
                    style={{
                      padding: 10,
                      borderRadius: 10,
                      border: "1px solid rgba(255,255,255,0.12)",
                      overflowX: "auto",
                      maxHeight: 160,
                      overflowY: "auto",
                    }}
                  >
                    {JSON.stringify(universeState || {}, null, 2)}
                  </pre>
                </div>

                <div style={{ marginTop: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>
                    Patches (filtered) ({universePatches.length})
                  </div>
                  <pre
                    style={{
                      padding: 10,
                      borderRadius: 10,
                      border: "1px solid rgba(255,255,255,0.12)",
                      overflowX: "auto",
                      maxHeight: 360,
                      overflowY: "auto",
                    }}
                  >
                    {JSON.stringify(universePatches || [], null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}