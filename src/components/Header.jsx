import {
  BatteryCharging, CalendarCheck2, Gauge, Info, LayoutDashboard,
  LogIn, LogOut, Menu, Tag, UserPlus, UserRound, X, Sun, BellRing
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { getUnreadNotificationCount, subscribeToBookings } from "../services/bookings";

const links = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/pricing", label: "Pricing", icon: Tag },
  { to: "/chargers", label: "Chargers", icon: BatteryCharging },
  { to: "/about", label: "About Us", icon: Info },
];

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [now, setNow] = useState(new Date());
  const [, setBookingVersion] = useState(0);
  const { user, isLoggedIn, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    const unsubscribe = subscribeToBookings(() => setBookingVersion((value) => value + 1));
    return () => { window.clearInterval(timer); unsubscribe(); };
  }, []);

  const notificationCount = isLoggedIn ? getUnreadNotificationCount(user?.id) : 0;

  function handleLogout() {
    logout();
    navigate("/dashboard");
  }

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <NavLink to="/dashboard" className="brand" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark"><Gauge size={24} /></span>
          <span><strong>Solar<span>Charge</span></strong><small>Smart EV Fast Charging</small></span>
        </NavLink>

        <nav className={`main-nav ${mobileOpen ? "open" : ""}`}>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setMobileOpen(false)}
              className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <Icon size={18} />{label}
            </NavLink>
          ))}
          {isLoggedIn && (
            <>
              <NavLink to="/booking" onClick={() => setMobileOpen(false)}
                className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                <CalendarCheck2 size={18} />Booking
              </NavLink>
              <NavLink to="/notifications" onClick={() => setMobileOpen(false)}
                className={({ isActive }) => isActive ? "nav-link active mobile-account-link" : "nav-link mobile-account-link"}>
                <BellRing size={18} />Notifications{notificationCount > 0 ? ` (${notificationCount})` : ""}
              </NavLink>
              <NavLink to="/account" onClick={() => setMobileOpen(false)}
                className={({ isActive }) => isActive ? "nav-link active mobile-account-link" : "nav-link mobile-account-link"}>
                <UserRound size={18} />My Account
              </NavLink>
            </>
          )}
          {!isLoggedIn ? (
            <>
              <NavLink to="/login" className="nav-link mobile-account-link" onClick={() => setMobileOpen(false)}><LogIn size={18} />Login</NavLink>
              <NavLink to="/signup" className="nav-link mobile-account-link" onClick={() => setMobileOpen(false)}><UserPlus size={18} />Create Account</NavLink>
            </>
          ) : (
            <button className="nav-link mobile-account-link mobile-logout" onClick={() => { setMobileOpen(false); handleLogout(); }}><LogOut size={18} />Logout</button>
          )}
        </nav>

        <div className="header-account">
          {isLoggedIn ? (
            <>
              <button className="header-notification-button" onClick={() => navigate("/notifications")} title="View charging notifications">
                <BellRing size={18} />
                {notificationCount > 0 && <span>{notificationCount}</span>}
              </button>
              <button className="account-chip" onClick={() => navigate("/account")} title="Open My Account">
                <span className="account-avatar">{user.name.slice(0, 1).toUpperCase()}</span>
                <span><strong>{user.name}</strong><small>My Account</small></span>
              </button>
              <button className="icon-account-button" onClick={handleLogout} title="Log out"><LogOut size={17} /></button>
            </>
          ) : (
            <>
              <button className="header-login" onClick={() => navigate("/login")}><LogIn size={16} /> Login</button>
              <button className="header-signup" onClick={() => navigate("/signup")}><UserPlus size={16} /> Create Account</button>
            </>
          )}
        </div>

        <div className="header-info compact-info">
          <div className="weather"><Sun size={24} /><span><strong>28°C</strong><small>Sunny</small></span></div>
          <div className="clock"><strong>{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</strong></div>
        </div>

        <button className="menu-button" onClick={() => setMobileOpen((value) => !value)} aria-label="Toggle menu">
          {mobileOpen ? <X /> : <Menu />}
        </button>
      </div>
    </header>
  );
}
