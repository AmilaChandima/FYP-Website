import { BarChart3, Eye, EyeOff, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAdminAuth } from "../../context/AdminAuthContext";

export default function AdminLogin() {
  const { isAdminLoggedIn, login } = useAdminAuth();
  const [form, setForm] = useState({ username: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  if (isAdminLoggedIn) return <Navigate to="/admin/dashboard" replace />;

  function submit(event) {
    event.preventDefault();
    setError("");
    try {
      login(form.username.trim(), form.password);
      navigate(location.state?.from || "/admin/dashboard", { replace: true });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="admin-login-page">
      <div className="admin-login-background" />
      <section className="admin-login-card">
        <div className="admin-login-logo"><BarChart3 /></div>
        <p className="admin-login-eyebrow">PRIVATE OWNER ACCESS</p>
        <h1>SolarCharge Admin</h1>
        <p className="admin-login-copy">Sign in to manage station operations, pricing, bookings, customers and optimization data.</p>

        <form onSubmit={submit} className="admin-login-form">
          <label>
            <span><UserRound size={17} /> Username</span>
            <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} placeholder="Administrator username" autoComplete="username" required />
          </label>
          <label>
            <span><LockKeyhole size={17} /> Password</span>
            <div className="admin-password-field">
              <input type={showPassword ? "text" : "password"} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="Administrator password" autoComplete="current-password" required />
              <button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff /> : <Eye />}</button>
            </div>
          </label>
          {error && <div className="admin-login-error">{error}</div>}
          <button className="admin-primary-button" type="submit"><ShieldCheck size={19} /> Access Admin Panel</button>
        </form>

        <div className="admin-login-note">
          <ShieldCheck size={17} />
          <span>This URL is not linked from the customer website. For production, replace this demo login with secure server-side authentication.</span>
        </div>
      </section>
    </main>
  );
}
