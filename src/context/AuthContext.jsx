import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { databaseApi } from "../services/databaseApi";

const AuthContext = createContext(null);
const SESSION_KEY = "solarcharge_session_v2";

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function normalizeVehicle(details = {}) {
  return {
    make: String(details.vehicleMake ?? details.make ?? "").trim(),
    model: String(details.vehicleModel ?? details.model ?? "").trim(),
    batteryCapacityKwh: Number(details.batteryCapacity ?? details.batteryCapacityKwh) || 0,
    maxChargingRateKw: Number(details.chargingRate ?? details.maxChargingRateKw) || 0,
    connectorType: String(details.connectorType || "CCS2").trim(),
    registrationNumber: String(details.registrationNumber || "").trim().toUpperCase(),
  };
}

function validateVehicle(vehicle) {
  if (!vehicle.make || !vehicle.model) throw new Error("Vehicle manufacturer and model are required.");
  if (vehicle.batteryCapacityKwh <= 0) throw new Error("Enter a valid battery capacity.");
  if (vehicle.maxChargingRateKw <= 0) throw new Error("Enter a valid maximum charging rate.");
}

function saveSession(user, setUser) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  setUser(user);
  return user;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readSession);

  useEffect(() => {
    if (!user?.id) return undefined;
    let cancelled = false;

    async function refreshProfile() {
      try {
        const fresh = await databaseApi.customer(user.id);
        if (!cancelled) saveSession(fresh, setUser);
      } catch (error) {
        if (!cancelled && /not found/i.test(error.message)) {
          localStorage.removeItem(SESSION_KEY);
          setUser(null);
        }
      }
    }

    refreshProfile();
    const timer = window.setInterval(refreshProfile, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [user?.id]);

  async function signUp(details) {
    const vehicle = normalizeVehicle(details);
    validateVehicle(vehicle);
    const account = await databaseApi.signup({
      name: details.name.trim(),
      phone: details.phone.trim(),
      email: details.email.trim().toLowerCase(),
      password: details.password,
      vehicle,
    });
    return saveSession(account, setUser);
  }

  async function login({ email, password }) {
    const account = await databaseApi.login({ email: email.trim().toLowerCase(), password });
    return saveSession(account, setUser);
  }

  async function updateProfile(details) {
    if (!user) throw new Error("You must be logged in to update your profile.");
    const vehicle = normalizeVehicle(details);
    validateVehicle(vehicle);
    const account = await databaseApi.updateCustomer(user.id, {
      name: details.name.trim(),
      phone: details.phone.trim(),
      vehicle,
    });
    window.dispatchEvent(new CustomEvent("solarcharge-customer-profile-changed"));
    return saveSession(account, setUser);
  }

  function logout() {
    localStorage.removeItem(SESSION_KEY);
    setUser(null);
  }

  const value = useMemo(
    () => ({ user, isLoggedIn: Boolean(user), signUp, login, updateProfile, logout }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
