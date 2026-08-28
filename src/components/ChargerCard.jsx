import { BatteryCharging, CheckCircle2, Clock3, Wrench } from "lucide-react";

export default function ChargerCard({ charger, detailed = false }) {
  const charging = charger.status === "charging";
  const offline = charger.status === "offline";

  return (
    <article className={`charger-card ${charger.status}`}>
      <div className="charger-number">{String(charger.id).padStart(2, "0")}</div>
      <div className="charger-icon">
        {offline ? <Wrench /> : charging ? <BatteryCharging /> : <CheckCircle2 />}
      </div>
      <strong className="status-text">
        {charging ? "Charging" : offline ? "Out of Service" : "Available"}
      </strong>

      {charging ? (
        <>
          <strong className="progress-value">{charger.progress}%</strong>
          <div className="progress-track">
            <span style={{ width: `${charger.progress}%` }} />
          </div>
          {detailed && <small><Clock3 size={14} /> {charger.remaining} remaining</small>}
        </>
      ) : (
        <span>{charger.power} kW</span>
      )}

      {detailed && <div className="connector">{charger.connector}</div>}
    </article>
  );
}
