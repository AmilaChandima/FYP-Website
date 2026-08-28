import {
  BatteryMedium, CarFront, CheckCircle2, Gauge, IdCard,
  Mail, Phone, PlugZap, Save, UserRound
} from "lucide-react";
import { useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";

function formFromUser(user) {
  return {
    name: user?.name || "",
    phone: user?.phone || "",
    email: user?.email || "",
    vehicleMake: user?.vehicle?.make || "",
    vehicleModel: user?.vehicle?.model || "",
    batteryCapacity: user?.vehicle?.batteryCapacityKwh || "",
    chargingRate: user?.vehicle?.maxChargingRateKw || "",
    connectorType: user?.vehicle?.connectorType || "CCS2",
    registrationNumber: user?.vehicle?.registrationNumber || "",
  };
}

export default function Account() {
  const { user, updateProfile } = useAuth();
  const [form, setForm] = useState(() => formFromUser(user));
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const estimatedMinutes = useMemo(() => {
    const capacity = Number(form.batteryCapacity);
    const vehicleRate = Number(form.chargingRate);
    if (capacity <= 0 || vehicleRate <= 0) return null;
    const effectivePower = Math.min(vehicleRate, 450);
    return Math.ceil((capacity * 0.7 / effectivePower) * 60);
  }, [form.batteryCapacity, form.chargingRate]);

  function change(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError("");
    setSuccess("");
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (Number(form.batteryCapacity) <= 0 || Number(form.chargingRate) <= 0) {
      setError("Battery capacity and charging rate must be greater than zero.");
      return;
    }

    setBusy(true);
    try {
      await updateProfile(form);
      setSuccess("Your customer and vehicle details were updated successfully.");
    } catch (err) {
      setError(err.message || "Unable to update your profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-width inner-page account-page">
      <div className="account-page-heading">
        <div>
          <p className="eyebrow">CUSTOMER ACCOUNT</p>
          <h1>My Account</h1>
          <p>Keep your contact and EV specifications accurate for charging reservations.</p>
        </div>
        <div className="account-profile-badge">
          <span>{user.name.slice(0, 1).toUpperCase()}</span>
          <div><strong>{user.name}</strong><small>Registered customer</small></div>
        </div>
      </div>

      <div className="account-layout">
        <form className="panel account-form-card" onSubmit={submit}>
          <div className="account-form-section">
            <div className="account-section-title">
              <UserRound />
              <div><h2>Customer Details</h2><p>Your primary account and contact information</p></div>
            </div>
            <div className="account-field-grid">
              <label><span><UserRound size={16} /> Full name</span><input name="name" value={form.name} onChange={change} required /></label>
              <label><span><Phone size={16} /> Phone number</span><input name="phone" type="tel" value={form.phone} onChange={change} required /></label>
              <label className="full-field"><span><Mail size={16} /> Email address</span><input value={form.email} readOnly /><small>Email is used for login and cannot be changed in this demo.</small></label>
            </div>
          </div>

          <div className="account-form-section">
            <div className="account-section-title">
              <CarFront />
              <div><h2>Electric Vehicle Details</h2><p>Used to understand charging compatibility and expected session requirements</p></div>
            </div>
            <div className="account-field-grid">
              <label><span><CarFront size={16} /> Manufacturer</span><input name="vehicleMake" value={form.vehicleMake} onChange={change} required placeholder="Tesla" /></label>
              <label><span><CarFront size={16} /> Vehicle model</span><input name="vehicleModel" value={form.vehicleModel} onChange={change} required placeholder="Model 3" /></label>
              <label>
                <span><BatteryMedium size={16} /> Battery capacity</span>
                <div className="input-with-unit"><input name="batteryCapacity" type="number" min="1" max="300" step="0.1" value={form.batteryCapacity} onChange={change} required /><b>kWh</b></div>
              </label>
              <label>
                <span><Gauge size={16} /> Maximum charging rate</span>
                <div className="input-with-unit"><input name="chargingRate" type="number" min="1" max="500" step="0.1" value={form.chargingRate} onChange={change} required /><b>kW</b></div>
              </label>
              <label><span><PlugZap size={16} /> Connector type</span><select name="connectorType" value={form.connectorType} onChange={change} required><option value="CCS2">CCS2</option><option value="CHAdeMO">CHAdeMO</option><option value="GB/T">GB/T</option><option value="Type 2">Type 2</option></select></label>
              <label><span><IdCard size={16} /> Registration number</span><input name="registrationNumber" value={form.registrationNumber} onChange={change} placeholder="Optional" /></label>
            </div>
          </div>

          {error && <div className="auth-error">{error}</div>}
          {success && <div className="profile-success"><CheckCircle2 size={18} /> {success}</div>}
          <button className="primary-action account-save-button" disabled={busy}><Save size={18} /> {busy ? "Saving..." : "Save Changes"}</button>
        </form>

        <aside className="account-summary-column">
          <article className="panel vehicle-summary-card">
            <div className="vehicle-summary-icon"><CarFront /></div>
            <p>YOUR REGISTERED EV</p>
            <h2>{form.vehicleMake || "Vehicle"} {form.vehicleModel || "details not added"}</h2>
            <div className="vehicle-summary-facts">
              <span><small>Battery</small><strong>{form.batteryCapacity ? `${form.batteryCapacity} kWh` : "Not added"}</strong></span>
              <span><small>Maximum rate</small><strong>{form.chargingRate ? `${form.chargingRate} kW` : "Not added"}</strong></span>
              <span><small>Connector</small><strong>{form.connectorType || "Not added"}</strong></span>
              <span><small>Registration</small><strong>{form.registrationNumber || "Not provided"}</strong></span>
            </div>
          </article>

          <article className="panel charging-estimate-card">
            <Gauge />
            <div><small>Indicative 10%–80% charging time</small><strong>{estimatedMinutes ? `About ${estimatedMinutes} minutes` : "Add EV specifications"}</strong></div>
            <p>This simple estimate uses the lower of your vehicle charging limit and the station's 450 kW charger rating. Actual time depends on battery temperature and charging taper.</p>
          </article>

        </aside>
      </div>
    </section>
  );
}
