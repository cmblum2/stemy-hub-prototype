const stages = [
  "maintenance.hpsc",
  "diff.primitive_streak",
  "diff.cardiac_mesoderm",
  "diff.immature_cardiomyocyte",
  "diff.mature_cardiomyocyte",
];

export default function StageTimeline({ stage }) {
  const idx = stages.indexOf(stage);
  return (
    <div className="timeline">
      {stages.map((s, i) => (
        <div key={s} className={`step ${idx >= 0 && i <= idx ? "active" : ""}`}>
          <div className="dot" />
          <div className="label">{s}</div>
        </div>
      ))}
    </div>
  );
}