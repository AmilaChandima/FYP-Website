import {
  BatteryMedium, CarFront, Gauge, IdCard, LockKeyhole,
  Mail, Phone, PlugZap, UserRound
} from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const initialForm = {
  name: "",
  phone: "",
  email: "",
  password: "",
  confirm: "",
  vehicleMake: "",
  vehicleModel: "",
  batteryCapacity: "",
  chargingRate: "",
  connectorType: "CCS2",
  registrationNumber: "",
};

export default function AuthPage({ mode }) {
  const isSignup = mode === "signup";
  const { isLoggedIn, login, signUp } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const redirect = params.get("redirect") || "/booking";
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (isLoggedIn) return <Navigate to={redirect} replace />;

  function change(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");

    if (isSignup && form.password !== form.confirm) {
      return setError("Passwords do not match.");
    }
    if (form.password.length < 6) {
      return setError("Password must contain at least 6 characters.");
    }
    if (isSignup && (Number(form.batteryCapacity) <= 0 || Number(form.chargingRate) <= 0)) {
      return setError("Battery capacity and charging rate must be greater than zero.");
    }

    setBusy(true);
    try {
      if (isSignup) await signUp(form);
      else await login(form);
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(err.message || "Unable to continue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-page">
      <div className={`auth-card ${isSignup ? "signup-card" : ""}`}>
        <p className="eyebrow">REGISTERED CUSTOMER ACCESS</p>
        <h1>{isSignup ? "Create your account" : "Welcome back"}</h1>
        <p className="auth-intro">
          {isSignup
            ? "Create an account and add your EV details to access registered-user prices and reserve compatible charging slots."
            : "Log in to view booking prices and manage charging reservations."}
        </p>

        <form onSubmit={submit} className="auth-form">
          {isSignup && (
            <>
              <div className="auth-section-heading">
                <UserRound size={18} />
                <div><strong>Customer Details</strong><small>Information used for your account and reservations</small></div>
              </div>

              <div className="auth-field-grid">
                <label>
                  <span><UserRound size={16} /> Full name</span>
                  <input name="name" value={form.name} onChange={change} required placeholder="Your full name" />
                </label>
                <label>
                  <span><Phone size={16} /> Phone number</span>
                  <input name="phone" type="tel" value={form.phone} onChange={change} required placeholder="+94 77 123 4567" />
                </label>
              </div>
            </>
          )}

          <div className={isSignup ? "auth-field-grid" : ""}>
            <label>
              <span><Mail size={16} /> Email address</span>
              <input name="email" type="email" value={form.email} onChange={change} required placeholder="you@example.com" />
            </label>
            <label>
              <span><LockKeyhole size={16} /> Password</span>
              <input name="password" type="password" value={form.password} onChange={change} required placeholder="Minimum 6 characters" />
            </label>
          </div>

          {isSignup && (
            <>
              <label className="confirm-password-field">
                <span><LockKeyhole size={16} /> Confirm password</span>
                <input name="confirm" type="password" value={form.confirm} onChange={change} required placeholder="Repeat password" />
              </label>

              <div className="auth-section-heading vehicle-heading">
                <CarFront size={18} />
                <div><strong>Electric Vehicle Details</strong><small>You can edit these specifications later from My Account</small></div>
              </div>

              <div className="auth-field-grid">
                <label>
                  <span><CarFront size={16} /> Manufacturer</span>
                  <input name="vehicleMake" value={form.vehicleMake} onChange={change} required placeholder="Example: Tesla" />
                </label>
                <label>
                  <span><CarFront size={16} /> Vehicle model</span>
                  <input name="vehicleModel" value={form.vehicleModel} onChange={change} required placeholder="Example: Model 3" />
                </label>
                <label>
                  <span><BatteryMedium size={16} /> Battery capacity</span>
                  <div className="input-with-unit">
                    <input name="batteryCapacity" type="number" min="1" max="300" step="0.1" value={form.batteryCapacity} onChange={change} required placeholder="75" />
                    <b>kWh</b>
                  </div>
                </label>
                <label>
                  <span><Gauge size={16} /> Maximum charging rate</span>
                  <div className="input-with-unit">
                    <input name="chargingRate" type="number" min="1" max="500" step="0.1" value={form.chargingRate} onChange={change} required placeholder="150" />
                    <b>kW</b>
                  </div>
                </label>
                <label>
                  <span><PlugZap size={16} /> Connector type</span>
                  <select name="connectorType" value={form.connectorType} onChange={change} required>
                    <option value="CCS2">CCS2</option>
                    <option value="CHAdeMO">CHAdeMO</option>
                    <option value="GB/T">GB/T</option>
                    <option value="Type 2">Type 2</option>
                  </select>
                </label>
                <label>
                  <span><IdCard size={16} /> Registration number</span>
                  <input name="registrationNumber" value={form.registrationNumber} onChange={change} placeholder="Optional" />
                </label>
              </div>
            </>
          )}

          {error && <div className="auth-error">{error}</div>}
          <button className="primary-action full" disabled={busy}>
            {busy ? "Please wait..." : isSignup ? "Create Account" : "Login"}
          </button>
        </form>

        <p className="auth-switch">
          {isSignup
            ? <>Already registered? <Link to={`/login?redirect=${encodeURIComponent(redirect)}`}>Login</Link></>
            : <>New customer? <Link to={`/signup?redirect=${encodeURIComponent(redirect)}`}>Create an account</Link></>}
        </p>
        <small className="demo-security-note">Customer accounts and EV details are stored in the shared MongoDB database. Only the current login session is kept on this browser.</small>
      </div>
    </section>
  );
}
