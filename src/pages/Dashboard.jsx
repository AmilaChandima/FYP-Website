import {
  CalendarCheck2,
  Info,
  LineChart as LineChartIcon,
  TimerReset,
  Zap,
} from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Hero from "../components/Hero";
import PriceChart from "../components/PriceChart";
import ChargerCard from "../components/ChargerCard";
import { useCurrentPrice } from "../hooks/useCurrentPrice";
import { useAuth } from "../context/AuthContext";
import { useStationData } from "../context/StationDataContext";

export default function Dashboard() {
  const { publicToday, chargers } = useStationData();
  const live = useCurrentPrice(publicToday);
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();

  const available = useMemo(
    () => chargers.filter((charger) => charger.status === "available").length,
    [chargers]
  );

  function startBooking() {
    navigate(isLoggedIn ? "/booking" : "/login?redirect=%2Fbooking");
  }

  return (
    <>
      <Hero />

      <section className="page-width current-price-banner">
        <div>
          <span className="live-label">
            <i /> CURRENT PUBLIC PRICE
          </span>

          <h2>
            Rs. {live.currentPrice.toFixed(2)} <small>/kWh</small>
          </h2>

          <p>
            {live.startTime}–{live.endTime} • Sri Lanka time {live.clock}
          </p>
        </div>

        <div className="price-banner-actions">
          <button className="primary-action" onClick={startBooking}>
            <CalendarCheck2 size={18} />
            Book Charging
          </button>

          <div className="current-price-icon">
            <TimerReset />
          </div>
        </div>
      </section>

      <section className="dashboard-grid dashboard-single-column page-width dashboard-spacing">

        {/* PRICE CHART */}
        <article className="panel price-panel">
          <div className="panel-heading">
            <div>
              <h2>
                <LineChartIcon size={23} />
                Today’s 15-Minute Public Price
              </h2>

              <p>Normal walk-in customer price (Rs/kWh)</p>
            </div>
          </div>

          <PriceChart
            prices={publicToday}
            activeSlotIndex={live.slotIndex}
          />

          <div className="info-strip">
            <Info size={18} />
            Public prices vary every 15 minutes. Advance bookings use separate
            fixed prices shown on the Pricing page.
          </div>
        </article>

        {/* CHARGER DETAILS - NOW BELOW PRICE CHART */}
        <article className="panel charger-panel">
          <div className="panel-heading">
            <div>
              <h2>
                <Zap size={23} />
                Charger Status (10 Chargers)
              </h2>

              <p>{available} currently available</p>
            </div>
          </div>

          <div className="charger-grid">
            {chargers.map((charger) => (
              <ChargerCard key={charger.id} charger={charger} />
            ))}
          </div>

          <div className="legend">
            <span>
              <i className="available-dot" />
              Available
            </span>

            <span>
              <i className="charging-dot" />
              Charging
            </span>

            <span>
              <i className="offline-dot" />
              Out of Service
            </span>
          </div>
        </article>

      </section>
    </>
  );
}