import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const axis = { stroke: "#616c82", fontSize: 11, fontFamily: "var(--mono)" };

export default function NavChart({ data }: { data: any[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1a2130" />
        <XAxis dataKey="date" tick={axis} minTickGap={60} />
        <YAxis tick={axis} domain={["auto", "auto"]} width={52} tickFormatter={(v) => v.toFixed(2)} />
        <Tooltip
          contentStyle={{ background: "#121723", border: "1px solid #232b3d", fontSize: 12, fontFamily: "var(--mono)" }}
          labelStyle={{ color: "#9aa4b8" }}
          formatter={(v: any, n: any) => [Number(v).toFixed(3), n === "strategy" ? "策略" : "买入持有"]}
        />
        <Legend formatter={(v) => (v === "strategy" ? "策略" : "买入持有")} wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="strategy" stroke="#ff4d4f" dot={false} strokeWidth={1.8} />
        <Line type="monotone" dataKey="benchmark" stroke="#4c8dff" dot={false} strokeWidth={1.4} strokeOpacity={0.85} />
      </LineChart>
    </ResponsiveContainer>
  );
}
