import { databaseApi } from "./databaseApi";

const MIGRATION_KEY = "solarcharge_mongodb_migration_done_v1";
const ACCOUNTS_KEY = "solarcharge_accounts_v1";
const BOOKINGS_KEY = "solarcharge_bookings_v1";
const STATION_KEY = "solarcharge_station_data_v1";
const REVENUE_KEY = "solarcharge_revenue_v1";

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export async function migratePreviousBrowserDataToMongo() {
  if (localStorage.getItem(MIGRATION_KEY) === "1") return null;

  const payload = {
    accounts: readJson(ACCOUNTS_KEY, []),
    bookings: readJson(BOOKINGS_KEY, []),
    station: readJson(STATION_KEY, null),
    revenue: readJson(REVENUE_KEY, null),
  };

  try {
    const result = await databaseApi.migrateLegacy(payload);
    localStorage.setItem(MIGRATION_KEY, "1");
    return result;
  } catch (error) {
    // Do not mark as completed. The migration will retry next time the backend/database is available.
    console.warn("MongoDB migration deferred:", error.message);
    return null;
  }
}
