import {
  BarChart3,
  BatteryCharging,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Gauge,
  LogOut,
  Menu,
  SlidersHorizontal,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAdminAuth } from "../context/AdminAuthContext";

const links = [
  { to: "/admin/dashboard", label: "Overview", icon: Gauge },
  { to: "/admin/optimization", label: "Price Optimization", icon: Sparkles },
  { to: "/admin/prices", label: "Price Management", icon: SlidersHorizontal },
  { to: "/admin/chargers", label: "Charger Control", icon: BatteryCharging },
  { to: "/admin/bookings", label: "Bookings", icon: BookOpenCheck },
  { to: "/admin/customers", label: "Customers", icon: UsersRound },
  { to: "/admin/revenue", label: "Income & Revenue", icon: CircleDollarSign },
];

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [now, setNow] = useState(new Date());
  const { logout } = useAdminAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  function signOut() {
    logout();
    navigate("/admin", { replace: true });
  }

  return (
    <div className={`admin-shell ${collapsed ? "admin-sidebar-collapsed" : ""}`}>
      <aside className={`admin-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="admin-brand">
          <span className="admin-brand-mark"><BarChart3 /></span>
          {!collapsed && <span><strong>SolarCharge</strong><small>Owner Administration</small></span>}
          <button className="admin-mobile-close" onClick={() => setMobileOpen(false)}><X /></button>
        </div>

        <nav className="admin-nav">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              title={collapsed ? label : undefined}
              className={({ isActive }) => isActive ? "admin-nav-link active" : "admin-nav-link"}
            >
              <Icon size={20} />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar-bottom">
          <button className="admin-collapse-button" onClick={() => setCollapsed((value) => !value)}>
            {collapsed ? <ChevronRight /> : <><ChevronLeft /><span>Collapse menu</span></>}
          </button>
          <button className="admin-logout-button" onClick={signOut}>
            <LogOut size={19} />{!collapsed && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <button className="admin-menu-button" onClick={() => setMobileOpen(true)}><Menu /></button>
          <div>
            <span className="admin-system-label">EV CHARGING STATION MANAGEMENT SYSTEM</span>
            <strong>Owner Control Centre</strong>
          </div>
          <div className="admin-topbar-right">
            <div className="admin-clock">
              <strong>{now.toLocaleTimeString("en-US", { timeZone: "Asia/Colombo", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</strong>
              <small>{now.toLocaleDateString("en-US", { timeZone: "Asia/Colombo", month: "short", day: "numeric", year: "numeric" })}</small>
            </div>
            <div className="admin-profile">
              <span>A</span>
              <div><strong>Administrator</strong><small>Station owner</small></div>
            </div>
          </div>
        </header>
        <main className="admin-content"><Outlet /></main>
      </div>
    </div>
  );
}
