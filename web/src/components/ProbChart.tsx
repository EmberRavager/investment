import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const axis = { stroke: "#616c82", fontSize: 11, fontFamily: "var(--mono)" };

export default function ProbChart({ data, threshold }: { data: any[]; threshold: number }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1a2130" />
        <XAxis dataKey="date" tick={axis} minTickGap={60} />
        <YAxis tick={axis} domain={[0, 1]} width={40} />
        <Tooltip
          contentStyle={{ background: "#121723", border: "1px solid #232b3d", fontSize: 12, fontFamily: "var(--mono)" }}
          labelStyle={{ color: "#9aa4b8" }}
          formatter={(v: any) => [Number(v).toFixed(3), "多头概率"]}
        />
        <ReferenceLine y={threshold} stroke="#f5a623" strokeDasharray="4 4" />
        <ReferenceLine y={0.5} stroke="#616c82" strokeDasharray="2 4" />
        <Line type="monotone" dataKey="proba" stroke="#1fbf75" dot={false} strokeWidth={1.4} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}
