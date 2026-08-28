import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BatteryCharging,
  BookOpenCheck,
  CircleDollarSign,
  Clock3,
  Sparkles,
  TrendingUp,
  UsersRound,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useStationData } from "../../context/StationDataContext";
import { formatDateLabel, formatTime12 } from "../../utils/time";
import {
  formatCurrency,
  getAllBookings,
  getCustomers,
  getRevenueData,
  getRevenueSummary,
  subscribeToAdminData,
} from "../../services/adminData";

export default function AdminOverview() {
  const [, setVersion] = useState(0);
  useEffect(() => subscribeToAdminData(() => setVersion((value) => value + 1)), []);
  const { chargers, lastPriceUpdate, fixedArrivalTomorrowPrices, flexibleBookingPrice } = useStationData();
  const fixedBookingMin = Math.min(...fixedArrivalTomorrowPrices);
  const fixedBookingMax = Math.max(...fixedArrivalTomorrowPrices);
  const customers = getCustomers();
  const bookings = getAllBookings();
  const revenue = getRevenueData();
  const summary = getRevenueSummary();
  const available = chargers.filter((charger) => charger.status === "available").length;
  const occupied = chargers.filter((charger) => charger.status === "charging").length;
  const activeBookings = bookings
    .filter((booking) => ["reserved", "scheduled", "pending"].includes(booking.status))
    .sort((a, b) => `${a.date}${a.scheduledStart || a.arrivalTime || a.windowStart || ""}`.localeCompare(`${b.date}${b.scheduledStart || b.arrivalTime || b.windowStart || ""}`));
  const pendingFlexible = bookings.filter((booking) => booking.status === "pending").length;
  const chartData = revenue.daily.slice(-14).map((item) => ({
    ...item,
    label: new Date(`${item.date}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }),
  }));

  return (
    <div className="admin-page">
      <div className="admin-page-heading">
        <div><p>STATION OVERVIEW</p><h1>Good afternoon, Administrator</h1><span>Live operational and commercial summary for SolarCharge Station.</span></div>
        <Link to="/admin/optimization" className="admin-primary-link"><Sparkles size={18} /> Run Tomorrow Optimization</Link>
      </div>

      <section className="admin-stat-grid">
        <article className="admin-stat-card revenue"><div><span>Income today, up to now</span><strong>{formatCurrency(summary.todayUpToNow)}</strong><small><TrendingUp size={14} /> Projected {formatCurrency(summary.todayProjected)}</small></div><CircleDollarSign /></article>
        <article className="admin-stat-card bookings"><div><span>Active booking records</span><strong>{activeBookings.length}</strong><small><BookOpenCheck size={14} /> {pendingFlexible} flexible requests pending</small></div><BookOpenCheck /></article>
        <article className="admin-stat-card chargers"><div><span>Charger availability</span><strong>{available} / 10</strong><small><Zap size={14} /> {occupied} currently occupied</small></div><BatteryCharging /></article>
        <article className="admin-stat-card customers"><div><span>Registered customers</span><strong>{customers.length}</strong><small><UsersRound size={14} /> Customer accounts</small></div><UsersRound /></article>
      </section>

      <section className="admin-booking-rate-strip">
        <span>Fixed-arrival booking <strong>Rs. {fixedBookingMin.toFixed(2)}–{fixedBookingMax.toFixed(2)}/kWh</strong></span>
        <span>Flexible smart booking <strong>Rs. {Number(flexibleBookingPrice).toFixed(2)}/kWh</strong></span>
        <Link to="/admin/prices">Manage booking rates</Link>
      </section>

      <section className="admin-overview-grid">
        <article className="admin-panel admin-revenue-preview">
          <div className="admin-panel-heading"><div><h2>Daily Station Income</h2><p>Revenue performance across the last 14 operating days.</p></div><Link to="/admin/revenue">View full report</Link></div>
          <div className="admin-chart-large">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 15, right: 10, left: 8, bottom: 0 }}>
                <defs><linearGradient id="adminRevenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#78e82f" stopOpacity={0.36} /><stop offset="100%" stopColor="#78e82f" stopOpacity={0.02} /></linearGradient></defs>
                <CartesianGrid stroke="rgba(148,163,184,.13)" vertical={false} />
                <XAxis dataKey="label" stroke="#8298aa" tickLine={false} axisLine={false} />
                <YAxis stroke="#8298aa" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(value / 1000)}k`} />
                <Tooltip formatter={(value) => [formatCurrency(value), "Income"]} contentStyle={{ background: "#0a1c2c", border: "1px solid rgba(255,255,255,.16)", borderRadius: 9 }} />
                <Area type="monotone" dataKey="amount" stroke="#78e82f" strokeWidth={3} fill="url(#adminRevenueFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="admin-panel admin-operations-card">
          <div className="admin-panel-heading"><div><h2>Live Station Status</h2><p>Current operating state of all charging points.</p></div><Link to="/admin/chargers">Manage</Link></div>
          <div className="admin-charger-mini-grid">
            {chargers.map((charger) => (
              <div key={charger.id} className={`admin-charger-mini ${charger.status}`}>
                <span>{String(charger.id).padStart(2, "0")}</span>
                <i />
                <strong>{charger.status === "charging" ? "Occupied" : charger.status === "offline" ? "Out of order" : "Available"}</strong>
              </div>
            ))}
          </div>
          <div className="admin-operation-note"><Clock3 size={17} /><span>Last pricing update: {lastPriceUpdate ? new Date(lastPriceUpdate).toLocaleString("en-US") : "Using initial schedules"}</span></div>
        </article>
      </section>

      <section className="admin-panel admin-booking-preview">
        <div className="admin-panel-heading"><div><h2>Tomorrow Booking Requirements</h2><p>Fixed reservations and flexible requests waiting for or receiving scheduling.</p></div><Link to="/admin/bookings">View all bookings</Link></div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Customer</th><th>Method</th><th>Date</th><th>Requested / scheduled time</th><th>Price</th><th>Status</th></tr></thead>
            <tbody>
              {activeBookings.slice(0, 6).map((booking) => (
                <tr key={booking.id}>
                  <td><strong>{booking.userName}</strong><small>{booking.userEmail}</small></td>
                  <td><span className={`booking-type-pill ${booking.bookingType}`}>{booking.bookingType === "fixed" ? "Fixed" : "Flexible"}</span></td>
                  <td>{formatDateLabel(booking.date)}</td>
                  <td>{booking.scheduledStart
                    ? `${formatTime12(booking.scheduledStart)}–${formatTime12(booking.scheduledEnd)}`
                    : `${formatTime12(booking.windowStart)}–${formatTime12(booking.windowEnd)}`}</td>
                  <td>Rs. {Number(booking.price).toFixed(2)}/kWh</td>
                  <td><span className={`admin-status-pill ${booking.status}`}>{booking.status}</span></td>
                </tr>
              ))}
              {activeBookings.length === 0 && <tr><td colSpan="6" className="admin-empty-table">No active booking records.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
