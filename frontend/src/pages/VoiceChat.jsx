// frontend/src/pages/VoiceChat.jsx
import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "../api";

/**
 * VoiceChat UI
 * - Text chat (POST /api/voice/ingest)
 * - Microphone "Hold to Talk" (Web Speech API → transcript → POST /api/voice/ingest)
 * - Debug logs + visible error banner
 * - Optional "Load patches/state" buttons (GET endpoints)
 */
export default function VoiceChat() {
  const [runId, setRunId] = useState("run_1");

  // chat state
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]); // {role, text, ts?}
  const [state, setState] = useState({});
  const [patches, setPatches] = useState([]);

  // UX/debug state
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);

  // Voice state
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState("");

  const recognitionRef = useRef(null);

  // ---------- helpers ----------
  function pushMessage(role, text) {
    setMessages((prev) => [...prev, { role, text, ts: Date.now() }]);
  }

  function setErr(msg) {
    setError(msg || "");
    if (msg) console.error(msg);
  }

  async function ingestText(text) {
    const payload = { run_id: runId, text };
    console.log("POSTING TO /api/voice/ingest", payload);

    const res = await apiPost("/api/voice/ingest", payload);
    console.log("RESPONSE", res);

    // Render assistant if present
    if (res?.assistant_message) pushMessage("assistant", res.assistant_message);

    // Update derived state + patches (if backend returns them)
    if (res?.state) setState(res.state);
    if (Array.isArray(res?.committed_patches)) {
      setPatches((prev) => [...prev, ...res.committed_patches]);
    }

    return res;
  }

  // ---------- text send ----------
  async function send() {
    console.log("CLICK SEND");

    setErr("");

    if (!input.trim()) return;

    const text = input.trim();
    setInput("");
    pushMessage("researcher", text);

    setIsSending(true);
    try {
      await ingestText(text);
    } catch (e) {
      setErr(`POST FAILED: ${e?.message || String(e)}`);
    } finally {
      setIsSending(false);
    }
  }

  // ---------- optional GETs ----------
  async function loadPatches() {
    setErr("");
    try {
      const res = await apiGet(`/api/runs/${encodeURIComponent(runId)}/patches`);
      console.log("GET PATCHES", res);
      setPatches(res?.patches || []);
    } catch (e) {
      setErr(`GET /patches FAILED: ${e?.message || String(e)}`);
    }
  }

  async function loadState() {
    setErr("");
    try {
      const res = await apiGet(`/api/runs/${encodeURIComponent(runId)}/state`);
      console.log("GET STATE", res);
      setState(res?.state || {});
    } catch (e) {
      setErr(`GET /state FAILED: ${e?.message || String(e)}`);
    }
  }

  // ---------- voice (Web Speech API) ----------
  // Works on Chrome/Edge (desktop). Safari/Firefox vary.
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      console.warn("Web Speech API not supported in this browser.");
      return;
    }

    const rec = new SpeechRecognition();
    rec.continuous = true; // keep listening
    rec.interimResults = true; // show interim
    rec.lang = "en-US";

    rec.onstart = () => {
      console.log("VOICE: onstart");
      setIsListening(true);
      setErr("");
    };

    rec.onend = () => {
      console.log("VOICE: onend");
      setIsListening(false);
      setInterim("");
    };

    rec.onerror = (event) => {
      console.error("VOICE: onerror", event);
      setErr(`Voice error: ${event?.error || "unknown"}`);
      setIsListening(false);
    };

    rec.onresult = async (event) => {
      // Build interim + final transcript
      let interimText = "";
      let finalText = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0]?.transcript || "";
        if (result.isFinal) finalText += transcript;
        else interimText += transcript;
      }

      setInterim(interimText);

      // If we got a final chunk, send it
      if (finalText.trim()) {
        const spoken = finalText.trim();
        console.log("VOICE FINAL:", spoken);

        // Show as researcher message
        pushMessage("researcher", `🎙️ ${spoken}`);

        setIsSending(true);
        try {
          await ingestText(spoken);
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
        rec.onresult = null;
        rec.onend = null;
        rec.onerror = null;
        rec.onstart = null;
        rec.stop();
      } catch {
        // ignore
      }
    };
  }, []);

  function startListening() {
    setErr("");
    const rec = recognitionRef.current;
    if (!rec) {
      setErr("Web Speech API not available in this browser (try Chrome/Edge).");
      return;
    }
    try {
      console.log("VOICE: start()");
      rec.start();
    } catch (e) {
      // Chrome throws if start() called twice
      console.warn("VOICE start error (often harmless):", e);
    }
  }

  function stopListening() {
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      console.log("VOICE: stop()");
      rec.stop();
    } catch (e) {
      console.warn("VOICE stop error:", e);
    }
  }

  // Allow Enter to send
  function onKeyDown(e) {
    if (e.key === "Enter") send();
  }

  // ---------- UI ----------
  return (
    <div style={{ padding: 30, maxWidth: 950 }}>
      <h2 style={{ marginBottom: 8 }}>StemY Conversational Assistant</h2>

      {/* Error banner */}
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

      {/* Run ID + controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <label style={{ minWidth: 55 }}>Run ID:</label>
        <input
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          style={{ width: 220 }}
        />

        <button onClick={loadState} type="button">
          Load State
        </button>
        <button onClick={loadPatches} type="button">
          Load Patches
        </button>

        <div style={{ marginLeft: "auto", opacity: 0.8, fontSize: 12 }}>
          {isSending ? "Sending..." : ""}
        </div>
      </div>

      {/* Voice controls */}
      <div style={{ marginTop: 16, display: "flex", gap: 10 }}>
        <button
          type="button"
          onMouseDown={startListening}
          onMouseUp={stopListening}
          onTouchStart={startListening}
          onTouchEnd={stopListening}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            cursor: "pointer",
          }}
        >
          {isListening ? "🎙️ Listening… (release to stop)" : "Hold to Talk"}
        </button>

        <button type="button" onClick={() => setMessages([])}>
          Clear Chat
        </button>

        <button type="button" onClick={() => setPatches([])}>
          Clear Patches
        </button>
      </div>

      {interim ? (
        <div style={{ marginTop: 10, opacity: 0.8 }}>
          <b>Interim:</b> {interim}
        </div>
      ) : null}

      {/* Chat transcript */}
      <div
        style={{
          marginTop: 18,
          padding: 16,
          borderRadius: 12,
          border: "1px solid rgba(255,255,255,0.12)",
          minHeight: 180,
        }}
      >
        {messages.length === 0 ? (
          <div style={{ opacity: 0.7 }}>
            Say or type an update (e.g., “CHIR was 8 micromolar for 24 hours, we
            started at 9am.”)
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <b style={{ textTransform: "lowercase" }}>{m.role}:</b> {m.text}
            </div>
          ))
        )}
      </div>

      {/* Text input */}
      <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Describe your experiment update..."
          style={{ flex: 1, minWidth: 300 }}
        />
        <button onClick={send} disabled={isSending}>
          Send
        </button>
      </div>

      {/* Derived State */}
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

      {/* Patches */}
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
    </div>
  );
}