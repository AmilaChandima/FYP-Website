import { BadgeCheck, Clock3, Leaf, MapPin, ShieldCheck, Zap } from "lucide-react";

export default function About() {
  return (
    <section className="page-width inner-page">
      <div className="page-title">
        <p className="eyebrow">ABOUT THE STATION</p>
        <h1>A Smarter Charging Experience</h1>
        <p>SolarCharge combines transparent customer pricing with clear charger availability.</p>
      </div>

      <div className="about-grid">
        <article className="about-copy panel">
          <h2>Designed for EV drivers</h2>
          <p>
            This customer-facing platform helps drivers check 15-minute charging prices,
            identify available chargers and plan charging sessions before arriving at the station.
          </p>
          <p>
            The interface can later be connected to your intelligent controller through an API,
            database or real-time WebSocket service.
          </p>
          <div className="about-location"><MapPin /> Colombo, Sri Lanka</div>
        </article>

        <div className="feature-grid">
          <article><Zap /><h3>Fast Charging</h3><p>Up to 450 kW charging capability.</p></article>
          <article><Clock3 /><h3>15-Minute Prices</h3><p>Clear time-slot-based customer tariffs.</p></article>
          <article><Leaf /><h3>Solar-Aware</h3><p>Encourages charging during favorable periods.</p></article>
          <article><ShieldCheck /><h3>Reliable</h3><p>Simple live-style charger status display.</p></article>
          <article><BadgeCheck /><h3>Transparent</h3><p>Prices are visible before charging begins.</p></article>
        </div>
      </div>
    </section>
  );
}
