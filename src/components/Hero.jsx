export default function Hero({ title = "Welcome to SolarCharge Station", subtitle = "Real-time pricing and charger availability for a smarter charging experience." }) {
  return (
    <section className="hero">
      <div className="hero-overlay" />
      <div className="hero-content">
        <p className="eyebrow">SMART EV FAST CHARGING</p>
        <h1>{title.includes("SolarCharge") ? (
          <>Welcome to <span>SolarCharge</span> Station</>
        ) : title}</h1>
        <h2>Intelligent. Sustainable. Reliable.</h2>
        <p>{subtitle}</p>
      </div>
    </section>
  );
}
