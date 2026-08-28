import {
  STATION_CHARGER_COUNT,
  calculateChargingRequirement,
  ceilToQuarterHour,
  getTomorrowDateKey,
  minutesFromTime,
  slotTime,
  timeFromMinutes,
} from "../utils/time.js";
import { databaseApi } from "./databaseApi";

const EVENT_NAME = "solarcharge-bookings-changed";
let bookingsCache = [];
let pollTimer = null;
let inFlightRefresh = null;

function normalizeBooking(booking) {
  if (booking.bookingType) return booking;
  const start = booking.scheduledStart || booking.time || "00:00";
  const end = booking.scheduledEnd || booking.endTime || timeFromMinutes(minutesFromTime(start) + 15);
  return {
    ...booking,
    bookingType: "fixed",
    arrivalTime: start,
    scheduledStart: start,
    scheduledEnd: end,
    chargerId: booking.chargerId || null,
    initialSoc: booking.initialSoc ?? 20,
    targetSoc: booking.targetSoc ?? 80,
    energyRequiredKwh: booking.energyRequiredKwh ?? null,
    durationMinutes: booking.durationMinutes ?? Math.max(15, minutesFromTime(end) - minutesFromTime(start)),
    notification: booking.notification || "Your charging period is reserved.",
  };
}

function emitBookings() {
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

function setCache(bookings) {
  const next = (Array.isArray(bookings) ? bookings : []).map(normalizeBooking);
  const before = JSON.stringify(bookingsCache);
  const after = JSON.stringify(next);
  bookingsCache = next;
  if (before !== after) emitBookings();
  return bookingsCache;
}

export async function refreshBookings() {
  if (inFlightRefresh) return inFlightRefresh;
  inFlightRefresh = databaseApi.bookings()
    .then(setCache)
    .finally(() => { inFlightRefresh = null; });
  return inFlightRefresh;
}

export function getBookings() {
  return bookingsCache.map(normalizeBooking);
}

export function getTomorrowBookings(now = new Date()) {
  const tomorrow = getTomorrowDateKey(now);
  return getBookings().filter((booking) => booking.date === tomorrow);
}

function buildCommonBooking({ user, date, initialSoc, targetSoc, price }) {
  const requirement = calculateChargingRequirement({
    batteryCapacityKwh: user.vehicle?.batteryCapacityKwh,
    chargingRateKw: user.vehicle?.maxChargingRateKw,
    initialSoc,
    targetSoc,
  });
  return {
    id: crypto.randomUUID(),
    userId: user.id,
    userName: user.name,
    userEmail: user.email,
    userPhone: user.phone || "",
    vehicleMake: user.vehicle?.make || "",
    vehicleModel: user.vehicle?.model || "",
    batteryCapacityKwh: Number(user.vehicle?.batteryCapacityKwh),
    chargingRateKw: Number(user.vehicle?.maxChargingRateKw),
    connectorType: user.vehicle?.connectorType || "",
    registrationNumber: user.vehicle?.registrationNumber || "",
    date,
    initialSoc: Number(initialSoc),
    targetSoc: Number(targetSoc),
    energyRequiredKwh: requirement.energyRequiredKwh,
    effectiveChargingRateKw: requirement.effectiveChargingRateKw,
    durationMinutes: requirement.durationMinutes,
    price: Number(price),
    createdAt: new Date().toISOString(),
  };
}

export async function createFixedBooking({ user, arrivalTime, initialSoc, targetSoc, price, now = new Date() }) {
  const date = getTomorrowDateKey(now);
  const startMinutes = minutesFromTime(arrivalTime);
  const common = buildCommonBooking({ user, date, initialSoc, targetSoc, price });
  const endMinutes = startMinutes + common.durationMinutes;
  if (!arrivalTime || startMinutes < 0 || startMinutes >= 1440) throw new Error("Select a valid arrival time for tomorrow.");
  if (endMinutes > 1440) throw new Error("The calculated charging session would continue beyond tomorrow. Select an earlier arrival time.");

  const payload = {
    ...common,
    bookingType: "fixed",
    arrivalTime,
    scheduledStart: arrivalTime,
    scheduledEnd: timeFromMinutes(endMinutes),
    chargerId: null,
    status: "reserved",
    notification: "",
    slotKey: `${date}T${arrivalTime}`,
  };
  const booking = await databaseApi.createBooking(payload);
  setCache([...bookingsCache.filter((item) => item.id !== booking.id), booking]);
  return booking;
}

export async function createFlexibleBooking({ user, windowStart, windowEnd, initialSoc, targetSoc, price, now = new Date() }) {
  const date = getTomorrowDateKey(now);
  const startMinutes = minutesFromTime(windowStart);
  const endMinutes = minutesFromTime(windowEnd);
  const common = buildCommonBooking({ user, date, initialSoc, targetSoc, price });
  if (!windowStart || !windowEnd || endMinutes <= startMinutes) throw new Error("The latest arrival time must be after the earliest arrival time.");
  if (startMinutes + common.durationMinutes > 1440) throw new Error("The earliest selected arrival time would make the session continue beyond tomorrow.");
  if (Math.min(endMinutes, 1440 - common.durationMinutes) < startMinutes) throw new Error("No feasible arrival time in this range allows the calculated session to finish tomorrow.");

  const payload = {
    ...common,
    bookingType: "flexible",
    windowStart,
    windowEnd,
    scheduledStart: null,
    scheduledEnd: null,
    chargerId: null,
    status: "pending",
    notification: "Your flexible booking request was received. The station will notify you after tomorrow's schedule is optimized.",
    slotKey: `${date}TFLEX-${crypto.randomUUID().slice(0, 8)}`,
  };
  const booking = await databaseApi.createBooking(payload);
  setCache([...bookingsCache.filter((item) => item.id !== booking.id), booking]);
  return booking;
}

function averagePriceForPeriod(prices, startMinutes, durationMinutes) {
  const firstSlot = Math.floor(startMinutes / 15);
  const slots = Math.max(1, Math.ceil(durationMinutes / 15));
  const values = prices.slice(firstSlot, firstSlot + slots);
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

function overlaps(startA, endA, startB, endB) { return startA < endB && startB < endA; }
function scheduledInterval(booking) {
  const start = booking.scheduledStart || (booking.bookingType === "fixed" ? booking.arrivalTime : null);
  const end = booking.scheduledEnd || booking.endTime;
  if (!start || !end) return null;
  return { start: minutesFromTime(start), end: minutesFromTime(end), chargerId: Number(booking.chargerId) || null };
}
function findAvailableCharger(bookings, date, startMinutes, endMinutes) {
  const scheduled = bookings.filter((booking) => booking.date === date && ["reserved", "scheduled", "completed"].includes(booking.status));
  for (let chargerId = 1; chargerId <= STATION_CHARGER_COUNT; chargerId += 1) {
    const conflict = scheduled.some((booking) => {
      const interval = scheduledInterval(booking);
      return interval?.chargerId === chargerId && overlaps(startMinutes, endMinutes, interval.start, interval.end);
    });
    if (!conflict) return chargerId;
  }
  return null;
}

export async function schedulePendingFlexibleBookings(publicTomorrowPrices, now = new Date()) {
  if (!Array.isArray(publicTomorrowPrices) || publicTomorrowPrices.length !== 96) throw new Error("A valid 96-slot tomorrow public price schedule is required.");
  await refreshBookings();
  const tomorrow = getTomorrowDateKey(now);
  let bookings = getBookings();
  const pending = bookings.filter((b) => b.date === tomorrow && b.bookingType === "flexible" && b.status === "pending")
    .sort((a, b) => minutesFromTime(a.windowEnd) - minutesFromTime(b.windowEnd));
  let scheduledCount = 0; let unscheduledCount = 0;
  for (const request of pending) {
    const earliest = ceilToQuarterHour(minutesFromTime(request.windowStart));
    const latestStart = Math.min(minutesFromTime(request.windowEnd), 1440 - request.durationMinutes);
    const candidates = [];
    for (let start = earliest; start <= latestStart; start += 15) {
      const end = start + request.durationMinutes;
      const chargerId = findAvailableCharger(bookings, tomorrow, start, end);
      if (!chargerId) continue;
      candidates.push({ start, end, chargerId, averagePublicPrice: averagePriceForPeriod(publicTomorrowPrices, start, request.durationMinutes) });
    }
    candidates.sort((a, b) => a.averagePublicPrice - b.averagePublicPrice || a.start - b.start);
    const selected = candidates[0];
    if (!selected) { unscheduledCount += 1; continue; }
    const scheduledStart = timeFromMinutes(selected.start);
    const scheduledEnd = timeFromMinutes(selected.end);
    const updated = await databaseApi.patchBooking(request.id, {
      status: "scheduled", scheduledStart, scheduledEnd, chargerId: selected.chargerId,
      notification: `Your flexible booking is scheduled for tomorrow from ${scheduledStart} to ${scheduledEnd}. Please arrive at ${scheduledStart}. Charger ${String(selected.chargerId).padStart(2, "0")} is assigned.`,
      notifiedAt: new Date().toISOString(),
    });
    bookings = bookings.map((b) => b.id === updated.id ? updated : b);
    scheduledCount += 1;
  }
  setCache(bookings);
  return { scheduledCount, unscheduledCount, bookings };
}

export async function cancelBooking(bookingId, userId) {
  const existing = bookingsCache.find((item) => item.id === bookingId && item.userId === userId);
  if (!existing) return false;
  const updated = await databaseApi.patchBooking(bookingId, {
    status: "cancelled",
    notification: "This booking was cancelled.",
    cancelledAt: new Date().toISOString(),
  });
  setCache(bookingsCache.map((b) => b.id === updated.id ? updated : b));
  return true;
}

export async function replaceBookings(bookings) {
  // Kept for compatibility. MongoDB records are updated one-by-one instead of replacing the whole shared collection.
  const updates = await Promise.all((bookings || []).map((booking) => databaseApi.patchBooking(booking.id, normalizeBooking(booking))));
  setCache(updates);
  return updates;
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}
export function buildBookingsCsv(bookings = getTomorrowBookings()) {
  const headers = ["booking_id","booking_type","status","date","customer_name","email","phone","vehicle","battery_capacity_kwh","charging_rate_kw","initial_soc_percent","target_soc_percent","energy_required_kwh","duration_minutes","arrival_time","flexible_window_start","flexible_window_end","scheduled_start","scheduled_end","charger_id","price_lkr_per_kwh","created_at"];
  const rows = bookings.map((b) => [b.id,b.bookingType,b.status,b.date,b.userName,b.userEmail,b.userPhone,`${b.vehicleMake || ""} ${b.vehicleModel || ""}`.trim(),b.batteryCapacityKwh,b.chargingRateKw,b.initialSoc,b.targetSoc,Number(b.energyRequiredKwh || 0).toFixed(3),b.durationMinutes,b.arrivalTime || "",b.windowStart || "",b.windowEnd || "",b.scheduledStart || "",b.scheduledEnd || "",b.chargerId || "",b.price,b.createdAt]);
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}
export function downloadTomorrowBookingsCsv() {
  const blob = new Blob([buildBookingsCsv()], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `solarcharge-bookings-${getTomorrowDateKey()}.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

export function subscribeToBookings(callback) {
  const handler = () => callback();
  window.addEventListener(EVENT_NAME, handler);
  if (!pollTimer) {
    refreshBookings().catch(() => {});
    pollTimer = window.setInterval(() => refreshBookings().catch(() => {}), 4000);
  }
  return () => window.removeEventListener(EVENT_NAME, handler);
}

function isCustomerOptimizerNotification(booking) {
  return booking?.notificationSource === "elastic_user_notifications.csv" && Boolean(String(booking?.notification || "").trim());
}
export function getUserNotifications(userId) {
  if (!userId) return [];
  return getBookings().filter((b) => b.userId === userId && isCustomerOptimizerNotification(b)).sort((a,b) => new Date(b.notifiedAt || b.updatedAt || b.createdAt || 0) - new Date(a.notifiedAt || a.updatedAt || a.createdAt || 0));
}
export function getUnreadNotificationCount(userId) { return getUserNotifications(userId).filter((b) => !b.notificationReadAt).length; }
export async function markUserNotificationRead(bookingId, userId) {
  const item = bookingsCache.find((b) => b.id === bookingId && b.userId === userId && isCustomerOptimizerNotification(b));
  if (!item || item.notificationReadAt) return false;
  const updated = await databaseApi.patchBooking(bookingId, { notificationReadAt: new Date().toISOString() });
  setCache(bookingsCache.map((b) => b.id === updated.id ? updated : b));
  return true;
}
export async function markAllUserNotificationsRead(userId) {
  const unread = getUserNotifications(userId).filter((b) => !b.notificationReadAt);
  if (!unread.length) return false;
  const readAt = new Date().toISOString();
  const updates = await Promise.all(unread.map((b) => databaseApi.patchBooking(b.id, { notificationReadAt: readAt })));
  const map = new Map(updates.map((b) => [b.id, b]));
  setCache(bookingsCache.map((b) => map.get(b.id) || b));
  return true;
}

export function createSlotLabels() { return Array.from({ length: 96 }, (_, index) => slotTime(index)); }
export function getOptimizerEligibleTomorrowBookings(now = new Date()) {
  return getTomorrowBookings(now).filter((booking) => ["pending", "reserved", "scheduled"].includes(booking.status) && booking.userId && booking.id);
}

export async function applyElasticOptimizerNotifications(result) {
  const notifications = Array.isArray(result?.elasticNotifications) ? result.elasticNotifications : [];
  const summary = await databaseApi.applyOptimizerNotifications(result?.jobId || "", notifications);
  await refreshBookings();
  return summary;
}
