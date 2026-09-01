import { Navigate, Route, Routes } from "react-router-dom";
import SiteLayout from "./components/SiteLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminProtectedRoute from "./components/AdminProtectedRoute";
import AdminLayout from "./components/AdminLayout";
import Dashboard from "./pages/Dashboard";
import Pricing from "./pages/Pricing";
import Chargers from "./pages/Chargers";
import About from "./pages/About";
import Booking from "./pages/Booking";
import Account from "./pages/Account";
import Notifications from "./pages/Notifications";
import AuthPage from "./pages/AuthPage";
import AdminLogin from "./pages/admin/AdminLogin";
import AdminOverview from "./pages/admin/AdminOverview";
import AdminOptimization from "./pages/admin/AdminOptimization";
import AdminOptimizationResults from "./pages/admin/AdminOptimizationResults";
import AdminPricing from "./pages/admin/AdminPricing";
import AdminBookings from "./pages/admin/AdminBookings";
import AdminCustomers from "./pages/admin/AdminCustomers";

export default function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/chargers" element={<Chargers />} />
        <Route path="/about" element={<About />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="/booking" element={<ProtectedRoute><Booking /></ProtectedRoute>} />
        <Route path="/account" element={<ProtectedRoute><Account /></ProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
      </Route>

      <Route path="/admin" element={<AdminLogin />} />
      <Route
        element={
          <AdminProtectedRoute>
            <AdminLayout />
          </AdminProtectedRoute>
        }
      >
        <Route path="/admin/dashboard" element={<AdminOverview />} />
        <Route path="/admin/optimization" element={<AdminOptimization />} />
        <Route path="/admin/optimization/results/:jobId" element={<AdminOptimizationResults />} />
        <Route path="/admin/prices" element={<AdminPricing />} />
        <Route path="/admin/bookings" element={<AdminBookings />} />
        <Route path="/admin/customers" element={<AdminCustomers />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
