import { Navigate, useLocation } from "react-router-dom";
import { useAdminAuth } from "../context/AdminAuthContext";

export default function AdminProtectedRoute({ children }) {
  const { isAdminLoggedIn } = useAdminAuth();
  const location = useLocation();
  if (!isAdminLoggedIn) {
    return <Navigate to="/admin" replace state={{ from: location.pathname }} />;
  }
  return children;
}
