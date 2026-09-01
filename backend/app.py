from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import (
    apply_optimizer_notifications,
    create_booking as db_create_booking,
    create_customer as db_create_customer,
    db_status,
    get_customer as db_get_customer,
    get_optimization_result as db_get_optimization_result,
    get_revenue_state,
    get_station_state,
    latest_optimization_result as db_latest_optimization_result,
    list_bookings as db_list_bookings,
    list_customers as db_list_customers,
    login_customer as db_login_customer,
    migrate_legacy,
    optimization_history as db_optimization_history,
    patch_booking as db_patch_booking,
    patch_station,
    reset_station,
    update_customer as db_update_customer,
    upsert_optimization_result,
    store_optimization_file,
    fetch_optimization_file,
    list_optimization_files,
)

BASE_DIR = Path(__file__).resolve().parent
OPTIMIZER_DIR = BASE_DIR / "optimizer"
INPUT_DIR = OPTIMIZER_DIR / "inputs"
RESULTS_DIR = OPTIMIZER_DIR / "results"
CODE_FILE = OPTIMIZER_DIR / "code" / "Test.py"
RUNS_DIR = BASE_DIR / "runs"
DATA_DIR = BASE_DIR / "data"
PRICE_STATE_FILE = DATA_DIR / "price_state.json"
DEMO_BASE_PRIMARY_ELASTIC = BASE_DIR / "demo" / "base" / "Primary_Elastic_EV_Users_base.xlsx"
GENERATED_INPUTS_DIR = DATA_DIR / "generated_inputs"
COLOMBO = ZoneInfo("Asia/Colombo")

for directory in (INPUT_DIR, RESULTS_DIR, RUNS_DIR, DATA_DIR, GENERATED_INPUTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SolarCharge Optimizer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
ACTIVE_PROCESSES: dict[str, subprocess.Popen] = {}


def now_colombo() -> datetime:
    return datetime.now(COLOMBO)


def date_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def tomorrow_key() -> str:
    return date_key(now_colombo() + timedelta(days=1))


def _load_price_state() -> dict[str, Any]:
    if PRICE_STATE_FILE.exists():
        try:
            state = json.loads(PRICE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}
    return _roll_price_state(state)


def _save_price_state(state: dict[str, Any]) -> None:
    PRICE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _valid_price_array(values: Any) -> bool:
    return isinstance(values, list) and len(values) == 96 and all(
        isinstance(v, (int, float)) and np.isfinite(float(v)) for v in values
    )


def _roll_price_state(state: dict[str, Any]) -> dict[str, Any]:
    today = date_key(now_colombo())
    tomorrow = date_key(now_colombo() + timedelta(days=1))
    changed = False

    if state.get("todayDate") != today:
        if state.get("tomorrowDate") == today and _valid_price_array(state.get("tomorrowPrices")):
            state["todayPrices"] = list(map(float, state["tomorrowPrices"]))
            state["todayDate"] = today
            state["todaySource"] = "previously published tomorrow forecast"
            changed = True
        else:
            state["todayDate"] = today

    if state.get("tomorrowDate") != tomorrow:
        state["tomorrowDate"] = tomorrow
        state["tomorrowPrices"] = None
        state["tomorrowPublishedAt"] = None
        state["tomorrowSourceJobId"] = None
        changed = True

    if changed:
        _save_price_state(state)
    return state


class PublishPricesRequest(BaseModel):
    jobId: str


class BookingInputBuildRequest(BaseModel):
    targetDate: str
    bookings: list[dict[str, Any]]


class CustomerSignupRequest(BaseModel):
    name: str
    phone: str = ""
    email: str
    password: str
    vehicle: dict[str, Any]


class CustomerLoginRequest(BaseModel):
    email: str
    password: str


class CustomerUpdateRequest(BaseModel):
    name: str
    phone: str = ""
    vehicle: dict[str, Any]


class LegacyMigrationRequest(BaseModel):
    accounts: list[dict[str, Any]] = []
    bookings: list[dict[str, Any]] = []
    station: dict[str, Any] | None = None
    revenue: dict[str, Any] | None = None


class OptimizerNotificationRequest(BaseModel):
    jobId: str
    elasticNotifications: list[dict[str, Any]] = []


@app.get("/api/database/status")
def database_status() -> dict[str, Any]:
    return db_status()


@app.post("/api/migration/import-local")
def import_legacy_local_data(request: LegacyMigrationRequest) -> dict[str, Any]:
    try:
        result = migrate_legacy(request.model_dump())
        return {"status":"ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to import previous browser data into MongoDB: {exc}") from exc


@app.get("/api/station")
def station_state() -> dict[str, Any]:
    try:
        return get_station_state()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB is unavailable: {exc}") from exc


@app.patch("/api/station")
def update_station(patch: dict[str, Any]) -> dict[str, Any]:
    try:
        if "publicToday" in patch and not _valid_price_array(patch["publicToday"]):
            raise ValueError("publicToday must contain exactly 96 numeric values.")
        if "publicTomorrow" in patch and not _valid_price_array(patch["publicTomorrow"]):
            raise ValueError("publicTomorrow must contain exactly 96 numeric values.")
        if "fixedArrivalTomorrowPrices" in patch and not _valid_price_array(patch["fixedArrivalTomorrowPrices"]):
            raise ValueError("fixedArrivalTomorrowPrices must contain exactly 96 numeric values.")
        return patch_station(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to update MongoDB station data: {exc}") from exc


@app.post("/api/station/reset")
def reset_station_endpoint() -> dict[str, Any]:
    try:
        return reset_station()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to reset MongoDB station data: {exc}") from exc


@app.get("/api/customers")
def customers() -> list[dict[str, Any]]:
    try:
        return db_list_customers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to read customers from MongoDB: {exc}") from exc


@app.get("/api/customers/{customer_id}")
def customer(customer_id: str) -> dict[str, Any]:
    try:
        item = db_get_customer(customer_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to read customer from MongoDB: {exc}") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Customer account was not found.")
    return item


@app.post("/api/customers/signup")
def customer_signup(request: CustomerSignupRequest) -> dict[str, Any]:
    try:
        return db_create_customer(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to save customer to MongoDB: {exc}") from exc


@app.post("/api/customers/login")
def customer_login(request: CustomerLoginRequest) -> dict[str, Any]:
    try:
        item = db_login_customer(request.email, request.password)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to access MongoDB: {exc}") from exc
    if not item:
        raise HTTPException(status_code=401, detail="Incorrect email address or password.")
    return item


@app.put("/api/customers/{customer_id}")
def customer_update(customer_id: str, request: CustomerUpdateRequest) -> dict[str, Any]:
    try:
        item = db_update_customer(customer_id, request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to update customer in MongoDB: {exc}") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Customer account was not found.")
    return item


@app.get("/api/bookings")
def bookings(user_id: str | None = None, date: str | None = None) -> list[dict[str, Any]]:
    try:
        return db_list_bookings(user_id=user_id, date=date)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to read bookings from MongoDB: {exc}") from exc


@app.post("/api/bookings")
def booking_create(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return db_create_booking(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to save booking to MongoDB: {exc}") from exc


@app.patch("/api/bookings/{booking_id}")
def booking_patch(booking_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        item = db_patch_booking(booking_id, patch)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to update booking in MongoDB: {exc}") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Booking was not found.")
    return item


@app.get("/api/admin/revenue")
def revenue_state() -> dict[str, Any]:
    try:
        return get_revenue_state()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to read revenue data from MongoDB: {exc}") from exc


@app.post("/api/notifications/apply-optimizer")
def notifications_apply_optimizer(request: OptimizerNotificationRequest) -> dict[str, Any]:
    result = {"jobId": request.jobId, "elasticNotifications": request.elasticNotifications}
    try:
        return apply_optimizer_notifications(result)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to save optimizer notifications in MongoDB: {exc}") from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    database = db_status()
    return {
        "status": "ok" if database.get("connected") else "degraded",
        "optimizerCodePresent": CODE_FILE.exists(),
        "database": database,
        "stationTimeZone": "Asia/Colombo",
        "stationTime": now_colombo().isoformat(),
    }


@app.get("/api/prices")
def get_prices() -> dict[str, Any]:
    try:
        state = get_station_state()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB is unavailable: {exc}") from exc
    return {
        "todayDate": state.get("publicTodayDate", date_key(now_colombo())),
        "todayPrices": state.get("publicToday"),
        "todaySource": state.get("todaySource"),
        "tomorrowDate": state.get("publicTomorrowDate", tomorrow_key()),
        "tomorrowPrices": state.get("publicTomorrow") if state.get("publicTomorrowAvailable") else None,
        "tomorrowPublishedAt": state.get("publicTomorrowPublishedAt"),
        "tomorrowSourceJobId": state.get("tomorrowSourceJobId"),
    }


def _read_text_profile(data: bytes, name: str) -> np.ndarray:
    try:
        values = np.loadtxt(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"{name} could not be read as a numeric text profile: {exc}") from exc
    values = np.asarray(values, dtype=float).flatten()
    if len(values) < 96:
        raise ValueError(f"{name} must contain at least 96 numeric values; found {len(values)}.")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} contains non-finite values.")
    return values


def _validate_grid_price(data: bytes) -> None:
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"grid_price_input_used.csv could not be read: {exc}") from exc
    if len(df) != 96:
        raise ValueError(f"grid_price_input_used.csv must contain exactly 96 rows; found {len(df)}.")
    cols = {str(c).strip().lower() for c in df.columns}
    required_groups = [
        {"interval_end_time_from_file", "time", "interval_end_time", "interval_start_time"},
        {"grid_export_price_lkr_kwh", "grid_export_price", "grid_export_nondispatchable_price_lkr_kwh", "grid_export_nondispatchable_price"},
        {"grid_export_dispatchable_price_lkr_kwh", "grid_export_dispatchable_price", "dispatchable_export_price_lkr_kwh", "dispatchable_export_price"},
        {"grid_import_price_lkr_kwh", "grid_import_price", "grid_buy_price_lkr_kwh", "grid_buy_price"},
    ]
    if any(not (cols & group) for group in required_groups):
        raise ValueError("grid_price_input_used.csv is missing one or more required time/import/export price columns.")


def _validate_primary_elastic(data: bytes) -> None:
    try:
        df = pd.read_excel(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Primary_Elastic_EV_Users.xlsx could not be read: {exc}") from exc
    required = {
        "Overall_EV_No", "Controller_EV_ID", "EV_Notation", "User_Type",
        "Battery_Capacity_kWh", "Initial_SOC_pct", "Target_SOC_pct",
        "Requested_Battery_Energy_kWh", "EV_Max_Charging_Power_kW",
        "Controller_Power_Limit_kW", "Elastic_Window_Start_Time", "Elastic_Window_End_Time",
    }
    missing = sorted(required - set(map(str, df.columns)))
    if missing:
        raise ValueError("Primary_Elastic_EV_Users.xlsx is missing required columns: " + ", ".join(missing))
    if len(df) == 0:
        raise ValueError("Primary_Elastic_EV_Users.xlsx contains no EV users.")




def _minutes_from_hhmm(value: Any) -> int:
    text = str(value or "").strip()
    try:
        hour, minute = text.split(":")[:2]
        total = int(hour) * 60 + int(minute)
    except Exception as exc:
        raise ValueError(f"Invalid booking time '{text}'. Expected HH:MM.") from exc
    if total < 0 or total >= 1440:
        raise ValueError(f"Booking time '{text}' is outside the valid day.")
    return total


def _hhmm(total_minutes: int) -> str:
    total = max(0, min(1440, int(total_minutes)))
    if total == 1440:
        return "24:00"
    return f"{total // 60:02d}:{total % 60:02d}"


def _web_booking_row(base_columns: list[str], booking: dict[str, Any], overall_no: int, type_no: int) -> dict[str, Any]:
    booking_type = str(booking.get("bookingType") or "").lower()
    if booking_type not in {"fixed", "flexible"}:
        raise ValueError("Website bookingType must be either fixed or flexible.")

    booking_id = str(booking.get("id") or "").strip()
    if not booking_id:
        raise ValueError("A website booking is missing its booking id.")

    start_text = booking.get("arrivalTime") if booking_type == "fixed" else booking.get("windowStart")
    start_minute = _minutes_from_hhmm(start_text)
    duration_min = max(1, int(round(float(booking.get("durationMinutes") or 1))))
    end_minute = min(1440, start_minute + duration_min)
    arrival_slot = min(96, start_minute // 15 + 1)
    completion_slot = max(arrival_slot, min(96, int(np.ceil(end_minute / 15.0))))

    battery = float(booking.get("batteryCapacityKwh") or 0)
    initial_soc = float(booking.get("initialSoc") or 0)
    target_soc = float(booking.get("targetSoc") or 0)
    requested_energy = float(booking.get("energyRequiredKwh") or (battery * (target_soc - initial_soc) / 100.0))
    max_power = max(1.0, float(booking.get("chargingRateKw") or booking.get("effectiveChargingRateKw") or 350.0))
    controller_limit = min(450.0, max_power)
    efficiency = 92.5
    grid_energy = requested_energy / (efficiency / 100.0)
    user_type = "primary" if booking_type == "fixed" else "elastic"
    notation = f"WEB-{'P' if booking_type == 'fixed' else 'E'}-{type_no:03d}"
    assigned_charger = int(booking.get("chargerId") or 1)

    row = {column: np.nan for column in base_columns}
    row.update({
        "Source_Cohort": "Website booking",
        "Overall_EV_No": overall_no,
        "Controller_EV_ID": f"WEB-{booking_id}",
        "EV_Notation": notation,
        "User_Type": user_type,
        "User_Type_Description": "Primary booked users" if user_type == "primary" else "Secondary elastic users",
        "Type_EV_No": type_no,
        "Queue_Priority": 0 if user_type == "primary" else 1,
        "Arrival_Day_Offset": 0,
        "Arrival_Time": _hhmm(start_minute),
        "Arrival_Minute": start_minute,
        "Original_Arrival_15min_Slot": arrival_slot,
        "Battery_Capacity_kWh": battery,
        "Initial_SOC_pct": initial_soc,
        "Target_SOC_pct": target_soc,
        "Requested_Battery_Energy_kWh": requested_energy,
        "Controller_Required_Energy_at_00_kWh": requested_energy,
        "Nominal_Grid_Energy_at_92_5pct": grid_energy,
        "EV_Max_Charging_Power_kW": max_power,
        "Controller_Power_Limit_kW": controller_limit,
        "Session_Efficiency_pct": efficiency,
        "Active_Chargers_Before_Arrival": 0,
        "Queue_Length_Before_Arrival": 0,
        "Admission_Status": "Website booking",
        "Assigned_Charger": assigned_charger,
        "Charging_Start_Day_Offset": 0,
        "Charging_Start_Time": _hhmm(start_minute),
        "Charging_Start_15min_Slot": arrival_slot,
        "Waiting_Time_min": 0,
        "Completion_Status": "Forecast booking",
        "Completion_Day_Offset": 0,
        "Completion_Time": _hhmm(end_minute),
        "Completion_15min_Slot": completion_slot,
        "Service_Duration_min": duration_min,
        "Total_Time_at_Station_min": duration_min,
        "Actual_Grid_Energy_kWh": grid_energy,
        "Actual_Battery_Energy_kWh": requested_energy,
        "Delivered_Energy_Ratio_pct": 100.0,
        "Average_Charging_Power_kW": min(controller_limit, grid_energy / max(duration_min / 60.0, 1e-6)),
        "Peak_Charging_Power_kW": controller_limit,
        "Final_SOC_pct": target_soc,
        "Crosses_Midnight": False,
        "Controller_Action_Class": "Fixed priority service" if user_type == "primary" else "Time-shift candidate",
        "Controller_Adjusted_Arrival_Slot": arrival_slot,
        "Waiting_QoS_Met": "Yes",
        "Completion_QoS_Met": "Yes",
        "Overall_QoS_Met": "Yes",
        "Elastic_Window_Start_Time": booking.get("windowStart") if user_type == "elastic" else np.nan,
        # Test.py constrains the complete elastic session inside this window.
        # The website asks for an arrival-time range, so extend the optimizer
        # window end by the charging duration to preserve the customer's latest
        # acceptable arrival time.
        "Elastic_Window_End_Time": _hhmm(min(1440, _minutes_from_hhmm(booking.get("windowEnd")) + duration_min)) if user_type == "elastic" else np.nan,
    })
    return row


def _build_primary_elastic_from_web_bookings(target_date: str, bookings: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    if target_date != tomorrow_key():
        raise ValueError(f"Website optimizer input can only be generated for tomorrow ({tomorrow_key()}).")
    if not DEMO_BASE_PRIMARY_ELASTIC.exists():
        raise FileNotFoundError("Fixed base Primary_Elastic_EV_Users workbook is missing from backend/demo/base.")

    base = pd.read_excel(DEMO_BASE_PRIMARY_ELASTIC)
    base_columns = list(base.columns)
    active = [
        booking for booking in bookings
        if str(booking.get("date")) == target_date
        and str(booking.get("status") or "").lower() in {"pending", "reserved", "scheduled"}
        and str(booking.get("id") or "").strip()
        and str(booking.get("userId") or "").strip()
    ]

    max_overall = int(pd.to_numeric(base.get("Overall_EV_No"), errors="coerce").max() or 0)
    type_counts = {
        "primary": int((base["User_Type"].astype(str).str.lower() == "primary").sum()),
        "elastic": int((base["User_Type"].astype(str).str.lower() == "elastic").sum()),
    }
    rows = []
    mapping = []
    for index, booking in enumerate(active, start=1):
        kind = "primary" if str(booking.get("bookingType")).lower() == "fixed" else "elastic"
        type_counts[kind] += 1
        row = _web_booking_row(base_columns, booking, max_overall + index, type_counts[kind])
        rows.append(row)
        mapping.append({
            "bookingId": booking.get("id"),
            "customerId": booking.get("userId"),
            "customerEmail": booking.get("userEmail"),
            "bookingType": booking.get("bookingType"),
            "controllerEvId": row["Controller_EV_ID"],
        })

    combined = pd.concat([base, pd.DataFrame(rows, columns=base_columns)], ignore_index=True) if rows else base.copy()
    for extra in ["Web_Booking_ID", "Web_Customer_ID", "Web_Customer_Email", "Web_Booking_Date"]:
        if extra not in combined.columns:
            combined[extra] = pd.Series([None] * len(combined), dtype="object")
    for i, info in enumerate(mapping, start=len(base)):
        combined.loc[i, "Web_Booking_ID"] = info["bookingId"]
        combined.loc[i, "Web_Customer_ID"] = info["customerId"]
        combined.loc[i, "Web_Customer_Email"] = info["customerEmail"]
        combined.loc[i, "Web_Booking_Date"] = target_date

    output = GENERATED_INPUTS_DIR / "Primary_Elastic_EV_Users.xlsx"
    combined.to_excel(output, index=False)
    map_path = GENERATED_INPUTS_DIR / "Primary_Elastic_EV_Users_web_mapping.json"
    map_path.write_text(json.dumps({"targetDate": target_date, "mapping": mapping}, indent=2), encoding="utf-8")
    summary = {
        "targetDate": target_date,
        "baseRows": len(base),
        "appendedBookings": len(rows),
        "fixedBookings": sum(1 for item in active if str(item.get("bookingType")).lower() == "fixed"),
        "flexibleBookings": sum(1 for item in active if str(item.get("bookingType")).lower() == "flexible"),
        "totalRows": len(combined),
        "fileName": output.name,
        "downloadUrl": "/api/demo/primary-elastic/download",
    }
    return output, summary


def _set_job(job_id: str, **updates: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def _get_summary_map(path: Path) -> dict[str, float | str]:
    df = pd.read_csv(path)
    result: dict[str, float | str] = {}
    for _, row in df.iterrows():
        key = str(row["Parameter"])
        raw = row["Value"]
        try:
            result[key] = float(raw)
        except Exception:
            result[key] = str(raw)
    return result


def _num(summary: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(summary.get(key, default))
    except Exception:
        return default


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    safe = df[columns].copy()
    safe = safe.replace([np.inf, -np.inf], np.nan).fillna(0)
    return safe.to_dict(orient="records")


def parse_optimizer_results(results_dir: Path, job_id: str, target_date: str) -> dict[str, Any]:
    slot_path = results_dir / "slot_summary_results.csv"
    summary_path = results_dir / "final_milp_summary.csv"
    if not slot_path.exists():
        raise FileNotFoundError("Optimizer finished but results/slot_summary_results.csv was not produced.")
    if not summary_path.exists():
        raise FileNotFoundError("Optimizer finished but results/final_milp_summary.csv was not produced.")

    slots = pd.read_csv(slot_path)
    if len(slots) != 96:
        raise ValueError(f"slot_summary_results.csv must contain 96 rows; found {len(slots)}.")
    if "secondary_tariff_after_LKR_kWh" not in slots.columns:
        raise ValueError("slot_summary_results.csv does not contain secondary_tariff_after_LKR_kWh.")

    summary = _get_summary_map(summary_path)
    price_signal = [float(v) for v in slots["secondary_tariff_after_LKR_kWh"].tolist()]

    notification_path = results_dir / "elastic_user_notifications.csv"
    elastic_notifications: list[dict[str, Any]] = []
    if notification_path.exists():
        notification_df = pd.read_csv(notification_path).replace([np.inf, -np.inf], np.nan).fillna("")
        elastic_notifications = notification_df.to_dict(orient="records")

    # Exact-minute charger occupancy is produced by the optimizer as
    # charger_minute_results.csv. The file contains rows only for occupied
    # charger/minute combinations, so missing charger rows at a selected minute
    # mean that those chargers are available. Keep a compact minute-keyed map in
    # the parsed result so both the Key Results and Detailed Results pages can
    # inspect charger status without loading the full CSV in the browser.
    charger_minute_path = results_dir / "charger_minute_results.csv"
    charger_excel_path = results_dir / "whole_vehicle_shift_milp_results.xlsx"
    charger_minute_source = "charger_minute_results.csv"
    charger_occupancy: dict[str, list[int]] = {}
    charger_occupancy_available = False

    charger_minute_df: pd.DataFrame | None = None
    if charger_minute_path.exists():
        try:
            charger_minute_df = pd.read_csv(charger_minute_path)
            charger_occupancy_available = True
        except pd.errors.EmptyDataError:
            charger_minute_df = pd.DataFrame()
            charger_occupancy_available = True
    elif charger_excel_path.exists():
        try:
            charger_minute_df = pd.read_excel(charger_excel_path, sheet_name="Charger_Minute")
            charger_minute_source = "whole_vehicle_shift_milp_results.xlsx / Charger_Minute"
            charger_occupancy_available = True
        except (ValueError, ImportError):
            charger_minute_df = None

    if charger_minute_df is not None and not charger_minute_df.empty:
        required_charger_columns = {"minute", "charger_pile_id", "active_user_count"}
        if required_charger_columns.issubset(set(map(str, charger_minute_df.columns))):
            safe_charger_df = charger_minute_df.replace([np.inf, -np.inf], np.nan).fillna(0)
            for _, row in safe_charger_df.iterrows():
                try:
                    minute = int(float(row.get("minute", -1)))
                    charger_id = int(float(row.get("charger_pile_id", 0)))
                    active_count = int(float(row.get("active_user_count", 0)))
                except (TypeError, ValueError):
                    continue

                if not (0 <= minute < 1440 and 1 <= charger_id <= 10 and active_count > 0):
                    continue

                minute_key = str(minute)
                charger_occupancy.setdefault(minute_key, []).append(charger_id)

            for minute_key in charger_occupancy:
                charger_occupancy[minute_key] = sorted(set(charger_occupancy[minute_key]))
        else:
            charger_occupancy_available = False

    primary_revenue = _num(summary, "Primary Revenue After")
    secondary_revenue = _num(summary, "Secondary Revenue After")
    export_revenue = _num(summary, "Total Grid Export Revenue After")
    total_revenue = primary_revenue + secondary_revenue + export_revenue

    key_metrics = {
        "forecastTotalRevenueLKR": total_revenue,
        "forecastEVChargingRevenueLKR": primary_revenue + secondary_revenue,
        "forecastGridExportRevenueLKR": export_revenue,
        "forecastTotalProfitLKR": _num(summary, "Daily Profit After"),
        "forecastGridImportEnergyKWh": _num(summary, "Grid Import Energy After"),
        "forecastGridExportEnergyKWh": _num(summary, "Total Grid Export Energy"),
        "forecastPeakGridImportKW": _num(summary, "Max Grid Import After"),
        "forecastTotalEVEnergyKWh": _num(summary, "Total EV Energy After"),
        "forecastPVEnergyKWh": _num(summary, "PV Energy"),
        "forecastPVToEVEnergyKWh": _num(summary, "PV to EV Energy"),
        "forecastPVToBESSEnergyKWh": _num(summary, "PV to BESS Energy"),
        "forecastPVToGridEnergyKWh": _num(summary, "PV to Grid Energy"),
        "forecastBESSToGridEnergyKWh": _num(summary, "BESS to Grid Energy"),
        "priceAverageLKRkWh": float(np.mean(price_signal)),
        "priceMinimumLKRkWh": float(np.min(price_signal)),
        "priceMaximumLKRkWh": float(np.max(price_signal)),
        "forecastEVUsers": int(round(_num(summary, "Number of EV Users"))),
        "forecastElasticUsers": int(round(_num(summary, "Number of Elastic Users"))),
    }

    charts = {
        "priceSignal": _records(slots, ["time", "secondary_tariff_after_LKR_kWh"]),
        "evLoad": _records(slots, ["time", "primary_load_after_kW", "dynamic_secondary_load_after_kW", "elastic_load_after_kW", "total_ev_load_after_kW"]),
        "gridFlow": _records(slots, ["time", "grid_import_after_kW", "grid_export_total_kW"]),
        "pvAllocation": _records(slots, ["time", "pv_generation_kW", "pv_to_ev_kW", "pv_to_bess_kW", "pv_to_grid_kW", "pv_curtailed_kW"]),
        "bessPower": _records(slots, ["time", "bess_charge_kW", "bess_to_ev_kW", "bess_to_grid_kW", "bess_discharge_total_kW", "bess_net_kW_positive_discharge"]),
        "soc": _records(slots, ["time", "soc_after_kWh"]),
        "activeUsers": _records(slots, ["time", "charging_primary_count", "charging_opportunistic_count", "charging_elastic_count", "charging_long_trip_count", "max_exact_active_user_count_after"]),
        "slotProfit": _records(slots, ["time", "slot_profit_LKR", "elastic_revenue_LKR", "dynamic_secondary_revenue_LKR"]),
    }

    # Compact after-optimization operational details for the selected 15-minute slot.
    # All power values in slot_summary_results.csv are converted to slot energy using
    # E = P * 0.25 h before they are sent to the web interface.
    slot_operation: list[dict[str, Any]] = []
    required_slot_columns = {
        "slot",
        "time",
        "pv_generation_kW",
        "total_ev_load_after_kW",
        "grid_import_after_kW",
        "grid_export_total_kW",
        "export_mode",
        "bess_charge_kW",
        "bess_discharge_total_kW",
    }
    slot_operation_available = required_slot_columns.issubset(set(map(str, slots.columns)))

    if slot_operation_available:
        for slot_index, (_, row) in enumerate(slots.iterrows()):
            def slot_num(column: str) -> float:
                value = row.get(column, 0.0)
                if pd.isna(value):
                    return 0.0
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0

            raw_slot = row.get("slot", slot_index)
            try:
                slot_number: int | float = int(float(raw_slot))
            except (TypeError, ValueError):
                slot_number = slot_index

            export_mode = row.get("export_mode", "No export")
            if pd.isna(export_mode) or not str(export_mode).strip():
                export_mode = "No export"

            slot_operation.append({
                "slotIndex": slot_index,
                "slotNumber": slot_number,
                "time": str(row.get("time", "")),
                "pvGenerationEnergyKWh": slot_num("pv_generation_kW") * 0.25,
                "evDemandEnergyKWh": slot_num("total_ev_load_after_kW") * 0.25,
                "gridImportEnergyKWh": slot_num("grid_import_after_kW") * 0.25,
                "gridExportEnergyKWh": slot_num("grid_export_total_kW") * 0.25,
                "exportMode": str(export_mode),
                "bessChargeEnergyKWh": slot_num("bess_charge_kW") * 0.25,
                "bessDischargeEnergyKWh": slot_num("bess_discharge_total_kW") * 0.25,
            })

    return {
        "jobId": job_id,
        "targetDate": target_date,
        "generatedAt": now_colombo().isoformat(),
        "forecastLabel": "Forecast results for tomorrow",
        "priceSignal": price_signal,
        "metrics": key_metrics,
        "charts": charts,
        "slotOperation": slot_operation,
        "slotOperationAvailable": slot_operation_available,
        "chargerOccupancy": charger_occupancy,
        "chargerOccupancyAvailable": charger_occupancy_available,
        "chargerOccupancySource": charger_minute_source,
        "elasticNotifications": elastic_notifications,
        "websiteElasticNotificationCount": sum(1 for item in elastic_notifications if str(item.get("user_id", "")).startswith("WEB-")),
        "resultFiles": [
            "slot_summary_results.csv",
            "final_milp_summary.csv",
            "elastic_user_notifications.csv",
            "optimized_ev_profile_pu.txt",
            "optimized_bess_profile_pu.txt",
        ],
    }


def _upgrade_local_result_with_charger_occupancy(parsed: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Backfill selected-time operational details for older local optimizer runs."""
    if "chargerOccupancy" in parsed and "slotOperation" in parsed:
        return parsed

    results_dir = RUNS_DIR / job_id / "results"
    if not results_dir.exists():
        return parsed

    try:
        upgraded = parse_optimizer_results(
            results_dir,
            job_id,
            str(parsed.get("targetDate") or tomorrow_key()),
        )
        if parsed.get("generatedAt"):
            upgraded["generatedAt"] = parsed["generatedAt"]

        parsed_file = RUNS_DIR / job_id / "parsed_results.json"
        parsed_file.write_text(json.dumps(upgraded, indent=2), encoding="utf-8")
        try:
            upsert_optimization_result(upgraded)
        except Exception:
            pass
        return upgraded
    except Exception:
        return parsed


def _clear_results() -> None:
    if RESULTS_DIR.exists():
        for child in RESULTS_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    (RESULTS_DIR / "graphs").mkdir(parents=True, exist_ok=True)


def _job_is_cancelled(job_id: str) -> bool:
    with JOBS_LOCK:
        return JOBS.get(job_id, {}).get("status") == "cancelled"


def _terminate_optimizer_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    # The project is normally run on Windows. taskkill /T also stops any child
    # processes started by the optimizer. The fallback keeps this backend
    # portable for Linux/macOS development.
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return
        except Exception:
            pass

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _run_optimizer_job(job_id: str, target_date: str, run_dir: Path) -> None:
    with RUN_LOCK:
        process: subprocess.Popen | None = None
        try:
            if _job_is_cancelled(job_id):
                return

            _set_job(job_id, status="running", phase="Preparing optimizer workspace", progress=10)
            _clear_results()

            if _job_is_cancelled(job_id):
                return

            _set_job(job_id, phase="Running MILP optimization with Gurobi", progress=25)
            process = subprocess.Popen(
                [sys.executable, str(CODE_FILE)],
                cwd=str(OPTIMIZER_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            with JOBS_LOCK:
                ACTIVE_PROCESSES[job_id] = process
                already_cancelled = JOBS.get(job_id, {}).get("status") == "cancelled"

            if already_cancelled:
                _terminate_optimizer_process(process)

            try:
                stdout, stderr = process.communicate(timeout=33000)
            except subprocess.TimeoutExpired:
                _terminate_optimizer_process(process)
                stdout, stderr = process.communicate()
                (run_dir / "optimizer_stdout.log").write_text(stdout or "", encoding="utf-8")
                (run_dir / "optimizer_stderr.log").write_text(stderr or "", encoding="utf-8")
                if _job_is_cancelled(job_id):
                    return
                raise
            finally:
                with JOBS_LOCK:
                    ACTIVE_PROCESSES.pop(job_id, None)

            (run_dir / "optimizer_stdout.log").write_text(stdout or "", encoding="utf-8")
            (run_dir / "optimizer_stderr.log").write_text(stderr or "", encoding="utf-8")

            if _job_is_cancelled(job_id):
                return

            if process.returncode != 0:
                error_tail = "\n".join((stderr or stdout or "Optimizer failed").splitlines()[-30:])
                raise RuntimeError(error_tail)

            _set_job(job_id, phase="Reading tomorrow forecast results", progress=85)
            if _job_is_cancelled(job_id):
                return

            run_results = run_dir / "results"
            shutil.copytree(RESULTS_DIR, run_results, dirs_exist_ok=True)
            parsed = parse_optimizer_results(run_results, job_id, target_date)

            if _job_is_cancelled(job_id):
                return

            (run_dir / "parsed_results.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            try:
                upsert_optimization_result(parsed)
                for shared_name in (
                    "slot_summary_results.csv", "final_milp_summary.csv", "elastic_user_notifications.csv",
                    "optimized_ev_profile_pu.txt", "optimized_bess_profile_pu.txt",
                ):
                    shared_path = run_results / shared_name
                    if shared_path.exists():
                        store_optimization_file(job_id, shared_name, shared_path.read_bytes())
                for log_name in ("optimizer_stdout.log", "optimizer_stderr.log"):
                    log_path = run_dir / log_name
                    if log_path.exists():
                        store_optimization_file(job_id, log_name, log_path.read_bytes())
            except Exception as db_exc:
                (run_dir / "database_warning.log").write_text(str(db_exc), encoding="utf-8")

            if _job_is_cancelled(job_id):
                try:
                    (run_dir / "parsed_results.json").unlink(missing_ok=True)
                except Exception:
                    pass
                return

            _set_job(job_id, status="success", phase="Completed", progress=100, result=parsed, error=None)
        except subprocess.TimeoutExpired:
            if not _job_is_cancelled(job_id):
                message = "Optimizer exceeded the configured execution timeout (33,000 seconds)."
                _set_job(job_id, status="error", phase="Failed", progress=100, error=message)
        except Exception as exc:
            if _job_is_cancelled(job_id):
                return
            message = str(exc).strip() or exc.__class__.__name__
            (run_dir / "backend_error.log").write_text(traceback.format_exc(), encoding="utf-8")
            _set_job(job_id, status="error", phase="Failed", progress=100, error=message)
        finally:
            with JOBS_LOCK:
                ACTIVE_PROCESSES.pop(job_id, None)


@app.post("/api/demo/primary-elastic/generate")
def generate_primary_elastic(request: BookingInputBuildRequest) -> dict[str, Any]:
    try:
        _, summary = _build_primary_elastic_from_web_bookings(request.targetDate, request.bookings)
        return summary
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/demo/primary-elastic/download")
def download_generated_primary_elastic():
    path = GENERATED_INPUTS_DIR / "Primary_Elastic_EV_Users.xlsx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generate the updated Primary_Elastic_EV_Users.xlsx file first.")
    return FileResponse(path, filename="Primary_Elastic_EV_Users.xlsx")


@app.get("/api/demo/primary-elastic/base-info")
def primary_elastic_base_info() -> dict[str, Any]:
    if not DEMO_BASE_PRIMARY_ELASTIC.exists():
        raise HTTPException(status_code=404, detail="Fixed base Primary_Elastic_EV_Users workbook is missing.")
    base = pd.read_excel(DEMO_BASE_PRIMARY_ELASTIC)
    user_types = base.get("User_Type", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    primary_users = int((user_types == "primary").sum())
    elastic_users = int((user_types == "elastic").sum())
    return {
        "baseRows": len(base),
        "primaryUsers": primary_users,
        "elasticUsers": elastic_users,
        "fileName": "Primary_Elastic_EV_Users_base.xlsx",
        "note": "The fixed base is never modified. Each generated file is rebuilt from this base plus current website bookings for tomorrow.",
    }


@app.post("/api/optimizer/run")
async def start_optimizer(
    pv: UploadFile = File(...),
    primary_elastic: UploadFile = File(...),
    grid_price: UploadFile = File(...),
) -> dict[str, Any]:
    with JOBS_LOCK:
        if any(job.get("status") in {"queued", "running"} for job in JOBS.values()):
            raise HTTPException(status_code=409, detail="An optimizer run is already in progress.")

    payloads = {
        "pv.txt": await pv.read(),
        "Primary_Elastic_EV_Users.xlsx": await primary_elastic.read(),
        "grid_price_input_used.csv": await grid_price.read(),
    }

    try:
        _read_text_profile(payloads["pv.txt"], "pv.txt")
        _validate_primary_elastic(payloads["Primary_Elastic_EV_Users.xlsx"])
        _validate_grid_price(payloads["grid_price_input_used.csv"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    target_date = tomorrow_key()
    run_dir = RUNS_DIR / job_id
    upload_dir = run_dir / "uploaded_inputs"
    upload_dir.mkdir(parents=True, exist_ok=True)

    for filename, data in payloads.items():
        (upload_dir / filename).write_bytes(data)
        (INPUT_DIR / filename).write_bytes(data)

    manifest = {
        "jobId": job_id,
        "targetDate": target_date,
        "uploadedAt": now_colombo().isoformat(),
        "files": {name: len(data) for name, data in payloads.items()},
        "note": "Typical_Day_Individual_EV_Controller.xlsx is bundled as fixed internal model data.",
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with JOBS_LOCK:
        JOBS[job_id] = {
            "jobId": job_id,
            "status": "queued",
            "phase": "Queued",
            "progress": 0,
            "targetDate": target_date,
            "createdAt": now_colombo().isoformat(),
            "result": None,
            "error": None,
        }

    thread = threading.Thread(target=_run_optimizer_job, args=(job_id, target_date, run_dir), daemon=True)
    thread.start()
    return {"jobId": job_id, "status": "queued", "targetDate": target_date}


@app.get("/api/optimizer/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            return job
    parsed_file = RUNS_DIR / job_id / "parsed_results.json"
    if parsed_file.exists():
        parsed = json.loads(parsed_file.read_text(encoding="utf-8"))
        parsed = _upgrade_local_result_with_charger_occupancy(parsed, job_id)
        return {"jobId": job_id, "status": "success", "progress": 100, "phase": "Completed", "result": parsed, "error": None, "resultFilesLocal": True}
    try:
        parsed = db_get_optimization_result(job_id)
    except Exception:
        parsed = None
    if parsed:
        return {"jobId": job_id, "status": "success", "progress": 100, "phase": "Completed on another group laptop", "result": parsed, "error": None, "resultFilesLocal": False}
    raise HTTPException(status_code=404, detail="Optimizer job not found locally or in MongoDB.")


@app.post("/api/optimizer/jobs/{job_id}/cancel")
def cancel_optimizer_job(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail="This optimizer job is not running on this backend.",
            )

        status = job.get("status")
        if status == "cancelled":
            return dict(job)
        if status not in {"queued", "running"}:
            raise HTTPException(
                status_code=409,
                detail=f"Only a queued or running optimization can be cancelled. Current status: {status}.",
            )

        job.update({
            "status": "cancelled",
            "phase": "Cancelled by administrator",
            "progress": 100,
            "error": None,
            "cancelledAt": now_colombo().isoformat(),
        })
        process = ACTIVE_PROCESSES.get(job_id)
        response = dict(job)

    # Do not hold JOBS_LOCK while terminating the child process.
    if process is not None:
        _terminate_optimizer_process(process)

    # A cancelled run must never be restored later as a completed run.
    try:
        (RUNS_DIR / job_id / "parsed_results.json").unlink(missing_ok=True)
    except Exception:
        pass

    return response


@app.get("/api/optimizer/latest")
def latest_result() -> dict[str, Any]:
    try:
        latest = db_latest_optimization_result()
        if latest:
            job_id = str(latest.get("jobId") or "")
            if job_id:
                latest = _upgrade_local_result_with_charger_occupancy(latest, job_id)
            return latest
    except Exception:
        pass
    candidates = []
    for run_dir in RUNS_DIR.iterdir():
        parsed = run_dir / "parsed_results.json"
        if parsed.exists():
            candidates.append((parsed.stat().st_mtime, parsed))
    if not candidates:
        raise HTTPException(status_code=404, detail="No completed optimization result is available yet.")
    _, latest_file = max(candidates, key=lambda item: item[0])
    return json.loads(latest_file.read_text(encoding="utf-8"))


@app.get("/api/optimizer/history")
def optimizer_history(limit: int = 10) -> list[dict[str, Any]]:
    try:
        return db_optimization_history(limit)
    except Exception:
        limit = max(1, min(int(limit), 50))
        candidates: list[tuple[float, dict[str, Any]]] = []
        for run_dir in RUNS_DIR.iterdir():
            parsed_file = run_dir / "parsed_results.json"
            if not parsed_file.exists():
                continue
            try:
                parsed = json.loads(parsed_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            candidates.append((parsed_file.stat().st_mtime, parsed))
        candidates.sort(key=lambda item: item[0], reverse=True)
        history = []
        for _, parsed in candidates[:limit]:
            metrics = parsed.get("metrics") or {}
            history.append({
                "jobId": parsed.get("jobId"), "targetDate": parsed.get("targetDate"), "generatedAt": parsed.get("generatedAt"),
                "priceAverageLKRkWh": metrics.get("priceAverageLKRkWh"), "forecastTotalProfitLKR": metrics.get("forecastTotalProfitLKR"),
                "forecastTotalRevenueLKR": metrics.get("forecastTotalRevenueLKR"), "machineName": "This laptop",
            })
        return history


@app.post("/api/prices/publish-tomorrow")
def publish_tomorrow(request: PublishPricesRequest) -> dict[str, Any]:
    parsed = None
    job_file = RUNS_DIR / request.jobId / "parsed_results.json"
    if job_file.exists():
        parsed = json.loads(job_file.read_text(encoding="utf-8"))
    if parsed is None:
        try:
            parsed = db_get_optimization_result(request.jobId)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"MongoDB is unavailable: {exc}") from exc
    if not parsed:
        raise HTTPException(status_code=404, detail="Completed optimization result not found for this job.")
    if parsed.get("targetDate") != tomorrow_key():
        raise HTTPException(status_code=409, detail="This optimization result is not for the current tomorrow date.")
    prices = parsed.get("priceSignal")
    if not _valid_price_array(prices):
        raise HTTPException(status_code=500, detail="Optimization result does not contain a valid 96-slot price signal.")
    published_at = now_colombo().isoformat()
    try:
        patch_station({
            "publicTomorrow": [float(v) for v in prices],
            "publicTomorrowDate": parsed["targetDate"],
            "publicTomorrowAvailable": True,
            "publicTomorrowPublishedAt": published_at,
            "tomorrowSourceJobId": request.jobId,
            "lastPriceUpdate": published_at,
        })
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to publish tomorrow price to MongoDB: {exc}") from exc
    return {"status":"published", "tomorrowDate":parsed["targetDate"], "publishedAt":published_at, "prices":[float(v) for v in prices]}


@app.post("/api/optimizer/jobs/{job_id}/publish-and-notify")
def publish_and_notify(job_id: str) -> dict[str, Any]:
    parsed = None
    local_file = RUNS_DIR / job_id / "parsed_results.json"
    if local_file.exists():
        parsed = json.loads(local_file.read_text(encoding="utf-8"))
    if parsed is None:
        try:
            parsed = db_get_optimization_result(job_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"MongoDB is unavailable: {exc}") from exc
    if not parsed:
        raise HTTPException(status_code=404, detail="Completed optimization result not found.")
    if parsed.get("targetDate") != tomorrow_key():
        raise HTTPException(status_code=409, detail="This optimization result is not for the current tomorrow date.")
    prices = parsed.get("priceSignal")
    if not _valid_price_array(prices):
        raise HTTPException(status_code=500, detail="Optimization result does not contain a valid 96-slot price signal.")
    published_at = now_colombo().isoformat()
    try:
        patch_station({
            "publicTomorrow": [float(v) for v in prices],
            "publicTomorrowDate": parsed["targetDate"],
            "publicTomorrowAvailable": True,
            "publicTomorrowPublishedAt": published_at,
            "tomorrowSourceJobId": job_id,
            "lastPriceUpdate": published_at,
        })
        notification_summary = apply_optimizer_notifications(parsed)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to publish price/notifications to MongoDB: {exc}") from exc
    return {
        "status":"published",
        "tomorrowDate": parsed["targetDate"],
        "publishedAt": published_at,
        "prices":[float(v) for v in prices],
        **notification_summary,
    }


@app.get("/api/optimizer/jobs/{job_id}/files/{filename}")
def download_result_file(job_id: str, filename: str):
    allowed = {
        "slot_summary_results.csv",
        "final_milp_summary.csv",
        "elastic_user_notifications.csv",
        "optimized_ev_profile_pu.txt",
        "optimized_bess_profile_pu.txt",
        "optimizer_stdout.log",
        "optimizer_stderr.log",
    }
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="File is not available for download.")
    if filename.startswith("optimizer_"):
        path = RUNS_DIR / job_id / filename
    else:
        path = RUNS_DIR / job_id / "results" / filename
    if path.exists():
        return FileResponse(path, filename=filename)
    try:
        data = fetch_optimization_file(job_id, filename)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to retrieve result file from MongoDB: {exc}") from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Result file not found locally or in MongoDB.")
    media = "text/csv" if filename.endswith(".csv") else "text/plain"
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/optimizer/jobs/{job_id}/download-all")
def download_all(job_id: str):
    run_dir = RUNS_DIR / job_id
    result_dir = run_dir / "results"
    zip_name = f"optimizer_results_{job_id}.zip"
    if result_dir.exists():
        zip_path = run_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in result_dir.rglob("*"):
                if path.is_file(): archive.write(path, path.relative_to(result_dir))
            for log_name in ("optimizer_stdout.log", "optimizer_stderr.log"):
                log_path = run_dir / log_name
                if log_path.exists(): archive.write(log_path, log_name)
        return FileResponse(zip_path, filename=zip_path.name)
    try:
        names = list_optimization_files(job_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to retrieve shared result files from MongoDB: {exc}") from exc
    if not names:
        raise HTTPException(status_code=404, detail="Completed results were not found locally or in MongoDB.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            data = fetch_optimization_file(job_id, name)
            if data is not None: archive.writestr(name, data)
    return Response(content=buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{zip_name}"'})
