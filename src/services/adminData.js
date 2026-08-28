import { dateKey, getStationDateTime } from "../utils/time.js";
import { databaseApi } from "./databaseApi";
import { getBookings, refreshBookings, subscribeToBookings } from "./bookings.js";

const EVENT_NAME = "solarcharge-admin-data-changed";
let customersCache = [];
function fallbackRevenue() {
  const today = new Date();
  const daily = Array.from({ length: 30 }, (_, index) => {
    const d = new Date(today); d.setDate(d.getDate() - (29 - index));
    return { date: d.toISOString().slice(0, 10), amount: 0 };
  });
  return { daily, todaySlots: Array.from({ length: 96 }, () => 0), generatedFor: today.toISOString().slice(0, 10) };
}
let revenueCache = fallbackRevenue();
let pollTimer = null;

function emit() { window.dispatchEvent(new CustomEvent(EVENT_NAME)); }

export async function refreshAdminData() {
  try {
    const [customers, revenue] = await Promise.all([databaseApi.customers(), databaseApi.revenue(), refreshBookings()]);
    const changed = JSON.stringify(customersCache) !== JSON.stringify(customers) || JSON.stringify(revenueCache) !== JSON.stringify(revenue);
    customersCache = Array.isArray(customers) ? customers : [];
    revenueCache = revenue || revenueCache;
    if (changed) emit();
    return { customers: customersCache, revenue: revenueCache };
  } catch (error) {
    console.warn("Unable to refresh shared MongoDB admin data:", error.message);
    return { customers: customersCache, revenue: revenueCache };
  }
}

export function ensureDemoData() {
  refreshAdminData().catch(() => {});
}

export function subscribeToAdminData(callback) {
  const handler = () => callback();
  window.addEventListener(EVENT_NAME, handler);
  const unsubscribeBookings = subscribeToBookings(handler);
  refreshAdminData().catch(() => {});
  if (!pollTimer) pollTimer = window.setInterval(() => refreshAdminData().catch(() => {}), 5000);
  return () => { window.removeEventListener(EVENT_NAME, handler); unsubscribeBookings(); };
}

export function getCustomers() { return customersCache; }
export function getAllBookings() { return getBookings(); }

export async function updateBookingStatus(bookingId, status) {
  const patch = {
    status,
    notification: status === "completed"
      ? "Your charging session was marked as completed."
      : status === "cancelled"
        ? "This booking was cancelled by the station administrator."
        : undefined,
  };
  Object.keys(patch).forEach((key) => patch[key] === undefined && delete patch[key]);
  const updated = await databaseApi.patchBooking(bookingId, patch);
  await refreshBookings();
  return updated;
}

export function getRevenueData() { return revenueCache; }

export function getRevenueSummary(now = new Date()) {
  const data = getRevenueData();
  const current = getStationDateTime(now);
  const currentSlot = Math.min(95, Math.floor((current.hour * 60 + current.minute) / 15));
  const todaySlots = Array.isArray(data.todaySlots) ? data.todaySlots : [];
  const daily = Array.isArray(data.daily) ? data.daily : [];
  const todayUpToNow = todaySlots.slice(0, currentSlot + 1).reduce((sum, value) => sum + Number(value || 0), 0);
  const todayProjected = todaySlots.reduce((sum, value) => sum + Number(value || 0), 0);
  const todayKey = dateKey(current);
  const historical = daily.filter((item) => item.date !== todayKey).reduce((sum, item) => sum + Number(item.amount || 0), 0);
  return { todayUpToNow, todayProjected, allTime: historical + todayUpToNow, currentSlot };
}

export function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "LKR", maximumFractionDigits: 0 })
    .format(Number(value) || 0).replace("LKR", "Rs.");
}
