import ChargerCard from "../components/ChargerCard";
import { useStationData } from "../context/StationDataContext";

export default function Chargers() {
  const { chargers } = useStationData();
  const available = chargers.filter((item) => item.status === "available").length;
  const charging = chargers.filter((item) => item.status === "charging").length;
  const offline = chargers.filter((item) => item.status === "offline").length;

  return (
    <section className="page-width inner-page">
      <div className="page-title"><p className="eyebrow">LIVE AVAILABILITY</p><h1>Charging Points</h1><p>Check the current status of every charger before arriving.</p></div>
      <div className="availability-summary"><span><strong>{available}</strong> Available</span><span><strong>{charging}</strong> Charging</span><span><strong>{offline}</strong> Out of service</span></div>
      <div className="charger-detail-grid">{chargers.map((charger) => <ChargerCard key={charger.id} charger={charger} detailed />)}</div>
      <article className="panel station-note"><h2>Station Information</h2><p>All ten charging points support CCS2 fast charging with a rated power of up to 450 kW per charger. Actual charging power depends on the vehicle battery, state of charge, and operating conditions.</p></article>
    </section>
  );
}
