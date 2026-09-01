import {
  Ban,
  BellRing,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  Download,
  FileSpreadsheet,
  RefreshCcw,
  Search,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getAllBookings, updateBookingStatus } from "../../services/adminData";
import {
  downloadTomorrowBookingsCsv,
  getOptimizerEligibleTomorrowBookings,
  subscribeToBookings,
} from "../../services/bookings";
import {
  downloadGeneratedPrimaryElasticInput,
  generatePrimaryElasticInput,
  getPrimaryElasticBaseInfo,
} from "../../services/optimizerApi";
import { formatDateLabel, formatTime12, getTomorrowDateKey } from "../../utils/time";

function statusLabel(status) {
  if (status === "pending") return "Pending schedule";
  if (status === "scheduled") return "Scheduled";
  if (status === "reserved") return "Reserved";
  if (status === "completed") return "Completed";
  return "Cancelled";
}

export default function AdminBookings() {
  const [version, setVersion] = useState(0);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [baseInfo, setBaseInfo] = useState(null);
  const [baseInfoError, setBaseInfoError] = useState("");
  const [builderResult, setBuilderResult] = useState(null);
  const [builderError, setBuilderError] = useState("");
  const [building, setBuilding] = useState(false);

  useEffect(() => subscribeToBookings(() => setVersion((value) => value + 1)), []);
  useEffect(() => {
    let active = true;

    getPrimaryElasticBaseInfo()
      .then((result) => {
        if (!active) return;
        setBaseInfo(result);
        setBaseInfoError("");
      })
      .catch((error) => {
        if (!active) return;
        setBaseInfo(null);
        setBaseInfoError(error.message || "Unable to load the original user counts.");
      });

    return () => { active = false; };
  }, []);

  const bookings = useMemo(
    () => getAllBookings().sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))),
    [version]
  );
  const optimizerBookings = useMemo(() => getOptimizerEligibleTomorrowBookings(), [version]);
  const optimizerFlexible = optimizerBookings.filter((item) => item.bookingType === "flexible").length;
  const optimizerFixed = optimizerBookings.filter((item) => item.bookingType === "fixed").length;

  const filtered = bookings.filter((booking) => {
    const matchesStatus = filter === "all" || booking.status === filter;
    const query = search.trim().toLowerCase();
    const matchesSearch = !query
      || booking.userName?.toLowerCase().includes(query)
      || booking.userEmail?.toLowerCase().includes(query)
      || booking.vehicleModel?.toLowerCase().includes(query)
      || booking.date?.includes(query);
    return matchesStatus && matchesSearch;
  });

  async function setStatus(id, status) {
    try {
      await updateBookingStatus(id, status);
      setVersion((value) => value + 1);
    } catch (error) {
      setBuilderError(error.message || "Unable to update booking status in MongoDB.");
    }
  }

  async function buildOptimizerInput() {
    setBuilding(true);
    setBuilderError("");
    setBuilderResult(null);
    try {
      const result = await generatePrimaryElasticInput(getTomorrowDateKey(), optimizerBookings);
      setBuilderResult(result);
      downloadGeneratedPrimaryElasticInput();
    } catch (error) {
      setBuilderError(error.message || "Unable to generate Primary_Elastic_EV_Users.xlsx.");
    } finally {
      setBuilding(false);
    }
  }

  const basePrimaryUsers = Number(baseInfo?.primaryUsers);
  const baseElasticUsers = Number(baseInfo?.elasticUsers);
  const baseCountsReady = Number.isFinite(basePrimaryUsers) && Number.isFinite(baseElasticUsers);
  const tomorrowKey = getTomorrowDateKey();
  const websiteFixedReservations = bookings.filter(
    (item) => item.date === tomorrowKey && item.bookingType === "fixed" && item.status === "reserved"
  ).length;
  const websiteFlexiblePending = bookings.filter(
    (item) => item.date === tomorrowKey && item.bookingType === "flexible" && item.status === "pending"
  ).length;

  const counts = {
    fixed: (baseCountsReady ? basePrimaryUsers : 0) + websiteFixedReservations,
    pending: (baseCountsReady ? baseElasticUsers : 0) + websiteFlexiblePending,
    scheduled: bookings.filter((item) => item.bookingType === "flexible" && item.status === "scheduled").length,
    completed: bookings.filter((item) => item.status === "completed").length,
  };

  const showScheduledPeriod = ["reserved", "scheduled", "completed"].includes(filter);
  const showStatus = filter !== "pending";
  const showAdminAction = ["all", "reserved", "scheduled"].includes(filter);
  const visibleColumnCount = 4
    + (showScheduledPeriod ? 1 : 0)
    + (showStatus ? 1 : 0)
    + (showAdminAction ? 1 : 0);

  return (
    <div className="admin-page">
      <div className="admin-page-heading">
        <div>
          <p>RESERVATION & FLEXIBILITY MANAGEMENT</p>
          <h1>Customer Bookings</h1>
          <span>Review bookings and prepare tomorrow's website bookings.</span>
        </div>
        <button className="admin-secondary-button" onClick={downloadTomorrowBookingsCsv}>
          <Download size={18} /> Export Tomorrow CSV
        </button>
      </div>

      <section className="admin-stat-grid compact">
        <article className="admin-stat-card bookings"><div><span>Fixed reservations</span><strong>{baseCountsReady ? counts.fixed : "—"}</strong></div><BookOpenCheck /></article>
        <article className="admin-stat-card warning"><div><span>Flexible pending</span><strong>{baseCountsReady ? counts.pending : "—"}</strong></div><Sparkles /></article>
{/*        <article className="admin-stat-card chargers"><div><span>Flexible scheduled</span><strong>{counts.scheduled}</strong><small>Customers notified</small></div><BellRing /></article>*/}

      </section>

      {baseInfoError && (
        <div className="optimizer-error-panel compact-error">
          <span>{baseInfoError}</span>
        </div>
      )}

      <section className="admin-panel optimizer-input-builder">
        <div className="admin-panel-heading">
          <div>
            <h2>Build Primary_Elastic_EV_Users.xlsx</h2>
            
          </div>
          <FileSpreadsheet />
        </div>
        <div className="optimizer-builder-flow">
          
        </div>

        {builderError && <div className="optimizer-error-panel compact-error"><span>{builderError}</span></div>}
        {builderResult && (
          <div className="admin-action-message success-message">
            <CheckCircle2 /> Generated successfully: {builderResult.baseRows} original rows + {builderResult.appendedBookings} website bookings = {builderResult.totalRows} total rows. The file has been downloaded.
          </div>
        )}
        <div className="admin-run-actions optimizer-builder-actions">
          <button className="admin-secondary-button" onClick={() => downloadGeneratedPrimaryElasticInput()} disabled={!builderResult}><Download size={17} /> Download Again</button>
          <button className="admin-primary-button" onClick={buildOptimizerInput} disabled={building}>
            {building ? <RefreshCcw className="spin-icon" size={17} /> : <FileSpreadsheet size={17} />}
            {building ? "Generating..." : "Generate Updated Primary_Elastic_EV_Users"}
          </button>
        </div>
      </section>

      <section className="admin-panel admin-booking-management">
        <div className="admin-table-toolbar">
          <div className="admin-search"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search customer, vehicle, email or date" /></div>
          <div className="admin-filter-buttons">
            {["all", "pending", "reserved", "scheduled", "completed", "cancelled"].map((item) => (
              <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item[0].toUpperCase() + item.slice(1)}</button>
            ))}
          </div>
        </div>

        <div className="admin-table-wrap">
          <table className="admin-table admin-booking-table-wide">
            <thead>
              <tr>
                <th>Customer & EV</th>
                <th>Method</th>
                <th>SOC / Energy</th>
                <th>Requested time</th>
                {showScheduledPeriod && <th>Scheduled period</th>}
                {showStatus && <th>Status</th>}
                {showAdminAction && <th>Admin action</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.map((booking) => (
                <tr key={booking.id}>
                  <td><strong>{booking.userName}</strong><small>{booking.userEmail}</small><small>{booking.vehicleMake} {booking.vehicleModel} · {booking.batteryCapacityKwh || "—"} kWh</small></td>
                  <td><span className={`booking-type-pill ${booking.bookingType}`}>{booking.bookingType === "fixed" ? "Fixed arrival" : "Flexible"}</span></td>
                  <td><strong>{booking.initialSoc}% → {booking.targetSoc}%</strong><small>{Number(booking.energyRequiredKwh || 0).toFixed(1)} kWh · {booking.durationMinutes} min</small></td>
                  <td><strong>{formatDateLabel(booking.date)}</strong><small>{booking.bookingType === "fixed" ? `Arrival ${formatTime12(booking.arrivalTime)}` : `Range ${formatTime12(booking.windowStart)}–${formatTime12(booking.windowEnd)}`}</small></td>
                  {showScheduledPeriod && (
                    <td>{booking.scheduledStart ? <span className="admin-time-cell"><Clock3 size={15} /> {formatTime12(booking.scheduledStart)}–{formatTime12(booking.scheduledEnd)}</span> : <span className="admin-muted-value">Not assigned</span>}</td>
                  )}
                  {showStatus && <td><span className={`admin-status-pill ${booking.status}`}>{statusLabel(booking.status)}</span></td>}
                  {showAdminAction && (
                    <td><div className="admin-row-actions">
                      {["reserved", "scheduled"].includes(booking.status) && <><button title="Mark completed" onClick={() => setStatus(booking.id, "completed")}><CheckCircle2 /></button><button title="Cancel booking" className="danger" onClick={() => setStatus(booking.id, "cancelled")}><Ban /></button></>}
                      {booking.status === "pending" && <span className="admin-pending-note">Include in next optimizer input</span>}
                      {["completed", "cancelled"].includes(booking.status) && <button onClick={() => setStatus(booking.id, booking.bookingType === "flexible" ? "pending" : "reserved")}>Restore</button>}
                    </div></td>
                  )}
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={visibleColumnCount} className="admin-empty-table">No bookings match the selected filter.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
