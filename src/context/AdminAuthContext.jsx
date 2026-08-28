import { createContext, useContext, useMemo, useState } from "react";

const AdminAuthContext = createContext(null);
const ADMIN_SESSION_KEY = "solarcharge_admin_session_v1";
const ADMIN_USERNAME = "admin";
const ADMIN_PASSWORD = "admin1234";

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(ADMIN_SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export function AdminAuthProvider({ children }) {
  const [admin, setAdmin] = useState(readSession);

  function login(username, password) {
    if (username !== ADMIN_USERNAME || password !== ADMIN_PASSWORD) {
      throw new Error("Incorrect administrator username or password.");
    }
    const session = { username: ADMIN_USERNAME, signedInAt: new Date().toISOString() };
    localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
    setAdmin(session);
    return session;
  }

  function logout() {
    localStorage.removeItem(ADMIN_SESSION_KEY);
    setAdmin(null);
  }

  const value = useMemo(
    () => ({ admin, isAdminLoggedIn: Boolean(admin), login, logout }),
    [admin]
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth() {
  const value = useContext(AdminAuthContext);
  if (!value) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return value;
}
