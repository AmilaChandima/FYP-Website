import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CircleDollarSign, Clock3, Landmark, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { formatCurrency, getRevenueData, getRevenueSummary, subscribeToAdminData } from "../../services/adminData";
import { slotTime } from "../../utils/time";

export default function AdminRevenue() {
  const [, setVersion] = useState(0);
  useEffect(() => subscribeToAdminData(() => setVersion((value) => value + 1)), []);
  const revenue = getRevenueData();
  const summary = getRevenueSummary();
  const dailyData = revenue.daily.map((item) => ({
    ...item,
    label: new Date(`${item.date}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }),
  }));
  const hourlyData = Array.from({ length: 24 }, (_, hour) => ({
    hour: `${String(hour).padStart(2, "0")}:00`,
    amount: revenue.todaySlots.slice(hour * 4, hour * 4 + 4).reduce((sum, value) => sum + value, 0),
  }));
  const completedHours = Math.floor(summary.currentSlot / 4);
  const todayHourlyUpToNow = hourlyData.slice(0, completedHours + 1);
  const bestDay = dailyData.reduce((best, item) => item.amount > best.amount ? item : best, dailyData[0]);
  const average = dailyData.reduce((sum, item) => sum + item.amount, 0) / dailyData.length;

  return (
    <div className="admin-page">
      <div className="admin-page-heading"><div><p>FINANCIAL PERFORMANCE</p><h1>Income & Revenue Analytics</h1><span>Monitor today’s income up to the current time and historical day-by-day station performance.</span></div></div>

      <section className="admin-stat-grid">
        <article className="admin-stat-card revenue"><div><span>Today, up to now</span><strong>{formatCurrency(summary.todayUpToNow)}</strong><small><Clock3 size={14} /> Through slot {slotTime(summary.currentSlot)}</small></div><CircleDollarSign /></article>
        <article className="admin-stat-card bookings"><div><span>Projected today</span><strong>{formatCurrency(summary.todayProjected)}</strong><small><TrendingUp size={14} /> Full-day estimate</small></div><TrendingUp /></article>
        <article className="admin-stat-card chargers"><div><span>30-day average</span><strong>{formatCurrency(average)}</strong><small>Average daily station income</small></div><Landmark /></article>
        <article className="admin-stat-card customers"><div><span>All-time demo income</span><strong>{formatCurrency(summary.allTime)}</strong><small>Accumulated stored records</small></div><CircleDollarSign /></article>
      </section>

      <section className="admin-revenue-grid">
        <article className="admin-panel">
          <div className="admin-panel-heading"><div><h2>Day-by-Day Income</h2><p>Complete stored station-income history for the last 30 days.</p></div><span className="admin-best-day">Best day: {bestDay.label} · {formatCurrency(bestDay.amount)}</span></div>
          <div className="admin-chart-xl">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dailyData} margin={{ top: 12, right: 12, left: 12, bottom: 0 }}>
                <defs><linearGradient id="revenuePageFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#43a7ff" stopOpacity={0.38} /><stop offset="100%" stopColor="#43a7ff" stopOpacity={0.02} /></linearGradient></defs>
                <CartesianGrid stroke="rgba(148,163,184,.13)" vertical={false} />
                <XAxis dataKey="label" stroke="#8298aa" tickLine={false} axisLine={false} interval={3} />
                <YAxis stroke="#8298aa" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(value / 1000)}k`} />
                <Tooltip formatter={(value) => [formatCurrency(value), "Income"]} contentStyle={{ background: "#091b2a", border: "1px solid rgba(255,255,255,.16)", borderRadius: 9 }} />
                <Area type="monotone" dataKey="amount" stroke="#43a7ff" strokeWidth={3} fill="url(#revenuePageFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-heading"><div><h2>Today’s Hourly Income</h2><p>Income earned up to the current station hour.</p></div></div>
          <div className="admin-chart-xl">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={todayHourlyUpToNow} margin={{ top: 12, right: 12, left: 12, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,.13)" vertical={false} />
                <XAxis dataKey="hour" stroke="#8298aa" tickLine={false} axisLine={false} interval={2} />
                <YAxis stroke="#8298aa" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(value / 1000)}k`} />
                <Tooltip formatter={(value) => [formatCurrency(value), "Income"]} contentStyle={{ background: "#091b2a", border: "1px solid rgba(255,255,255,.16)", borderRadius: 9 }} />
                <Bar dataKey="amount" fill="#78e82f" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="admin-panel">
        <div className="admin-panel-heading"><div><h2>Daily Income Records</h2><p>Stored revenue totals available to the station owner.</p></div></div>
        <div className="admin-table-wrap">
          <table className="admin-table"><thead><tr><th>Date</th><th>Daily income</th><th>Difference from average</th><th>Performance</th></tr></thead><tbody>
            {[...dailyData].reverse().map((item) => {
              const difference = item.amount - average;
              return <tr key={item.date}><td><strong>{new Date(`${item.date}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" })}</strong></td><td>{formatCurrency(item.amount)}</td><td className={difference >= 0 ? "positive-number" : "negative-number"}>{difference >= 0 ? "+" : ""}{formatCurrency(difference)}</td><td><span className={`admin-status-pill ${difference >= 0 ? "completed" : "cancelled"}`}>{difference >= 0 ? "Above average" : "Below average"}</span></td></tr>;
            })}
          </tbody></table>
        </div>
      </section>
    </div>
  );
}
