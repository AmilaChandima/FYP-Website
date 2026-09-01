import {
  BatteryCharging,
  BellRing,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Gauge,
  Info,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import PriceChart from "../components/PriceChart";
import { useAuth } from "../context/AuthContext";
import { useStationData } from "../context/StationDataContext";
import {
  cancelBooking,
  createFixedBooking,
  createFlexibleBooking,
  getBookings,
  subscribeToBookings,
} from "../services/bookings";
import {
  calculateChargingRequirement,
  formatDateLabel,
  formatTime12,
  getTomorrowDateKey,
  minutesFromTime,
  timeFromMinutes,
} from "../utils/time";

const DEFAULT_FIXED_FORM = {
  initialSoc: 20,
  targetSoc: 80,
  arrivalTime: "10:00",
};

const DEFAULT_FLEXIBLE_FORM = {
  initialSoc: 20,
  targetSoc: 80,
  windowStart: "09:00",
  windowEnd: "17:00",
};

function calculateForUser(user, form) {
  try {
    return calculateChargingRequirement({
      batteryCapacityKwh: user.vehicle?.batteryCapacityKwh,
      chargingRateKw: user.vehicle?.maxChargingRateKw,
      initialSoc: form.initialSoc,
      targetSoc: form.targetSoc,
    });
  } catch {
    return null;
  }
}

function bookingStatusLabel(booking) {
  if (booking.status === "pending") return "Waiting for scheduling";
  if (booking.status === "scheduled") return "Scheduled by station";
  if (booking.status === "reserved") return "Confirmed reservation";
  if (booking.status === "completed") return "Completed";
  return "Cancelled";
}

export default function Booking() {
  const { user } = useAuth();
  const { flexibleBookingPrice, fixedArrivalTomorrowPrices } = useStationData();
  const [params, setParams] = useSearchParams();
  const initialType = params.get("type") === "flexible" ? "flexible" : "fixed";
  const [bookingType, setBookingType] = useState(initialType);
  const [fixedForm, setFixedForm] = useState(DEFAULT_FIXED_FORM);
  const [flexibleForm, setFlexibleForm] = useState(DEFAULT_FLEXIBLE_FORM);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const tomorrow = getTomorrowDateKey();

  useEffect(() => subscribeToBookings(() => setVersion((value) => value + 1)), []);

  const fixedCalculation = useMemo(
    () => calculateForUser(user, fixedForm),
    [user, fixedForm]
  );
  const flexibleCalculation = useMemo(
    () => calculateForUser(user, flexibleForm),
    [user, flexibleForm]
  );

  const fixedBookingPriceSchedule = fixedArrivalTomorrowPrices;
  const flexibleBookingPriceSchedule = fixedBookingPriceSchedule;

  const selectedFixedArrivalSlot = Math.min(
    95,
    Math.floor(minutesFromTime(fixedForm.arrivalTime) / 15)
  );
  const selectedFixedArrivalPrice = Number(
    fixedBookingPriceSchedule[selectedFixedArrivalSlot]
  );
  const fixedPriceMinimum = Math.min(...fixedBookingPriceSchedule);
  const fixedPriceMaximum = Math.max(...fixedBookingPriceSchedule);

  const myBookings = useMemo(
    () => getBookings()
      .filter((booking) => booking.userId === user.id)
      .sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))),
    [user.id, version]
  );

  function selectType(type) {
    setBookingType(type);
    setParams({ type });
    setMessage("");
    setError("");
  }

  function updateFixed(event) {
    setFixedForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setMessage("");
    setError("");
  }

  function updateFlexible(event) {
    setFlexibleForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setMessage("");
    setError("");
  }

  function submitFixed(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const booking = createFixedBooking({
        user,
        ...fixedForm,
        price: selectedFixedArrivalPrice,
      });
      setMessage(`Booking confirmed. Charger ${String(booking.chargerId).padStart(2, "0")} is reserved tomorrow from ${formatTime12(booking.scheduledStart)} to ${formatTime12(booking.scheduledEnd)}.`);
      setVersion((value) => value + 1);
    } catch (err) {
      setError(err.message || "The booking could not be created.");
    }
  }

  function submitFlexible(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      createFlexibleBooking({
        user,
        ...flexibleForm,
        price: flexibleBookingPrice,
      });
      setMessage("Your flexible request was submitted. The station will notify you with the exact arrival time after scheduling.");
      setVersion((value) => value + 1);
    } catch (err) {
      setError(err.message || "The flexible booking request could not be submitted.");
    }
  }

  const fixedEnd = fixedCalculation
    ? timeFromMinutes(minutesFromTime(fixedForm.arrivalTime) + fixedCalculation.durationMinutes)
    : null;
  const flexibleStartMinutes = minutesFromTime(flexibleForm.windowStart);
  const flexibleEndMinutes = minutesFromTime(flexibleForm.windowEnd);
  const flexibleRangeMinutes = flexibleEndMinutes - flexibleStartMinutes;
  const hasValidFlexibleRange = flexibleRangeMinutes > 0;
  const selectedFlexibleStartSlot = hasValidFlexibleRange
    ? Math.max(0, Math.min(95, Math.floor(flexibleStartMinutes / 15)))
    : null;
  const selectedFlexibleEndSlot = hasValidFlexibleRange
    ? Math.max(0, Math.min(95, Math.floor((flexibleEndMinutes - 1) / 15)))
    : null;
  const selectedFlexiblePrices = hasValidFlexibleRange
    ? flexibleBookingPriceSchedule.slice(selectedFlexibleStartSlot, selectedFlexibleEndSlot + 1)
    : [];
  const selectedFlexiblePriceMinimum = selectedFlexiblePrices.length
    ? Math.min(...selectedFlexiblePrices)
    : null;
  const selectedFlexiblePriceMaximum = selectedFlexiblePrices.length
    ? Math.max(...selectedFlexiblePrices)
    : null;
  const flexibleScheduleMinimum = Math.min(...flexibleBookingPriceSchedule);
  const flexibleScheduleMaximum = Math.max(...flexibleBookingPriceSchedule);

  return (
    <section className="page-width inner-page booking-page dual-booking-page">
      <div className="booking-heading-row">
        <div className="page-title booking-title">
          <p className="eyebrow">TOMORROW’S REGISTERED BOOKING</p>
          <h1>Choose Your Booking Method</h1>
          <p>
            Booking date: <strong>{formatDateLabel(tomorrow)}</strong>. Your registered EV is {user.vehicle?.make} {user.vehicle?.model},
            with a {user.vehicle?.batteryCapacityKwh} kWh battery and a maximum charging rate of {user.vehicle?.maxChargingRateKw} kW.
          </p>
        </div>
      </div>

      <div className="booking-option-selector">
        <button
          type="button"
          className={bookingType === "fixed" ? "active fixed" : "fixed"}
          onClick={() => selectType("fixed")}
        >
          <div className="booking-option-topline">
            <span>OPTION 1</span>
            <CalendarClock />
          </div>
          <div className="booking-option-price-badge fixed-badge">STANDARD PRICE</div>
          <h3>Fixed-Arrival Booking</h3>
          <p className="booking-option-rate">
            Rs. {fixedPriceMinimum.toFixed(0)}–{fixedPriceMaximum.toFixed(0)} <small>/kWh</small>
          </p>
        </button>

        <button
          type="button"
          className={bookingType === "flexible" ? "active flexible" : "flexible"}
          onClick={() => selectType("flexible")}
        >
          <div className="booking-option-topline">
            <span>OPTION 2</span>
            <Sparkles />
          </div>
          <div className="booking-option-price-badge flexible-badge">LOWER THAN FIXED-ARRIVAL PRICES</div>
          <h3>Flexible Smart Booking</h3>
          <p className="booking-option-rate">
            Rs. {flexibleScheduleMinimum.toFixed(0)}–{flexibleScheduleMaximum.toFixed(0)} <small>/kWh</small>
          </p>
        </button>
      </div>

      <div className="new-booking-layout">
        <article className="panel booking-form-panel">
          {bookingType === "fixed" ? (
            <form onSubmit={submitFixed}>
              <div className="booking-form-heading">
                <div className="booking-form-icon fixed"><CalendarClock /></div>
                <div>
                  <p>FIXED-ARRIVAL RESERVATION</p>
                  <h2>Reserve a charger at your selected time</h2>
                  <span>The complete calculated charging period must fit within tomorrow and one of the 10 chargers must be free.</span>
                </div>
              </div>

              <div className="fixed-booking-price-chart">
                <div className="fixed-booking-price-chart-heading">
                  <div>
                    <p>TOMORROW’S FIXED-ARRIVAL PRICE</p>
                    <h3>15-Minute Booking Price Schedule</h3>
                    <span>Hover over the step graph to check the booking price at any arrival time.</span>
                  </div>
                  <strong>Rs. {selectedFixedArrivalPrice.toFixed(2)}<small>/kWh</small></strong>
                </div>

                <PriceChart
                  prices={fixedBookingPriceSchedule}
                  compact
                  variant="booking"
                  activeSlotIndex={selectedFixedArrivalSlot}
                  activeLabel="Selected arrival"
                />

                <div className="fixed-booking-chart-note">
                  The fixed-arrival booking price varies throughout tomorrow. The price applied to your reservation
                  is the value assigned to the 15-minute interval containing your selected arrival time.
                </div>
              </div>

              <div className="booking-input-grid">
                <label>
                  <span>Initial SOC on arrival</span>
                  <div className="input-with-unit"><input name="initialSoc" type="number" min="0" max="99" step="1" value={fixedForm.initialSoc} onChange={updateFixed} required /><b>%</b></div>
                </label>
                <label>
                  <span>Target SOC</span>
                  <div className="input-with-unit"><input name="targetSoc" type="number" min="1" max="100" step="1" value={fixedForm.targetSoc} onChange={updateFixed} required /><b>%</b></div>
                </label>
                <label className="full-field">
                  <span>Arrival time tomorrow</span>
                  <input name="arrivalTime" type="time" step="60" value={fixedForm.arrivalTime} onChange={updateFixed} required />
                  <small>You may select an exact minute. The calculated session will reserve one charger continuously.</small>
                </label>
              </div>

              <div className="calculation-summary fixed-summary">
                <div><BatteryCharging /><span>Energy required<strong>{fixedCalculation ? `${fixedCalculation.energyRequiredKwh.toFixed(1)} kWh` : "Check SOC inputs"}</strong></span></div>
                <div><Gauge /><span>Effective charging rate<strong>{fixedCalculation ? `${fixedCalculation.effectiveChargingRateKw.toFixed(1)} kW` : "—"}</strong></span></div>
                <div><Clock3 /><span>Reserved duration<strong>{fixedCalculation ? `${fixedCalculation.durationMinutes} minutes` : "—"}</strong></span></div>
                <div><CalendarClock /><span>Calculated period<strong>{fixedCalculation && fixedEnd ? `${formatTime12(fixedForm.arrivalTime)}–${formatTime12(fixedEnd)}` : "—"}</strong></span></div>
              </div>

              <div className="booking-price-confirmation">
                <span>Price at selected arrival time</span>
                <strong>Rs. {selectedFixedArrivalPrice.toFixed(2)}/kWh</strong>
              </div>
              <button className="primary-action full" type="submit"><CheckCircle2 /> Check Capacity & Confirm</button>
            </form>
          ) : (
            <form onSubmit={submitFlexible}>
              <div className="booking-form-heading">
                <div className="booking-form-icon flexible"><Sparkles /></div>
                <div>
                  <p>FLEXIBLE SMART RESERVATION</p>
                  <h2>Give the station a suitable time range</h2>
                  <span>The optimization algorithm will select an exact arrival time within your range and notify you. Charging may continue beyond the range end.</span>
                </div>
              </div>

              <div className="fixed-booking-price-chart">
                <div className="fixed-booking-price-chart-heading">
                  <div>
                    <p>TOMORROW’S FLEXIBLE BOOKING PRICE</p>
                    <h3>15-Minute Booking Price Schedule</h3>
                    <span>Select your acceptable arrival range to highlight it and view the possible price range.</span>
                  </div>
                  <strong>
                    {selectedFlexiblePriceMinimum !== null
                      ? `Rs. ${selectedFlexiblePriceMinimum.toFixed(2)}–${selectedFlexiblePriceMaximum.toFixed(2)}`
                      : "Select a range"}
                    <small>/kWh</small>
                  </strong>
                </div>

                <PriceChart
                  prices={flexibleBookingPriceSchedule}
                  compact
                  variant="flexible"
                  rangeStartSlotIndex={selectedFlexibleStartSlot}
                  rangeEndSlotIndex={selectedFlexibleEndSlot}
                  rangeLabel="Your acceptable arrival range"
                />

                <div className="fixed-booking-chart-note">
                  Flexible booking uses the same tomorrow price signal as fixed-arrival booking. The station will select one exact arrival
                  time inside your highlighted range, and the final price will correspond to that scheduled time.
                </div>
              </div>

              <div className="booking-input-grid">
                <label>
                  <span>Initial SOC on arrival</span>
                  <div className="input-with-unit"><input name="initialSoc" type="number" min="0" max="99" step="1" value={flexibleForm.initialSoc} onChange={updateFlexible} required /><b>%</b></div>
                </label>
                <label>
                  <span>Target SOC</span>
                  <div className="input-with-unit"><input name="targetSoc" type="number" min="1" max="100" step="1" value={flexibleForm.targetSoc} onChange={updateFlexible} required /><b>%</b></div>
                </label>
                <label>
                  <span>Earliest acceptable arrival</span>
                  <input name="windowStart" type="time" step="60" value={flexibleForm.windowStart} onChange={updateFlexible} required />
                </label>
                <label>
                  <span>Latest acceptable arrival</span>
                  <input name="windowEnd" type="time" step="60" value={flexibleForm.windowEnd} onChange={updateFlexible} required />
                </label>
              </div>

              <div className="calculation-summary flexible-summary">
                <div><BatteryCharging /><span>Energy required<strong>{flexibleCalculation ? `${flexibleCalculation.energyRequiredKwh.toFixed(1)} kWh` : "Check SOC inputs"}</strong></span></div>
                <div><Clock3 /><span>Charging duration<strong>{flexibleCalculation ? `${flexibleCalculation.durationMinutes} minutes` : "—"}</strong></span></div>
                <div><CalendarClock /><span>Available range<strong>{flexibleRangeMinutes > 0 ? `${flexibleRangeMinutes} minutes` : "Invalid range"}</strong></span></div>
                <div><BellRing /><span>Exact arrival time<strong>Sent after optimization</strong></span></div>
              </div>

              <div className="booking-price-confirmation flexible">
                <span>Selected arrival range and possible flexible price</span>
                <strong>
                  {hasValidFlexibleRange && selectedFlexiblePriceMinimum !== null
                    ? `${formatTime12(flexibleForm.windowStart)}–${formatTime12(flexibleForm.windowEnd)} · Rs. ${selectedFlexiblePriceMinimum.toFixed(2)}–${selectedFlexiblePriceMaximum.toFixed(2)}/kWh`
                    : "Select a valid time range"}
                </strong>
              </div>
              <button className="flexible-action-button full" type="submit"><Sparkles /> Submit Flexible Request</button>
            </form>
          )}

          {error && <div className="auth-error booking-form-message">{error}</div>}
          {message && <div className="profile-success booking-form-message"><CheckCircle2 /> {message}</div>}
        </article>

        <aside className="booking-information-column">
          <article className="panel booking-rule-card">
            <Info />
            <div>
              <h3>How charger capacity is protected</h3>
              <p>Every confirmed session reserves one charger for its full calculated duration. The system rejects a fixed arrival if all 10 chargers would already be occupied during any part of that period.</p>
            </div>
          </article>

          <article className="panel my-bookings new-my-bookings">
            <div className="my-bookings-heading"><h2>My Booking Requests</h2><span>{myBookings.length}</span></div>
            {myBookings.length === 0 ? (
              <p className="muted-copy">No booking requests have been created yet.</p>
            ) : myBookings.map((booking) => (
              <div className={`new-booking-item ${booking.bookingType} ${booking.status}`} key={booking.id}>
                <div className="new-booking-item-top">
                  <span>{booking.bookingType === "fixed" ? "FIXED ARRIVAL" : "FLEXIBLE"}</span>
                  <b>{bookingStatusLabel(booking)}</b>
                </div>
                <strong>{formatDateLabel(booking.date)}</strong>
                {booking.bookingType === "fixed" ? (
                  <p>{formatTime12(booking.scheduledStart)}–{formatTime12(booking.scheduledEnd)} · Charger {booking.chargerId || "—"}</p>
                ) : booking.scheduledStart ? (
                  <p>{formatTime12(booking.scheduledStart)}–{formatTime12(booking.scheduledEnd)} · Charger {booking.chargerId || "—"}</p>
                ) : (
                  <p>Requested range: {formatTime12(booking.windowStart)}–{formatTime12(booking.windowEnd)}</p>
                )}
                <small>{booking.durationMinutes} min · {Number(booking.energyRequiredKwh || 0).toFixed(1)} kWh · Rs. {Number(booking.price).toFixed(2)}/kWh</small>
                {booking.notification && <div className="booking-notification"><BellRing /> {booking.notification}</div>}
                {["pending", "scheduled", "reserved"].includes(booking.status) && (
                  <button className="cancel-booking-button" onClick={() => cancelBooking(booking.id, user.id)}><XCircle /> Cancel</button>
                )}
              </div>
            ))}
          </article>
        </aside>
      </div>
    </section>
  );
}
