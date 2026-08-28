import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { todayPrices, tomorrowPrices } from "../data/prices";
import { chargers as defaultChargers } from "../data/chargers";
import { fixedArrivalTomorrowPrices as defaultFixedArrivalTomorrowPrices } from "../data/fixedArrivalPrices";
import { addDaysToDateKey, dateKey, getStationDateTime } from "../utils/time";
import { databaseApi } from "../services/databaseApi";

const StationDataContext = createContext(null);

function validPrices(values) {
  return Array.isArray(values) && values.length === 96 && values.every((value) => Number.isFinite(Number(value)));
}
function currentScheduleKeys(now = new Date()) {
  const stationNow = getStationDateTime(now);
  const today = dateKey(stationNow);
  return { today, tomorrow: addDaysToDateKey(today, 1) };
}
function createDefaultState(now = new Date()) {
  const { today, tomorrow } = currentScheduleKeys(now);
  return {
    publicToday: [...todayPrices], publicTomorrow: [...tomorrowPrices], publicTodayDate: today, publicTomorrowDate: tomorrow,
    publicTomorrowAvailable: false, publicTomorrowPublishedAt: null, backendPriceSync: false, databaseConnected: false,
    fixedBookingPrice: 78, fixedArrivalTomorrowPrices: [...defaultFixedArrivalTomorrowPrices], flexibleBookingPrice: 62,
    chargers: defaultChargers, draftPublicTomorrow: null, draftForDate: null, draftGeneratedAt: null,
    lastAutoPublishedForDate: null, lastPriceUpdate: null,
  };
}
function normalizeRemote(remote, current = createDefaultState()) {
  const source = remote && typeof remote === "object" ? remote : {};
  return {
    ...current,
    ...source,
    publicToday: validPrices(source.publicToday) ? source.publicToday.map(Number) : current.publicToday,
    publicTomorrow: validPrices(source.publicTomorrow) ? source.publicTomorrow.map(Number) : current.publicTomorrow,
    fixedArrivalTomorrowPrices: validPrices(source.fixedArrivalTomorrowPrices) ? source.fixedArrivalTomorrowPrices.map(Number) : current.fixedArrivalTomorrowPrices,
    chargers: Array.isArray(source.chargers) && source.chargers.length === 10 ? source.chargers : current.chargers,
    flexibleBookingPrice: Number(source.flexibleBookingPrice) > 0 ? Number(source.flexibleBookingPrice) : current.flexibleBookingPrice,
    fixedBookingPrice: Number(source.fixedBookingPrice) > 0 ? Number(source.fixedBookingPrice) : current.fixedBookingPrice,
    backendPriceSync: true,
    databaseConnected: true,
  };
}

export function StationDataProvider({ children }) {
  const [station, setStation] = useState(() => createDefaultState());

  async function syncPublishedPrices() {
    try {
      const remote = await databaseApi.station();
      setStation((current) => normalizeRemote(remote, current));
      return remote;
    } catch {
      setStation((current) => ({ ...current, backendPriceSync: false, databaseConnected: false }));
      return null;
    }
  }

  useEffect(() => {
    syncPublishedPrices();
    const timer = window.setInterval(syncPublishedPrices, 4000);
    return () => window.clearInterval(timer);
  }, []);

  async function savePatch(patch) {
    const remote = await databaseApi.patchStation(patch);
    setStation((current) => normalizeRemote(remote, current));
    return remote;
  }

  function updatePriceSchedule(key, prices) {
    if (!["publicToday", "publicTomorrow"].includes(key)) throw new Error("Only public today or tomorrow schedules can be edited as 96-slot prices.");
    if (!validPrices(prices)) throw new Error("A price schedule must contain exactly 96 numeric values.");
    const normalized = prices.map(Number);
    const patch = { [key]: normalized, lastPriceUpdate: new Date().toISOString() };
    if (key === "publicTomorrow") patch.publicTomorrowAvailable = true;
    setStation((current) => ({ ...current, ...patch }));
    return savePatch(patch);
  }

  function updateFixedArrivalPriceSchedule(prices) {
    if (!validPrices(prices)) throw new Error("The fixed-arrival booking schedule must contain exactly 96 numeric values.");
    const normalized = prices.map(Number);
    if (normalized.some((value) => value <= 0)) throw new Error("Every fixed-arrival booking price must be greater than zero.");
    const average = normalized.reduce((sum, value) => sum + value, 0) / normalized.length;
    const patch = { fixedArrivalTomorrowPrices: normalized, fixedBookingPrice: Number(average.toFixed(2)), lastPriceUpdate: new Date().toISOString() };
    setStation((current) => ({ ...current, ...patch }));
    return savePatch(patch);
  }

  function updateFlexibleBookingPrice(flexiblePrice) {
    const flexible = Number(flexiblePrice);
    if (!Number.isFinite(flexible) || flexible <= 0) throw new Error("The flexible booking reference price must be greater than zero.");
    const patch = { flexibleBookingPrice: flexible, lastPriceUpdate: new Date().toISOString() };
    setStation((current) => ({ ...current, ...patch }));
    return savePatch(patch);
  }

  function updateBookingPrices({ fixedPrice, flexiblePrice }) {
    const fixed = Number(fixedPrice); const flexible = Number(flexiblePrice);
    if (fixed <= 0 || flexible <= 0) throw new Error("Booking prices must be greater than zero.");
    if (flexible >= fixed) throw new Error("The flexible booking price must be lower than the fixed-arrival booking price.");
    updateFixedArrivalPriceSchedule(Array.from({ length: 96 }, () => fixed));
    return updateFlexibleBookingPrice(flexible);
  }

  function setTomorrowOptimizationDraft(prices) {
    if (!validPrices(prices)) throw new Error("Tomorrow's draft must contain exactly 96 numeric values.");
    const { tomorrow } = currentScheduleKeys();
    setStation((current) => ({ ...current, draftPublicTomorrow: prices.map(Number), draftForDate: tomorrow, draftGeneratedAt: new Date().toISOString() }));
  }

  function publishTomorrowDraft() {
    const { tomorrow } = currentScheduleKeys();
    if (station.draftForDate !== tomorrow || !validPrices(station.draftPublicTomorrow)) throw new Error("No valid optimization draft is available for tomorrow.");
    const patch = {
      publicTomorrow: [...station.draftPublicTomorrow], publicTomorrowDate: tomorrow, publicTomorrowAvailable: true,
      publicTomorrowPublishedAt: new Date().toISOString(), lastPriceUpdate: new Date().toISOString(),
    };
    setStation((current) => ({ ...current, ...patch }));
    return savePatch(patch);
  }

  function updateCharger(id, patch) {
    const chargers = station.chargers.map((charger) => charger.id === id ? { ...charger, ...patch } : charger);
    setStation((current) => ({ ...current, chargers }));
    return savePatch({ chargers });
  }

  async function resetStationData() {
    const remote = await databaseApi.resetStation();
    setStation(normalizeRemote(remote, createDefaultState()));
  }

  const value = useMemo(() => ({ ...station, updatePriceSchedule, updateFixedArrivalPriceSchedule, updateFlexibleBookingPrice, updateBookingPrices, setTomorrowOptimizationDraft, publishTomorrowDraft, syncPublishedPrices, updateCharger, resetStationData }), [station]);
  return <StationDataContext.Provider value={value}>{children}</StationDataContext.Provider>;
}

export function useStationData() {
  const value = useContext(StationDataContext);
  if (!value) throw new Error("useStationData must be used inside StationDataProvider");
  return value;
}
