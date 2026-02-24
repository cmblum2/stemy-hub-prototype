function groupKey(k) {
  if (k.startsWith("env.")) return "Environment";
  if (k.startsWith("process.")) return "Process";
  if (k.startsWith("cell.")) return "Cell";
  if (k.startsWith("media.")) return "Media";
  return "Other";
}

export default function StateTable({ state, compact }) {
  const entries = Object.entries(state || {}).sort((a, b) => a[0].localeCompare(b[0]));
  const grouped = entries.reduce((acc, [k, v]) => {
    const g = groupKey(k);
    acc[g] = acc[g] || [];
    acc[g].push([k, v]);
    return acc;
  }, {});

  return (
    <div className={compact ? "state compact" : "state"}>
      {Object.keys(grouped).map((g) => (
        <div key={g} className="stateGroup">
          <h3>{g}</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Value</th>
                {!compact && <th>Type</th>}
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {grouped[g].map(([k, obj]) => (
                <tr key={k}>
                  <td className="mono">{k}</td>
                  <td>{String(obj?.value?.v ?? "")}</td>
                  {!compact && <td className="muted">{obj?.value?.t}</td>}
                  <td className="muted">{obj?.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}