export default function PatchFeed({ feed }) {
  if (!feed?.length) return <div className="muted">Waiting for patches…</div>;

  return (
    <div className="feed">
      {feed.map((p, i) => {
        const keys = Object.keys(p?.kv || {});
        return (
          <div className="feedItem" key={i}>
            <div className="muted small">{p?.ts}</div>
            <div className="mono small">{p?.patch_id}</div>
            <div className="small">
              {keys.slice(0, 6).join(", ")}{keys.length > 6 ? "…" : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}