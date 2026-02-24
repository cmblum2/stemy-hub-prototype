import { useEffect, useRef, useState } from "react";
import { sseUrl } from "../api";

export function useSSE(runId) {
  const [connected, setConnected] = useState(false);
  const [feed, setFeed] = useState([]);
  const stateRef = useRef({}); // merged kv snapshot in-memory

  useEffect(() => {
    if (!runId) return;

    const es = new EventSource(sseUrl(runId));

    es.addEventListener("hello", () => setConnected(true));

    es.addEventListener("patch", (evt) => {
      try {
        const msg = JSON.parse(evt.data); // {type:"patch", data:{...patch...}}
        const patch = msg?.data;

        setFeed((prev) => [patch, ...prev].slice(0, 200));

        // merge kv into in-memory state
        const kv = patch?.kv || {};
        Object.entries(kv).forEach(([k, v]) => {
          stateRef.current[k] = { value: v, ts: patch.ts };
        });
      } catch {
        // ignore malformed
      }
    });

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [runId]);

  return { connected, feed, mergedState: stateRef.current };
}