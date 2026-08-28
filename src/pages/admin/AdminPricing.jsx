import {
  CheckCircle2,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sparkles,
  Tag,
  UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PriceChart from "../../components/PriceChart";
import { useStationData } from "../../context/StationDataContext";

const slots = ["00", "15", "30", "45"];

function scheduleStats(values) {
  if (!values.length) return { min: 0, max: 0, avg: 0 };
  return {
    min: Math.min(...values.map(Number)),
    max: Math.max(...values.map(Number)),
    avg: values.reduce((sum, value) => sum + Number(value), 0) / values.length,
  };
}

function PriceEditor({ values, onChange }) {
  return (
    <div className="admin-price-table-wrap">
      <table className="admin-price-table">
        <thead>
          <tr><th>Hour</th>{slots.map((slot) => <th key={slot}>:{slot}</th>)}</tr>
        </thead>
        <tbody>
          {Array.from({ length: 24 }, (_, hour) => (
            <tr key={hour}>
              <th>{String(hour).padStart(2, "0")}:00</th>
              {slots.map((slot, offset) => {
                const index = hour * 4 + offset;
                return (
                  <td key={slot}>
                    <div className="admin-price-input">
                      <span>Rs.</span>
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={values[index] ?? 0}
                        onChange={(event) => onChange(index, event.target.value)}
                      />
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPricing() {
  const station = useStationData();
  const [day, setDay] = useState("today");
  const [draft, setDraft] = useState([]);
  const [fixedDraft, setFixedDraft] = useState([]);
  const [flexiblePrice, setFlexiblePrice] = useState(station.flexibleBookingPrice);
  const [message, setMessage] = useState("");
  const [fixedMessage, setFixedMessage] = useState("");
  const [flexibleMessage, setFlexibleMessage] = useState("");

  const key = day === "today" ? "publicToday" : "publicTomorrow";
  const source = station[key];

  // StationDataContext performs periodic normalization/synchronization. That can
  // create a new array object even when the saved prices have not changed.
  // Depend on the actual price values instead of the array reference so an
  // unsaved edit is never overwritten by a background refresh.
  const publicSourceSignature = source.map(Number).join("|");
  const fixedSourceSignature = station.fixedArrivalTomorrowPrices.map(Number).join("|");

  useEffect(() => {
    setDraft([...source]);
    setMessage("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, publicSourceSignature]);

  useEffect(() => {
    setFixedDraft([...station.fixedArrivalTomorrowPrices]);
    setFixedMessage("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fixedSourceSignature]);

  useEffect(() => {
    setFlexiblePrice(station.flexibleBookingPrice);
  }, [station.flexibleBookingPrice]);

  const stats = useMemo(() => scheduleStats(draft), [draft]);
  const fixedStats = useMemo(() => scheduleStats(fixedDraft), [fixedDraft]);

  function updatePublic(index, value) {
    const number = Math.max(0, Number(value));
    setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? number : item));
    setMessage("");
  }

  function updateFixed(index, value) {
    const number = Math.max(0.01, Number(value));
    setFixedDraft((current) => current.map((item, itemIndex) => itemIndex === index ? number : item));
    setFixedMessage("");
  }

  async function savePublicSchedule() {
    try {
      await station.updatePriceSchedule(key, draft);
      setMessage(`The ${day} public 96-slot price schedule has been saved.`);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function saveFixedSchedule() {
    setFixedMessage("");
    try {
      await station.updateFixedArrivalPriceSchedule(fixedDraft);
      setFixedMessage("The 96-slot fixed-arrival booking schedule has been published to the customer Pricing and Booking pages.");
    } catch (error) {
      setFixedMessage(error.message);
    }
  }

  async function saveFlexiblePrice() {
    setFlexibleMessage("");
    try {
      await station.updateFlexibleBookingPrice(flexiblePrice);
      setFlexibleMessage("The flexible-booking reference price has been updated. Flexible customer prices remain below the fixed-arrival schedule.");
    } catch (error) {
      setFlexibleMessage(error.message);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-heading">
        <div>
          <p>PUBLIC & BOOKING PRICE CONTROL</p>
          <h1>Price Management</h1>
          <span>Manage the public tariff, the 96-slot fixed-arrival booking schedule and the lower flexible-booking price.</span>
        </div>
      </div>

      <section className="admin-panel admin-price-preview">
        <div className="admin-panel-heading">
          <div>
            <h2><UsersRound size={20} /> Fixed-Arrival Booking Prices — Tomorrow</h2>
            <p>These 96 values are the live registered-customer fixed-arrival prices used by the Pricing and Booking pages.</p>
          </div>
          <button className="admin-primary-button" onClick={saveFixedSchedule}>
            <Save size={18} /> Update Fixed-Arrival Prices
          </button>
        </div>

        <div className="admin-price-summary">
          <span>Minimum <strong>Rs. {fixedStats.min.toFixed(2)}</strong></span>
          <span>Average <strong>Rs. {fixedStats.avg.toFixed(2)}</strong></span>
          <span>Maximum <strong>Rs. {fixedStats.max.toFixed(2)}</strong></span>
        </div>

        {fixedDraft.length === 96 && <PriceChart prices={fixedDraft} variant="booking" />}

        <div className="admin-panel-heading" style={{ marginTop: 18 }}>
          <div>
            <h2><SlidersHorizontal size={20} /> 96-Slot Fixed-Arrival Price Editor</h2>
            <p>Each row is one hour. Edit the :00, :15, :30 and :45 arrival prices, then publish the schedule.</p>
          </div>
          <button className="admin-reset-button" onClick={() => setFixedDraft([...station.fixedArrivalTomorrowPrices])}>
            <RotateCcw size={17} /> Undo Unsaved Changes
          </button>
        </div>

        <PriceEditor values={fixedDraft} onChange={updateFixed} />
        {fixedMessage && <div className="admin-save-message"><CheckCircle2 size={18} /> {fixedMessage}</div>}
      </section>

      <section className="admin-panel admin-fixed-booking-prices">
        <div className="admin-panel-heading">
          <div>
            <h2><Sparkles size={20} /> Flexible Smart-Booking Price</h2>
            <p>This value controls the discounted flexible schedule. The customer-facing flexible prices are generated below the fixed-arrival pattern.</p>
          </div>
          <button className="admin-primary-button" onClick={saveFlexiblePrice}>
            <Save size={18} /> Update Flexible Price
          </button>
        </div>
        <div className="admin-booking-price-inputs">
          <label className="admin-booking-price-input flexible">
            <span>Flexible booking reference</span>
            <div>
              <small>Rs.</small>
              <input
                type="number"
                min="1"
                step="0.01"
                value={flexiblePrice}
                onChange={(event) => setFlexiblePrice(event.target.value)}
              />
              <b>/kWh</b>
            </div>
            <p>The application applies a discount to the fixed-arrival time pattern so flexible customers see a lower time-varying tariff.</p>
          </label>
        </div>
        {flexibleMessage && <div className="admin-save-message"><CheckCircle2 size={18} /> {flexibleMessage}</div>}
      </section>

      <section className="admin-panel admin-price-toolbar">
        <div className="admin-control-group">
          <span>Public schedule day</span>
          <div className="admin-toggle">
            <button className={day === "today" ? "active" : ""} onClick={() => setDay("today")}>Today</button>
            <button className={day === "tomorrow" ? "active" : ""} onClick={() => setDay("tomorrow")}>Tomorrow</button>
          </div>
        </div>
        <div className="admin-price-summary">
          <span>Minimum <strong>Rs. {stats.min.toFixed(2)}</strong></span>
          <span>Average <strong>Rs. {stats.avg.toFixed(2)}</strong></span>
          <span>Maximum <strong>Rs. {stats.max.toFixed(2)}</strong></span>
        </div>
      </section>

      <section className="admin-panel admin-price-preview">
        <div className="admin-panel-heading">
          <div>
            <h2><Tag size={20} /> {day === "today" ? "Today’s" : "Tomorrow’s"} Public Price Preview</h2>
            <p>Dynamic public / walk-in tariff at 15-minute resolution.</p>
          </div>
          <button className="admin-primary-button" onClick={savePublicSchedule}>
            <Save size={18} /> Save Public Schedule
          </button>
        </div>
        {draft.length === 96 && <PriceChart prices={draft} variant={day === "tomorrow" ? "forecast" : "public"} />}
      </section>

      <section className="admin-panel admin-price-editor">
        <div className="admin-panel-heading">
          <div>
            <h2><SlidersHorizontal size={20} /> 96-Slot Public Price Editor</h2>
            <p>Each row is one hour. The four values represent :00, :15, :30 and :45.</p>
          </div>
          <button className="admin-reset-button" onClick={() => setDraft([...source])}>
            <RotateCcw size={17} /> Undo Unsaved Changes
          </button>
        </div>
        <PriceEditor values={draft} onChange={updatePublic} />
        {message && <div className="admin-save-message"><CheckCircle2 size={18} /> {message}</div>}
      </section>
    </div>
  );
}
