export default function Progress({ stage, pct }: { stage: string; pct: number }) {
  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 9 }}>
        <span>
          <b>{stage}</b>
          …
        </span>
        <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>
          {Math.round(pct)}%
        </span>
      </div>
      <div className="pbar">
        <div className="pfill" style={{ width: `${Math.max(2, pct)}%` }} />
      </div>
    </div>
  );
}
