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

export default function AdminForecastChart({ data, series, height = 330, yLabel = "", valueSuffix = "" }) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 18, right: 24, left: 6, bottom: 8 }}>
          <CartesianGrid stroke="rgba(148,174,196,.13)" vertical={false} />
          <XAxis dataKey="time" stroke="#8297aa" tickLine={false} axisLine={false} interval={15} minTickGap={24} />
          <YAxis stroke="#8297aa" tickLine={false} axisLine={false} width={64} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#8297aa", fontSize: 11 } : undefined} />
          <Tooltip
            contentStyle={{ background: "#071827", border: "1px solid rgba(148,174,196,.25)", borderRadius: 9 }}
            labelStyle={{ color: "#dce8f1" }}
            formatter={(value, name) => [`${Number(value).toFixed(2)}${valueSuffix}`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
          {series.map((item, index) => (
            <Line
              key={item.key}
              type={item.step ? "stepAfter" : "monotone"}
              dataKey={item.key}
              name={item.label}
              stroke={item.color}
              strokeWidth={item.width || 2.2}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={index < 4}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
