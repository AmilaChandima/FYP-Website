export const STATION_TIME_ZONE = "Asia/Colombo";
export const STATION_CHARGER_COUNT = 10;
export const STATION_CHARGER_POWER_KW = 450;

export function getStationDateTime(date = new Date()) {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: STATION_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });

  return Object.fromEntries(
    formatter
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)])
  );
}

export function dateKey({ year, month, day }) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function addDaysToDateKey(key, days) {
  const [year, month, day] = key.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days, 12, 0, 0));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

export function getTomorrowDateKey(now = new Date()) {
  return addDaysToDateKey(dateKey(getStationDateTime(now)), 1);
}

export function formatDateLabel(key) {
  const [year, month, day] = key.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

export function slotTime(index) {
  const total = (index % 96) * 15;
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export function minutesFromTime(time) {
  const [hour, minute] = String(time || "00:00").split(":").map(Number);
  return hour * 60 + minute;
}

export function timeFromMinutes(totalMinutes) {
  const safe = Math.max(0, Math.min(1440, Math.round(totalMinutes)));
  if (safe === 1440) return "24:00";
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

export function formatTime12(time24) {
  if (time24 === "24:00") return "12:00 AM";
  const [hour, minute] = String(time24).split(":").map(Number);
  const suffix = hour >= 12 ? "PM" : "AM";
  const h = hour % 12 || 12;
  return `${h}:${String(minute).padStart(2, "0")} ${suffix}`;
}

export function ceilToQuarterHour(totalMinutes) {
  return Math.ceil(totalMinutes / 15) * 15;
}

export function calculateChargingRequirement({
  batteryCapacityKwh,
  chargingRateKw,
  initialSoc,
  targetSoc,
}) {
  const capacity = Number(batteryCapacityKwh);
  const vehicleRate = Number(chargingRateKw);
  const initial = Number(initialSoc);
  const target = Number(targetSoc);

  if (!Number.isFinite(capacity) || capacity <= 0) {
    throw new Error("A valid vehicle battery capacity is required.");
  }
  if (!Number.isFinite(vehicleRate) || vehicleRate <= 0) {
    throw new Error("A valid vehicle charging rate is required.");
  }
  if (!Number.isFinite(initial) || !Number.isFinite(target) || initial < 0 || target > 100 || target <= initial) {
    throw new Error("Target SOC must be greater than initial SOC and not exceed 100%.");
  }

  const energyRequiredKwh = capacity * ((target - initial) / 100);
  const effectiveChargingRateKw = Math.min(vehicleRate, STATION_CHARGER_POWER_KW);
  const rawDurationMinutes = (energyRequiredKwh / effectiveChargingRateKw) * 60;
  const durationMinutes = Math.max(15, ceilToQuarterHour(rawDurationMinutes));

  return {
    energyRequiredKwh,
    effectiveChargingRateKw,
    rawDurationMinutes,
    durationMinutes,
  };
}
