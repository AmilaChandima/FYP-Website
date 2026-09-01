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
import {
  BatteryCharging,
  CircleDollarSign,
  Clock3,
  Sparkles,
  UsersRound,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useStationData } from "../../context/StationDataContext";
import {
  dateKey,
  formatDateLabel,
  formatTime12,
  getStationDateTime,
} from "../../utils/time";
import {
  formatCurrency,
  getAllBookings,
  getCustomers,
  subscribeToAdminData,
} from "../../services/adminData";
import {
  getLatestOptimizerResult,
  getOptimizerHistory,
  getOptimizerJob,
  getPrimaryElasticBaseInfo,
} from "../../services/optimizerApi";

function stationClock(now = new Date()) {
  const parts = getStationDateTime(now);
  const time24 = `${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
  const minuteOfDay = Math.max(0, Math.min(1439, parts.hour * 60 + parts.minute));
  return {
    ...parts,
    date: dateKey(parts),
    time24,
    minuteOfDay,
    slotIndex: Math.min(95, Math.floor(minuteOfDay / 15)),
  };
}

function occupiedChargersAtMinute(result, minute) {
  const entries = result?.chargerOccupancy?.[String(minute)]
    ?? result?.chargerOccupancy?.[minute]
    ?? [];

  const occupied = new Set();
  if (Array.isArray(entries)) {
    entries.forEach((entry) => {
      const chargerId = Number(typeof entry === "object" ? entry?.chargerId : entry);
      if (chargerId >= 1 && chargerId <= 10) occupied.add(chargerId);
    });
  }
  return occupied;
}

function slotForIndex(result, slotIndex) {
  const rows = Array.isArray(result?.slotOperation) ? result.slotOperation : [];
  if (rows.length === 0) return null;
  return rows.find((item) => Number(item?.slotIndex) === slotIndex) || rows[slotIndex] || null;
}

function energy(value) {
  return `${Number(value || 0).toFixed(1)} kWh`;
}

function cumulativeEnergyRows(result, currentSlotIndex) {
  const rows = Array.isArray(result?.slotOperation) ? result.slotOperation : [];
  if (rows.length === 0) return [];

  let pv = 0;
  let ev = 0;
  let gridImport = 0;
  let gridExport = 0;
  let bessCharge = 0;
  let bessDischarge = 0;

  return rows
    .filter((item) => Number(item?.slotIndex) <= currentSlotIndex)
    .sort((a, b) => Number(a?.slotIndex) - Number(b?.slotIndex))
    .map((item) => {
      pv += Number(item?.pvGenerationEnergyKWh || 0);
      ev += Number(item?.evDemandEnergyKWh || 0);
      gridImport += Number(item?.gridImportEnergyKWh || 0);
      gridExport += Number(item?.gridExportEnergyKWh || 0);
      bessCharge += Number(item?.bessChargeEnergyKWh || 0);
      bessDischarge += Number(item?.bessDischargeEnergyKWh || 0);

      return {
        slotNumber: Number(item?.slotNumber ?? item?.slotIndex ?? 0),
        pvGeneration: Number(pv.toFixed(3)),
        evDemand: Number(ev.toFixed(3)),
        gridImport: Number(gridImport.toFixed(3)),
        gridExport: Number(gridExport.toFixed(3)),
        bessCharge: Number(bessCharge.toFixed(3)),
        bessDischarge: Number(bessDischarge.toFixed(3)),
      };
    });
}

export default function AdminOverview() {
  const { chargers, fixedArrivalTomorrowPrices, flexibleBookingPrice } = useStationData();
  const [adminVersion, setAdminVersion] = useState(0);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [baseInfo, setBaseInfo] = useState(null);
  const [createdCustomerCount, setCreatedCustomerCount] = useState(null);
  const [todayOptimization, setTodayOptimization] = useState(null);
  const [todayOptimizationLoading, setTodayOptimizationLoading] = useState(true);

  const clock = useMemo(() => stationClock(new Date(clockTick)), [clockTick]);
  const fixedBookingMin = Math.min(...fixedArrivalTomorrowPrices);
  const fixedBookingMax = Math.max(...fixedArrivalTomorrowPrices);
  const customers = getCustomers();
  const bookings = getAllBookings();

  useEffect(() => subscribeToAdminData(() => setAdminVersion((value) => value + 1)), []);

  useEffect(() => {
    let active = true;

    fetch(`/api/customers?refresh=${Date.now()}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Unable to load customer accounts.");
        return response.json();
      })
      .then((items) => {
        if (active) setCreatedCustomerCount(Array.isArray(items) ? items.length : customers.length);
      })
      .catch(() => {
        if (active) setCreatedCustomerCount(customers.length);
      });

    return () => { active = false; };
  }, [adminVersion, customers.length]);

  useEffect(() => {
    const timer = window.setInterval(() => setClockTick(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    getPrimaryElasticBaseInfo()
      .then((result) => {
        if (active) setBaseInfo(result);
      })
      .catch(() => {
        if (active) setBaseInfo(null);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadTodayOptimization() {
      setTodayOptimizationLoading(true);
      let selected = null;

      try {
        const history = await getOptimizerHistory(50);
        const match = Array.isArray(history)
          ? history.find((item) => String(item?.targetDate || "") === clock.date && item?.jobId)
          : null;

        if (match?.jobId) {
          const job = await getOptimizerJob(match.jobId);
          if (job?.status === "success" && job?.result?.targetDate === clock.date) {
            selected = job.result;
          }
        }
      } catch {
        selected = null;
      }

      if (!selected) {
        try {
          const latest = await getLatestOptimizerResult();
          if (latest?.targetDate === clock.date) selected = latest;
        } catch {
          selected = null;
        }
      }

      if (active) {
        setTodayOptimization(selected);
        setTodayOptimizationLoading(false);
      }
    }

    loadTodayOptimization();
    return () => { active = false; };
  }, [clock.date]);

  const currentOccupied = useMemo(
    () => occupiedChargersAtMinute(todayOptimization, clock.minuteOfDay),
    [todayOptimization, clock.minuteOfDay]
  );

  const currentSlot = useMemo(
    () => slotForIndex(todayOptimization, clock.slotIndex),
    [todayOptimization, clock.slotIndex]
  );

  const cumulativeData = useMemo(
    () => cumulativeEnergyRows(todayOptimization, clock.slotIndex),
    [todayOptimization, clock.slotIndex]
  );

  const profitTodayUpToNow = useMemo(() => {
    const rows = Array.isArray(todayOptimization?.charts?.slotProfit)
      ? todayOptimization.charts.slotProfit
      : [];

    return rows
      .slice(0, clock.slotIndex + 1)
      .reduce((sum, item) => sum + Number(item?.slot_profit_LKR || 0), 0);
  }, [todayOptimization, clock.slotIndex]);

  const profitRealtimeReady = Boolean(
    Array.isArray(todayOptimization?.charts?.slotProfit)
    && todayOptimization.charts.slotProfit.length > 0
  );

  const optimizationRealtimeReady = Boolean(
    todayOptimization
    && todayOptimization.chargerOccupancyAvailable !== false
    && Array.isArray(todayOptimization.slotOperation)
    && todayOptimization.slotOperation.length > 0
  );

  const manualAvailable = chargers.filter((charger) => charger.status === "available").length;
  const manualOccupied = chargers.filter((charger) => charger.status === "charging").length;
  const occupied = optimizationRealtimeReady ? currentOccupied.size : manualOccupied;
  const available = optimizationRealtimeReady ? 10 - currentOccupied.size : manualAvailable;

  const baseCustomerCount = Number(baseInfo?.baseRows);
  const optimizerCustomerCount = Number.isFinite(baseCustomerCount)
    ? baseCustomerCount
    : Number(baseInfo?.primaryUsers || 0) + Number(baseInfo?.elasticUsers || 0);
  const websiteCustomerCount = Number.isFinite(Number(createdCustomerCount)) ? Number(createdCustomerCount) : customers.length;
  const registeredCustomerTotal = websiteCustomerCount + (Number.isFinite(optimizerCustomerCount) ? optimizerCustomerCount : 0);

  const activeBookings = bookings
    .filter((booking) => ["reserved", "scheduled", "pending"].includes(booking.status))
    .sort((a, b) => `${a.date}${a.scheduledStart || a.arrivalTime || a.windowStart || ""}`.localeCompare(`${b.date}${b.scheduledStart || b.arrivalTime || b.windowStart || ""}`));

  const gridImportEnergy = Number(currentSlot?.gridImportEnergyKWh || 0);
  const gridExportEnergy = Number(currentSlot?.gridExportEnergyKWh || 0);
  const bessChargeEnergy = Number(currentSlot?.bessChargeEnergyKWh || 0);
  const bessDischargeEnergy = Number(currentSlot?.bessDischargeEnergyKWh || 0);

  const gridExchangeValue = gridImportEnergy > 1e-6
    ? `Import · ${energy(gridImportEnergy)}`
    : gridExportEnergy > 1e-6
      ? `Export · ${energy(gridExportEnergy)}`
      : "No exchange · 0.0 kWh";

  const exportModeValue = gridExportEnergy > 1e-6
    ? String(currentSlot?.exportMode || "Export")
    : "No export";

  const batteryOperationValue = bessChargeEnergy > 1e-6
    ? `Charging · ${energy(bessChargeEnergy)}`
    : bessDischargeEnergy > 1e-6
      ? `Discharging · ${energy(bessDischargeEnergy)}`
      : "Idle · 0.0 kWh";

  return (
    <div className="admin-page">
      <div className="admin-page-heading">
        <div><p>STATION OVERVIEW</p><h1>Good afternoon, Administrator</h1><span>Live operational and commercial summary for SolarCharge Station.</span></div>
        <Link to="/admin/optimization" className="admin-primary-link"><Sparkles size={18} /> Run Tomorrow Optimization</Link>
      </div>

      <section className="admin-stat-grid compact overview-main-stat-grid">
        <article className="admin-stat-card revenue"><div><span>Profit today, up to now</span><strong>{profitRealtimeReady ? formatCurrency(profitTodayUpToNow) : "—"}</strong><small><Clock3 size={14} /> Through current slot {currentSlot?.slotNumber ?? clock.slotIndex}</small></div><CircleDollarSign /></article>
        <article className="admin-stat-card chargers"><div><span>Charger availability</span><strong>{available} / 10</strong><small><Zap size={14} /> {occupied} currently occupied</small></div><BatteryCharging /></article>
        <article className="admin-stat-card customers"><div><span>Registered customers</span><strong>{registeredCustomerTotal}</strong></div><UsersRound /></article>
      </section>
{/*}
      <section className="admin-booking-rate-strip">
        <span>Fixed-arrival booking <strong>Rs. {fixedBookingMin.toFixed(2)}–{fixedBookingMax.toFixed(2)}/kWh</strong></span>
        <span>Flexible smart booking <strong>Rs. {Number(flexibleBookingPrice).toFixed(2)}/kWh</strong></span>
        <Link to="/admin/prices">Manage booking rates</Link>
      </section>
*/}
      <section className="admin-panel admin-operations-card overview-realtime-occupancy-card">
          <div className="admin-panel-heading">
            <div><h2>Real-Time Charger Occupancy</h2><p>{formatDateLabel(clock.date)} · {formatTime12(clock.time24)}</p></div>
          </div>

          {optimizationRealtimeReady ? (
            <div className="admin-charger-mini-grid charger-occupancy-mini-grid overview-realtime-charger-grid">
              {Array.from({ length: 10 }, (_, index) => {
                const chargerId = index + 1;
                const isOccupied = currentOccupied.has(chargerId);
                return (
                  <div key={chargerId} className={`admin-charger-mini ${isOccupied ? "charging" : "available"}`}>
                    <span>{String(chargerId).padStart(2, "0")}</span>
                    <i />
                    <strong>{isOccupied ? "Occupied" : "Available"}</strong>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="overview-realtime-unavailable">
              <Clock3 size={19} />
              <span>{todayOptimizationLoading ? "Loading today’s optimized charger status..." : "Today’s optimized charger status is not available."}</span>
            </div>
          )}

          <div className="admin-operation-note"><Clock3 size={17} /><span>Current station time: {formatTime12(clock.time24)}</span></div>
      </section>

      <section className="admin-panel overview-realtime-operation-panel">
        <div className="admin-panel-heading overview-realtime-heading">
          <div><h2>Today Real-Time Optimized Operation</h2></div>
          <div className="overview-live-time"><Clock3 size={17} /><strong>{formatTime12(clock.time24)}</strong></div>
        </div>

        {currentSlot ? (
          <div className="selected-slot-results-grid overview-live-slot-grid">
            <div className="selected-slot-result-card"><span>Slot Number</span><strong>{currentSlot.slotNumber}</strong></div>
            <div className="selected-slot-result-card"><span>PV Generation</span><strong>{energy(currentSlot.pvGenerationEnergyKWh)}</strong></div>
            <div className="selected-slot-result-card"><span>EV Demand</span><strong>{energy(currentSlot.evDemandEnergyKWh)}</strong></div>
            <div className="selected-slot-result-card"><span>Grid Import / Export</span><strong>{gridExchangeValue}</strong></div>
            <div className="selected-slot-result-card"><span>Export Mode</span><strong>{exportModeValue}</strong></div>
            <div className="selected-slot-result-card"><span>Battery Operation</span><strong>{batteryOperationValue}</strong></div>
          </div>
        ) : (
          <div className="overview-realtime-unavailable wide">
            <Clock3 size={19} />
            <span>{todayOptimizationLoading ? "Loading today’s optimized operating values..." : "Today’s optimized operating values are not available."}</span>
          </div>
        )}
      </section>

      <section className="admin-panel overview-cumulative-panel">
        <div className="admin-panel-heading overview-realtime-heading">
          <div><h2>Today Cumulative Optimized Energy</h2></div>
          <div className="overview-live-time"><span>Through slot</span><strong>{currentSlot?.slotNumber ?? clock.slotIndex}</strong></div>
        </div>

        {cumulativeData.length > 0 ? (
          <div className="overview-cumulative-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cumulativeData} margin={{ top: 14, right: 18, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(148,163,184,.13)" vertical={false} />
                <XAxis dataKey="slotNumber" stroke="#8298aa" tickLine={false} axisLine={false} />
                <YAxis stroke="#8298aa" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(value)} kWh`} />
                <Tooltip
                  formatter={(value, name) => [`${Number(value).toFixed(1)} kWh`, name]}
                  labelFormatter={(value) => `Slot ${value}`}
                  contentStyle={{ background: "#0a1c2c", border: "1px solid rgba(255,255,255,.16)", borderRadius: 9 }}
                />
                <Legend />
                <Line type="monotone" dataKey="pvGeneration" name="PV Generation" stroke="#78e82f" strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="evDemand" name="EV Demand" stroke="#43a7ff" strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="gridImport" name="Grid Import" stroke="#ffb74d" strokeWidth={2.1} dot={false} />
                <Line type="monotone" dataKey="gridExport" name="Grid Export" stroke="#42d3a5" strokeWidth={2.1} dot={false} />
                <Line type="monotone" dataKey="bessCharge" name="BESS Charge" stroke="#b57cff" strokeWidth={2.1} dot={false} />
                <Line type="monotone" dataKey="bessDischarge" name="BESS Discharge" stroke="#ff6f91" strokeWidth={2.1} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="overview-realtime-unavailable wide">
            <Clock3 size={19} />
            <span>{todayOptimizationLoading ? "Loading today’s cumulative optimized energy..." : "Today’s cumulative optimized energy is not available."}</span>
          </div>
        )}
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
