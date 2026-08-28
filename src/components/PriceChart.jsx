import {
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
} from "recharts";
import { buildPriceSeries } from "../data/prices";

const CHART_COLORS = {
  public: "#7bea29",
  booking: "#43a7ff",
  flexible: "#a789ff",
  forecast: "#a789ff",
};

function PriceTooltip({ active, payload, label, variant }) {
  if (!active || !payload?.length) return null;

  const title = variant === "booking"
    ? "Registered booking price"
    : variant === "flexible"
      ? "Flexible booking price"
      : variant === "forecast"
        ? "Forecast public price"
        : "Public charging price";

  return (
    <div className={`chart-tooltip ${["booking", "flexible"].includes(variant) ? "booking-tooltip" : ""}`}>
      <small>{title}</small>
      <strong>Rs. {Number(payload[0].value).toFixed(2)} /kWh</strong>
      <span>{label}</span>
      <small>15-minute slot</small>
    </div>
  );
}

export default function PriceChart({
  prices,
  compact = false,
  activeSlotIndex = null,
  variant = "public",
  activeLabel = "Current slot",
  rangeStartSlotIndex = null,
  rangeEndSlotIndex = null,
  rangeLabel = "Selected time range",
}) {
  const data = buildPriceSeries(prices);
  const activeTime = Number.isInteger(activeSlotIndex)
    ? data[activeSlotIndex]?.time
    : null;
  const hasRange = Number.isInteger(rangeStartSlotIndex)
    && Number.isInteger(rangeEndSlotIndex)
    && rangeEndSlotIndex >= rangeStartSlotIndex;
  const rangeStartTime = hasRange ? data[rangeStartSlotIndex]?.time : null;
  const rangeEndTime = hasRange ? data[rangeEndSlotIndex]?.time : null;
  const lineColor = CHART_COLORS[variant] ?? CHART_COLORS.public;

  return (
    <div className={compact ? "chart-wrap compact" : "chart-wrap"}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 2 }}>
          <CartesianGrid stroke="rgba(148,163,184,.14)" vertical={false} />
          <XAxis
            dataKey="time"
            stroke="#89a0b7"
            tickLine={false}
            axisLine={{ stroke: "rgba(148,163,184,.25)" }}
            interval={15}
            minTickGap={24}
          />
          <YAxis
            stroke="#89a0b7"
            tickLine={false}
            axisLine={false}
            width={48}
            domain={[0, "dataMax + 10"]}
            tickFormatter={(value) => value.toFixed(0)}
          />
          <Tooltip
            content={<PriceTooltip variant={variant} />}
            cursor={{ stroke: "rgba(255,255,255,.4)", strokeDasharray: "4 4" }}
          />

          {hasRange && rangeStartTime && rangeEndTime && (
            <>
              <ReferenceArea
                x1={rangeStartTime}
                x2={rangeEndTime}
                fill={lineColor}
                fillOpacity={0.15}
                strokeOpacity={0}
                label={{
                  value: rangeLabel,
                  position: "insideTop",
                  fill: "#dce8f1",
                  fontSize: 11,
                }}
              />
              <ReferenceLine
                x={rangeStartTime}
                stroke="#ffffff"
                strokeDasharray="4 4"
                label={{ value: "Earliest", position: "insideTopLeft", fill: "#dce8f1", fontSize: 10 }}
              />
              <ReferenceLine
                x={rangeEndTime}
                stroke="#ffffff"
                strokeDasharray="4 4"
                label={{ value: "Latest", position: "insideTopRight", fill: "#dce8f1", fontSize: 10 }}
              />
            </>
          )}

          {activeTime && (
            <ReferenceLine
              x={activeTime}
              stroke="#fff"
              strokeDasharray="4 4"
              label={{
                value: activeLabel,
                position: "insideTopRight",
                fill: "#dce8f1",
                fontSize: 11,
              }}
            />
          )}
          <Line
            type="stepAfter"
            dataKey="price"
            stroke={lineColor}
            strokeWidth={3}
            dot={false}
            activeDot={{ r: 5, fill: "#f3f8fc", stroke: lineColor, strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
