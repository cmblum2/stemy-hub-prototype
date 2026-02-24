export default function StatusBadge({ connected }) {
  return (
    <span className={`badge ${connected ? "ok" : "bad"}`}>
      {connected ? "SSE Connected" : "SSE Disconnected"}
    </span>
  );
}