import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function FeatureImportance({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data || {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => a.value - b.value)
    .slice(-18);

  if (!rows.length) {
    return <div className="hint">该模型无特征重要性（如线性/距离类模型）。</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 10, bottom: 0 }}>
        <CartesianGrid stroke="#1a2130" horizontal={false} />
        <XAxis type="number" tick={{ stroke: "#616c82", fontSize: 11, fontFamily: "var(--mono)" }} />
        <YAxis
          type="category"
          dataKey="name"
          width={92}
          tick={{ stroke: "#9aa4b8", fontSize: 11, fontFamily: "var(--mono)" }}
        />
        <Tooltip
          contentStyle={{ background: "#121723", border: "1px solid #232b3d", fontSize: 12, fontFamily: "var(--mono)" }}
          labelStyle={{ color: "#9aa4b8" }}
          formatter={(v: any) => [Number(v).toFixed(4), "重要性"]}
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]}>
          {rows.map((_, i) => (
            <Cell key={i} fill={`rgba(76,141,255,${0.45 + (0.5 * i) / rows.length})`} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
