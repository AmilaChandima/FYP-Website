import { AlertTriangle, BatteryCharging, CheckCircle2, Wrench, Zap } from "lucide-react";
import { useStationData } from "../../context/StationDataContext";

export default function AdminChargers() {
  const { chargers, updateCharger } = useStationData();
  const available = chargers.filter((item) => item.status === "available").length;
  const occupied = chargers.filter((item) => item.status === "charging").length;
  const offline = chargers.filter((item) => item.status === "offline").length;

  function changeStatus(charger, status) {
    updateCharger(charger.id, {
      status,
      progress: status === "charging" ? (charger.progress || 25) : undefined,
      remaining: status === "charging" ? (charger.remaining || "30 min") : undefined,
    });
  }

  return (
    <div className="admin-page">
      <div className="admin-page-heading"><div><p>LIVE OPERATIONS</p><h1>Charger Control</h1><span>Update charger availability, occupied status, charging progress and maintenance state.</span></div></div>

      <section className="admin-stat-grid compact">
        <article className="admin-stat-card chargers"><div><span>Available</span><strong>{available}</strong><small>Ready for customers</small></div><CheckCircle2 /></article>
        <article className="admin-stat-card bookings"><div><span>Occupied</span><strong>{occupied}</strong><small>Active charging sessions</small></div><BatteryCharging /></article>
        <article className="admin-stat-card warning"><div><span>Out of order</span><strong>{offline}</strong><small>Maintenance required</small></div><AlertTriangle /></article>
      </section>

      <section className="admin-charger-control-grid">
        {chargers.map((charger) => (
          <article className={`admin-panel admin-charger-control-card ${charger.status}`} key={charger.id}>
            <div className="admin-charger-control-heading"><div><span>CHARGER</span><strong>{String(charger.id).padStart(2, "0")}</strong></div><div className="admin-charger-status-icon">{charger.status === "available" ? <CheckCircle2 /> : charger.status === "charging" ? <BatteryCharging /> : <Wrench />}</div></div>
            <div className="admin-charger-spec"><span><Zap size={15} /> {charger.power} kW</span><span>{charger.connector}</span></div>
            <label className="admin-field"><span>Operating status</span><select value={charger.status} onChange={(event) => changeStatus(charger, event.target.value)}><option value="available">Available</option><option value="charging">Occupied / Charging</option><option value="offline">Out of order</option></select></label>
            {charger.status === "charging" && (
              <div className="admin-charging-controls">
                <label className="admin-field"><span>Charging progress</span><input type="range" min="0" max="100" value={charger.progress || 0} onChange={(event) => updateCharger(charger.id, { progress: Number(event.target.value) })} /><b>{charger.progress || 0}%</b></label>
                <label className="admin-field"><span>Estimated remaining time</span><input value={charger.remaining || ""} onChange={(event) => updateCharger(charger.id, { remaining: event.target.value })} /></label>
              </div>
            )}
            <div className={`admin-charger-state ${charger.status}`}>{charger.status === "available" ? "Visible to customers as Available" : charger.status === "charging" ? "Visible to customers as Charging" : "Visible to customers as Out of Service"}</div>
          </article>
        ))}
      </section>
    </div>
  );
}
