import {
  CalendarClock,
  CheckCircle2,
  Clock3,
  Info,
  MoveRight,
  ShieldCheck,
  Sparkles,
  Tag,
} from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import PriceChart from "../components/PriceChart";
import { useStationData } from "../context/StationDataContext";
import { useCurrentPrice } from "../hooks/useCurrentPrice";
import { useAuth } from "../context/AuthContext";
import { formatDateLabel, getTomorrowDateKey } from "../utils/time";

function getStats(prices) {
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const average =
    prices.reduce((sum, value) => sum + Number(value), 0) / prices.length;

  return { min, max, average };
}

function buildFlexiblePriceSchedule(
  fixedPrices,
  flexibleReferencePrice
) {
  const fixedAverage = getStats(fixedPrices).average;

  const discount = Math.max(
    5,
    fixedAverage - Number(flexibleReferencePrice)
  );

  return fixedPrices.map((price) =>
    Number((Number(price) - discount).toFixed(2))
  );
}

export default function Pricing() {
  const navigate = useNavigate();
  const { isLoggedIn } = useAuth();

  const {
    publicToday,
    publicTomorrow,
    publicTomorrowAvailable,
    publicTomorrowPublishedAt,
    flexibleBookingPrice,
    fixedArrivalTomorrowPrices,
  } = useStationData();

  const publicLive = useCurrentPrice(publicToday);

  const stats = useMemo(
    () => getStats(publicToday),
    [publicToday]
  );

  const tomorrowStats = useMemo(
    () =>
      publicTomorrowAvailable
        ? getStats(publicTomorrow)
        : null,
    [publicTomorrow, publicTomorrowAvailable]
  );

  const tomorrowDate = getTomorrowDateKey();

  const fixedStats = useMemo(
    () => getStats(fixedArrivalTomorrowPrices),
    [fixedArrivalTomorrowPrices]
  );

  const flexibleSchedule = useMemo(
    () =>
      buildFlexiblePriceSchedule(
        fixedArrivalTomorrowPrices,
        flexibleBookingPrice
      ),
    [fixedArrivalTomorrowPrices, flexibleBookingPrice]
  );

  const flexibleStats = useMemo(
    () => getStats(flexibleSchedule),
    [flexibleSchedule]
  );

  function startBooking(type) {
    const destination = `/booking?type=${type}`;

    navigate(
      isLoggedIn
        ? destination
        : `/login?redirect=${encodeURIComponent(destination)}`
    );
  }

  return (
    <section className="customer-page page-width inner-page pricing-page revised-pricing-page">
      {/* PAGE TITLE */}
      <div className="page-title pricing-title">
        <p className="eyebrow">
          CLEAR CUSTOMER PRICING
        </p>

        <h1>Three Ways to Charge</h1>

        <p style={{ fontSize: "20px" }}>
          Walk-in charging follows today’s real-time
          15-minute price. Registered customers can book
          tomorrow using the common booking-price schedule,
          while flexible customers receive a lower price for
          allowing the station to select their exact arrival
          time.
        </p>
      </div>

      {/* CURRENT PUBLIC PRICE */}
      <article className="pricing-live-card public-live-card">
        <div>
          <span className="live-label">
            <i />
            CURRENT WALK-IN PRICE
          </span>

          <h2>
            Rs. {publicLive.currentPrice.toFixed(2)}{" "}
            <small>/kWh</small>
          </h2>

          <p style={{ fontSize: "18px" }}>
            Active today from {publicLive.startTime} to{" "}
            {publicLive.endTime}
          </p>
        </div>

        <div className="pricing-live-time">
          <Clock3 />

          <strong>
            {publicLive.clock}
          </strong>

          <span>
            Asia/Colombo
          </span>
        </div>
      </article>

      {/* TODAY PUBLIC PRICE */}
      <article className="panel pricing-scheme-panel public-price-panel-revised">
        <div className="pricing-scheme-heading">
          <div>
            <span className="scheme-label public-label">
              <Tag size={15} />
              PUBLIC / WALK-IN PRICE
            </span>

            <h2>
              Today’s Dynamic Price Schedule
            </h2>

            <p style={{ fontSize: "18px" }}>
              No account or reservation is required. The
              price changes at each 15-minute boundary.
            </p>
          </div>

          <div className="scheme-mini-stats">
            <span>
              Low
              <b>
                Rs. {stats.min.toFixed(2)}
              </b>
            </span>

            <span>
              Average
              <b>
                Rs. {stats.average.toFixed(2)}
              </b>
            </span>

            <span>
              High
              <b>
                Rs. {stats.max.toFixed(2)}
              </b>
            </span>
          </div>
        </div>

        <PriceChart
          prices={publicToday}
          activeSlotIndex={publicLive.slotIndex}
          variant="public"
        />

        <div className="chart-scheme-footer">
          <span className="chart-key public-key">
            <i />
            Today’s public price
          </span>

          <span style={{ fontSize: "18px" }}>
            Hover over the graph to check the exact price for
            any 15-minute period.
          </span>
        </div>
      </article>

      {/* TOMORROW PUBLIC FORECAST */}
      <section className="tomorrow-public-forecast-section">
        <div className="tomorrow-public-forecast-heading">
          <div>
            <p className="eyebrow">
              DAY-AHEAD FORECAST
            </p>

            <h2>
              Tomorrow&apos;s Public Charging Price
            </h2>

            <p style={{ fontSize: "18px" }}>
              The station publishes this 96-slot forecast
              after the administrator runs the Python
              optimization using tomorrow&apos;s PV, EV-user,
              grid-price and BESS forecast inputs.
            </p>
          </div>

          <span
            className={`tomorrow-price-status ${
              publicTomorrowAvailable
                ? "published"
                : "pending"
            }`}
          >
            {publicTomorrowAvailable
              ? "Forecast published"
              : "Not published yet"}
          </span>
        </div>

        {publicTomorrowAvailable ? (
          <article className="panel pricing-scheme-panel tomorrow-public-panel">
            <div className="pricing-scheme-heading">
              <div>
                <span className="scheme-label public-label">
                  <Tag size={15} />
                  FORECAST PUBLIC PRICE
                </span>

                <h2>
                  {formatDateLabel(tomorrowDate)}
                </h2>

                <p style={{ fontSize: "18px" }}>
                  Optimized day-ahead public charging-price
                  signal. After midnight, this schedule
                  automatically becomes today&apos;s public
                  price.
                </p>
              </div>

              <div className="scheme-mini-stats">
                <span>
                  Low
                  <b>
                    Rs. {tomorrowStats.min.toFixed(2)}
                  </b>
                </span>

                <span>
                  Average
                  <b>
                    Rs. {tomorrowStats.average.toFixed(2)}
                  </b>
                </span>

                <span>
                  High
                  <b>
                    Rs. {tomorrowStats.max.toFixed(2)}
                  </b>
                </span>
              </div>
            </div>

            <PriceChart
              prices={publicTomorrow}
              variant="forecast"
            />

            <div className="chart-scheme-footer">
              <span className="chart-key public-key">
                <i />
                Tomorrow forecast
              </span>

              <span>
                {publicTomorrowPublishedAt
                  ? `Published ${new Date(
                      publicTomorrowPublishedAt
                    ).toLocaleString("en-US", {
                      timeZone: "Asia/Colombo",
                    })}`
                  : "Published by station administrator"}
              </span>
            </div>
          </article>
        ) : (
          <div className="tomorrow-price-pending-card">
            <Info />

            <div>
              <strong>
                Tomorrow&apos;s optimized price is not
                available yet.
              </strong>

              <p>
                It will appear here after the station
                completes the day-ahead optimization and
                publishes the new forecast.
              </p>
            </div>
          </div>
        )}
      </section>

      {/* REGISTERED BOOKINGS */}
      <section className="booking-price-explainer">
        <div className="booking-price-heading">
          <div>
            <p className="eyebrow">
              REGISTERED CUSTOMER BOOKINGS
            </p>

            <h2>
              Tomorrow’s Common Booking-Price Schedule
            </h2>

            <p style={{ fontSize: "18px" }}>
              This 15-minute schedule is the common reference
              for both registered booking methods.
              Fixed-arrival customers pay the price at their
              selected arrival time. Flexible customers
              receive a lower tariff because the station can
              choose the exact charging time inside their
              acceptable range.
            </p>
          </div>

          <div className="booking-requirement-note">
            <ShieldCheck />
            Login is required only when you book
          </div>
        </div>

        {/* BOOKING PRICE CHART */}
        <article className="panel pricing-scheme-panel">
          <div className="pricing-scheme-heading">
            <div>
              <span className="scheme-label">
                <CalendarClock size={15} />
                REGISTERED BOOKING PRICE
              </span>

              <h2>
                Tomorrow’s 15-Minute Booking Schedule
              </h2>

              <p style={{ fontSize: "18px" }}>
                Review this graph before choosing either
                booking method.
              </p>
            </div>

            <div className="scheme-mini-stats">
              <span>
                Low
                <b>
                  Rs. {fixedStats.min.toFixed(2)}
                </b>
              </span>

              <span>
                Average
                <b>
                  Rs. {fixedStats.average.toFixed(2)}
                </b>
              </span>

              <span>
                High
                <b>
                  Rs. {fixedStats.max.toFixed(2)}
                </b>
              </span>
            </div>
          </div>

          <PriceChart
            prices={fixedArrivalTomorrowPrices}
            variant="booking"
          />

          <div className="chart-scheme-footer">
            <span
              style={{ fontSize: "18px" }}
              className="chart-key"
            >
              <i />
              Common registered booking schedule
            </span>

            <span style={{ fontSize: "18px" }}>
              Flexible customers pay below the corresponding
              fixed-arrival values.
            </span>
          </div>
        </article>

        {/* BOOKING OPTIONS */}
        <div className="booking-method-grid">
          {/* OPTION 1 */}
          <article className="booking-method-card fixed-method-card">
            <div className="booking-method-topline">
              <span style={{ fontSize: "18px" }}>
                OPTION 1
              </span>

              <CalendarClock />
            </div>

            <div className="standard-price-badge">
              STANDARD PRICE
            </div>

            <h3>
              Fixed-Arrival Booking
            </h3>

            <p className="booking-rate">
              Rs. {fixedStats.min.toFixed(0)}–
              {fixedStats.max.toFixed(0)}{" "}
              <small>/kWh</small>
            </p>

            <p style={{ fontSize: "18px" }}>
              Tell us tomorrow’s arrival time, initial SOC and
              target SOC. Your price is selected from the
              graph at the chosen arrival time, and one
              charger is reserved for the calculated
              duration.
            </p>

            <ul>
              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                Exact arrival time and price selected by you
              </li>

              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                Charging duration calculated automatically
              </li>

              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                Charger confirmed immediately when capacity
                is available
              </li>
            </ul>

            <button
              className="primary-action full"
              onClick={() => startBooking("fixed")}
            >
              Choose Fixed Arrival
              <MoveRight size={18} />
            </button>
          </article>

          {/* OPTION 2 */}
          <article className="booking-method-card flexible-method-card">
            <div className="booking-method-topline">
              <span style={{ fontSize: "18px" }}>
                OPTION 2
              </span>

              <Sparkles />
            </div>

            <div className="lower-price-badge">
              LOWER THAN FIXED-ARRIVAL PRICES
            </div>

            <h3>
              Flexible Smart Booking
            </h3>

            <p className="booking-rate">
              Rs. {flexibleStats.min.toFixed(0)}–
              {flexibleStats.max.toFixed(0)}{" "}
              <small>/kWh</small>
            </p>

            <p style={{ fontSize: "18px" }}>
              Give an acceptable arrival-time range for
              tomorrow. The station selects the exact arrival
              time inside that range and applies a discounted
              price below the common booking schedule.
            </p>

            <ul>
              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                You provide the earliest and latest acceptable
                times
              </li>

              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                The station chooses the exact arrival time
              </li>

              <li style={{ fontSize: "18px" }}>
                <CheckCircle2 />
                Lower price in return for scheduling
                flexibility
              </li>
            </ul>

            <button
              className="flexible-action-button"
              onClick={() => startBooking("flexible")}
            >
              Choose Flexible Booking
              <MoveRight size={18} />
            </button>
          </article>
        </div>

        {/* FLEXIBLE PRICE EXPLANATION */}
        <div className="pricing-clarity-note">
          <Info />

          <div>
            <strong>
              How is the flexible price determined?
            </strong>

            <p style={{ fontSize: "18px" }}>
              The same time-based booking pattern is used, but
              a station-controlled discount is applied. After
              a customer selects a flexible arrival window,
              the booking page shows the lowest and highest
              possible flexible prices within that range
              before the request is submitted.
            </p>
          </div>
        </div>
      </section>
    </section>
  );
}