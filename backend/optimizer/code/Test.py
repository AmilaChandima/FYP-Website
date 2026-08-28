import matplotlib
matplotlib.use("Agg")

import os
import re
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pyomo.environ as pyo
import gurobipy as gp

# ============================================================
# AUTO PATH SETUP
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_DIR = os.path.join(PROJECT_DIR, "inputs")

OUT_DIR = os.path.join(PROJECT_DIR, "results")
GRAPH_DIR = os.path.join(OUT_DIR, "graphs")
os.makedirs(GRAPH_DIR, exist_ok=True)

# ============================================================
# INPUT FILES
# ============================================================
USER_SESSION_FILE = os.path.join(INPUT_DIR, "Typical_Day_Individual_EV_Controller.xlsx")
PRIMARY_ELASTIC_USER_SESSION_FILE = os.path.join(INPUT_DIR, "Primary_Elastic_EV_Users.xlsx")
PV_FILE = os.path.join(INPUT_DIR, "pv.txt")

# Dynamic 15-minute grid energy prices.
# The program first looks for the Excel file and then for the CSV file
# in the project inputs folder.
GRID_PRICE_FILE = os.path.join(
    INPUT_DIR,
    "grid_price_input_used.csv",
)

if not os.path.exists(USER_SESSION_FILE):
    USER_SESSION_FILE = os.path.join(SCRIPT_DIR, "Typical_Day_Individual_EV_Controller.xlsx")
if not os.path.exists(PRIMARY_ELASTIC_USER_SESSION_FILE):
    PRIMARY_ELASTIC_USER_SESSION_FILE = os.path.join(SCRIPT_DIR, "Primary_Elastic_EV_Users.xlsx")
if not os.path.exists(PV_FILE):
    PV_FILE = os.path.join(SCRIPT_DIR, "pv.txt")

# ============================================================
# TIME PARAMETERS
# ============================================================
N = 96
T = list(range(N))
dt = 0.25
MINUTES_PER_DAY = 1440
M = list(range(MINUTES_PER_DAY))
hours = np.array([t / 4 for t in T])

# ============================================================
# GRID PEAK PERIOD
# ============================================================
GRID_PEAK_PERIOD_START_HOUR = 18.5   # 18:30
GRID_PEAK_PERIOD_END_HOUR = 22.5     # 22:30

# ============================================================
# PHYSICAL CHARGER PARAMETERS
# 10 charger piles, 450 kW per pile, one EV per pile at exact time
# ============================================================
NUMBER_OF_CHARGER_PILES = 10
CHARGER_PILE_RATED_POWER_KW = 450.0
CHARGER_IDS = list(range(1, NUMBER_OF_CHARGER_PILES + 1))

STATION_POWER_CAPACITY = NUMBER_OF_CHARGER_PILES * CHARGER_PILE_RATED_POWER_KW

# Physical/contractual upper bound at the point of common coupling.
GRID_IMPORT_MAX_KW = 4000.0

# Demand-peak protection without explicitly adding a demand-charge term.
# The optimized schedule is forced to keep its maximum grid import at least
# 10% below the actual pre-optimization maximum grid import.
#
# Example:
#   previous maximum = 3,600 kW
#   minimum reduction = 10%
#   optimized cap     = 3,240 kW
#
# Change this fraction to modify the required minimum peak reduction.
# For example, use 0.15 for 15% or 0.20 for 20%.
ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION = True
MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE = 0.10

if not (
    0.0
    <= MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE
    < 1.0
):
    raise ValueError(
        "MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE "
        "must be between 0 and 1."
    )

# Use exact-minute charger checking, not full 15-minute overlap checking
ENABLE_EXACT_MINUTE_CHARGER_CONSTRAINTS = True
ENABLE_EXACT_MINUTE_STATION_CONSTRAINTS = True

# ============================================================
# PV AND BESS PARAMETERS
# ============================================================
PV_RATED_POWER = 5000.0
BESS_ENERGY_CAPACITY = 5300.0
BESS_POWER_RATING = 2650.0

ETA_CH = 0.95
ETA_DIS = 0.95

SOC_MIN_PERCENTAGE = 0.10
SOC_MAX_PERCENTAGE = 0.90
SOC_INITIAL_PERCENTAGE = 0.10

SOC_MIN = SOC_MIN_PERCENTAGE * BESS_ENERGY_CAPACITY
SOC_MAX = SOC_MAX_PERCENTAGE * BESS_ENERGY_CAPACITY
SOC_INITIAL = SOC_INITIAL_PERCENTAGE * BESS_ENERGY_CAPACITY

P_CH_MAX = BESS_POWER_RATING
P_DIS_MAX = BESS_POWER_RATING
ALLOW_GRID_TO_BESS = True

# The previous fixed clock-time restriction on grid-to-BESS charging is
# removed. Grid charging is allowed at any time only when there is no PV
# surplus after serving the optimized EV load.
SOLAR_BALANCE_BIG_M = PV_RATED_POWER + STATION_POWER_CAPACITY

# Direct BESS export to the grid is available only in the final profit stage.
# BESS-to-EV and BESS-to-grid share the same PCS discharge-power rating.
ALLOW_BESS_TO_GRID = True
BESS_TO_GRID_MAX_KW = BESS_POWER_RATING

# ============================================================
# GRID EXPORT AND PV CURTAILMENT
# ============================================================
ALLOW_PV_EXPORT = True
PV_EXPORT_MAX_KW = 4000.0
PV_CURTAILMENT_PENALTY = 50.0

# Dispatchable export is committed as a complete one-hour block. Because the
# optimization uses 15-minute intervals, each block contains four slots and
# the same export rate must be delivered in all four slots.
#
# A dispatchable block is valid only when the station can maintain at least
# 1,000 kW during every slot of the full hour. If that minimum cannot be
# maintained, the optimizer leaves the block unselected and any available
# export is handled through the non-dispatchable export product instead.
DISPATCH_BLOCK_SLOTS = 4
DISPATCH_BLOCK_STARTS = list(range(0, N, DISPATCH_BLOCK_SLOTS))
MIN_DISPATCHABLE_EXPORT_KW = 1000.0
MAX_DISPATCHABLE_EXPORT_KW = PV_EXPORT_MAX_KW
MAX_DISPATCHABLE_BLOCKS_PER_DAY = len(DISPATCH_BLOCK_STARTS)

if MIN_DISPATCHABLE_EXPORT_KW > MAX_DISPATCHABLE_EXPORT_KW:
    raise ValueError(
        "MIN_DISPATCHABLE_EXPORT_KW cannot exceed "
        "MAX_DISPATCHABLE_EXPORT_KW."
    )

# ============================================================
# RAMPING CONSTRAINTS
# ============================================================
ENABLE_LOAD_RAMP = True
LOAD_RAMP_LIMIT_KW = 1000.0

ENABLE_PRICE_RAMP = True
PRICE_RAMP_LIMIT_LKR_KWH = 20.0

ENABLE_GRID_IMPORT_RAMP = True
GRID_IMPORT_RAMP_LIMIT_KW = 1000.0

# ============================================================
# WHOLE-VEHICLE SHIFTING METHOD
# ============================================================
SECONDARY_SHIFT_START_SLOT = 22
SECONDARY_SHIFT_END_SLOT = 75
LONG_TRIP_SHIFT_END_SLOT = 90

INCLUDE_ORIGINAL_START_FOR_SECONDARY = True
CANDIDATE_START_STEP = 1

ENABLE_SECONDARY_SOLAR_SHIFT_REWARD = True
SOLAR_SHIFT_REWARD_LKR_PER_KWH = 150.0
NON_SOLAR_SECONDARY_PENALTY_LKR_PER_KWH = 35.0
SHIFTING_DISCOMFORT_COST_LKR_PER_SESSION = 100.0

# Soft tariff guidance used only in the Stage 3 objective.
# This is not a hard tariff cap: every tariff level remains feasible.
# A tariff far from the solar-based target receives an objective penalty
# only for the secondary energy actually sold in that slot.
ENABLE_SOLAR_PRICE_ALIGNMENT = True
SOLAR_PRICE_ALIGNMENT_PENALTY_LKR_PER_KWH = 120.0

LIMIT_SHIFTED_SECONDARY_USERS = True
MAX_SHIFTED_SECONDARY_USER_PERCENTAGE = 0.5

TYPE_SOLAR_SHIFT_WEIGHT = {
    "opportunistic": 1.0,
    "elastic": 1.8,
    "long_trip": 0.6,
}

# ============================================================
# BOOKED ELASTIC USER SERVICE
# ============================================================
ELASTIC_WINDOW_START_COLUMN = "Elastic_Window_Start_Time"
ELASTIC_WINDOW_END_COLUMN = "Elastic_Window_End_Time"

# The elastic tariff is precomputed for every feasible whole-session start.
# Its base is the minute-weighted PRIMARY tariff over that candidate session,
# after which the usable-flexibility and solar discounts are deducted.
# One fixed resulting tariff is charged for the entire selected session.
ELASTIC_MIN_RATE_LKR_KWH = 50.0
ELASTIC_FLEX_DISCOUNT_LKR_PER_HOUR = 2.0
ELASTIC_MAX_FLEX_DISCOUNT_LKR_KWH = 10.0

# A small part of the flexibility discount is guaranteed for providing a
# schedulable window. The remaining part is earned according to the average
# solar score of the selected complete session.
#
# Effective flexibility discount:
#   D_flex_eff = D_flex_potential *
#                [alpha + (1 - alpha) * session_average_solar_score]
ELASTIC_BASIC_FLEX_REWARD_FRACTION = 0.25

ELASTIC_MAX_SOLAR_DISCOUNT_LKR_KWH = 12.0

# Used only if an elastic row has invalid/missing window data.
ELASTIC_DEFAULT_PADDING_BEFORE_MIN = 120
ELASTIC_DEFAULT_PADDING_AFTER_MIN = 240

# ============================================================
# SOLAR EXCESS TARIFF CAP
# ============================================================
ENABLE_SOLAR_EXCESS_TARIFF_CAP = False
MEDIUM_SOLAR_EXCESS_MARGIN = 300.0
HIGH_SOLAR_EXCESS_MARGIN = 1000.0
MEDIUM_SOLAR_MAX_TARIFF = 87.0
HIGH_SOLAR_MAX_TARIFF = 70.0

# ============================================================
# SECONDARY USER DYNAMIC TARIFF LEVELS
# ============================================================
secondary_tariff_levels = [
   55, 60, 65, 70,
    75, 80, 85, 90, 95,
    100, 105, 110, 115, 120,
    125, 130, 135, 140, 145, 150,
]

# Monotonically decreasing price-response factors.
# Lower prices can support a larger share of the available secondary demand,
# while higher prices can support only a smaller share.
attraction_factor = {
   
    55: 1.43,
    60: 1.36,
    65: 1.29,
    70: 1.22,
    75: 1.15,
    80: 1.08,
    85: 1.00,
    90: 0.92,
    95: 0.84,
    100: 0.76,
    105: 0.68,
    110: 0.60,
    115: 0.52,
    120: 0.44,
    125: 0.36,
    130: 0.30,
    135: 0.25,
    140: 0.20,
    145: 0.16,
    150: 0.12,
}

ENFORCE_SECONDARY_AVG_TARIFF_LIMIT = False
MAX_SECONDARY_AVG_TARIFF_MULTIPLIER = 1.15

# ============================================================
# GUROBI SOLVER PARAMETERS
# ============================================================
# The Pyomo model is solved through Gurobi's direct Python interface.
# This keeps the full mathematical formulation unchanged and replaces
# only the optimization engine that was previously used.
SOLVER_NAME = "gurobi_direct"
SOLVER_TIME_LIMIT = 30000  # seconds
SOLVER_GAP = 0.00001          # relative MIP gap
EPS_KWH = 1.0              # lexicographic retention tolerance

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def check_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file missing: {path}")


def read_profile(path, default_zero=False):
    if not os.path.exists(path):
        if default_zero:
            print("Optional file not found, using zero profile:", path)
            return np.zeros(N)
        raise FileNotFoundError(f"File not found: {path}")

    try:
        data = np.loadtxt(path)
    except Exception:
        data = pd.read_csv(path, header=None).values.flatten()

    return np.asarray(data, dtype=float).flatten()


def convert_to_96(data, method="mean"):
    data = np.asarray(data, dtype=float).flatten()

    if len(data) == 96:
        return data

    if len(data) >= 1440:
        data = data[:1440].reshape(96, 15)
        if method == "max":
            return np.max(data, axis=1)
        return np.mean(data, axis=1)

    if len(data) > 96:
        print("WARNING: Profile has more than 96 but fewer than 1440 values. Using first 96 values.")
        return data[:96]

    raise ValueError("Profile has fewer than 96 values.")


def present_ev_selling_tariff():
    tariff = np.zeros(N)
    for t in T:
        h = hours[t]
        if 18.5 <= h < 22.5:
            tariff[t] = 111.0
        elif 5.5 <= h < 18.5:
            tariff[t] = 87.0
        else:
            tariff[t] = 53.0
    return tariff


def read_grid_price_signal(path):
    """
    Read the 96-slot grid import and export price signals.

    The preferred input is grid_price_input_used.csv with columns:
        interval_end_time_from_file
        grid_export_price_LKR_kWh
        grid_export_dispatchable_price_LKR_kWh
        grid_import_price_LKR_kWh

    The reader also accepts the older short column names:
        time
        grid_export_price
        grid_export_dispatchable_price
        grid_import_price

    Dispatchable export prices must remain constant over every four
    consecutive 15-minute slots because each dispatchable commitment is
    exactly one clock hour.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            "Dynamic grid-price file not found:\n"
            f"{path}\n\n"
            "Place grid_price_signal_with_dispatchable_export.xlsx in the same folder as this script."
        )

    extension = os.path.splitext(path)[1].lower()

    if extension in [".xlsx", ".xls"]:
        try:
            price_df = pd.read_excel(path)
        except ImportError:
            raise ImportError(
                "Reading the Excel grid-price file requires openpyxl.\n"
                "Install it using: py -m pip install openpyxl"
            )
    elif extension == ".csv":
        price_df = pd.read_csv(path)
    else:
        raise ValueError(
            "Unsupported grid-price file type. Use an .xlsx, .xls, or .csv file."
        )

    price_df.columns = [
        str(column).strip().lower()
        for column in price_df.columns
    ]

    def choose_column(candidates, description):
        for candidate in candidates:
            if candidate in price_df.columns:
                return candidate
        raise ValueError(
            f"Grid-price file is missing the {description} column.\n"
            f"Accepted names: {', '.join(candidates)}"
        )

    time_column = choose_column(
        [
            "interval_end_time_from_file",
            "time",
            "interval_end_time",
            "interval_start_time",
        ],
        "time",
    )

    normal_export_column = choose_column(
        [
            "grid_export_price_lkr_kwh",
            "grid_export_price",
            "grid_export_nondispatchable_price_lkr_kwh",
            "grid_export_nondispatchable_price",
        ],
        "normal/non-dispatchable export price",
    )

    dispatchable_export_column = choose_column(
        [
            "grid_export_dispatchable_price_lkr_kwh",
            "grid_export_dispatchable_price",
            "dispatchable_export_price_lkr_kwh",
            "dispatchable_export_price",
        ],
        "dispatchable export price",
    )

    import_column = choose_column(
        [
            "grid_import_price_lkr_kwh",
            "grid_import_price",
        ],
        "grid import price",
    )

    if len(price_df) != N:
        raise ValueError(
            f"Grid-price file must contain exactly {N} rows. "
            f"Rows found: {len(price_df)}"
        )

    time_labels = price_df[time_column].astype(str).str.strip().to_numpy()

    grid_export_prices = pd.to_numeric(
        price_df[normal_export_column],
        errors="coerce",
    ).to_numpy(dtype=float)

    grid_dispatchable_export_prices = pd.to_numeric(
        price_df[dispatchable_export_column],
        errors="coerce",
    ).to_numpy(dtype=float)

    grid_import_prices = pd.to_numeric(
        price_df[import_column],
        errors="coerce",
    ).to_numpy(dtype=float)

    price_arrays = {
        "normal export": grid_export_prices,
        "dispatchable export": grid_dispatchable_export_prices,
        "grid import": grid_import_prices,
    }

    for price_name, price_values in price_arrays.items():
        if np.isnan(price_values).any():
            bad_rows = np.where(np.isnan(price_values))[0] + 2
            raise ValueError(
                f"Invalid {price_name} values at file rows: "
                + ", ".join(map(str, bad_rows))
            )

        if np.any(price_values < 0):
            raise ValueError(f"{price_name.title()} prices cannot be negative.")

    # The dispatchable tariff must be one constant value for the complete hour.
    for block_start in DISPATCH_BLOCK_STARTS:
        block_end = block_start + DISPATCH_BLOCK_SLOTS
        hourly_prices = grid_dispatchable_export_prices[block_start:block_end]

        if len(hourly_prices) != DISPATCH_BLOCK_SLOTS:
            raise ValueError(
                f"Incomplete dispatchable price block starting at slot {block_start}."
            )

        if not np.allclose(hourly_prices, hourly_prices[0], atol=1e-9, rtol=0.0):
            raise ValueError(
                "Dispatchable export price must be identical across each "
                "four-slot clock hour. Invalid block starts at slot "
                f"{block_start}. Values: {hourly_prices.tolist()}"
            )

    lower_import_slots = np.where(
        grid_import_prices < np.maximum(
            grid_export_prices,
            grid_dispatchable_export_prices,
        )
    )[0]

    if len(lower_import_slots) > 0:
        print(
            "WARNING:",
            len(lower_import_slots),
            "slots have import price below at least one export price."
        )
        print("Import/export exclusivity prevents same-slot arbitrage.")

    lower_dispatchable_slots = np.where(
        grid_dispatchable_export_prices < grid_export_prices
    )[0]

    if len(lower_dispatchable_slots) > 0:
        print(
            "WARNING:",
            len(lower_dispatchable_slots),
            "slots have dispatchable export price below normal export price."
        )

    print("\nDynamic grid price signal loaded:", path)
    print("Number of price slots:", len(price_df))
    print(
        "Grid import price range:",
        round(float(np.min(grid_import_prices)), 3),
        "to",
        round(float(np.max(grid_import_prices)), 3),
        "LKR/kWh",
    )
    print(
        "Normal export price range:",
        round(float(np.min(grid_export_prices)), 3),
        "to",
        round(float(np.max(grid_export_prices)), 3),
        "LKR/kWh",
    )
    print(
        "Dispatchable export price range:",
        round(float(np.min(grid_dispatchable_export_prices)), 3),
        "to",
        round(float(np.max(grid_dispatchable_export_prices)), 3),
        "LKR/kWh",
    )

    return (
        time_labels,
        grid_export_prices,
        grid_dispatchable_export_prices,
        grid_import_prices,
    )

def get_value(var):
    val = pyo.value(var, exception=False)
    if val is None:
        return 0.0
    return float(val)


def safe_numeric(series, default_value=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(default_value)


def standardize_user_type(user_type):
    s = str(user_type).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ["primary", "p"]:
        return "primary"
    if s in ["opportunistic", "opp"]:
        return "opportunistic"
    if s in ["elastic", "e"]:
        return "elastic"
    if s in ["long_trip", "longtrip", "long"]:
        return "long_trip"
    return s


def is_primary_user(user_type):
    return str(user_type).strip().lower() == "primary"


def is_elastic_user(user_type):
    return str(user_type).strip().lower() == "elastic"


def is_dynamic_secondary_user(user_type):
    return (
        not is_primary_user(user_type)
        and not is_elastic_user(user_type)
    )


def is_secondary_user(user_type):
    # All non-primary users, including booked elastic users.
    return not is_primary_user(user_type)


def parse_charger_id(value):
    if pd.isna(value):
        return 1

    text = str(value).strip()
    match = re.search(r"\d+", text)

    if match:
        charger_id = int(match.group(0))
    else:
        try:
            charger_id = int(float(text))
        except Exception:
            charger_id = 1

    if charger_id < 1 or charger_id > NUMBER_OF_CHARGER_PILES:
        charger_id = ((charger_id - 1) % NUMBER_OF_CHARGER_PILES) + 1

    return charger_id


def parse_bool_value(value):
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ["true", "1", "yes", "y"]


def parse_time_to_minute(value):
    if pd.isna(value):
        return None

    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)

    text = str(value).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", text)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        return h * 60 + m

    try:
        x = float(text)
        if 0 <= x < 1:
            return int(round(x * 1440)) % 1440
    except Exception:
        pass

    return None


def convert_slot_series(raw_series):
    raw = safe_numeric(raw_series, 1).astype(int)
    min_val = int(raw.min())
    max_val = int(raw.max())

    if min_val >= 1 and max_val <= 96:
        slots = raw - 1
        slot_base = "one_based"
    else:
        slots = raw
        slot_base = "zero_based"

    slots = slots.clip(lower=0, upper=N - 1).astype(int)
    return slots, slot_base


def convert_single_slot(value, slot_base):
    if pd.isna(value):
        return None
    try:
        raw = int(float(value))
    except Exception:
        return None

    if slot_base == "one_based":
        return max(0, min(N - 1, raw - 1))
    return max(0, min(N - 1, raw))


def convert_completion_to_boundary_slot(completion_value, arrival_slot, crosses_midnight, slot_base):
    try:
        raw = int(float(completion_value))
    except Exception:
        raw = N

    if crosses_midnight:
        return N

    if slot_base == "one_based":
        boundary_slot = raw
    else:
        boundary_slot = raw + 1

    boundary_slot = max(arrival_slot + 1, min(N, boundary_slot))
    return boundary_slot


def get_solar_cap_value(pv_value, reference_load_value):
    pv_excess = pv_value - reference_load_value

    if pv_excess >= HIGH_SOLAR_EXCESS_MARGIN:
        return HIGH_SOLAR_MAX_TARIFF, "High solar excess"
    if pv_excess >= MEDIUM_SOLAR_EXCESS_MARGIN:
        return MEDIUM_SOLAR_MAX_TARIFF, "Medium solar excess"
    return max(secondary_tariff_levels), "No solar cap"


def slot_to_time(slot_index):
    slot_index = int(slot_index)
    h = int(slot_index // 4)
    m = int((slot_index % 4) * 15)
    return f"{h:02d}:{m:02d}"


def minute_to_time(minute):
    minute = int(minute)
    if minute >= 1440:
        return "24:00"
    if minute < 0:
        minute = 0
    return f"{minute // 60:02d}:{minute % 60:02d}"


def pyomo_sum_or_zero(terms, zero_anchor):
    terms = list(terms)
    if len(terms) > 0:
        return pyo.quicksum(terms)
    return 0 * zero_anchor


def overlap_minutes(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def make_candidate_starts(
    user_type,
    original_start_slot,
    duration_slots,
    start_minute_offset=0,
    duration_min=None,
    elastic_window_start_minute=None,
    elastic_window_end_minute=None,
):
    latest_start = max(0, N - duration_slots)
    original_start_slot = max(0, min(latest_start, int(original_start_slot)))

    if is_primary_user(user_type):
        return [original_start_slot]

    if is_elastic_user(user_type):
        if duration_min is None:
            duration_min = duration_slots * 15

        # Elastic users are notified only at exact 15-minute plug-in times.
        # Therefore, their original within-slot minute offset is intentionally
        # not carried into candidate starts. For example: 10:00, 10:15, 10:30.
        earliest_start_slot = int(math.ceil(
            float(elastic_window_start_minute) / 15.0
        ))
        latest_window_start_slot = int(math.floor(
            (
                float(elastic_window_end_minute)
                - float(duration_min)
            )
            / 15.0
        ))

        latest_day_start_slot = int(math.floor(
            (MINUTES_PER_DAY - float(duration_min)) / 15.0
        ))

        earliest_start_slot = max(0, earliest_start_slot)
        latest_window_start_slot = min(
            latest_day_start_slot,
            latest_window_start_slot,
        )

        starts = list(range(
            earliest_start_slot,
            latest_window_start_slot + 1,
            CANDIDATE_START_STEP,
        ))

        if len(starts) == 0:
            raise ValueError(
                f"No feasible elastic start remains for window "
                f"{minute_to_time(elastic_window_start_minute)}-"
                f"{minute_to_time(elastic_window_end_minute)}."
            )

        return starts

    candidate_starts = set()

    if INCLUDE_ORIGINAL_START_FOR_SECONDARY:
        candidate_starts.add(original_start_slot)

    start_a = SECONDARY_SHIFT_START_SLOT

    if str(user_type) == "long_trip":
        end_b = LONG_TRIP_SHIFT_END_SLOT
    else:
        end_b = SECONDARY_SHIFT_END_SLOT

    latest_solar_start = min(latest_start, end_b - duration_slots)

    if latest_solar_start >= start_a:
        for s in range(start_a, latest_solar_start + 1, CANDIDATE_START_STEP):
            candidate_starts.add(s)

    if len(candidate_starts) == 0:
        candidate_starts.add(original_start_slot)

    return sorted(candidate_starts)


def option_start_minute(user_index, start_slot):
    # Elastic users receive round 15-minute appointment times. Primary and
    # dynamic-secondary users retain their original exact-minute offset.
    if is_elastic_user(users.loc[user_index, "user_type"]):
        return int(start_slot) * 15

    return int(start_slot) * 15 + int(users.loc[user_index, "start_minute_offset"])


def option_end_minute(user_index, start_slot):
    return option_start_minute(user_index, start_slot) + int(users.loc[user_index, "session_duration_min"])


# ============================================================
# CHECK INPUT FILES
# ============================================================
check_file(USER_SESSION_FILE)
check_file(PRIMARY_ELASTIC_USER_SESSION_FILE)
check_file(PV_FILE)
check_file(GRID_PRICE_FILE)

print("Found user session file:", USER_SESSION_FILE)
print("Found primary and elastic user session file:", PRIMARY_ELASTIC_USER_SESSION_FILE)
print("Found PV file:", PV_FILE)
print("Found dynamic grid price file:", GRID_PRICE_FILE)

# ============================================================
# READ PV DATA
# ============================================================
pv_raw = convert_to_96(read_profile(PV_FILE), method="mean")
pv = pv_raw * PV_RATED_POWER

# The before-optimization BESS profile is not read from an input file.
# It is generated later from the actual PV and EV-load relationship.

primary_tariff = present_ev_selling_tariff()

(
    grid_price_time_labels,
    grid_export_price,
    grid_dispatchable_export_price,
    grid_buy,
) = read_grid_price_signal(GRID_PRICE_FILE)

# Keep an explicit record of the exact price inputs used by the model.
grid_price_input_df = pd.DataFrame({
    "slot": T,
    "interval_start_time": [
        f"{int(t // 4):02d}:{int((t % 4) * 15):02d}"
        for t in T
    ],
    "interval_end_time_from_file": grid_price_time_labels,
    "grid_export_price_LKR_kWh": grid_export_price,
    "grid_export_dispatchable_price_LKR_kWh": grid_dispatchable_export_price,
    "grid_import_price_LKR_kWh": grid_buy,
})

secondary_tariff_before = primary_tariff.copy()

# ============================================================
# READ USER-LEVEL EXCEL DATA
# ============================================================
try:
    other_users_df = pd.read_excel(USER_SESSION_FILE)
    primary_elastic_users_df = pd.read_excel(PRIMARY_ELASTIC_USER_SESSION_FILE)
except ImportError:
    raise ImportError("Install openpyxl using: py -m pip install openpyxl")

raw_df = pd.concat(
    [other_users_df, primary_elastic_users_df],
    ignore_index=True,
)
raw_df.columns = [str(c).strip() for c in raw_df.columns]
raw_df = raw_df.sort_values(
    "Overall_EV_No",
    kind="stable",
).reset_index(drop=True)

required_columns = [
    "Controller_EV_ID",
    "EV_Notation",
    "User_Type",
    "Queue_Priority",
    "Original_Arrival_15min_Slot",
    "Arrival_Minute",
    "Assigned_Charger",
    "Battery_Capacity_kWh",
    "Initial_SOC_pct",
    "Target_SOC_pct",
    "Requested_Battery_Energy_kWh",
    "EV_Max_Charging_Power_kW",
    "Controller_Power_Limit_kW",
    "Session_Efficiency_pct",
    "Completion_15min_Slot",
    ELASTIC_WINDOW_START_COLUMN,
    ELASTIC_WINDOW_END_COLUMN,
]

missing_columns = [c for c in required_columns if c not in raw_df.columns]
if missing_columns:
    raise ValueError("Missing required Excel columns:\n" + "\n".join(missing_columns))

users = pd.DataFrame()
users["raw_index"] = raw_df.index
users["user_id"] = raw_df["Controller_EV_ID"].astype(str)
users["ev_notation"] = raw_df["EV_Notation"].astype(str)
users["user_type"] = raw_df["User_Type"].apply(standardize_user_type)
users["priority"] = safe_numeric(raw_df["Queue_Priority"], 99).astype(int)
users["arrival_minute"] = safe_numeric(raw_df["Arrival_Minute"], 0).astype(int)

arrival_slots, slot_base = convert_slot_series(raw_df["Original_Arrival_15min_Slot"])
users["arrival_slot"] = arrival_slots
users["arrival_slot_original"] = safe_numeric(raw_df["Original_Arrival_15min_Slot"], 1).astype(int)

users["assigned_charger"] = raw_df["Assigned_Charger"].apply(parse_charger_id).astype(int)

users["battery_capacity_kWh"] = safe_numeric(raw_df["Battery_Capacity_kWh"], 50.0)
users["entry_soc_pct"] = safe_numeric(raw_df["Initial_SOC_pct"], 20.0)
users["target_soc_pct"] = safe_numeric(raw_df["Target_SOC_pct"], 80.0)

requested_energy_from_soc = (
    users["battery_capacity_kWh"]
    * (users["target_soc_pct"] - users["entry_soc_pct"])
    / 100.0
)

users["required_energy_original_kWh"] = safe_numeric(
    raw_df["Requested_Battery_Energy_kWh"],
    np.nan,
).fillna(requested_energy_from_soc)

if "Actual_Battery_Energy_kWh" in raw_df.columns:
    actual_batt = safe_numeric(raw_df["Actual_Battery_Energy_kWh"], np.nan)
    users["required_energy_original_kWh"] = actual_batt.fillna(users["required_energy_original_kWh"])

ev_max_power = safe_numeric(raw_df["EV_Max_Charging_Power_kW"], 350.0)
controller_power_limit = safe_numeric(raw_df["Controller_Power_Limit_kW"], 350.0)

users["max_power_kW"] = np.minimum(
    np.minimum(ev_max_power, controller_power_limit),
    CHARGER_PILE_RATED_POWER_KW,
).clip(lower=1.0)

users["efficiency_pct"] = safe_numeric(raw_df["Session_Efficiency_pct"], 92.5)
users["efficiency"] = (users["efficiency_pct"] / 100.0).clip(lower=0.50, upper=1.00)

if "Crosses_Midnight" in raw_df.columns:
    crosses_midnight = raw_df["Crosses_Midnight"].apply(parse_bool_value)
else:
    completion_original = safe_numeric(raw_df["Completion_15min_Slot"], 96).astype(int)
    arrival_original = safe_numeric(raw_df["Original_Arrival_15min_Slot"], 1).astype(int)
    crosses_midnight = completion_original < arrival_original

completion_boundary_slots = []

for i in range(len(users)):
    arrival_slot = int(users.loc[i, "arrival_slot"])
    completion_value = raw_df.loc[i, "Completion_15min_Slot"]
    cross_value = bool(crosses_midnight.iloc[i])
    completion_boundary_slots.append(
        convert_completion_to_boundary_slot(completion_value, arrival_slot, cross_value, slot_base)
    )

users["predicted_completion_boundary_slot"] = completion_boundary_slots

if "Charging_Start_15min_Slot" in raw_df.columns:
    start_raw = raw_df["Charging_Start_15min_Slot"]
else:
    start_raw = raw_df["Original_Arrival_15min_Slot"]

original_start_slots = []

for i in range(len(users)):
    start_slot = convert_single_slot(start_raw.iloc[i], slot_base)
    if start_slot is None:
        start_slot = int(users.loc[i, "arrival_slot"])
    original_start_slots.append(start_slot)

users["original_start_slot"] = original_start_slots

exact_start_minutes = []

for i in range(len(users)):
    minute_value = None

    if "Charging_Start_Time" in raw_df.columns:
        minute_value = parse_time_to_minute(raw_df.loc[i, "Charging_Start_Time"])

    if minute_value is None:
        minute_value = int(users.loc[i, "original_start_slot"]) * 15

    exact_start_minutes.append(int(minute_value))

users["original_start_minute"] = exact_start_minutes
users["start_minute_offset"] = users["original_start_minute"] - users["original_start_slot"] * 15
users["start_minute_offset"] = users["start_minute_offset"].clip(lower=0, upper=14).astype(int)

users["required_energy_kWh"] = users["required_energy_original_kWh"].clip(lower=0.0)
users["energy_adjusted_flag"] = "No"
users["pending_energy_kWh"] = 0.0

if "Service_Duration_min" in raw_df.columns:
    service_duration_min = safe_numeric(raw_df["Service_Duration_min"], np.nan)
else:
    service_duration_min = pd.Series([np.nan] * len(users))

session_duration_min = []
session_duration_slots = []
session_power_kW = []
charger_energy_kWh = []
original_end_slots = []
original_end_minutes = []

for i in range(len(users)):
    required_energy = float(users.loc[i, "required_energy_kWh"])
    eff = float(users.loc[i, "efficiency"])
    max_power = float(users.loc[i, "max_power_kW"])
    original_start_slot = int(users.loc[i, "original_start_slot"])
    exact_start_minute = int(users.loc[i, "original_start_minute"])
    predicted_completion = int(users.loc[i, "predicted_completion_boundary_slot"])

    charger_energy = required_energy / max(eff, 1e-6)

    if "Actual_Grid_Energy_kWh" in raw_df.columns:
        actual_grid_energy = safe_numeric(raw_df["Actual_Grid_Energy_kWh"], np.nan).iloc[i]
        if not pd.isna(actual_grid_energy) and actual_grid_energy > 0:
            charger_energy = float(actual_grid_energy)

    if not pd.isna(service_duration_min.iloc[i]) and float(service_duration_min.iloc[i]) > 0:
        duration_min = int(math.ceil(float(service_duration_min.iloc[i])))
    else:
        duration_min = max(1, (predicted_completion - original_start_slot) * 15)

    min_duration_for_450 = int(math.ceil((charger_energy / max(max_power, 1e-6)) * 60.0))
    duration_min = max(1, duration_min, min_duration_for_450)

    if exact_start_minute + duration_min > MINUTES_PER_DAY:
        duration_min = max(1, MINUTES_PER_DAY - exact_start_minute)
        max_possible_charger_energy = max_power * duration_min / 60.0

        if charger_energy > max_possible_charger_energy:
            old_batt_energy = required_energy
            charger_energy = max_possible_charger_energy * 0.999
            required_energy = charger_energy * eff
            users.loc[i, "required_energy_kWh"] = required_energy
            users.loc[i, "pending_energy_kWh"] = max(0.0, old_batt_energy - required_energy)
            users.loc[i, "energy_adjusted_flag"] = "Yes"

    power = charger_energy / max(duration_min / 60.0, 1e-6)
    power = min(power, max_power)

    duration_slots = int(math.ceil((users.loc[i, "start_minute_offset"] + duration_min) / 15.0))
    duration_slots = max(1, duration_slots)

    latest_start_slot = max(0, N - duration_slots)
    original_start_slot = max(0, min(latest_start_slot, original_start_slot))
    users.loc[i, "original_start_slot"] = original_start_slot

    original_end_minute = min(MINUTES_PER_DAY, exact_start_minute + duration_min)
    original_end_slot = min(N, int(math.ceil(original_end_minute / 15.0)))

    session_duration_min.append(duration_min)
    session_duration_slots.append(duration_slots)
    session_power_kW.append(power)
    charger_energy_kWh.append(power * duration_min / 60.0)
    original_end_slots.append(original_end_slot)
    original_end_minutes.append(original_end_minute)

users["session_duration_min"] = session_duration_min
users["session_duration_slots"] = session_duration_slots
users["session_power_kW"] = session_power_kW
users["charger_energy_kWh"] = charger_energy_kWh
users["original_end_slot"] = original_end_slots
users["original_end_minute"] = original_end_minutes

# Parse each booked elastic user's personal same-day scheduling window.
users["elastic_window_start_minute"] = np.nan
users["elastic_window_end_minute"] = np.nan
users["elastic_window_adjusted_flag"] = "No"
users["elastic_window_adjustment_reason"] = "Not applicable"

for i in range(len(users)):
    if not is_elastic_user(users.loc[i, "user_type"]):
        continue

    start_minute = parse_time_to_minute(raw_df.loc[i, ELASTIC_WINDOW_START_COLUMN])
    end_minute = parse_time_to_minute(raw_df.loc[i, ELASTIC_WINDOW_END_COLUMN])
    duration_min = int(users.loc[i, "session_duration_min"])
    original_start_minute = int(users.loc[i, "original_start_minute"])
    original_end_minute = int(users.loc[i, "original_end_minute"])
    adjusted = False
    reasons = []

    if (
        start_minute is None
        or end_minute is None
        or start_minute < 0
        or end_minute > MINUTES_PER_DAY
        or end_minute <= start_minute
    ):
        start_minute = max(
            0,
            original_start_minute - ELASTIC_DEFAULT_PADDING_BEFORE_MIN,
        )
        end_minute = min(
            MINUTES_PER_DAY,
            original_end_minute + ELASTIC_DEFAULT_PADDING_AFTER_MIN,
        )
        adjusted = True
        reasons.append("Missing or invalid same-day window; default window used")

    # Add alignment allowance so at least one exact whole-session start exists
    # on the model's 15-minute candidate grid while retaining minute accuracy.
    required_window_width = duration_min + 15

    if end_minute - start_minute < required_window_width:
        centre = 0.5 * (start_minute + end_minute)
        start_minute = int(math.floor(centre - required_window_width / 2.0))
        end_minute = start_minute + required_window_width

        if start_minute < 0:
            end_minute -= start_minute
            start_minute = 0
        if end_minute > MINUTES_PER_DAY:
            start_minute -= end_minute - MINUTES_PER_DAY
            end_minute = MINUTES_PER_DAY

        start_minute = max(0, start_minute)
        end_minute = min(MINUTES_PER_DAY, end_minute)
        adjusted = True
        reasons.append("Window widened to fit the complete charging session")

    users.loc[i, "elastic_window_start_minute"] = int(start_minute)
    users.loc[i, "elastic_window_end_minute"] = int(end_minute)
    users.loc[i, "elastic_window_adjusted_flag"] = "Yes" if adjusted else "No"
    users.loc[i, "elastic_window_adjustment_reason"] = (
        "; ".join(reasons) if reasons else "Original window accepted"
    )

users["elastic_window_start_time"] = users["elastic_window_start_minute"].apply(
    lambda x: minute_to_time(x) if not pd.isna(x) else ""
)
users["elastic_window_end_time"] = users["elastic_window_end_minute"].apply(
    lambda x: minute_to_time(x) if not pd.isna(x) else ""
)
users["elastic_flexibility_hours"] = np.where(
    users["user_type"] == "elastic",
    np.maximum(
        (
            users["elastic_window_end_minute"]
            - users["elastic_window_start_minute"]
            - users["session_duration_min"]
        )
        / 60.0,
        0.0,
    ),
    0.0,
)

users = users[users["required_energy_kWh"] > 0.001].reset_index(drop=True)
U = list(range(len(users)))

secondary_user_indices = [u for u in U if is_secondary_user(users.loc[u, "user_type"])]
elastic_user_indices = [u for u in U if is_elastic_user(users.loc[u, "user_type"])]
dynamic_secondary_user_indices = [
    u for u in U if is_dynamic_secondary_user(users.loc[u, "user_type"])
]

# The 45% cap applies only to price-responsive dynamic secondary users.
MAX_SHIFTED_SECONDARY_USERS_ALLOWED = int(
    math.floor(
        MAX_SHIFTED_SECONDARY_USER_PERCENTAGE
        * len(dynamic_secondary_user_indices)
    )
)

MAX_SHIFTED_SECONDARY_USERS_ALLOWED = max(
    0,
    min(
        MAX_SHIFTED_SECONDARY_USERS_ALLOWED,
        len(dynamic_secondary_user_indices),
    ),
)

print("\nNumber of EV users loaded:", len(users))
print(users["user_type"].value_counts())

print("\nCharging station:")
print("Number of charger piles:", NUMBER_OF_CHARGER_PILES)
print("Charger pile rated power:", CHARGER_PILE_RATED_POWER_KW, "kW")
print("Station charging capacity:", STATION_POWER_CAPACITY, "kW")
print("All non-primary users:", len(secondary_user_indices))
print("Booked elastic users:", len(elastic_user_indices))
print("Dynamic secondary users:", len(dynamic_secondary_user_indices))
print("Maximum shifted dynamic secondary users allowed:", MAX_SHIFTED_SECONDARY_USERS_ALLOWED)

# ============================================================
# CANDIDATE START SLOTS
# ============================================================
candidate_starts_by_user = {}
candidate_start_pairs = []

# Elastic users receive a joint whole-session start-and-charger decision.
# Primary and dynamic-secondary users keep their charger from the input file.
elastic_candidate_start_charger_triples = []

for u in U:
    user_type = users.loc[u, "user_type"]
    original_start = int(users.loc[u, "original_start_slot"])
    duration_slots = int(users.loc[u, "session_duration_slots"])

    starts = make_candidate_starts(
        user_type,
        original_start,
        duration_slots,
        start_minute_offset=int(users.loc[u, "start_minute_offset"]),
        duration_min=int(users.loc[u, "session_duration_min"]),
        elastic_window_start_minute=(
            int(users.loc[u, "elastic_window_start_minute"])
            if is_elastic_user(user_type)
            else None
        ),
        elastic_window_end_minute=(
            int(users.loc[u, "elastic_window_end_minute"])
            if is_elastic_user(user_type)
            else None
        ),
    )

    candidate_starts_by_user[u] = starts

    for s in starts:
        candidate_start_pairs.append((u, s))

        if is_elastic_user(user_type):
            for c in CHARGER_IDS:
                elastic_candidate_start_charger_triples.append((u, s, c))

print("\nCandidate start variables:", len(candidate_start_pairs))
print(
    "Elastic start-and-charger variables:",
    len(elastic_candidate_start_charger_triples),
)
print("Primary users fixed at original exact start minute.")
print("Dynamic secondary users choose original or shifted exact-minute session.")
print("Elastic users choose one complete session inside their personal booking window at exact 15-minute plug-in times.")

clean_user_csv = os.path.join(OUT_DIR, "ev_user_sessions_clean.csv")
users.to_csv(clean_user_csv, index=False)

# ============================================================
# ACTIVE MAPS WITH EXACT MINUTES AND FRACTIONAL SLOT OVERLAP
# ============================================================
active_candidates_by_slot = {t: [] for t in T}
primary_active_candidates_by_slot = {t: [] for t in T}
secondary_active_candidates_by_slot = {t: [] for t in T}
dynamic_secondary_active_candidates_by_slot = {t: [] for t in T}
elastic_active_candidates_by_slot = {t: [] for t in T}
slot_overlap_fraction = {}

active_candidates_by_minute = {m: [] for m in M}

# Fixed-charger candidates contain primary and dynamic-secondary users.
# Elastic candidates are mapped to every possible charger because the MILP
# chooses one charger jointly with one 15-minute-boundary start time.
fixed_active_candidates_by_charger_minute = {
    (c, m): [] for c in CHARGER_IDS for m in M
}
elastic_active_candidates_by_charger_minute = {
    (c, m): [] for c in CHARGER_IDS for m in M
}

for u in U:
    user_type = users.loc[u, "user_type"]
    input_charger_id = int(users.loc[u, "assigned_charger"])
    duration_min = int(users.loc[u, "session_duration_min"])

    for s in candidate_starts_by_user[u]:
        start_min = option_start_minute(u, s)
        end_min = min(MINUTES_PER_DAY, start_min + duration_min)

        for m in range(max(0, start_min), max(0, end_min)):
            active_candidates_by_minute[m].append((u, s))

            if is_elastic_user(user_type):
                for c in CHARGER_IDS:
                    elastic_active_candidates_by_charger_minute[(c, m)].append(
                        (u, s, c)
                    )
            else:
                fixed_active_candidates_by_charger_minute[
                    (input_charger_id, m)
                ].append((u, s))

        for t in T:
            ov = overlap_minutes(start_min, end_min, t * 15, (t + 1) * 15)

            if ov > 0:
                frac = ov / 15.0
                slot_overlap_fraction[(u, s, t)] = frac
                active_candidates_by_slot[t].append((u, s))

                if is_primary_user(user_type):
                    primary_active_candidates_by_slot[t].append((u, s))
                else:
                    secondary_active_candidates_by_slot[t].append((u, s))

                    if is_elastic_user(user_type):
                        elastic_active_candidates_by_slot[t].append((u, s))
                    else:
                        dynamic_secondary_active_candidates_by_slot[t].append((u, s))

# ============================================================
# BEFORE OPTIMIZATION LOAD AND EXACT-MINUTE VALIDATION
# ============================================================
ev_load_before = np.zeros(N)
primary_load_before = np.zeros(N)
dynamic_secondary_load_before = np.zeros(N)
elastic_load_before = np.zeros(N)
secondary_load_before = np.zeros(N)

active_user_count_before_exact_minute = np.zeros(MINUTES_PER_DAY)
station_power_before_exact_minute = np.zeros(MINUTES_PER_DAY)

charger_count_before_exact = {(c, m): 0 for c in CHARGER_IDS for m in M}
charger_power_before_exact = {(c, m): 0.0 for c in CHARGER_IDS for m in M}

for u in U:
    start_min = int(users.loc[u, "original_start_minute"])
    end_min = int(users.loc[u, "original_end_minute"])
    power = float(users.loc[u, "session_power_kW"])
    user_type = users.loc[u, "user_type"]
    charger_id = int(users.loc[u, "assigned_charger"])

    for t in T:
        ov = overlap_minutes(start_min, end_min, t * 15, (t + 1) * 15)

        if ov > 0:
            avg_power = power * ov / 15.0
            ev_load_before[t] += avg_power

            if is_primary_user(user_type):
                primary_load_before[t] += avg_power
            elif is_elastic_user(user_type):
                elastic_load_before[t] += avg_power
            else:
                dynamic_secondary_load_before[t] += avg_power

            secondary_load_before[t] = (
                dynamic_secondary_load_before[t]
                + elastic_load_before[t]
            )

    for m in range(max(0, start_min), min(MINUTES_PER_DAY, end_min)):
        active_user_count_before_exact_minute[m] += 1
        station_power_before_exact_minute[m] += power
        charger_count_before_exact[(charger_id, m)] += 1
        charger_power_before_exact[(charger_id, m)] += power

before_charger_user_violations = sum(
    1 for c in CHARGER_IDS for m in M if charger_count_before_exact[(c, m)] > 1
)

before_charger_power_violations = sum(
    1 for c in CHARGER_IDS for m in M
    if charger_power_before_exact[(c, m)] > CHARGER_PILE_RATED_POWER_KW + 1e-6
)

before_station_count_violations = int(
    np.sum(active_user_count_before_exact_minute > NUMBER_OF_CHARGER_PILES)
)

before_station_power_violations = int(
    np.sum(station_power_before_exact_minute > STATION_POWER_CAPACITY + 1e-6)
)

print("\nExact-minute input validation:")
print("Before charger one-user violations:", before_charger_user_violations)
print("Before charger power violations:", before_charger_power_violations)
print("Before station count violations:", before_station_count_violations)
print("Before station power violations:", before_station_power_violations)
print("Max exact active EV count before:", int(np.max(active_user_count_before_exact_minute)))
print("Max exact charger power before:", round(max(charger_power_before_exact.values()), 3), "kW")

# ============================================================
# SOLAR CAP AND SOLAR SHIFT SCORE
# ============================================================
solar_max_allowed_tariff = np.zeros(N)
solar_cap_status = []

for t in T:
    cap_value, cap_text = get_solar_cap_value(pv[t], primary_load_before[t])
    solar_max_allowed_tariff[t] = cap_value
    solar_cap_status.append(cap_text)

# ------------------------------------------------------------
# RULE-BASED BESS OPERATION BEFORE OPTIMIZATION
# ------------------------------------------------------------
# Requested baseline dispatch:
#   1. If PV generation is greater than EV load, use the surplus PV
#      to charge the BESS.
#   2. If EV load is greater than PV generation, discharge the BESS
#      to support the remaining EV demand.
#   3. No grid-to-BESS charging is used before optimization.
#   4. No BESS-to-grid export is used before optimization.
#   5. BESS power, efficiency, and SOC limits are enforced.
#
# Sign convention for bess_before:
#   positive = BESS discharge
#   negative = BESS charge

bess_before = np.zeros(N)
bess_ch_before = np.zeros(N)
bess_dis_before = np.zeros(N)
soc_before = np.zeros(N)

grid_import_before = np.zeros(N)
pv_excess_before = np.zeros(N)

soc_previous = SOC_INITIAL

for t in T:
    pv_power = float(pv[t])
    ev_power = float(ev_load_before[t])

    # --------------------------------------------------------
    # PV is greater than EV demand: charge the BESS from PV.
    # --------------------------------------------------------
    if pv_power > ev_power:
        pv_surplus = pv_power - ev_power

        # Maximum charging power allowed by the remaining SOC space.
        max_charge_from_soc = max(
            0.0,
            (SOC_MAX - soc_previous) / (ETA_CH * dt),
        )

        charge_power = min(
            pv_surplus,
            P_CH_MAX,
            max_charge_from_soc,
        )

        bess_ch_before[t] = charge_power
        bess_dis_before[t] = 0.0
        bess_before[t] = -charge_power

        # No grid import is required while PV exceeds the EV load.
        grid_import_before[t] = 0.0

        # Any PV remaining after EV supply and BESS charging is available
        # for normal/non-dispatchable export before optimization.
        pv_excess_before[t] = max(
            pv_surplus - charge_power,
            0.0,
        )

        soc_previous = (
            soc_previous
            + ETA_CH * charge_power * dt
        )

    # --------------------------------------------------------
    # EV demand is greater than PV: discharge BESS to the EVs.
    # --------------------------------------------------------
    elif ev_power > pv_power:
        ev_deficit = ev_power - pv_power

        # Maximum discharge power permitted while maintaining SOC_MIN.
        max_discharge_from_soc = max(
            0.0,
            (soc_previous - SOC_MIN) * ETA_DIS / dt,
        )

        discharge_power = min(
            ev_deficit,
            P_DIS_MAX,
            max_discharge_from_soc,
        )

        bess_ch_before[t] = 0.0
        bess_dis_before[t] = discharge_power
        bess_before[t] = discharge_power

        # The grid supplies only the EV deficit remaining after BESS support.
        grid_import_before[t] = max(
            ev_deficit - discharge_power,
            0.0,
        )

        pv_excess_before[t] = 0.0

        soc_previous = (
            soc_previous
            - discharge_power * dt / ETA_DIS
        )

    # --------------------------------------------------------
    # PV exactly equals EV demand: BESS remains idle.
    # --------------------------------------------------------
    else:
        bess_ch_before[t] = 0.0
        bess_dis_before[t] = 0.0
        bess_before[t] = 0.0
        grid_import_before[t] = 0.0
        pv_excess_before[t] = 0.0

    # Numerical protection for the SOC bounds.
    soc_previous = min(
        max(soc_previous, SOC_MIN),
        SOC_MAX,
    )

    # soc_before[t] is the BESS SOC at the end of interval t.
    soc_before[t] = soc_previous

# ------------------------------------------------------------
# POST-OPTIMIZATION GRID-IMPORT PEAK CAP
# ------------------------------------------------------------
# This cap is calculated from the actual pre-optimization grid-import profile.
# It prevents low-price grid-to-BESS charging from creating a new demand peak.
GRID_IMPORT_PEAK_BEFORE_KW = float(np.max(grid_import_before))

if ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION:
    OPTIMIZED_GRID_IMPORT_MAX_KW = min(
        GRID_IMPORT_MAX_KW,
        GRID_IMPORT_PEAK_BEFORE_KW
        * (
            1.0
            - MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE
        ),
    )
else:
    OPTIMIZED_GRID_IMPORT_MAX_KW = GRID_IMPORT_MAX_KW

if OPTIMIZED_GRID_IMPORT_MAX_KW <= 0:
    raise ValueError("OPTIMIZED_GRID_IMPORT_MAX_KW must be positive.")

print("\nGrid-import peak protection:")
print(
    "Pre-optimization maximum grid import:",
    round(GRID_IMPORT_PEAK_BEFORE_KW, 3),
    "kW",
)
print(
    "Minimum required peak reduction:",
    round(
        MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE * 100.0,
        2,
    )
    if ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION
    else 0.0,
    "%",
)
print(
    "Grid-import cap used in all optimization stages:",
    round(OPTIMIZED_GRID_IMPORT_MAX_KW, 3),
    "kW",
)

if ALLOW_PV_EXPORT:
    pv_export_before = np.minimum(pv_excess_before, PV_EXPORT_MAX_KW)
else:
    pv_export_before = np.zeros(N)

pv_curtailed_before = np.maximum(pv_excess_before - pv_export_before, 0)

primary_revenue_before = np.sum(primary_load_before * primary_tariff * dt)
dynamic_secondary_revenue_before = np.sum(
    dynamic_secondary_load_before * secondary_tariff_before * dt
)
pv_export_revenue_before = np.sum(pv_export_before * grid_export_price * dt)
grid_cost_before = np.sum(grid_import_before * grid_buy * dt)

existing_secondary_avg_tariff = (
    np.sum(dynamic_secondary_load_before * secondary_tariff_before * dt)
    / max(np.sum(dynamic_secondary_load_before * dt), 1e-6)
)

solar_shift_score = np.zeros(N)

for t in T:
    pv_excess = max(pv[t] - primary_load_before[t], 0.0)
    solar_shift_score[t] = min(
        pv_excess / max(HIGH_SOLAR_EXCESS_MARGIN, 1e-6),
        1.0,
    )

# Candidate-specific booked elastic tariff. Each price is fixed before the
# solver chooses the start, so the formulation remains a MILP.
#
# For candidate session (u, s):
#   elastic price = session-average primary tariff
#                   - effective flexibility discount
#                   - session-average solar discount
#
# The effective flexibility discount contains a 25% basic reward and a 75%
# portion scaled by the complete session's average solar score. This avoids
# granting the full flexibility benefit to night-only charging windows.
# The tariff remains subject to the absolute minimum elastic tariff.
elastic_price_by_candidate = {}
elastic_base_rate_by_candidate = {}
elastic_solar_score_by_candidate = {}
elastic_solar_discount_by_candidate = {}

# Potential flexibility discount is based only on the amount of usable
# scheduling freedom provided by the customer. The actual discount applied to
# a candidate session is smaller at night and increases with solar placement.
elastic_flex_discount_potential_by_user = {}
elastic_effective_flex_discount_by_candidate = {}
elastic_basic_flex_reward_by_candidate = {}
elastic_solar_scaled_flex_reward_by_candidate = {}

elastic_baseline_price_by_user = {}
elastic_baseline_base_rate_by_user = {}
elastic_baseline_effective_flex_discount_by_user = {}
elastic_baseline_basic_flex_reward_by_user = {}
elastic_baseline_solar_scaled_flex_reward_by_user = {}


def minute_weighted_session_average(values_by_slot, start_minute, end_minute):
    """Return the minute-weighted average of a 96-slot signal over a session."""
    weighted_value = 0.0
    total_minutes = 0.0

    for t in T:
        ov = overlap_minutes(start_minute, end_minute, t * 15, (t + 1) * 15)
        if ov > 0:
            weighted_value += float(values_by_slot[t]) * ov
            total_minutes += ov

    if total_minutes <= 0:
        raise ValueError(
            f"Session {minute_to_time(start_minute)}-"
            f"{minute_to_time(end_minute)} has no overlap with the model day."
        )

    return weighted_value / total_minutes


def average_solar_score_for_session(start_minute, end_minute):
    return minute_weighted_session_average(
        solar_shift_score,
        start_minute,
        end_minute,
    )


def average_primary_tariff_for_session(start_minute, end_minute):
    return minute_weighted_session_average(
        primary_tariff,
        start_minute,
        end_minute,
    )


def calculate_effective_flexibility_discount(
    flexibility_discount_potential,
    average_solar_score,
):
    """
    Apply Option 2: give a small guaranteed flexibility reward and scale the
    remaining flexibility reward by the average solar score of the selected
    complete charging session.

    D_flex_eff = D_flex_potential *
                 [alpha + (1 - alpha) * S_session]

    With alpha = 0.25:
      - a night-only session with S_session = 0 receives 25% of the potential
        flexibility discount;
      - a fully solar-rich session with S_session = 1 receives 100%.
    """
    bounded_solar_score = max(0.0, min(float(average_solar_score), 1.0))
    alpha = max(0.0, min(float(ELASTIC_BASIC_FLEX_REWARD_FRACTION), 1.0))

    basic_reward = float(flexibility_discount_potential) * alpha
    solar_scaled_reward = (
        float(flexibility_discount_potential)
        * (1.0 - alpha)
        * bounded_solar_score
    )
    effective_discount = basic_reward + solar_scaled_reward

    return effective_discount, basic_reward, solar_scaled_reward


def calculate_elastic_session_tariff(
    primary_session_base_rate,
    flexibility_discount_potential,
    average_solar_score,
):
    """
    Calculate one fixed elastic tariff for the complete candidate session.

    final elastic tariff = session-average primary tariff
                           - effective flexibility discount
                           - solar discount

    The final tariff can never exceed the corresponding primary-session base
    and cannot fall below ELASTIC_MIN_RATE_LKR_KWH.
    """
    bounded_solar_score = max(0.0, min(float(average_solar_score), 1.0))

    (
        effective_flex_discount,
        basic_flex_reward,
        solar_scaled_flex_reward,
    ) = calculate_effective_flexibility_discount(
        flexibility_discount_potential,
        bounded_solar_score,
    )

    solar_discount = (
        ELASTIC_MAX_SOLAR_DISCOUNT_LKR_KWH
        * bounded_solar_score
    )

    discounted_price = (
        float(primary_session_base_rate)
        - effective_flex_discount
        - solar_discount
    )

    final_price = min(
        float(primary_session_base_rate),
        max(ELASTIC_MIN_RATE_LKR_KWH, discounted_price),
    )

    return (
        final_price,
        solar_discount,
        effective_flex_discount,
        basic_flex_reward,
        solar_scaled_flex_reward,
    )


for u in elastic_user_indices:
    # Maximum flexibility discount available to this customer before the
    # candidate-specific solar scaling is applied.
    flexibility_hours = float(users.loc[u, "elastic_flexibility_hours"])
    flexibility_discount_potential = min(
        ELASTIC_MAX_FLEX_DISCOUNT_LKR_KWH,
        ELASTIC_FLEX_DISCOUNT_LKR_PER_HOUR * flexibility_hours,
    )
    elastic_flex_discount_potential_by_user[u] = (
        flexibility_discount_potential
    )

    # Before-optimization elastic price: apply the same pricing rule to the
    # user's original session for a consistent before/after comparison.
    original_start_minute = int(users.loc[u, "original_start_minute"])
    original_end_minute = int(users.loc[u, "original_end_minute"])

    baseline_primary_base_rate = average_primary_tariff_for_session(
        original_start_minute,
        original_end_minute,
    )
    baseline_solar_score = average_solar_score_for_session(
        original_start_minute,
        original_end_minute,
    )
    (
        baseline_price,
        _,
        baseline_effective_flex_discount,
        baseline_basic_flex_reward,
        baseline_solar_scaled_flex_reward,
    ) = calculate_elastic_session_tariff(
        baseline_primary_base_rate,
        flexibility_discount_potential,
        baseline_solar_score,
    )

    elastic_baseline_base_rate_by_user[u] = baseline_primary_base_rate
    elastic_baseline_price_by_user[u] = baseline_price
    elastic_baseline_effective_flex_discount_by_user[u] = (
        baseline_effective_flex_discount
    )
    elastic_baseline_basic_flex_reward_by_user[u] = (
        baseline_basic_flex_reward
    )
    elastic_baseline_solar_scaled_flex_reward_by_user[u] = (
        baseline_solar_scaled_flex_reward
    )

    # Candidate price: use the minute-weighted primary tariff and solar score
    # across the WHOLE candidate charging session, not only its first slot.
    for s in candidate_starts_by_user[u]:
        start_minute = option_start_minute(u, s)
        end_minute = start_minute + int(users.loc[u, "session_duration_min"])

        primary_session_base_rate = average_primary_tariff_for_session(
            start_minute,
            end_minute,
        )
        average_solar_score = average_solar_score_for_session(
            start_minute,
            end_minute,
        )
        (
            candidate_price,
            solar_discount,
            effective_flex_discount,
            basic_flex_reward,
            solar_scaled_flex_reward,
        ) = calculate_elastic_session_tariff(
            primary_session_base_rate,
            flexibility_discount_potential,
            average_solar_score,
        )

        elastic_price_by_candidate[(u, s)] = candidate_price
        elastic_base_rate_by_candidate[(u, s)] = primary_session_base_rate
        elastic_solar_score_by_candidate[(u, s)] = average_solar_score
        elastic_solar_discount_by_candidate[(u, s)] = solar_discount
        elastic_effective_flex_discount_by_candidate[(u, s)] = (
            effective_flex_discount
        )
        elastic_basic_flex_reward_by_candidate[(u, s)] = basic_flex_reward
        elastic_solar_scaled_flex_reward_by_candidate[(u, s)] = (
            solar_scaled_flex_reward
        )

elastic_revenue_before = sum(
    float(users.loc[u, "charger_energy_kWh"])
    * elastic_baseline_price_by_user[u]
    for u in elastic_user_indices
)
secondary_revenue_before = (
    dynamic_secondary_revenue_before
    + elastic_revenue_before
)
profit_before = (
    primary_revenue_before
    + secondary_revenue_before
    + pv_export_revenue_before
    - grid_cost_before
)

# Maximum physically available dynamic-secondary power in each slot.
# Each EV is counted only once, even when several of its candidate start
# options overlap the same slot. Only one start option can ultimately be
# selected for an EV, so summing every (user, candidate-start) pair would
# artificially multiply the available demand.
secondary_potential_power = np.zeros(N)

for t in T:
    maximum_contribution_by_user = {}

    for (u, s) in dynamic_secondary_active_candidates_by_slot[t]:
        frac = slot_overlap_fraction.get((u, s, t), 0.0)
        possible_power = (
            float(users.loc[u, "session_power_kW"])
            * frac
        )

        maximum_contribution_by_user[u] = max(
            maximum_contribution_by_user.get(u, 0.0),
            possible_power,
        )

    secondary_potential_power[t] = sum(
        maximum_contribution_by_user.values()
    )

# A smooth solar-based reference tariff used by the soft Stage 3 penalty.
# No tariff is prohibited. The optimizer may deviate from this target when
# the additional revenue or another operating benefit justifies the penalty.
MIN_SECONDARY_TARIFF = float(min(secondary_tariff_levels))
MAX_SECONDARY_TARIFF = float(max(secondary_tariff_levels))
SECONDARY_TARIFF_RANGE = max(
    MAX_SECONDARY_TARIFF - MIN_SECONDARY_TARIFF,
    1e-6,
)

solar_target_tariff = (
    MAX_SECONDARY_TARIFF
    - solar_shift_score * SECONDARY_TARIFF_RANGE
)

# ============================================================
# PYOMO MODEL BUILDER
# ============================================================
def build_model(stage, pv_to_ev_min=None, pv_to_bess_min=None):
    model = pyo.ConcreteModel(name=f"Exact_Minute_EV_FCS_{stage}")

    K = list(range(len(secondary_tariff_levels)))

    model.T = pyo.Set(initialize=T)
    model.K = pyo.Set(initialize=K)
    model.DISPATCH_BLOCKS = pyo.Set(initialize=DISPATCH_BLOCK_STARTS)
    model.U = pyo.Set(initialize=U)
    model.US = pyo.Set(dimen=2, initialize=candidate_start_pairs)
    model.USC_ELASTIC = pyo.Set(
        dimen=3,
        initialize=elastic_candidate_start_charger_triples,
    )

    # X_start selects the whole-session start for every user.
    model.X_start = pyo.Var(model.US, domain=pyo.Binary)

    # For elastic users only, this variable jointly assigns the selected
    # start option to exactly one physical charger for the complete session.
    model.X_elastic_start_charger = pyo.Var(
        model.USC_ELASTIC,
        domain=pyo.Binary,
    )

    model.x_tariff = pyo.Var(model.T, model.K, domain=pyo.Binary)
    model.P_secondary_tariff = pyo.Var(model.T, model.K, domain=pyo.NonNegativeReals)

    model.PV_to_EV = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.PV_to_BESS = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.PV_to_Grid = pyo.Var(model.T, domain=pyo.NonNegativeReals)

    # Total point-of-common-coupling export is split into mutually exclusive
    # dispatchable and non-dispatchable market products. It may be supplied by
    # direct PV export and/or BESS discharge.
    model.PV_Export = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.PV_Export_Dispatchable = pyo.Var(
        model.T,
        domain=pyo.NonNegativeReals,
    )
    model.PV_Export_Nondispatchable = pyo.Var(
        model.T,
        domain=pyo.NonNegativeReals,
    )

    model.Dispatch_Block_Selected = pyo.Var(
        model.DISPATCH_BLOCKS,
        domain=pyo.Binary,
    )
    model.Dispatch_Block_Rate = pyo.Var(
        model.DISPATCH_BLOCKS,
        domain=pyo.NonNegativeReals,
    )

    model.PV_Curtailed = pyo.Var(model.T, domain=pyo.NonNegativeReals)

    model.Grid_to_EV = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.Grid_to_BESS = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.BESS_to_EV = pyo.Var(model.T, domain=pyo.NonNegativeReals)
    model.BESS_to_Grid = pyo.Var(model.T, domain=pyo.NonNegativeReals)

    model.SOC = pyo.Var(
        model.T,
        domain=pyo.NonNegativeReals,
        bounds=(SOC_MIN, SOC_MAX),
    )

    model.grid_mode = pyo.Var(model.T, domain=pyo.Binary)
    model.bess_mode = pyo.Var(model.T, domain=pyo.Binary)

    # 1 when the optimized EV load is greater than or equal to PV generation,
    # so there is no PV surplus available for BESS charging in the interval.
    model.no_solar_excess_mode = pyo.Var(model.T, domain=pyo.Binary)

    model.constraints = pyo.ConstraintList()

    # One-hour dispatchable-export commitment variables. A selected hour uses
    # one constant export rate across all four constituent 15-minute slots.
    for block_start in DISPATCH_BLOCK_STARTS:
        model.constraints.add(
            model.Dispatch_Block_Rate[block_start]
            <= MAX_DISPATCHABLE_EXPORT_KW
            * model.Dispatch_Block_Selected[block_start]
        )
        # If the hour is selected as dispatchable, the constant committed
        # export rate must be at least 1,000 kW. When the hour is not selected,
        # the rate is forced to zero by the upper-bound constraint above.
        model.constraints.add(
            model.Dispatch_Block_Rate[block_start]
            >= MIN_DISPATCHABLE_EXPORT_KW
            * model.Dispatch_Block_Selected[block_start]
        )

    model.constraints.add(
        pyo.quicksum(
            model.Dispatch_Block_Selected[block_start]
            for block_start in DISPATCH_BLOCK_STARTS
        )
        <= MAX_DISPATCHABLE_BLOCKS_PER_DAY
    )

    primary_load_expr_by_t = {}
    dynamic_secondary_load_expr_by_t = {}
    elastic_load_expr_by_t = {}
    secondary_load_expr_by_t = {}
    total_ev_load_expr_by_t = {}

    # Each EV selects exactly one whole-session start option.
    for u in U:
        model.constraints.add(
            pyo.quicksum(
                model.X_start[u, s]
                for s in candidate_starts_by_user[u]
            )
            ==
            1
        )

    # Link each elastic start decision to exactly one charger assignment.
    # If X_start[u,s] = 1, one and only one charger c must satisfy
    # X_elastic_start_charger[u,s,c] = 1. If the start is not selected,
    # all charger-assignment variables for that start are zero.
    for u in elastic_user_indices:
        for s in candidate_starts_by_user[u]:
            model.constraints.add(
                pyo.quicksum(
                    model.X_elastic_start_charger[u, s, c]
                    for c in CHARGER_IDS
                )
                ==
                model.X_start[u, s]
            )

    # Limit shifted secondary users.
    if LIMIT_SHIFTED_SECONDARY_USERS:
        shifted_secondary_terms = []

        for u in U:
            if is_dynamic_secondary_user(users.loc[u, "user_type"]):
                original_start = int(users.loc[u, "original_start_slot"])

                for s in candidate_starts_by_user[u]:
                    if s != original_start:
                        shifted_secondary_terms.append(model.X_start[u, s])

        if len(shifted_secondary_terms) > 0:
            model.constraints.add(
                pyo.quicksum(shifted_secondary_terms)
                <=
                MAX_SHIFTED_SECONDARY_USERS_ALLOWED
            )

    # Exact-minute physical charger constraints.
    # Primary and dynamic-secondary users remain on their input charger.
    # Elastic users may use any charger, but one selected (u,s,c) variable
    # reserves that same charger for every minute of the whole session.
    if ENABLE_EXACT_MINUTE_CHARGER_CONSTRAINTS:
        for c in CHARGER_IDS:
            for m in M:
                fixed_active_list = (
                    fixed_active_candidates_by_charger_minute[(c, m)]
                )
                elastic_active_list = (
                    elastic_active_candidates_by_charger_minute[(c, m)]
                )

                if len(fixed_active_list) > 0 or len(elastic_active_list) > 0:
                    model.constraints.add(
                        pyo.quicksum(
                            model.X_start[u, s]
                            for (u, s) in fixed_active_list
                        )
                        +
                        pyo.quicksum(
                            model.X_elastic_start_charger[u, s, c_option]
                            for (u, s, c_option) in elastic_active_list
                        )
                        <=
                        1
                    )

                    model.constraints.add(
                        pyo.quicksum(
                            float(users.loc[u, "session_power_kW"])
                            * model.X_start[u, s]
                            for (u, s) in fixed_active_list
                        )
                        +
                        pyo.quicksum(
                            float(users.loc[u, "session_power_kW"])
                            * model.X_elastic_start_charger[u, s, c_option]
                            for (u, s, c_option) in elastic_active_list
                        )
                        <=
                        CHARGER_PILE_RATED_POWER_KW
                    )

    if ENABLE_EXACT_MINUTE_STATION_CONSTRAINTS:
        for m in M:
            active_list = active_candidates_by_minute[m]

            if len(active_list) > 0:
                model.constraints.add(
                    pyo.quicksum(
                        model.X_start[u, s]
                        for (u, s) in active_list
                    )
                    <=
                    NUMBER_OF_CHARGER_PILES
                )

                model.constraints.add(
                    pyo.quicksum(
                        float(users.loc[u, "session_power_kW"])
                        * model.X_start[u, s]
                        for (u, s) in active_list
                    )
                    <=
                    STATION_POWER_CAPACITY
                )

    # Slot-wise energy/PV/grid/BESS constraints with fractional overlap.
    for t in T:
        primary_terms = []

        for (u, s) in primary_active_candidates_by_slot[t]:
            frac = slot_overlap_fraction.get((u, s, t), 0.0)
            primary_terms.append(
                float(users.loc[u, "session_power_kW"])
                * frac
                * model.X_start[u, s]
            )

        dynamic_secondary_terms = []

        for (u, s) in dynamic_secondary_active_candidates_by_slot[t]:
            frac = slot_overlap_fraction.get((u, s, t), 0.0)
            dynamic_secondary_terms.append(
                float(users.loc[u, "session_power_kW"])
                * frac
                * model.X_start[u, s]
            )

        elastic_terms = []

        for (u, s) in elastic_active_candidates_by_slot[t]:
            frac = slot_overlap_fraction.get((u, s, t), 0.0)
            elastic_terms.append(
                float(users.loc[u, "session_power_kW"])
                * frac
                * model.X_start[u, s]
            )

        primary_load_expr = pyomo_sum_or_zero(primary_terms, model.grid_mode[t])
        dynamic_secondary_load_expr = pyomo_sum_or_zero(
            dynamic_secondary_terms,
            model.grid_mode[t],
        )
        elastic_load_expr = pyomo_sum_or_zero(elastic_terms, model.grid_mode[t])
        secondary_load_expr = dynamic_secondary_load_expr + elastic_load_expr
        total_ev_load_expr = primary_load_expr + secondary_load_expr

        primary_load_expr_by_t[t] = primary_load_expr
        dynamic_secondary_load_expr_by_t[t] = dynamic_secondary_load_expr
        elastic_load_expr_by_t[t] = elastic_load_expr
        secondary_load_expr_by_t[t] = secondary_load_expr
        total_ev_load_expr_by_t[t] = total_ev_load_expr

        model.constraints.add(
            total_ev_load_expr <= STATION_POWER_CAPACITY
        )

        if ENABLE_LOAD_RAMP and t > 0:
            previous_total_ev_load_expr = total_ev_load_expr_by_t[t - 1]

            model.constraints.add(
                total_ev_load_expr - previous_total_ev_load_expr
                <=
                LOAD_RAMP_LIMIT_KW
            )

            model.constraints.add(
                previous_total_ev_load_expr - total_ev_load_expr
                <=
                LOAD_RAMP_LIMIT_KW
            )

        model.constraints.add(
            pyo.quicksum(model.x_tariff[t, k] for k in K) == 1
        )

        model.constraints.add(
            dynamic_secondary_load_expr
            ==
            pyo.quicksum(model.P_secondary_tariff[t, k] for k in K)
        )

        for k in K:
            tariff = secondary_tariff_levels[k]

            model.constraints.add(
                model.P_secondary_tariff[t, k]
                <=
                STATION_POWER_CAPACITY * model.x_tariff[t, k]
            )

            model.constraints.add(
                model.P_secondary_tariff[t, k]
                <=
                secondary_potential_power[t]
                * attraction_factor[tariff]
                * model.x_tariff[t, k]
            )

        if ENABLE_PRICE_RAMP and t > 0:
            tariff_now = pyo.quicksum(
                secondary_tariff_levels[k] * model.x_tariff[t, k]
                for k in K
            )

            tariff_previous = pyo.quicksum(
                secondary_tariff_levels[k] * model.x_tariff[t - 1, k]
                for k in K
            )

            model.constraints.add(
                tariff_now - tariff_previous
                <=
                PRICE_RAMP_LIMIT_LKR_KWH
            )

            model.constraints.add(
                tariff_previous - tariff_now
                <=
                PRICE_RAMP_LIMIT_LKR_KWH
            )

        if ENABLE_SOLAR_EXCESS_TARIFF_CAP:
            max_allowed_tariff = solar_max_allowed_tariff[t]

            for k in K:
                tariff = secondary_tariff_levels[k]

                if tariff > max_allowed_tariff:
                    model.constraints.add(
                        model.x_tariff[t, k] == 0
                    )

        model.constraints.add(
            model.PV_to_EV[t]
            + model.Grid_to_EV[t]
            + model.BESS_to_EV[t]
            ==
            total_ev_load_expr
        )

        # Each interval belongs to one clock-hour dispatchable-export block.
        block_start = (t // DISPATCH_BLOCK_SLOTS) * DISPATCH_BLOCK_SLOTS

        # A selected dispatchable block delivers one constant power level in
        # every 15-minute interval of the complete hour.
        model.constraints.add(
            model.PV_Export_Dispatchable[t]
            == model.Dispatch_Block_Rate[block_start]
        )

        # The two market products are mutually exclusive. When the complete
        # hour is selected as dispatchable, non-dispatchable export is zero.
        model.constraints.add(
            model.PV_Export_Nondispatchable[t]
            <= PV_EXPORT_MAX_KW
            * (1 - model.Dispatch_Block_Selected[block_start])
        )

        model.constraints.add(
            model.PV_Export[t]
            == model.PV_Export_Dispatchable[t]
            + model.PV_Export_Nondispatchable[t]
        )

        # Total grid export at the PCC may originate from PV and/or the BESS.
        model.constraints.add(
            model.PV_Export[t]
            == model.PV_to_Grid[t]
            + model.BESS_to_Grid[t]
        )

        # PV source balance. BESS-to-grid is excluded because it is supplied
        # from stored energy and is represented through the SOC equation.
        model.constraints.add(
            model.PV_to_EV[t]
            + model.PV_to_BESS[t]
            + model.PV_to_Grid[t]
            + model.PV_Curtailed[t]
            == pv[t]
        )

        model.constraints.add(
            model.PV_to_BESS[t] + model.Grid_to_BESS[t]
            <= P_CH_MAX
        )

        model.constraints.add(
            model.BESS_to_EV[t] + model.BESS_to_Grid[t]
            <= P_DIS_MAX
        )

        current_grid_import = model.Grid_to_EV[t] + model.Grid_to_BESS[t]

        model.constraints.add(
            current_grid_import <= OPTIMIZED_GRID_IMPORT_MAX_KW
        )

        # Import and export are mutually exclusive in each interval. This also
        # blocks same-slot grid-to-BESS-to-grid arbitrage.
        model.constraints.add(
            current_grid_import <= OPTIMIZED_GRID_IMPORT_MAX_KW * model.grid_mode[t]
        )

        if ALLOW_PV_EXPORT:
            model.constraints.add(
                model.PV_Export[t]
                <= PV_EXPORT_MAX_KW * (1 - model.grid_mode[t])
            )
        else:
            model.constraints.add(
                model.PV_Export[t] == 0
            )

        if ENABLE_GRID_IMPORT_RAMP and t > 0:
            previous_grid_import = (
                model.Grid_to_EV[t - 1] + model.Grid_to_BESS[t - 1]
            )

            model.constraints.add(
                current_grid_import - previous_grid_import
                <= GRID_IMPORT_RAMP_LIMIT_KW
            )

            model.constraints.add(
                previous_grid_import - current_grid_import
                <= GRID_IMPORT_RAMP_LIMIT_KW
            )

        # The BESS cannot charge and discharge simultaneously. Both charging
        # sources share the charging rating, and both discharge destinations
        # share the discharge rating.
        model.constraints.add(
            model.PV_to_BESS[t] + model.Grid_to_BESS[t]
            <= P_CH_MAX * model.bess_mode[t]
        )

        model.constraints.add(
            model.BESS_to_EV[t] + model.BESS_to_Grid[t]
            <= P_DIS_MAX * (1 - model.bess_mode[t])
        )

        # BESS-to-grid export is enabled only in the final profit stage. This
        # prevents Stages 1 and 2 from emptying the battery merely to create
        # storage space while maximizing the solar-priority objectives.
        if not ALLOW_BESS_TO_GRID or stage != "stage_3_max_profit":
            model.constraints.add(
                model.BESS_to_Grid[t] == 0
            )
        else:
            model.constraints.add(
                model.BESS_to_Grid[t] <= BESS_TO_GRID_MAX_KW
            )

        # Grid-to-BESS charging has no fixed clock-time window. It is allowed
        # only when there is no PV surplus after serving EV charging demand:
        #     optimized EV load >= PV generation.
        if not ALLOW_GRID_TO_BESS:
            model.constraints.add(
                model.Grid_to_BESS[t] == 0
            )
        else:
            model.constraints.add(
                total_ev_load_expr - pv[t]
                <= SOLAR_BALANCE_BIG_M * model.no_solar_excess_mode[t]
            )
            model.constraints.add(
                pv[t] - total_ev_load_expr
                <= SOLAR_BALANCE_BIG_M
                * (1 - model.no_solar_excess_mode[t])
            )
            model.constraints.add(
                model.Grid_to_BESS[t]
                <= P_CH_MAX * model.no_solar_excess_mode[t]
            )

        bess_charge = model.PV_to_BESS[t] + model.Grid_to_BESS[t]
        bess_discharge = model.BESS_to_EV[t] + model.BESS_to_Grid[t]

        if t == 0:
            model.constraints.add(
                model.SOC[t]
                ==
                SOC_INITIAL
                + ETA_CH * bess_charge * dt
                - bess_discharge * dt / ETA_DIS
            )
        else:
            model.constraints.add(
                model.SOC[t]
                ==
                model.SOC[t - 1]
                + ETA_CH * bess_charge * dt
                - bess_discharge * dt / ETA_DIS
            )

    model.constraints.add(
        model.SOC[N - 1] >= SOC_INITIAL
    )

    if ENFORCE_SECONDARY_AVG_TARIFF_LIMIT:
        secondary_dynamic_revenue_for_avg = pyo.quicksum(
            secondary_tariff_levels[k]
            * model.P_secondary_tariff[t, k]
            * dt
            for t in T
            for k in K
        )

        model.constraints.add(
            secondary_dynamic_revenue_for_avg
            <=
            MAX_SECONDARY_AVG_TARIFF_MULTIPLIER
            * existing_secondary_avg_tariff
            * max(np.sum(dynamic_secondary_load_before * dt), 1e-6)
        )

    if pv_to_ev_min is not None:
        model.constraints.add(
            pyo.quicksum(model.PV_to_EV[t] * dt for t in T)
            >=
            pv_to_ev_min
        )

    if pv_to_bess_min is not None:
        model.constraints.add(
            pyo.quicksum(model.PV_to_BESS[t] * dt for t in T)
            >=
            pv_to_bess_min
        )

    primary_revenue = pyo.quicksum(
        primary_tariff[t]
        * primary_load_expr_by_t[t]
        * dt
        for t in T
    )

    dynamic_secondary_revenue = pyo.quicksum(
        secondary_tariff_levels[k]
        * model.P_secondary_tariff[t, k]
        * dt
        for t in T
        for k in K
    )

    elastic_revenue = pyo.quicksum(
        float(users.loc[u, "charger_energy_kWh"])
        * elastic_price_by_candidate[(u, s)]
        * model.X_start[u, s]
        for u in elastic_user_indices
        for s in candidate_starts_by_user[u]
    )

    secondary_revenue = dynamic_secondary_revenue + elastic_revenue

    nondispatchable_export_revenue = pyo.quicksum(
        grid_export_price[t]
        * model.PV_Export_Nondispatchable[t]
        * dt
        for t in T
    )

    dispatchable_export_revenue = pyo.quicksum(
        grid_dispatchable_export_price[t]
        * model.PV_Export_Dispatchable[t]
        * dt
        for t in T
    )

    pv_export_revenue = (
        nondispatchable_export_revenue
        + dispatchable_export_revenue
    )

    grid_import_cost = pyo.quicksum(
        grid_buy[t]
        * (model.Grid_to_EV[t] + model.Grid_to_BESS[t])
        * dt
        for t in T
    )

    pv_curtailment_cost = pyo.quicksum(
        PV_CURTAILMENT_PENALTY
        * model.PV_Curtailed[t]
        * dt
        for t in T
    )

    # Soft price-alignment penalty.
    # At high solar surplus, solar_target_tariff approaches the minimum
    # tariff. At low solar surplus, it approaches the maximum tariff.
    # Because the coefficient multiplies P_secondary_tariff, the expression
    # remains linear and applies only to secondary energy actually delivered.
    if ENABLE_SOLAR_PRICE_ALIGNMENT:
        solar_price_alignment_cost = pyo.quicksum(
            SOLAR_PRICE_ALIGNMENT_PENALTY_LKR_PER_KWH
            * (
                abs(
                    float(secondary_tariff_levels[k])
                    - float(solar_target_tariff[t])
                )
                / SECONDARY_TARIFF_RANGE
            )
            * model.P_secondary_tariff[t, k]
            * dt
            for t in T
            for k in K
        )
    else:
        solar_price_alignment_cost = 0

    if ENABLE_SECONDARY_SOLAR_SHIFT_REWARD:
        secondary_solar_shift_reward_terms = []
        secondary_non_solar_penalty_terms = []

        for t in T:
            for (u, s) in secondary_active_candidates_by_slot[t]:
                frac = slot_overlap_fraction.get((u, s, t), 0.0)
                weight = TYPE_SOLAR_SHIFT_WEIGHT.get(str(users.loc[u, "user_type"]), 1.0)
                power = float(users.loc[u, "session_power_kW"])

                secondary_solar_shift_reward_terms.append(
                    SOLAR_SHIFT_REWARD_LKR_PER_KWH
                    * weight
                    * solar_shift_score[t]
                    * power
                    * frac
                    * model.X_start[u, s]
                    * dt
                )

                secondary_non_solar_penalty_terms.append(
                    NON_SOLAR_SECONDARY_PENALTY_LKR_PER_KWH
                    * weight
                    * (1.0 - solar_shift_score[t])
                    * power
                    * frac
                    * model.X_start[u, s]
                    * dt
                )

        secondary_solar_shift_reward = pyomo_sum_or_zero(
            secondary_solar_shift_reward_terms,
            model.grid_mode[0],
        )

        secondary_non_solar_penalty = pyomo_sum_or_zero(
            secondary_non_solar_penalty_terms,
            model.grid_mode[0],
        )
    else:
        secondary_solar_shift_reward = 0
        secondary_non_solar_penalty = 0

    secondary_shift_discomfort_cost = pyo.quicksum(
        SHIFTING_DISCOMFORT_COST_LKR_PER_SESSION
        * model.X_start[u, s]
        for u in U
        for s in candidate_starts_by_user[u]
        if is_dynamic_secondary_user(users.loc[u, "user_type"])
        and s != int(users.loc[u, "original_start_slot"])
    )

    profit_objective = (
        primary_revenue
        + secondary_revenue
        + pv_export_revenue
        - grid_import_cost
        - pv_curtailment_cost
        - solar_price_alignment_cost
        + secondary_solar_shift_reward
        - secondary_non_solar_penalty
        - secondary_shift_discomfort_cost
    )

    if stage == "stage_1_max_pv_to_ev":
        objective_expr = pyo.quicksum(model.PV_to_EV[t] * dt for t in T)
    elif stage == "stage_2_max_pv_to_bess":
        objective_expr = (
            1000.0
            * pyo.quicksum(
                model.PV_to_BESS[t] * dt
                for t in T
            )
            + pyo.quicksum(
                (
                    grid_export_price[t]
                    * model.PV_Export_Nondispatchable[t]
                    + grid_dispatchable_export_price[t]
                    * model.PV_Export_Dispatchable[t]
                )
                * dt
                for t in T
            )
            - 200.0
            * pyo.quicksum(
                model.PV_Curtailed[t] * dt
                for t in T
            )
        )
    elif stage == "stage_3_max_profit":
        objective_expr = profit_objective
    else:
        raise ValueError("Invalid stage name.")

    model.objective = pyo.Objective(
        expr=objective_expr,
        sense=pyo.maximize,
    )

    return model

# ============================================================
# GUROBI SOLVER SETUP
# ============================================================
# The direct interface translates the Pyomo model directly to gurobipy.
# manage_env=True creates a dedicated Gurobi environment that is released
# after the three optimization stages have been completed.
solver = pyo.SolverFactory(
    SOLVER_NAME,
    manage_env=True,
)

try:
    solver_available = solver.available(exception_flag=False)
except Exception as exc:
    raise RuntimeError(
        "Gurobi could not be initialized through Pyomo.\n"
        "Verify that gurobipy is installed and that a valid Gurobi license "
        "is available."
    ) from exc

if not solver_available:
    raise RuntimeError(
        "Gurobi is not available in the active Python environment.\n"
        "Install the required packages using:\n"
        "py -m pip install pyomo gurobipy openpyxl pandas numpy matplotlib\n"
        "Then activate a valid Gurobi license before running this program."
    )

# Gurobi parameter names are case-sensitive.
solver.options["TimeLimit"] = SOLVER_TIME_LIMIT
solver.options["MIPGap"] = SOLVER_GAP

print(
    "Gurobi version:",
    ".".join(str(v) for v in gp.gurobi.version()),
)


def solve_model(model, stage_name):
    print(f"\nSolving {stage_name} using Pyomo + Gurobi...")

    try:
        results = solver.solve(
            model,
            tee=True,
            load_solutions=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Gurobi failed while solving {stage_name}.\n"
            "Check the Gurobi installation and license, and confirm that the "
            "license supports the size of this MILP."
        ) from exc

    status = results.solver.status
    termination = results.solver.termination_condition

    print(f"{stage_name} Status:", status)
    print(f"{stage_name} Termination:", termination)

    # A time-limit result is accepted only when Gurobi returned a feasible
    # incumbent and Pyomo successfully loaded it into the model variables.
    try:
        objective_value = float(pyo.value(model.objective))
        has_incumbent = math.isfinite(objective_value)
    except (TypeError, ValueError):
        objective_value = float("nan")
        has_incumbent = False

    if termination == pyo.TerminationCondition.maxTimeLimit:
        if not has_incumbent:
            raise RuntimeError(
                f"{stage_name} reached the time limit without a feasible "
                "incumbent solution."
            )
        print(
            f"WARNING: {stage_name} reached the time limit. "
            "The best feasible Gurobi incumbent will be used."
        )
    elif termination not in [
        pyo.TerminationCondition.optimal,
        pyo.TerminationCondition.feasible,
    ]:
        raise RuntimeError(
            f"\n{stage_name} did not solve successfully.\n"
            f"Solver status: {status}\n"
            f"Termination condition: {termination}\n\n"
            "Try these one by one if the model is infeasible:\n"
            "1. Set ENABLE_LOAD_RAMP = False\n"
            "2. Set ENABLE_GRID_IMPORT_RAMP = False\n"
            "3. Set ENABLE_PRICE_RAMP = False\n"
            "4. Reduce MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE or increase GRID_IMPORT_MAX_KW\n"
        )

    if not has_incumbent:
        raise RuntimeError(
            f"{stage_name} terminated without variable values that form a "
            "usable incumbent solution."
        )

    print(f"{stage_name} Objective:", round(objective_value, 6))
    return results

# ============================================================
# SOLVE THREE-STAGE MILP
# ============================================================
try:
    print("\n========== STAGE 1: MAXIMIZE PV TO EV ==========")

    model1 = build_model("stage_1_max_pv_to_ev")
    solve_model(model1, "Stage 1")

    pv_to_ev_max = sum(
        get_value(model1.PV_to_EV[t]) * dt
        for t in T
    )

    print(
        "Maximum PV to EV Energy:",
        round(pv_to_ev_max, 3),
        "kWh",
    )

    print("\n========== STAGE 2: MAXIMIZE PV TO BESS ==========")

    model2 = build_model(
        "stage_2_max_pv_to_bess",
        pv_to_ev_min=pv_to_ev_max - EPS_KWH,
    )

    solve_model(model2, "Stage 2")

    pv_to_bess_max = sum(
        get_value(model2.PV_to_BESS[t]) * dt
        for t in T
    )

    print(
        "Maximum PV to BESS Energy:",
        round(pv_to_bess_max, 3),
        "kWh",
    )

    print(
        "\n========== STAGE 3: MAXIMIZE PROFIT + "
        "WHOLE-VEHICLE SHIFTING =========="
    )

    model3 = build_model(
        "stage_3_max_profit",
        pv_to_ev_min=pv_to_ev_max - EPS_KWH,
        pv_to_bess_min=pv_to_bess_max - EPS_KWH,
    )

    solve_model(model3, "Stage 3")

    print("Stage 3 completed.")
finally:
    # Release the dedicated Gurobi environment and license immediately after
    # all optimization calls. The Pyomo variable values remain available for
    # the result-extraction and plotting sections below.
    solver.close()

# ============================================================
# EXTRACT OPTIMIZED STARTS
# ============================================================
optimized_start_slot = np.zeros(len(users), dtype=int)
optimized_start_minute = np.zeros(len(users), dtype=int)
optimized_end_minute = np.zeros(len(users), dtype=int)

for u in U:
    best_s = int(users.loc[u, "original_start_slot"])
    best_val = -1.0

    for s in candidate_starts_by_user[u]:
        val = get_value(model3.X_start[u, s])

        if val > best_val:
            best_val = val
            best_s = s

    optimized_start_slot[u] = best_s
    optimized_start_minute[u] = option_start_minute(u, best_s)

    optimized_end_minute[u] = min(
        MINUTES_PER_DAY,
        optimized_start_minute[u] + int(users.loc[u, "session_duration_min"]),
    )

users["optimized_start_slot"] = optimized_start_slot
users["optimized_start_minute"] = optimized_start_minute
users["optimized_end_minute"] = optimized_end_minute
users["optimized_end_slot"] = np.ceil(users["optimized_end_minute"] / 15.0).astype(int).clip(lower=0, upper=N)

# Compare exact minutes rather than only slot indices. This correctly marks
# an elastic session moved from, for example, 10:07 to the 10:00 boundary.
users["is_shifted"] = np.where(
    users["optimized_start_minute"] != users["original_start_minute"],
    "Yes",
    "No",
)

users["shifted_slots"] = users["optimized_start_slot"] - users["original_start_slot"]
users["shifted_minutes"] = users["optimized_start_minute"] - users["original_start_minute"]

users["original_start_time"] = users["original_start_minute"].apply(minute_to_time)
users["original_end_time"] = users["original_end_minute"].apply(minute_to_time)
users["optimized_start_time"] = users["optimized_start_minute"].apply(minute_to_time)
users["optimized_end_time"] = users["optimized_end_minute"].apply(minute_to_time)

users["elastic_base_rate_LKR_kWh"] = np.nan
users["elastic_flex_discount_potential_LKR_kWh"] = np.nan
users["elastic_basic_flex_reward_LKR_kWh"] = np.nan
users["elastic_solar_scaled_flex_reward_LKR_kWh"] = np.nan
users["elastic_flex_discount_LKR_kWh"] = np.nan
users["elastic_solar_discount_LKR_kWh"] = np.nan
users["elastic_session_average_solar_score"] = np.nan
users["elastic_assigned_tariff_LKR_kWh"] = np.nan
users["elastic_schedule_within_window"] = "Not applicable"
users["elastic_round_15min_start"] = "Not applicable"

for u in elastic_user_indices:
    selected_s = int(users.loc[u, "optimized_start_slot"])
    users.loc[u, "elastic_base_rate_LKR_kWh"] = elastic_base_rate_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_flex_discount_potential_LKR_kWh"] = elastic_flex_discount_potential_by_user[u]
    users.loc[u, "elastic_basic_flex_reward_LKR_kWh"] = elastic_basic_flex_reward_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_solar_scaled_flex_reward_LKR_kWh"] = elastic_solar_scaled_flex_reward_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_flex_discount_LKR_kWh"] = elastic_effective_flex_discount_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_solar_discount_LKR_kWh"] = elastic_solar_discount_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_session_average_solar_score"] = elastic_solar_score_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_assigned_tariff_LKR_kWh"] = elastic_price_by_candidate[(u, selected_s)]
    users.loc[u, "elastic_round_15min_start"] = (
        "Yes" if int(users.loc[u, "optimized_start_minute"]) % 15 == 0 else "No"
    )

    within_window = (
        int(users.loc[u, "optimized_start_minute"])
        >= int(users.loc[u, "elastic_window_start_minute"])
        and int(users.loc[u, "optimized_end_minute"])
        <= int(users.loc[u, "elastic_window_end_minute"])
    )
    users.loc[u, "elastic_schedule_within_window"] = "Yes" if within_window else "No"

# Primary and dynamic-secondary users keep their input charger.
# For each elastic user, extract the charger selected jointly with the
# optimized 15-minute-boundary start. The same charger is used throughout
# the complete uninterrupted charging session.
optimized_charger_pile = users["assigned_charger"].astype(int).to_numpy(copy=True)

for u in elastic_user_indices:
    selected_s = int(users.loc[u, "optimized_start_slot"])
    best_c = int(users.loc[u, "assigned_charger"])
    best_assignment_value = -1.0

    for c in CHARGER_IDS:
        assignment_value = get_value(
            model3.X_elastic_start_charger[u, selected_s, c]
        )

        if assignment_value > best_assignment_value:
            best_assignment_value = assignment_value
            best_c = c

    optimized_charger_pile[u] = best_c

users["optimized_charger_pile"] = optimized_charger_pile

# ============================================================
# EXTRACT SLOT RESULTS
# ============================================================
primary_load_after = np.zeros(N)
dynamic_secondary_load_after = np.zeros(N)
elastic_load_after = np.zeros(N)
secondary_load_after = np.zeros(N)
total_ev_after = np.zeros(N)
elastic_revenue_after_slot = np.zeros(N)

active_user_count_after_exact_minute = np.zeros(MINUTES_PER_DAY)
station_power_after_exact_minute = np.zeros(MINUTES_PER_DAY)

charger_count_after_exact = {(c, m): 0 for c in CHARGER_IDS for m in M}
charger_power_after_exact = {(c, m): 0.0 for c in CHARGER_IDS for m in M}
charger_user_ids_after_exact = {(c, m): [] for c in CHARGER_IDS for m in M}

for u in U:
    start_min = int(users.loc[u, "optimized_start_minute"])
    end_min = int(users.loc[u, "optimized_end_minute"])
    power = float(users.loc[u, "session_power_kW"])
    user_type = users.loc[u, "user_type"]
    charger_id = int(users.loc[u, "optimized_charger_pile"])

    for t in T:
        ov = overlap_minutes(start_min, end_min, t * 15, (t + 1) * 15)

        if ov > 0:
            avg_power = power * ov / 15.0

            if is_primary_user(user_type):
                primary_load_after[t] += avg_power
            elif is_elastic_user(user_type):
                elastic_load_after[t] += avg_power
                elastic_revenue_after_slot[t] += (
                    avg_power
                    * float(users.loc[u, "elastic_assigned_tariff_LKR_kWh"])
                    * dt
                )
            else:
                dynamic_secondary_load_after[t] += avg_power

            secondary_load_after[t] = (
                dynamic_secondary_load_after[t]
                + elastic_load_after[t]
            )

    for m in range(max(0, start_min), min(MINUTES_PER_DAY, end_min)):
        active_user_count_after_exact_minute[m] += 1
        station_power_after_exact_minute[m] += power
        charger_count_after_exact[(charger_id, m)] += 1
        charger_power_after_exact[(charger_id, m)] += power
        charger_user_ids_after_exact[(charger_id, m)].append(str(users.loc[u, "user_id"]))

total_ev_after = primary_load_after + secondary_load_after

secondary_tariff_after = np.zeros(N)
pv_to_ev = np.zeros(N)
pv_to_bess = np.zeros(N)
pv_to_grid = np.zeros(N)
pv_export = np.zeros(N)  # Total PCC export from PV plus BESS
pv_export_dispatchable = np.zeros(N)
pv_export_nondispatchable = np.zeros(N)
dispatch_mode_active = np.zeros(N, dtype=int)
pv_curtailed = np.zeros(N)
grid_to_ev = np.zeros(N)
grid_to_bess = np.zeros(N)
grid_import_after = np.zeros(N)
bess_to_ev = np.zeros(N)
bess_to_grid = np.zeros(N)
bess_charge_after = np.zeros(N)
bess_discharge_after = np.zeros(N)
bess_net_after = np.zeros(N)
soc_after = np.zeros(N)

for t in T:
    for k, tariff in enumerate(secondary_tariff_levels):
        if get_value(model3.x_tariff[t, k]) > 0.5:
            secondary_tariff_after[t] = tariff
            break

    pv_to_ev[t] = get_value(model3.PV_to_EV[t])
    pv_to_bess[t] = get_value(model3.PV_to_BESS[t])
    pv_to_grid[t] = get_value(model3.PV_to_Grid[t])
    pv_export[t] = get_value(model3.PV_Export[t])
    pv_export_dispatchable[t] = get_value(
        model3.PV_Export_Dispatchable[t]
    )
    pv_export_nondispatchable[t] = get_value(
        model3.PV_Export_Nondispatchable[t]
    )

    block_start = (t // DISPATCH_BLOCK_SLOTS) * DISPATCH_BLOCK_SLOTS
    dispatch_mode_active[t] = int(
        get_value(model3.Dispatch_Block_Selected[block_start]) > 0.5
    )

    pv_curtailed[t] = get_value(model3.PV_Curtailed[t])

    grid_to_ev[t] = get_value(model3.Grid_to_EV[t])
    grid_to_bess[t] = get_value(model3.Grid_to_BESS[t])
    grid_import_after[t] = grid_to_ev[t] + grid_to_bess[t]

    bess_to_ev[t] = get_value(model3.BESS_to_EV[t])
    bess_to_grid[t] = get_value(model3.BESS_to_Grid[t])
    bess_charge_after[t] = pv_to_bess[t] + grid_to_bess[t]
    bess_discharge_after[t] = bess_to_ev[t] + bess_to_grid[t]
    bess_net_after[t] = bess_discharge_after[t] - bess_charge_after[t]
    soc_after[t] = get_value(model3.SOC[t])

# ============================================================
# GRID-IMPORT PEAK VALIDATION
# ============================================================
GRID_IMPORT_PEAK_AFTER_KW = float(np.max(grid_import_after))

# ============================================================
# GRID IMPORT ENERGY AND PEAK-PERIOD RESULTS
# ============================================================

# Total daily grid-import energy
GRID_IMPORT_ENERGY_BEFORE_KWH = float(
    np.sum(grid_import_before * dt)
)

GRID_IMPORT_ENERGY_AFTER_KWH = float(
    np.sum(grid_import_after * dt)
)

# Overall daily peak grid import
GRID_IMPORT_PEAK_BEFORE_KW = float(
    np.max(grid_import_before)
)

GRID_IMPORT_PEAK_AFTER_KW = float(
    np.max(grid_import_after)
)

# Peak-period mask: 18:30 to 22:30
peak_period_mask = (
    (hours >= GRID_PEAK_PERIOD_START_HOUR)
    & (hours < GRID_PEAK_PERIOD_END_HOUR)
)

# Maximum grid import occurring only during the peak period
GRID_IMPORT_PEAK_PERIOD_BEFORE_KW = float(
    np.max(grid_import_before[peak_period_mask])
)

GRID_IMPORT_PEAK_PERIOD_AFTER_KW = float(
    np.max(grid_import_after[peak_period_mask])
)

GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_KW = (
    GRID_IMPORT_PEAK_BEFORE_KW - GRID_IMPORT_PEAK_AFTER_KW
)
GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_PERCENTAGE = (
    100.0
    * GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_KW
    / max(GRID_IMPORT_PEAK_BEFORE_KW, 1e-6)
)

if GRID_IMPORT_PEAK_AFTER_KW > OPTIMIZED_GRID_IMPORT_MAX_KW + 1e-4:
    raise RuntimeError(
        "Optimized grid import does not satisfy the required minimum percentage peak reduction."
    )

print("\nGrid-import peak result:")
print(
    "Maximum grid import before optimization:",
    round(GRID_IMPORT_PEAK_BEFORE_KW, 3),
    "kW",
)
print(
    "Maximum grid import after optimization:",
    round(GRID_IMPORT_PEAK_AFTER_KW, 3),
    "kW",
)
print(
    "Achieved grid-import peak reduction:",
    round(GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_KW, 3),
    "kW",
)
print(
    "Achieved grid-import peak reduction percentage:",
    round(GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_PERCENTAGE, 3),
    "%",
)

# ============================================================
# RAMP AND PROFIT
# ============================================================
total_ev_load_ramp_after = np.zeros(N)
secondary_tariff_ramp_after = np.zeros(N)
grid_import_ramp_after = np.zeros(N)

for t in range(1, N):
    total_ev_load_ramp_after[t] = total_ev_after[t] - total_ev_after[t - 1]
    secondary_tariff_ramp_after[t] = secondary_tariff_after[t] - secondary_tariff_after[t - 1]
    grid_import_ramp_after[t] = grid_import_after[t] - grid_import_after[t - 1]

primary_revenue_after_slot = primary_load_after * primary_tariff * dt
dynamic_secondary_revenue_after_slot = (
    dynamic_secondary_load_after * secondary_tariff_after * dt
)
secondary_revenue_after_slot = (
    dynamic_secondary_revenue_after_slot
    + elastic_revenue_after_slot
)

pv_export_nondispatchable_revenue_after_slot = (
    pv_export_nondispatchable * grid_export_price * dt
)
pv_export_dispatchable_revenue_after_slot = (
    pv_export_dispatchable * grid_dispatchable_export_price * dt
)
pv_export_revenue_after_slot = (
    pv_export_nondispatchable_revenue_after_slot
    + pv_export_dispatchable_revenue_after_slot
)
grid_cost_after_slot = grid_import_after * grid_buy * dt
pv_curtailment_cost_after_slot = pv_curtailed * PV_CURTAILMENT_PENALTY * dt

profit_after_slot = (
    primary_revenue_after_slot
    + secondary_revenue_after_slot
    + pv_export_revenue_after_slot
    - grid_cost_after_slot
    - pv_curtailment_cost_after_slot
)

profit_after = np.sum(profit_after_slot)

# ============================================================
# PROFIT IMPROVEMENT PERCENTAGE
# ============================================================

PROFIT_IMPROVEMENT_LKR = (
    profit_after - profit_before
)

PROFIT_IMPROVEMENT_PERCENTAGE = (
    100.0
    * PROFIT_IMPROVEMENT_LKR
    / max(abs(profit_before), 1e-6)
)


# ============================================================
# PV UTILIZATION BEFORE AND AFTER OPTIMIZATION
# ============================================================

# Total available PV energy
PV_TOTAL_ENERGY_KWH = float(
    np.sum(pv * dt)
)


# ------------------------------------------------------------
# BEFORE OPTIMIZATION
# ------------------------------------------------------------

# Direct PV energy supplied to EVs
PV_TO_EV_BEFORE_KWH = float(
    np.sum(
        np.minimum(
            pv,
            ev_load_before,
        )
        * dt
    )
)

# PV energy used to charge the BESS
PV_TO_BESS_BEFORE_KWH = float(
    np.sum(
        bess_ch_before * dt
    )
)

# Total PV internally utilized by EV + BESS
PV_UTILIZED_BEFORE_KWH = (
    PV_TO_EV_BEFORE_KWH
    + PV_TO_BESS_BEFORE_KWH
)

PV_UTILIZATION_BEFORE_PERCENTAGE = (
    100.0
    * PV_UTILIZED_BEFORE_KWH
    / max(PV_TOTAL_ENERGY_KWH, 1e-6)
)


# ------------------------------------------------------------
# AFTER OPTIMIZATION
# ------------------------------------------------------------

PV_TO_EV_AFTER_KWH = float(
    np.sum(pv_to_ev * dt)
)

PV_TO_BESS_AFTER_KWH = float(
    np.sum(pv_to_bess * dt)
)

PV_UTILIZED_AFTER_KWH = (
    PV_TO_EV_AFTER_KWH
    + PV_TO_BESS_AFTER_KWH
)

PV_UTILIZATION_AFTER_PERCENTAGE = (
    100.0
    * PV_UTILIZED_AFTER_KWH
    / max(PV_TOTAL_ENERGY_KWH, 1e-6)
)


# ------------------------------------------------------------
# PV UTILIZATION IMPROVEMENT
# ------------------------------------------------------------

PV_UTILIZATION_IMPROVEMENT_PERCENTAGE_POINTS = (
    PV_UTILIZATION_AFTER_PERCENTAGE
    - PV_UTILIZATION_BEFORE_PERCENTAGE
)

primary_revenue_after = np.sum(primary_revenue_after_slot)
dynamic_secondary_revenue_after = np.sum(dynamic_secondary_revenue_after_slot)
elastic_revenue_after = np.sum(elastic_revenue_after_slot)
secondary_revenue_after = np.sum(secondary_revenue_after_slot)
pv_export_nondispatchable_revenue_after = np.sum(
    pv_export_nondispatchable_revenue_after_slot
)
pv_export_dispatchable_revenue_after = np.sum(
    pv_export_dispatchable_revenue_after_slot
)
pv_export_revenue_after = np.sum(pv_export_revenue_after_slot)
grid_cost_after = np.sum(grid_cost_after_slot)
pv_curtailment_cost_after = np.sum(pv_curtailment_cost_after_slot)

optimized_secondary_avg_tariff = (
    np.sum(dynamic_secondary_load_after * secondary_tariff_after * dt)
    / max(np.sum(dynamic_secondary_load_after * dt), 1e-6)
)
optimized_elastic_avg_tariff = (
    elastic_revenue_after
    / max(np.sum(elastic_load_after * dt), 1e-6)
)

# ============================================================
# VALIDATION AFTER OPTIMIZATION
# ============================================================
after_charger_one_user_violations = sum(
    1 for c in CHARGER_IDS for m in M
    if charger_count_after_exact[(c, m)] > 1
)

after_charger_power_violations = sum(
    1 for c in CHARGER_IDS for m in M
    if charger_power_after_exact[(c, m)] > CHARGER_PILE_RATED_POWER_KW + 1e-6
)

after_station_count_violations = int(
    np.sum(active_user_count_after_exact_minute > NUMBER_OF_CHARGER_PILES)
)

after_station_power_violations = int(
    np.sum(station_power_after_exact_minute > STATION_POWER_CAPACITY + 1e-6)
)

max_after_exact_station_count = int(np.max(active_user_count_after_exact_minute))
max_after_exact_station_power = float(np.max(station_power_after_exact_minute))
max_after_exact_charger_count = max(charger_count_after_exact.values())
max_after_exact_charger_power = max(charger_power_after_exact.values())

# ============================================================
# USER-SLOT RESULTS
# ============================================================
user_slot_rows = []

for u in U:
    user_type = users.loc[u, "user_type"]
    user_id = users.loc[u, "user_id"]
    charger_id = int(users.loc[u, "optimized_charger_pile"])
    eff = float(users.loc[u, "efficiency"])
    start_min = int(users.loc[u, "optimized_start_minute"])
    end_min = int(users.loc[u, "optimized_end_minute"])
    power = float(users.loc[u, "session_power_kW"])

    for t in T:
        ov = overlap_minutes(start_min, end_min, t * 15, (t + 1) * 15)

        if ov <= 0:
            continue

        avg_power_in_slot = power * ov / 15.0
        charger_energy = power * ov / 60.0
        battery_energy = charger_energy * eff

        if is_primary_user(user_type):
            tariff = primary_tariff[t]
        elif is_elastic_user(user_type):
            tariff = float(users.loc[u, "elastic_assigned_tariff_LKR_kWh"])
        else:
            tariff = secondary_tariff_after[t]

        cost = charger_energy * tariff

        if total_ev_after[t] > 1e-6:
            pv_fraction = pv_to_ev[t] / total_ev_after[t]
            grid_fraction = grid_to_ev[t] / total_ev_after[t]
            bess_fraction = bess_to_ev[t] / total_ev_after[t]
        else:
            pv_fraction = 0.0
            grid_fraction = 0.0
            bess_fraction = 0.0

        user_slot_rows.append({
            "slot": t,
            "hour": hours[t],
            "time": slot_to_time(t),
            "overlap_minutes_in_slot": ov,
            "user_id": user_id,
            "ev_notation": users.loc[u, "ev_notation"],
            "user_type": user_type,
            "assigned_charger_from_input": users.loc[u, "assigned_charger"],
            "optimized_charger_pile": charger_id,
            "original_start_time": users.loc[u, "original_start_time"],
            "optimized_start_time": users.loc[u, "optimized_start_time"],
            "optimized_end_time": users.loc[u, "optimized_end_time"],
            "is_shifted": users.loc[u, "is_shifted"],
            "shifted_minutes": users.loc[u, "shifted_minutes"],
            "instant_charging_power_kW": power,
            "average_power_in_15min_slot_kW": avg_power_in_slot,
            "charger_energy_kWh": charger_energy,
            "battery_energy_kWh": battery_energy,
            "tariff_LKR_kWh": tariff,
            "cost_LKR": cost,
            "solar_shift_score": solar_shift_score[t],
            "pv_energy_kWh": charger_energy * pv_fraction,
            "grid_energy_kWh": charger_energy * grid_fraction,
            "bess_energy_kWh": charger_energy * bess_fraction,
        })

user_slot_df = pd.DataFrame(user_slot_rows)

# ============================================================
# STACKED PROFIT COMPONENTS BEFORE AND AFTER OPTIMIZATION
# ============================================================

STACKED_USER_TYPES = [
    "primary",
    "opportunistic",
    "elastic",
    "long_trip",
]

STACKED_USER_LABELS = {
    "primary": "Primary Revenue",
    "opportunistic": "Opportunistic Revenue",
    "elastic": "Elastic Revenue",
    "long_trip": "Long-Trip Revenue",
}

# ------------------------------------------------------------
# BEFORE OPTIMIZATION USER-TYPE REVENUES
# ------------------------------------------------------------

stacked_revenue_before = {
    user_type: 0.0
    for user_type in STACKED_USER_TYPES
}

for u in U:

    user_type = standardize_user_type(
        users.loc[u, "user_type"]
    )

    if user_type not in STACKED_USER_TYPES:
        continue

    start_min = int(
        users.loc[u, "original_start_minute"]
    )

    end_min = int(
        users.loc[u, "original_end_minute"]
    )

    power = float(
        users.loc[u, "session_power_kW"]
    )

    for t in T:

        ov = overlap_minutes(
            start_min,
            end_min,
            t * 15,
            (t + 1) * 15,
        )

        if ov <= 0:
            continue

        charger_energy_kWh = power * ov / 60.0

        if user_type == "primary":
            tariff = primary_tariff[t]

        elif user_type == "elastic":
            tariff = elastic_baseline_price_by_user[u]

        else:
            # opportunistic and long_trip
            tariff = secondary_tariff_before[t]

        stacked_revenue_before[user_type] += (
            charger_energy_kWh * tariff
        )


# ------------------------------------------------------------
# AFTER OPTIMIZATION USER-TYPE REVENUES
# ------------------------------------------------------------

stacked_revenue_after = {
    user_type: 0.0
    for user_type in STACKED_USER_TYPES
}

for user_type in STACKED_USER_TYPES:

    temp_rows = user_slot_df[
        user_slot_df["user_type"] == user_type
    ]

    if len(temp_rows) > 0:
        stacked_revenue_after[user_type] = float(
            temp_rows["cost_LKR"].sum()
        )


# ------------------------------------------------------------
# POSITIVE PROFIT COMPONENTS
# ------------------------------------------------------------

primary_before = stacked_revenue_before["primary"]
opportunistic_before = stacked_revenue_before["opportunistic"]
elastic_before = stacked_revenue_before["elastic"]
long_trip_before = stacked_revenue_before["long_trip"]
export_before = pv_export_revenue_before

primary_after = stacked_revenue_after["primary"]
opportunistic_after = stacked_revenue_after["opportunistic"]
elastic_after = stacked_revenue_after["elastic"]
long_trip_after = stacked_revenue_after["long_trip"]
export_after = pv_export_revenue_after


# ------------------------------------------------------------
# NEGATIVE PROFIT COMPONENT
# ------------------------------------------------------------

import_cost_before_negative = -grid_cost_before
import_cost_after_negative = -grid_cost_after


# ------------------------------------------------------------
# TOTAL POSITIVE PARTS
# ------------------------------------------------------------

positive_total_before = (
    primary_before
    + opportunistic_before
    + elastic_before
    + long_trip_before
    + export_before
)

positive_total_after = (
    primary_after
    + opportunistic_after
    + elastic_after
    + long_trip_after
    + export_after
)

# ============================================================
# USER SUMMARY RESULTS
# ============================================================
user_summary_rows = []

for u in U:
    user_id = users.loc[u, "user_id"]
    user_rows = user_slot_df[user_slot_df["user_id"] == user_id]

    if len(user_rows) > 0:
        delivered_battery_energy = user_rows["battery_energy_kWh"].sum()
        charger_energy = user_rows["charger_energy_kWh"].sum()
        total_cost = user_rows["cost_LKR"].sum()

        energy_in_solar_slots = user_rows.loc[
            user_rows["solar_shift_score"] > 0.5,
            "charger_energy_kWh",
        ].sum()
    else:
        delivered_battery_energy = 0.0
        charger_energy = 0.0
        total_cost = 0.0
        energy_in_solar_slots = 0.0

    final_soc = (
        float(users.loc[u, "entry_soc_pct"])
        + delivered_battery_energy
        / max(float(users.loc[u, "battery_capacity_kWh"]), 1e-6)
        * 100.0
    )

    qos_met = delivered_battery_energy + 1e-3 >= float(users.loc[u, "required_energy_kWh"])

    user_summary_rows.append({
        "user_id": user_id,
        "ev_notation": users.loc[u, "ev_notation"],
        "user_type": users.loc[u, "user_type"],
        "priority": users.loc[u, "priority"],
        "assigned_charger_from_input": users.loc[u, "assigned_charger"],
        "optimized_charger_pile": users.loc[u, "optimized_charger_pile"],
        "original_start_slot": users.loc[u, "original_start_slot"],
        "original_start_time": users.loc[u, "original_start_time"],
        "original_end_time": users.loc[u, "original_end_time"],
        "optimized_start_slot": users.loc[u, "optimized_start_slot"],
        "optimized_start_time": users.loc[u, "optimized_start_time"],
        "optimized_end_time": users.loc[u, "optimized_end_time"],
        "is_shifted": users.loc[u, "is_shifted"],
        "shifted_slots": users.loc[u, "shifted_slots"],
        "shifted_minutes": users.loc[u, "shifted_minutes"],
        "session_duration_min": users.loc[u, "session_duration_min"],
        "session_duration_slots": users.loc[u, "session_duration_slots"],
        "session_power_kW": users.loc[u, "session_power_kW"],
        "battery_capacity_kWh": users.loc[u, "battery_capacity_kWh"],
        "entry_soc_pct": users.loc[u, "entry_soc_pct"],
        "target_soc_pct": users.loc[u, "target_soc_pct"],
        "required_energy_original_kWh": users.loc[u, "required_energy_original_kWh"],
        "required_energy_used_in_model_kWh": users.loc[u, "required_energy_kWh"],
        "delivered_battery_energy_kWh": delivered_battery_energy,
        "charger_energy_kWh": charger_energy,
        "energy_in_solar_slots_kWh": energy_in_solar_slots,
        "solar_slot_energy_percentage": 100.0 * energy_in_solar_slots / max(charger_energy, 1e-6),
        "final_soc_pct": final_soc,
        "total_cost_LKR": total_cost,
        "qos_met": "Yes" if qos_met else "No",
        "energy_adjusted_flag": users.loc[u, "energy_adjusted_flag"],
        "pending_energy_kWh": users.loc[u, "pending_energy_kWh"],
        "elastic_window_start_time": users.loc[u, "elastic_window_start_time"],
        "elastic_window_end_time": users.loc[u, "elastic_window_end_time"],
        "elastic_window_adjusted_flag": users.loc[u, "elastic_window_adjusted_flag"],
        "elastic_window_adjustment_reason": users.loc[u, "elastic_window_adjustment_reason"],
        "elastic_flexibility_hours": users.loc[u, "elastic_flexibility_hours"],
        "elastic_schedule_within_window": users.loc[u, "elastic_schedule_within_window"],
        "elastic_round_15min_start": users.loc[u, "elastic_round_15min_start"],
        "elastic_base_rate_LKR_kWh": users.loc[u, "elastic_base_rate_LKR_kWh"],
        "elastic_flex_discount_potential_LKR_kWh": users.loc[u, "elastic_flex_discount_potential_LKR_kWh"],
        "elastic_basic_flex_reward_LKR_kWh": users.loc[u, "elastic_basic_flex_reward_LKR_kWh"],
        "elastic_solar_scaled_flex_reward_LKR_kWh": users.loc[u, "elastic_solar_scaled_flex_reward_LKR_kWh"],
        "elastic_flex_discount_LKR_kWh": users.loc[u, "elastic_flex_discount_LKR_kWh"],
        "elastic_solar_discount_LKR_kWh": users.loc[u, "elastic_solar_discount_LKR_kWh"],
        "elastic_session_average_solar_score": users.loc[u, "elastic_session_average_solar_score"],
        "elastic_assigned_tariff_LKR_kWh": users.loc[u, "elastic_assigned_tariff_LKR_kWh"],
    })

user_summary_df = pd.DataFrame(user_summary_rows)

# Customer-facing booked elastic notification report.
elastic_notification_rows = []

for u in elastic_user_indices:
    user_id = users.loc[u, "user_id"]
    user_rows = user_slot_df[user_slot_df["user_id"] == user_id]
    charger_energy = user_rows["charger_energy_kWh"].sum() if len(user_rows) > 0 else 0.0
    solar_energy = user_rows["pv_energy_kWh"].sum() if len(user_rows) > 0 else 0.0
    solar_percentage = 100.0 * solar_energy / max(charger_energy, 1e-6)

    elastic_notification_rows.append({
        "user_id": user_id,
        "ev_notation": users.loc[u, "ev_notation"],
        "booked_window_start": users.loc[u, "elastic_window_start_time"],
        "booked_window_end": users.loc[u, "elastic_window_end_time"],
        "window_adjusted_flag": users.loc[u, "elastic_window_adjusted_flag"],
        "window_adjustment_reason": users.loc[u, "elastic_window_adjustment_reason"],
        "available_flexibility_hours": users.loc[u, "elastic_flexibility_hours"],
        "assigned_arrival_and_plugin_time": users.loc[u, "optimized_start_time"],
        "expected_charging_completion_time": users.loc[u, "optimized_end_time"],
        "assigned_charger_pile": users.loc[u, "optimized_charger_pile"],
        "required_battery_energy_kWh": users.loc[u, "required_energy_kWh"],
        "session_duration_min": users.loc[u, "session_duration_min"],
        "charging_power_kW": users.loc[u, "session_power_kW"],
        "elastic_base_rate_LKR_kWh": users.loc[u, "elastic_base_rate_LKR_kWh"],
        "flexibility_discount_potential_LKR_kWh": users.loc[u, "elastic_flex_discount_potential_LKR_kWh"],
        "basic_flexibility_reward_LKR_kWh": users.loc[u, "elastic_basic_flex_reward_LKR_kWh"],
        "solar_scaled_flexibility_reward_LKR_kWh": users.loc[u, "elastic_solar_scaled_flex_reward_LKR_kWh"],
        "effective_flexibility_discount_LKR_kWh": users.loc[u, "elastic_flex_discount_LKR_kWh"],
        "solar_discount_LKR_kWh": users.loc[u, "elastic_solar_discount_LKR_kWh"],
        "final_elastic_tariff_LKR_kWh": users.loc[u, "elastic_assigned_tariff_LKR_kWh"],
        "estimated_customer_charge_LKR": (
            charger_energy
            * float(users.loc[u, "elastic_assigned_tariff_LKR_kWh"])
        ),
        "session_average_solar_score": users.loc[u, "elastic_session_average_solar_score"],
        "estimated_PV_energy_percentage": solar_percentage,
        "complete_session_inside_booked_window": users.loc[u, "elastic_schedule_within_window"],
        "round_15_minute_plugin_time": users.loc[u, "elastic_round_15min_start"],
        "notification_message": (
            f"Arrive and plug in at {users.loc[u, 'optimized_start_time']}; "
            f"charging is expected to finish at {users.loc[u, 'optimized_end_time']} "
            f"on charger {int(users.loc[u, 'optimized_charger_pile'])}. "
            f"Confirmed elastic tariff: "
            f"{float(users.loc[u, 'elastic_assigned_tariff_LKR_kWh']):.2f} LKR/kWh."
        ),
    })

elastic_notification_df = pd.DataFrame(elastic_notification_rows)

# Elastic-user analytical summary for reporting and visualization.
elastic_analysis_rows = []

for u in elastic_user_indices:
    user_id = users.loc[u, "user_id"]
    user_rows = user_slot_df[user_slot_df["user_id"] == user_id]
    charger_energy = user_rows["charger_energy_kWh"].sum() if len(user_rows) > 0 else 0.0
    solar_energy = user_rows["pv_energy_kWh"].sum() if len(user_rows) > 0 else 0.0
    grid_energy = user_rows["grid_energy_kWh"].sum() if len(user_rows) > 0 else 0.0
    bess_energy = user_rows["bess_energy_kWh"].sum() if len(user_rows) > 0 else 0.0

    booked_start_min = int(users.loc[u, "elastic_window_start_minute"])
    booked_end_min = int(users.loc[u, "elastic_window_end_minute"])
    original_start_min = int(users.loc[u, "original_start_minute"])
    optimized_start_min = int(users.loc[u, "optimized_start_minute"])
    session_duration_min = int(users.loc[u, "session_duration_min"])
    booked_window_duration_min = booked_end_min - booked_start_min

    slack_before_min = max(0, optimized_start_min - booked_start_min)
    slack_after_min = max(0, booked_end_min - int(users.loc[u, "optimized_end_minute"]))

    if booked_window_duration_min > session_duration_min:
        normalized_start_position = 100.0 * slack_before_min / max(booked_window_duration_min - session_duration_min, 1)
    else:
        normalized_start_position = 0.0

    elastic_analysis_rows.append({
        "user_id": user_id,
        "ev_notation": users.loc[u, "ev_notation"],
        "optimized_charger_pile": users.loc[u, "optimized_charger_pile"],
        "booked_window_start": users.loc[u, "elastic_window_start_time"],
        "booked_window_end": users.loc[u, "elastic_window_end_time"],
        "booked_window_duration_min": booked_window_duration_min,
        "original_start_time": users.loc[u, "original_start_time"],
        "optimized_start_time": users.loc[u, "optimized_start_time"],
        "optimized_end_time": users.loc[u, "optimized_end_time"],
        "session_duration_min": session_duration_min,
        "shifted_minutes": users.loc[u, "shifted_minutes"],
        "waiting_from_window_start_min": slack_before_min,
        "remaining_window_after_session_min": slack_after_min,
        "normalized_start_position_pct": normalized_start_position,
        "flexibility_hours": users.loc[u, "elastic_flexibility_hours"],
        "charger_energy_kWh": charger_energy,
        "pv_energy_kWh": solar_energy,
        "grid_energy_kWh": grid_energy,
        "bess_energy_kWh": bess_energy,
        "pv_energy_percentage": 100.0 * solar_energy / max(charger_energy, 1e-6),
        "grid_energy_percentage": 100.0 * grid_energy / max(charger_energy, 1e-6),
        "bess_energy_percentage": 100.0 * bess_energy / max(charger_energy, 1e-6),
        "base_rate_LKR_kWh": users.loc[u, "elastic_base_rate_LKR_kWh"],
        "flexibility_discount_potential_LKR_kWh": users.loc[u, "elastic_flex_discount_potential_LKR_kWh"],
        "basic_flexibility_reward_LKR_kWh": users.loc[u, "elastic_basic_flex_reward_LKR_kWh"],
        "solar_scaled_flexibility_reward_LKR_kWh": users.loc[u, "elastic_solar_scaled_flex_reward_LKR_kWh"],
        "flexibility_discount_LKR_kWh": users.loc[u, "elastic_flex_discount_LKR_kWh"],
        "solar_discount_LKR_kWh": users.loc[u, "elastic_solar_discount_LKR_kWh"],
        "final_tariff_LKR_kWh": users.loc[u, "elastic_assigned_tariff_LKR_kWh"],
        "session_average_solar_score": users.loc[u, "elastic_session_average_solar_score"],
        "inside_window": users.loc[u, "elastic_schedule_within_window"],
        "round_15_minute_plugin_time": users.loc[u, "elastic_round_15min_start"],
    })

elastic_analysis_df = pd.DataFrame(elastic_analysis_rows)

# ============================================================
# CHARGER MINUTE RESULTS AND CHARGER SLOT RESULTS
# ============================================================
charger_minute_rows = []

for c in CHARGER_IDS:
    for m in M:
        count = charger_count_after_exact[(c, m)]
        power = charger_power_after_exact[(c, m)]

        if count > 0 or power > 0:
            charger_minute_rows.append({
                "minute": m,
                "time": minute_to_time(m),
                "charger_pile_id": c,
                "active_user_count": count,
                "active_user_ids": ",".join(charger_user_ids_after_exact[(c, m)]),
                "total_charger_power_kW": power,
                "charger_power_limit_kW": CHARGER_PILE_RATED_POWER_KW,
                "one_user_per_pile_ok": "Yes" if count <= 1 else "No",
                "power_limit_ok": "Yes" if power <= CHARGER_PILE_RATED_POWER_KW + 1e-6 else "No",
            })

charger_minute_df = pd.DataFrame(charger_minute_rows)

charger_slot_rows = []

for c in CHARGER_IDS:
    for t in T:
        slot_minutes = range(t * 15, (t + 1) * 15)

        max_count = max(charger_count_after_exact[(c, m)] for m in slot_minutes)
        max_power = max(charger_power_after_exact[(c, m)] for m in slot_minutes)

        energy = 0.0
        ids = set()

        for m in slot_minutes:
            energy += charger_power_after_exact[(c, m)] / 60.0
            ids.update(charger_user_ids_after_exact[(c, m)])

        charger_slot_rows.append({
            "slot": t,
            "hour": hours[t],
            "time": slot_to_time(t),
            "charger_pile_id": c,
            "max_exact_active_user_count_in_slot": max_count,
            "max_exact_power_kW_in_slot": max_power,
            "charger_energy_kWh": energy,
            "active_user_ids_in_slot": ",".join(sorted(ids)),
            "one_user_per_pile_ok": "Yes" if max_count <= 1 else "No",
            "power_limit_ok": "Yes" if max_power <= CHARGER_PILE_RATED_POWER_KW + 1e-6 else "No",
        })

charger_slot_df = pd.DataFrame(charger_slot_rows)

minute_station_rows = []

for m in M:
    if active_user_count_after_exact_minute[m] > 0 or station_power_after_exact_minute[m] > 0:
        minute_station_rows.append({
            "minute": m,
            "time": minute_to_time(m),
            "active_user_count": active_user_count_after_exact_minute[m],
            "active_user_count_limit": NUMBER_OF_CHARGER_PILES,
            "station_power_kW": station_power_after_exact_minute[m],
            "station_power_limit_kW": STATION_POWER_CAPACITY,
            "active_user_count_ok": "Yes" if active_user_count_after_exact_minute[m] <= NUMBER_OF_CHARGER_PILES else "No",
            "station_power_ok": "Yes" if station_power_after_exact_minute[m] <= STATION_POWER_CAPACITY + 1e-6 else "No",
        })

minute_station_df = pd.DataFrame(minute_station_rows)

active_user_count_before_slot_max = np.zeros(N)
active_user_count_after_slot_max = np.zeros(N)
station_power_before_slot_max = np.zeros(N)
station_power_after_slot_max = np.zeros(N)

for t in T:
    mins = range(t * 15, (t + 1) * 15)

    active_user_count_before_slot_max[t] = max(
        active_user_count_before_exact_minute[m]
        for m in mins
    )

    active_user_count_after_slot_max[t] = max(
        active_user_count_after_exact_minute[m]
        for m in mins
    )

    station_power_before_slot_max[t] = max(
        station_power_before_exact_minute[m]
        for m in mins
    )

    station_power_after_slot_max[t] = max(
        station_power_after_exact_minute[m]
        for m in mins
    )

# ============================================================
# DISPATCHABLE EXPORT BLOCK RESULTS
# ============================================================
dispatch_block_rows = []

for block_start in DISPATCH_BLOCK_STARTS:
    block_end = block_start + DISPATCH_BLOCK_SLOTS
    selected = int(
        get_value(model3.Dispatch_Block_Selected[block_start]) > 0.5
    )
    rate_kw = get_value(model3.Dispatch_Block_Rate[block_start])
    energy_kwh = rate_kw * DISPATCH_BLOCK_SLOTS * dt
    hourly_price = float(grid_dispatchable_export_price[block_start])

    block_pv_to_grid_energy = float(
        np.sum(pv_to_grid[block_start:block_end] * dt)
    )
    block_bess_to_grid_energy = float(
        np.sum(bess_to_grid[block_start:block_end] * dt)
    )

    dispatch_block_rows.append({
        "block_start_slot": block_start,
        "block_end_slot_exclusive": block_end,
        "block_start_time": slot_to_time(block_start),
        "block_end_time": slot_to_time(block_end),
        "selected": "Yes" if selected else "No",
        "minimum_dispatchable_export_kW": MIN_DISPATCHABLE_EXPORT_KW,
        "constant_dispatch_rate_kW": rate_kw,
        "minimum_power_requirement_met": (
            "Yes"
            if selected and rate_kw + 1e-6 >= MIN_DISPATCHABLE_EXPORT_KW
            else "Not selected"
            if not selected
            else "No"
        ),
        "fallback_export_mode": (
            "Dispatchable"
            if selected
            else "Non-dispatchable when export is available"
        ),
        "dispatchable_price_LKR_kWh": hourly_price,
        "dispatchable_energy_kWh": energy_kwh,
        "pv_to_grid_energy_in_block_kWh": block_pv_to_grid_energy,
        "bess_to_grid_energy_in_block_kWh": block_bess_to_grid_energy,
        "dispatchable_revenue_LKR": energy_kwh * hourly_price,
    })

dispatch_block_df = pd.DataFrame(dispatch_block_rows)
selected_dispatchable_blocks = int(
    np.sum(dispatch_block_df["selected"] == "Yes")
)

# ============================================================
# SLOT SUMMARY RESULTS
# ============================================================
slot_summary_rows = []

for t in T:
    charging_temp = user_slot_df[user_slot_df["slot"] == t]

    slot_summary_rows.append({
        "slot": t,
        "hour": hours[t],
        "time": slot_to_time(t),

        "charging_primary_count": int(np.sum(charging_temp["user_type"] == "primary")) if len(charging_temp) > 0 else 0,
        "charging_opportunistic_count": int(np.sum(charging_temp["user_type"] == "opportunistic")) if len(charging_temp) > 0 else 0,
        "charging_elastic_count": int(np.sum(charging_temp["user_type"] == "elastic")) if len(charging_temp) > 0 else 0,
        "charging_long_trip_count": int(np.sum(charging_temp["user_type"] == "long_trip")) if len(charging_temp) > 0 else 0,
        "charging_total_unique_users_in_slot": int(charging_temp["user_id"].nunique()) if len(charging_temp) > 0 else 0,

        "max_exact_active_user_count_before": active_user_count_before_slot_max[t],
        "max_exact_active_user_count_after": active_user_count_after_slot_max[t],
        "active_user_count_limit": NUMBER_OF_CHARGER_PILES,

        "max_exact_station_power_before_kW": station_power_before_slot_max[t],
        "max_exact_station_power_after_kW": station_power_after_slot_max[t],
        "station_power_limit_kW": STATION_POWER_CAPACITY,

        "primary_load_before_kW": primary_load_before[t],
        "dynamic_secondary_load_before_kW": dynamic_secondary_load_before[t],
        "elastic_load_before_kW": elastic_load_before[t],
        "secondary_load_before_kW": secondary_load_before[t],
        "total_ev_load_before_kW": ev_load_before[t],

        "primary_load_after_kW": primary_load_after[t],
        "dynamic_secondary_load_after_kW": dynamic_secondary_load_after[t],
        "elastic_load_after_kW": elastic_load_after[t],
        "secondary_load_after_kW": secondary_load_after[t],
        "total_ev_load_after_kW": total_ev_after[t],
        "total_ev_load_ramp_after_kW": total_ev_load_ramp_after[t],

        "primary_tariff_LKR_kWh": primary_tariff[t],
        "secondary_tariff_before_LKR_kWh": secondary_tariff_before[t],
        "secondary_tariff_after_LKR_kWh": secondary_tariff_after[t],
        "secondary_tariff_ramp_LKR_kWh": secondary_tariff_ramp_after[t],
        "solar_target_tariff_LKR_kWh": solar_target_tariff[t],
        "tariff_deviation_from_solar_target_LKR_kWh": (
            secondary_tariff_after[t] - solar_target_tariff[t]
        ),

        "solar_max_allowed_tariff_LKR_kWh": solar_max_allowed_tariff[t],
        "solar_cap_status": solar_cap_status[t],
        "solar_shift_score": solar_shift_score[t],

        "pv_generation_kW": pv[t],
        "pv_to_ev_kW": pv_to_ev[t],
        "pv_to_bess_kW": pv_to_bess[t],
        "pv_to_grid_kW": pv_to_grid[t],
        "bess_to_grid_kW": bess_to_grid[t],
        "export_mode": (
            "Dispatchable"
            if dispatch_mode_active[t] == 1
            else "Non-dispatchable"
            if pv_export_nondispatchable[t] > 1e-6
            else "No export"
        ),
        "dispatch_mode_active": dispatch_mode_active[t],
        "grid_export_dispatchable_kW": pv_export_dispatchable[t],
        "grid_export_nondispatchable_kW": pv_export_nondispatchable[t],
        "grid_export_total_kW": pv_export[t],
        "pv_curtailed_kW": pv_curtailed[t],

        "grid_price_interval_end": grid_price_time_labels[t],
        "grid_import_price_LKR_kWh": grid_buy[t],
        "grid_export_price_LKR_kWh": grid_export_price[t],
        "grid_export_dispatchable_price_LKR_kWh": (
            grid_dispatchable_export_price[t]
        ),
        "dispatchable_export_revenue_LKR": (
            pv_export_dispatchable_revenue_after_slot[t]
        ),
        "nondispatchable_export_revenue_LKR": (
            pv_export_nondispatchable_revenue_after_slot[t]
        ),

        "grid_to_ev_kW": grid_to_ev[t],
        "grid_to_bess_kW": grid_to_bess[t],
        "grid_import_after_kW": grid_import_after[t],
        "minimum_grid_import_peak_reduction_percentage": (
            MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE * 100.0
            if ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION
            else 0.0
        ),
        "optimized_grid_import_cap_kW": OPTIMIZED_GRID_IMPORT_MAX_KW,
        "grid_import_ramp_after_kW": grid_import_ramp_after[t],

        "bess_charge_kW": bess_charge_after[t],
        "bess_to_ev_kW": bess_to_ev[t],
        "bess_to_grid_kW": bess_to_grid[t],
        "bess_discharge_total_kW": bess_discharge_after[t],
        "bess_net_kW_positive_discharge": bess_net_after[t],
        "soc_after_kWh": soc_after[t],

        "elastic_revenue_LKR": elastic_revenue_after_slot[t],
        "dynamic_secondary_revenue_LKR": dynamic_secondary_revenue_after_slot[t],
        "slot_profit_LKR": profit_after_slot[t],
    })

slot_summary_df = pd.DataFrame(slot_summary_rows)
station_slot_df = slot_summary_df.copy()

# ============================================================
# SUMMARY
# ============================================================
secondary_users_df = users[users["user_type"] != "primary"]
dynamic_secondary_users_df = users[
    users["user_type"].apply(is_dynamic_secondary_user)
]
elastic_users_df = users[users["user_type"] == "elastic"]
shifted_secondary_users_df = dynamic_secondary_users_df[
    dynamic_secondary_users_df["is_shifted"] == "Yes"
]

non_primary_user_slot_df = user_slot_df[user_slot_df["user_type"] != "primary"]
elastic_user_slot_df = user_slot_df[user_slot_df["user_type"] == "elastic"]

if len(non_primary_user_slot_df) > 0:
    secondary_energy_in_solar_slots = non_primary_user_slot_df.loc[
        non_primary_user_slot_df["solar_shift_score"] > 0.5,
        "charger_energy_kWh",
    ].sum()

    total_secondary_charger_energy = non_primary_user_slot_df["charger_energy_kWh"].sum()
else:
    secondary_energy_in_solar_slots = 0.0
    total_secondary_charger_energy = 0.0

secondary_solar_shift_percentage = (
    100.0
    * secondary_energy_in_solar_slots
    / max(total_secondary_charger_energy, 1e-6)
)

actual_shifted_secondary_percentage = (
    100.0
    * len(shifted_secondary_users_df)
    / max(len(dynamic_secondary_users_df), 1)
)

if len(elastic_user_slot_df) > 0:
    elastic_energy_in_solar_slots = elastic_user_slot_df.loc[
        elastic_user_slot_df["solar_shift_score"] > 0.5,
        "charger_energy_kWh",
    ].sum()
    total_elastic_charger_energy = elastic_user_slot_df["charger_energy_kWh"].sum()
else:
    elastic_energy_in_solar_slots = 0.0
    total_elastic_charger_energy = 0.0

elastic_solar_shift_percentage = (
    100.0
    * elastic_energy_in_solar_slots
    / max(total_elastic_charger_energy, 1e-6)
)
elastic_window_adjusted_count = int(
    np.sum(elastic_users_df["elastic_window_adjusted_flag"] == "Yes")
)
elastic_window_violation_count = int(
    np.sum(elastic_users_df["elastic_schedule_within_window"] != "Yes")
)

summary_df = pd.DataFrame({
    "Parameter": [
        "Number of Charger Piles",
        "Charger Pile Rated Power kW",
        "Station Charging Capacity kW",
        "Physical Grid Import Maximum kW",
        "Post-Optimization Peak Reduction Enabled",
        "Minimum Required Grid Import Peak Reduction Percentage",
        "Optimized Grid Import Cap kW",
        "Exact Minute Charger Constraints Enabled",
        "Exact Minute Station Constraints Enabled",

        "Before Charger One-User Violations",
        "Before Charger Power Violations",
        "Before Station Count Violations",
        "Before Station Power Violations",

        "After Charger One-User Violations",
        "After Charger Power Violations",
        "After Station Count Violations",
        "After Station Power Violations",

        "Max Exact Active EV Count Before",
        "Max Exact Active EV Count After",
        "Max Exact Charger Active Count After",
        "Max Exact Charger Power After kW",
        "Max Exact Station Power After kW",

        "Number of EV Users",
        "Number of Primary Users",
        "Number of Secondary Users",
        "Number of Dynamic Secondary Users",
        "Number of Opportunistic Users",
        "Number of Elastic Users",
        "Number of Long Trip Users",

        "Maximum Shifted Secondary User Percentage",
        "Maximum Shifted Secondary Users Allowed",
        "Actual Shifted Secondary Users",
        "Actual Shifted Secondary User Percentage",
        "Actual Unshifted Secondary Users",
        "Elastic Users Excluded from Shift Cap",
        "Elastic Windows Adjusted",
        "Elastic Window Schedule Violations",

        "SOC Minimum Limit Percentage",
        "SOC Maximum Limit Percentage",
        "SOC Initial Percentage",
        "SOC Minimum Limit kWh",
        "SOC Maximum Limit kWh",
        "SOC Initial kWh",
        "BESS to Grid Enabled",
        "BESS to Grid Maximum kW",
        "Minimum Dispatchable Export Power kW",
        "Maximum Dispatchable Export Power kW",
        "Dispatchable Block Duration Slots",
        "Dispatchable Block Duration Hours",

        "Stage 1 Max PV to EV Energy",
        "Stage 2 Max PV to BESS Energy",

        "Primary Revenue Before",
        "Dynamic Secondary Revenue Before",
        "Elastic Revenue Before",
        "Secondary Revenue Before",
        "PV Export Revenue Before",
        "Grid Cost Before",
        "Daily Profit Before",

        "Primary Revenue After",
        "Dynamic Secondary Revenue After",
        "Elastic Revenue After",
        "Secondary Revenue After",
        "Total Grid Export Revenue After",
        "Dispatchable Export Revenue After",
        "Non-dispatchable Export Revenue After",
        "Grid Cost After",
        "PV Curtailment Penalty Cost After",
        "Daily Profit After",

        "Profit Improvement",

        "Total EV Energy Before",
        "Total EV Energy After",
        "Primary Energy After",
        "Dynamic Secondary Energy After",
        "Elastic Energy After",
        "Secondary Energy After",

        "PV Energy",
        "PV to EV Energy",
        "PV to BESS Energy",
        "PV to Grid Energy",
        "BESS to Grid Energy",
        "Total Grid Export Energy",
        "Dispatchable Export Energy",
        "Non-dispatchable Export Energy",
        "Selected One-Hour Dispatchable Blocks",
        "PV Curtailed Energy",

        "Grid Import Energy Before",
        "Grid Import Energy After",
        "Max Grid Import Before",
        "Max Grid Import After",
        "Achieved Grid Import Peak Reduction kW",
        "Achieved Grid Import Peak Reduction Percentage",

        "Existing Secondary Avg Tariff Before",
        "Optimized Secondary Avg Tariff After",
        "Optimized Elastic Avg Tariff After",

        "Max Absolute Total EV Load Ramp After",
        "Max Absolute Secondary Tariff Ramp After",
        "Max Absolute Grid Import Ramp After",

        "Secondary Energy in Solar Slots",
        "Total Secondary Charger Energy",
        "Secondary Solar Shift Percentage",
        "Elastic Energy in Solar Slots",
        "Total Elastic Charger Energy",
        "Elastic Solar Shift Percentage",

        "Users with Energy Adjusted",
    ],
    "Value": [
        NUMBER_OF_CHARGER_PILES,
        CHARGER_PILE_RATED_POWER_KW,
        STATION_POWER_CAPACITY,
        GRID_IMPORT_MAX_KW,
        str(ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION),
        (
            MINIMUM_GRID_IMPORT_PEAK_REDUCTION_PERCENTAGE * 100.0
            if ENABLE_POST_OPTIMIZATION_GRID_PEAK_REDUCTION
            else 0.0
        ),
        OPTIMIZED_GRID_IMPORT_MAX_KW,
        str(ENABLE_EXACT_MINUTE_CHARGER_CONSTRAINTS),
        str(ENABLE_EXACT_MINUTE_STATION_CONSTRAINTS),

        before_charger_user_violations,
        before_charger_power_violations,
        before_station_count_violations,
        before_station_power_violations,

        after_charger_one_user_violations,
        after_charger_power_violations,
        after_station_count_violations,
        after_station_power_violations,

        int(np.max(active_user_count_before_exact_minute)),
        max_after_exact_station_count,
        max_after_exact_charger_count,
        max_after_exact_charger_power,
        max_after_exact_station_power,

        len(users),
        int(np.sum(users["user_type"] == "primary")),
        int(np.sum(users["user_type"] != "primary")),
        len(dynamic_secondary_users_df),
        int(np.sum(users["user_type"] == "opportunistic")),
        int(np.sum(users["user_type"] == "elastic")),
        int(np.sum(users["user_type"] == "long_trip")),

        MAX_SHIFTED_SECONDARY_USER_PERCENTAGE * 100,
        MAX_SHIFTED_SECONDARY_USERS_ALLOWED,
        len(shifted_secondary_users_df),
        actual_shifted_secondary_percentage,
        len(dynamic_secondary_users_df) - len(shifted_secondary_users_df),
        len(elastic_users_df),
        elastic_window_adjusted_count,
        elastic_window_violation_count,

        SOC_MIN_PERCENTAGE * 100,
        SOC_MAX_PERCENTAGE * 100,
        SOC_INITIAL_PERCENTAGE * 100,
        SOC_MIN,
        SOC_MAX,
        SOC_INITIAL,
        str(ALLOW_BESS_TO_GRID),
        BESS_TO_GRID_MAX_KW,
        MIN_DISPATCHABLE_EXPORT_KW,
        MAX_DISPATCHABLE_EXPORT_KW,
        DISPATCH_BLOCK_SLOTS,
        DISPATCH_BLOCK_SLOTS * dt,

        pv_to_ev_max,
        pv_to_bess_max,

        primary_revenue_before,
        dynamic_secondary_revenue_before,
        elastic_revenue_before,
        secondary_revenue_before,
        pv_export_revenue_before,
        grid_cost_before,
        profit_before,

        primary_revenue_after,
        dynamic_secondary_revenue_after,
        elastic_revenue_after,
        secondary_revenue_after,
        pv_export_revenue_after,
        pv_export_dispatchable_revenue_after,
        pv_export_nondispatchable_revenue_after,
        grid_cost_after,
        pv_curtailment_cost_after,
        profit_after,

        profit_after - profit_before,

        np.sum(ev_load_before * dt),
        np.sum(total_ev_after * dt),
        np.sum(primary_load_after * dt),
        np.sum(dynamic_secondary_load_after * dt),
        np.sum(elastic_load_after * dt),
        np.sum(secondary_load_after * dt),

        np.sum(pv * dt),
        np.sum(pv_to_ev * dt),
        np.sum(pv_to_bess * dt),
        np.sum(pv_to_grid * dt),
        np.sum(bess_to_grid * dt),
        np.sum(pv_export * dt),
        np.sum(pv_export_dispatchable * dt),
        np.sum(pv_export_nondispatchable * dt),
        selected_dispatchable_blocks,
        np.sum(pv_curtailed * dt),

        np.sum(grid_import_before * dt),
        np.sum(grid_import_after * dt),
        GRID_IMPORT_PEAK_BEFORE_KW,
        GRID_IMPORT_PEAK_AFTER_KW,
        GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_KW,
        GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_PERCENTAGE,

        existing_secondary_avg_tariff,
        optimized_secondary_avg_tariff,
        optimized_elastic_avg_tariff,

        np.max(np.abs(total_ev_load_ramp_after[1:])),
        np.max(np.abs(secondary_tariff_ramp_after[1:])),
        np.max(np.abs(grid_import_ramp_after[1:])),

        secondary_energy_in_solar_slots,
        total_secondary_charger_energy,
        secondary_solar_shift_percentage,
        elastic_energy_in_solar_slots,
        total_elastic_charger_energy,
        elastic_solar_shift_percentage,

        int(np.sum(users["energy_adjusted_flag"] == "Yes")),
    ],
})

# ============================================================
# SAVE OUTPUTS
# ============================================================
# ============================================================
# OPTIMIZED EV AND BESS PER-UNIT PROFILES
# ============================================================

# Per-unit bases requested for OpenDSS profiles
EV_PROFILE_BASE_KW = 4500.0
BESS_PROFILE_BASE_KW = 5300.0

# ------------------------------------------------------------
# Optimized EV profile
# ------------------------------------------------------------
# total_ev_after is the optimized total EV charging load in kW.
#
# PU value:
#     EV_pu = optimized EV power / 4500 kW
#
optimized_ev_profile_pu = (
    total_ev_after / EV_PROFILE_BASE_KW
)

# ------------------------------------------------------------
# Optimized BESS profile
# ------------------------------------------------------------
# bess_net_after follows the existing sign convention:
#
#     positive = BESS discharge
#     negative = BESS charge
#
# PU value:
#     BESS_pu = optimized BESS net power / 5300
#
optimized_bess_profile_pu = (
    bess_net_after / BESS_PROFILE_BASE_KW
)

# ------------------------------------------------------------
# Output text-file paths
# ------------------------------------------------------------

optimized_ev_profile_txt = os.path.join(
    OUT_DIR,
    "optimized_ev_profile_pu.txt",
)

optimized_bess_profile_txt = os.path.join(
    OUT_DIR,
    "optimized_bess_profile_pu.txt",
)

# ------------------------------------------------------------
# Save one PU value per line
# 96 values = 96 × 15-minute intervals
# ------------------------------------------------------------

np.savetxt(
    optimized_ev_profile_txt,
    optimized_ev_profile_pu,
    fmt="%.8f",
)

np.savetxt(
    optimized_bess_profile_txt,
    optimized_bess_profile_pu,
    fmt="%.8f",
)

print("\nOptimized PU profiles saved:")
print(
    "EV profile   :",
    optimized_ev_profile_txt,
    "(base = 4500 kW)",
)
print(
    "BESS profile :",
    optimized_bess_profile_txt,
    "(base = 5300)",
)


station_slot_csv = os.path.join(OUT_DIR, "station_slot_results.csv")
slot_summary_csv = os.path.join(OUT_DIR, "slot_summary_results.csv")
user_slot_csv = os.path.join(OUT_DIR, "user_slot_charging_results.csv")
user_summary_csv = os.path.join(OUT_DIR, "user_summary_results.csv")
elastic_notification_csv = os.path.join(OUT_DIR, "elastic_user_notifications.csv")
elastic_analysis_csv = os.path.join(OUT_DIR, "elastic_user_analysis.csv")
charger_slot_csv = os.path.join(OUT_DIR, "charger_slot_results.csv")
charger_minute_csv = os.path.join(OUT_DIR, "charger_minute_results.csv")
minute_station_csv = os.path.join(OUT_DIR, "minute_station_results.csv")
summary_csv = os.path.join(OUT_DIR, "final_milp_summary.csv")
dispatch_block_csv = os.path.join(OUT_DIR, "dispatchable_export_blocks.csv")
grid_price_input_csv = os.path.join(OUT_DIR, "grid_price_input_used.csv")
excel_file = os.path.join(OUT_DIR, "whole_vehicle_shift_milp_results.xlsx")

station_slot_df.to_csv(station_slot_csv, index=False)
slot_summary_df.to_csv(slot_summary_csv, index=False)
user_slot_df.to_csv(user_slot_csv, index=False)
user_summary_df.to_csv(user_summary_csv, index=False)
elastic_notification_df.to_csv(elastic_notification_csv, index=False)
elastic_analysis_df.to_csv(elastic_analysis_csv, index=False)
charger_slot_df.to_csv(charger_slot_csv, index=False)
charger_minute_df.to_csv(charger_minute_csv, index=False)
minute_station_df.to_csv(minute_station_csv, index=False)
summary_df.to_csv(summary_csv, index=False)
dispatch_block_df.to_csv(dispatch_block_csv, index=False)
grid_price_input_df.to_csv(grid_price_input_csv, index=False)
users.to_csv(clean_user_csv, index=False)

try:
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        dispatch_block_df.to_excel(writer, sheet_name="Dispatch_Blocks", index=False)
        grid_price_input_df.to_excel(writer, sheet_name="Grid_Price_Input", index=False)
        station_slot_df.to_excel(writer, sheet_name="Station_Slot", index=False)
        slot_summary_df.to_excel(writer, sheet_name="Slot_Summary", index=False)
        user_slot_df.to_excel(writer, sheet_name="User_Slot", index=False)
        user_summary_df.to_excel(writer, sheet_name="User_Summary", index=False)
        elastic_notification_df.to_excel(writer, sheet_name="Elastic_Notifications", index=False)
        elastic_analysis_df.to_excel(writer, sheet_name="Elastic_Analysis", index=False)
        charger_slot_df.to_excel(writer, sheet_name="Charger_Slot", index=False)
        charger_minute_df.to_excel(writer, sheet_name="Charger_Minute", index=False)
        minute_station_df.to_excel(writer, sheet_name="Station_Minute", index=False)
        users.to_excel(writer, sheet_name="Clean_User_Input", index=False)
except Exception as e:
    print("Excel file not saved:", e)
    print("Install openpyxl using: py -m pip install openpyxl")


# ============================================================
# PV UTILIZATION POWER PROFILES
# ============================================================

# ------------------------------------------------------------
# BEFORE OPTIMIZATION
# ------------------------------------------------------------

# PV directly used by EV charging
pv_to_ev_before_profile = np.minimum(
    pv,
    ev_load_before,
)

# Total internally utilized PV power:
# PV -> EV + PV -> BESS
pv_utilization_before_profile = (
    pv_to_ev_before_profile
    + bess_ch_before
)


# ------------------------------------------------------------
# AFTER OPTIMIZATION
# ------------------------------------------------------------

# Total internally utilized PV power:
# PV -> EV + PV -> BESS
pv_utilization_after_profile = (
    pv_to_ev
    + pv_to_bess
)


# ============================================================
# GRAPHS
# ============================================================
# Publication-style formatting applied consistently to every figure.
PLOT_FONT_NAME = "Times New Roman"
PLOT_FONT_SIZE = 15
MAX_ELASTIC_USERS_PER_FIGURE = 10

plt.rcParams.update({
    "font.family": PLOT_FONT_NAME,
    "font.size": PLOT_FONT_SIZE,
    "axes.titlesize": PLOT_FONT_SIZE,
    "axes.titleweight": "bold",
    "axes.labelsize": PLOT_FONT_SIZE,
    "axes.labelweight": "bold",
    "xtick.labelsize": PLOT_FONT_SIZE,
    "ytick.labelsize": PLOT_FONT_SIZE,
    "legend.fontsize": PLOT_FONT_SIZE,
    "figure.titlesize": PLOT_FONT_SIZE,
    "mathtext.fontset": "stix",
})


def apply_plot_formatting(
    legend_loc="best",
    legend_outside=False,
    legend_bbox_to_anchor=None,
    legend_ncol=1,
):
    """Apply Times New Roman, bold labels, and configurable legend placement."""
    ax = plt.gca()

    ax.title.set_fontname(PLOT_FONT_NAME)
    ax.title.set_fontsize(PLOT_FONT_SIZE)
    ax.title.set_fontweight("bold")

    ax.xaxis.label.set_fontname(PLOT_FONT_NAME)
    ax.xaxis.label.set_fontsize(PLOT_FONT_SIZE)
    ax.xaxis.label.set_fontweight("bold")

    ax.yaxis.label.set_fontname(PLOT_FONT_NAME)
    ax.yaxis.label.set_fontsize(PLOT_FONT_SIZE)
    ax.yaxis.label.set_fontweight("bold")

    for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
        tick_label.set_fontname(PLOT_FONT_NAME)
        tick_label.set_fontsize(PLOT_FONT_SIZE)
        tick_label.set_fontweight("bold")

    for annotation in ax.texts:
        annotation.set_fontname(PLOT_FONT_NAME)
        annotation.set_fontsize(PLOT_FONT_SIZE)
        annotation.set_fontweight("bold")

    handles, labels = ax.get_legend_handles_labels()
    if len(handles) > 0:
        if legend_outside:
            if legend_bbox_to_anchor is None:
                legend_bbox_to_anchor = (1.02, 1.0)
            legend = ax.legend(
                handles,
                labels,
                loc=legend_loc,
                bbox_to_anchor=legend_bbox_to_anchor,
                ncol=legend_ncol,
                frameon=True,
                borderaxespad=0.0,
            )
        else:
            # For an inside legend, bbox_to_anchor is optional. When it is
            # supplied, the first value moves the legend horizontally and
            # the second value moves it vertically in axes coordinates.
            legend_kwargs = {
                "loc": legend_loc,
                "ncol": legend_ncol,
                "frameon": True,
            }

            if legend_bbox_to_anchor is not None:
                legend_kwargs["bbox_to_anchor"] = legend_bbox_to_anchor

            legend = ax.legend(
                handles,
                labels,
                **legend_kwargs,
            )

        for legend_text in legend.get_texts():
            legend_text.set_fontname(PLOT_FONT_NAME)
            legend_text.set_fontsize(PLOT_FONT_SIZE)
            legend_text.set_fontweight("bold")

        legend_title = legend.get_title()
        if legend_title is not None:
            legend_title.set_fontname(PLOT_FONT_NAME)
            legend_title.set_fontsize(PLOT_FONT_SIZE)
            legend_title.set_fontweight("bold")


def line_graph(
    filename,
    series,
    ylabel,
    title,
    legend_loc="best",
    legend_outside=False,
    legend_bbox_to_anchor=None,
    legend_ncol=1,
):
    plt.figure(figsize=(12, 5))

    for data, label in series:
        plt.plot(hours, data, label=label)

    plt.xlabel("Time (hour)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    apply_plot_formatting(
        legend_loc=legend_loc,
        legend_outside=legend_outside,
        legend_bbox_to_anchor=legend_bbox_to_anchor,
        legend_ncol=legend_ncol,
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(GRAPH_DIR, filename),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()


# Plot the exact 15-minute grid import and export prices read from the input file.
plt.figure(figsize=(12, 5))

plt.step(
    hours,
    grid_buy,
    where="post",
    linewidth=2,
    label="Grid Import Price",
)

plt.step(
    hours,
    grid_export_price,
    where="post",
    linewidth=2,
    label="Normal Export Price",
)

plt.step(
    hours,
    grid_dispatchable_export_price,
    where="post",
    linewidth=2,
    label="Dispatchable Export Price",
)

plt.xlim(0, 24)
plt.xticks(np.arange(0, 25, 2))
plt.xlabel("Time (hour)")
plt.ylabel("Energy Price (LKR/kWh)")
plt.title("Input Grid Import, Normal Export and Dispatchable Export Prices")
plt.grid(True)
plt.legend()
apply_plot_formatting(
    legend_loc="best",
)
plt.tight_layout()
plt.savefig(
    os.path.join(
        GRAPH_DIR,
        "00_input_grid_import_export_prices.png",
    ),
    dpi=300,
    bbox_inches="tight",
)
plt.close()


plt.figure(figsize=(12, 5))

plt.step(
    hours,
    secondary_tariff_after,
    where="post",
    linewidth=2,
    label="Secondary Tariff After",
)

plt.step(
    hours,
    secondary_tariff_before,
    where="post",
    linewidth=2,
    label="Secondary Tariff Before",
)

plt.xlabel("Time (hour)")
plt.ylabel("Tariff (LKR/kWh)")
plt.title("Secondary User Tariff Before and After Optimization")
plt.grid(True)
plt.legend()
apply_plot_formatting(legend_loc="best")
plt.tight_layout()
plt.savefig(os.path.join(GRAPH_DIR, "01_secondary_tariff_before_after.png"), dpi=300, bbox_inches="tight")
plt.close()

line_graph(
    "02_total_ev_load_before_after.png",
    [
        (ev_load_before, "Total EV Load Before"),
        (total_ev_after, "Total EV Load After"),
    ],
    "Power (kW)",
    "Total EV Load Before and After Optimization",
)

line_graph(
    "03_secondary_load_before_after.png",
    [
        (secondary_load_before, "Secondary Load Before"),
        (secondary_load_after, "Secondary Load After"),
    ],
    "Power (kW)",
    "Secondary Load Before and After Whole-Session Shifting",
)

line_graph(
    "04_pv_allocation.png",
    [
        (pv, "PV Generation"),
        (pv_to_ev, "PV to EV"),
        (pv_to_bess, "PV to BESS"),
        (pv_to_grid, "PV to Grid"),
        (pv_curtailed, "PV Curtailed"),
    ],
    "Power (kW)",
    "PV Allocation",
    legend_loc="best",
)

line_graph(
    "04b_grid_export_sources_and_modes.png",
    [
        (pv_to_grid, "PV to Grid"),
        (bess_to_grid, "BESS to Grid"),
        (pv_export_dispatchable, "Dispatchable Grid Export"),
        (pv_export_nondispatchable, "Non-dispatchable Grid Export"),
        (pv_export, "Total Grid Export"),
    ],
    "Power (kW)",
    "Grid Export Sources and Market Modes",
    legend_loc="best",
)

line_graph(
    "05_grid_import.png",
    [
        (grid_import_before, "Grid Import Before"),
        (grid_import_after, "Grid Import After"),
    ],
    "Power (kW)",
    "Grid Import Before and After",
)

line_graph(
    "05b_pv_utilization_before_after.png",
    [
        (
            pv,
            "Available PV Generation",
        ),
        (
            pv_utilization_before_profile,
            "PV Utilization Before Optimization",
        ),
        (
            pv_utilization_after_profile,
            "PV Utilization After Optimization",
        ),
    ],
    "Power (kW)",
    "Solar PV Utilization Before and After Optimization",
    legend_loc="upper right",
    legend_bbox_to_anchor=(0.98, 0.98),
)

line_graph(
    "06_bess_operation.png",
    [
        (bess_charge_after, "BESS Charge"),
        (bess_to_ev, "BESS to EV"),
        (bess_to_grid, "BESS to Grid"),
        (bess_discharge_after, "BESS Total Discharge"),
        (bess_net_after, "BESS Net Positive Discharge"),
    ],
    "Power (kW)",
    "BESS Operation",
    # Figure 06: bottom-right, slightly above the lower border.
    legend_loc="lower right",
    legend_bbox_to_anchor=(0.99, 0.01),
)

plt.figure(figsize=(12, 5))
plt.step(
    hours,
    bess_to_grid,
    where="post",
    linewidth=2,
    label="BESS to Grid",
)
plt.axhline(
    BESS_TO_GRID_MAX_KW,
    linestyle="--",
    linewidth=1.5,
    label="BESS-to-Grid Power Limit",
)
plt.xlim(0, 24)
plt.xticks(np.arange(0, 25, 2))
plt.xlabel("Time (hour)")
plt.ylabel("Power (kW)")
plt.title("Direct BESS Discharge to Grid")
plt.grid(True)
plt.legend()
apply_plot_formatting(
    # Figure 06b: upper-left inside the axes.
    legend_loc="upper left",
    legend_bbox_to_anchor=(0.02, 0.98),
)
plt.tight_layout()
plt.savefig(
    os.path.join(GRAPH_DIR, "06b_bess_to_grid.png"),
    dpi=300,
    bbox_inches="tight",
)
plt.close()

line_graph(
    "07_soc.png",
    [
        (soc_before, "SOC Before"),
        (soc_after, "SOC After"),
        (np.full(N, SOC_MAX), "SOC Upper Limit 90%"),
        (np.full(N, SOC_MIN), "SOC Lower Limit 10%"),
    ],
    "Energy (kWh)",
    "BESS SOC with 10% and 90% Limits",
    # Figure 07: upper-right inside the axes.
    legend_loc="upper right",
    legend_bbox_to_anchor=(0.78, 0.42),
)

plt.figure(figsize=(7, 5))
plt.bar(["Before", "After MILP"], [profit_before, profit_after])
plt.ylabel("Profit (LKR/day)")
plt.title("Daily Profit Comparison")
plt.grid(axis="y")
apply_plot_formatting()
plt.tight_layout()
plt.savefig(os.path.join(GRAPH_DIR, "08_profit_comparison.png"), dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# FIGURE 08b:
# STACKED PROFIT COMPONENTS BEFORE AND AFTER OPTIMIZATION
# ============================================================

x = np.array([0.0, 0.4])
labels = ["Before", "After Optimization"]
bar_width = 0.2

plt.figure(figsize=(10, 6))

# ------------------------------------------------------------
# STACK POSITIVE REVENUE COMPONENTS
# ------------------------------------------------------------

# Primary
plt.bar(
    x,
    [primary_before, primary_after],
    bar_width,
    label="Primary \n Revenue",
)

# Opportunistic
plt.bar(
    x,
    [opportunistic_before, opportunistic_after],
    bar_width,
    bottom=[primary_before, primary_after],
    label="Opportunistic \n Revenue",
)

# Elastic
plt.bar(
    x,
    [elastic_before, elastic_after],
    bar_width,
    bottom=[
        primary_before + opportunistic_before,
        primary_after + opportunistic_after,
    ],
    label="Elastic \n Revenue",
)

# Long-Trip
plt.bar(
    x,
    [long_trip_before, long_trip_after],
    bar_width,
    bottom=[
        primary_before + opportunistic_before + elastic_before,
        primary_after + opportunistic_after + elastic_after,
    ],
    label="Long-Trip \n Revenue",
)

# Grid Export Revenue
plt.bar(
    x,
    [export_before, export_after],
    bar_width,
    bottom=[
        primary_before + opportunistic_before + elastic_before + long_trip_before,
        primary_after + opportunistic_after + elastic_after + long_trip_after,
    ],
    label="Grid Export \n Revenue",
)

# ------------------------------------------------------------
# NEGATIVE COST COMPONENT
# ------------------------------------------------------------

plt.bar(
    x,
    [import_cost_before_negative, import_cost_after_negative],
    bar_width,
    label="Grid Import Cost",
)

# ------------------------------------------------------------
# TOTAL PROFIT TEXT
# ------------------------------------------------------------

positive_max = max(
    positive_total_before,
    positive_total_after,
    1.0,
)

text_offset = 0.03 * positive_max

plt.text(
    x[0],
    positive_total_before + text_offset,
    f"Net Profit = {profit_before:.0f}",
    ha="center",
    va="bottom",
    fontname=PLOT_FONT_NAME,
    fontsize=PLOT_FONT_SIZE,
    fontweight="bold",
)

plt.text(
    x[1],
    positive_total_after + text_offset,
    f"Net Profit = {profit_after:.0f}",
    ha="center",
    va="bottom",
    fontname=PLOT_FONT_NAME,
    fontsize=PLOT_FONT_SIZE,
    fontweight="bold",
)

# ------------------------------------------------------------
# AXES / LABELS
# ------------------------------------------------------------

plt.xticks(x, labels)

plt.xlabel("Case")
plt.ylabel("Daily Financial Value (LKR/day)")
plt.title("Profit Components Before and After Optimization")

plt.axhline(
    0,
    linestyle="--",
    linewidth=1.5,
)

plt.grid(axis="y")

plt.legend()

apply_plot_formatting(
    legend_loc="upper right",
    legend_bbox_to_anchor=(0.64, 0.98),
)

plt.ylim(
    bottom=min(import_cost_before_negative, import_cost_after_negative) * 1.15,
    top=max(positive_total_before, positive_total_after) * 1.18
)

plt.tight_layout()

plt.savefig(
    os.path.join(
        GRAPH_DIR,
        "08b_stacked_profit_components_before_after.png",
    ),
    dpi=300,
    bbox_inches="tight",
)

plt.close()

plt.figure(figsize=(12, 5))

plt.step(
    hours,
    active_user_count_before_slot_max,
    where="post",
    linewidth=2,
    label="Exact Active EV \nCount Before",
)

plt.step(
    hours,
    active_user_count_after_slot_max,
    where="post",
    linewidth=2,
    label="Exact Active EV \n Count After",
)

plt.axhline(
    NUMBER_OF_CHARGER_PILES,
    linestyle="--",
    linewidth=2,
    label="10 Charger \nPile Limit",
)

plt.xlabel("Time (hour)")
plt.ylabel("Number of Active EVs")
plt.title("Exact Active EV Count Before and After Optimization")
plt.grid(True)
plt.legend()
apply_plot_formatting(
    # Figure 09: upper-left inside the axes.
    legend_loc="upper left",
    legend_bbox_to_anchor=(0.02, 0.98),
)
plt.tight_layout()
plt.savefig(os.path.join(GRAPH_DIR, "09_exact_active_ev_count_before_after.png"), dpi=300, bbox_inches="tight")
plt.close()


# ============================================================
# FIGURES 09b AND 09c:
# DIFFERENT USERS BY TYPE IN EACH 15-MINUTE INTERVAL
# DIVIDED INTO THREE 8-HOUR FIGURES
# ============================================================
# Each EV is counted once in every 15-minute interval that overlaps
# any part of its charging session. This is not the maximum simultaneous
# count used in Figure 09.

USER_TYPES_FOR_INTERVAL_COUNT = [
    "primary",
    "opportunistic",
    "elastic",
    "long_trip",
]

USER_TYPE_INTERVAL_LABELS = {
    "primary": "Primary users",
    "opportunistic": "Opportunistic users",
    "elastic": "Elastic users",
    "long_trip": "Long-trip users",
}

user_type_count_before_slot = {
    user_type: np.zeros(N, dtype=int)
    for user_type in USER_TYPES_FOR_INTERVAL_COUNT
}

user_type_count_after_slot = {
    user_type: np.zeros(N, dtype=int)
    for user_type in USER_TYPES_FOR_INTERVAL_COUNT
}

# Count each user once in each 15-minute interval that the session overlaps.
for u in U:
    user_type = standardize_user_type(users.loc[u, "user_type"])

    if user_type not in USER_TYPES_FOR_INTERVAL_COUNT:
        continue

    original_start_minute = int(users.loc[u, "original_start_minute"])
    original_end_minute = int(users.loc[u, "original_end_minute"])
    optimized_start_minute_u = int(users.loc[u, "optimized_start_minute"])
    optimized_end_minute_u = int(users.loc[u, "optimized_end_minute"])

    for t in T:
        slot_start_minute = int(t * 15)
        slot_end_minute = int((t + 1) * 15)

        if overlap_minutes(
            original_start_minute,
            original_end_minute,
            slot_start_minute,
            slot_end_minute,
        ) > 0:
            user_type_count_before_slot[user_type][t] += 1

        if overlap_minutes(
            optimized_start_minute_u,
            optimized_end_minute_u,
            slot_start_minute,
            slot_end_minute,
        ) > 0:
            user_type_count_after_slot[user_type][t] += 1

# Total different users appearing in each 15-minute interval.
total_different_users_before_slot = np.zeros(N, dtype=int)
total_different_users_after_slot = np.zeros(N, dtype=int)

for user_type in USER_TYPES_FOR_INTERVAL_COUNT:
    total_different_users_before_slot += user_type_count_before_slot[user_type]
    total_different_users_after_slot += user_type_count_after_slot[user_type]

# Save interval counts to CSV.
user_type_count_15min_df = pd.DataFrame({
    "slot": T,
    "hour": hours,
    "time": [slot_to_time(t) for t in T],
    "primary_users_before": user_type_count_before_slot["primary"],
    "opportunistic_users_before": user_type_count_before_slot["opportunistic"],
    "elastic_users_before": user_type_count_before_slot["elastic"],
    "long_trip_users_before": user_type_count_before_slot["long_trip"],
    "total_different_users_before": total_different_users_before_slot,
    "primary_users_after": user_type_count_after_slot["primary"],
    "opportunistic_users_after": user_type_count_after_slot["opportunistic"],
    "elastic_users_after": user_type_count_after_slot["elastic"],
    "long_trip_users_after": user_type_count_after_slot["long_trip"],
    "total_different_users_after": total_different_users_after_slot,
})

user_type_count_15min_df.to_csv(
    os.path.join(
        OUT_DIR,
        "different_users_by_type_in_each_15min_interval.csv",
    ),
    index=False,
)

EIGHT_HOUR_INTERVAL_PARTS = [
    (0, 32, "00:00-08:00", "00_08"),
    (32, 64, "08:00-16:00", "08_16"),
    (64, 96, "16:00-24:00", "16_24"),
]

common_interval_user_ymax = int(max(
    np.max(total_different_users_before_slot),
    np.max(total_different_users_after_slot),
    1,
))


def plot_user_type_interval_parts(
    count_dictionary,
    stage_title,
    output_prefix,
):
    """Draw three stacked-column figures covering 8 hours each."""

    # Larger fonts used only for Figures 09b and 09c.
    USER_COUNT_TITLE_SIZE = 22
    USER_COUNT_AXIS_SIZE = 20
    USER_COUNT_XTICK_SIZE = 18
    USER_COUNT_YTICK_SIZE = 19
    USER_COUNT_LEGEND_SIZE = 18

    for part_number, (
        start_slot,
        end_slot,
        period_label,
        period_file_label,
    ) in enumerate(EIGHT_HOUR_INTERVAL_PARTS, start=1):

        selected_slots = list(range(start_slot, end_slot))
        x_positions = np.arange(len(selected_slots))
        time_labels = [slot_to_time(t) for t in selected_slots]

        primary_values = np.asarray(
            count_dictionary["primary"][start_slot:end_slot],
            dtype=int,
        )
        opportunistic_values = np.asarray(
            count_dictionary["opportunistic"][start_slot:end_slot],
            dtype=int,
        )
        elastic_values = np.asarray(
            count_dictionary["elastic"][start_slot:end_slot],
            dtype=int,
        )
        long_trip_values = np.asarray(
            count_dictionary["long_trip"][start_slot:end_slot],
            dtype=int,
        )

        plt.figure(figsize=(15, 7))

        plt.bar(
            x_positions,
            primary_values,
            width=0.86,
            label=USER_TYPE_INTERVAL_LABELS["primary"],
        )
        plt.bar(
            x_positions,
            opportunistic_values,
            width=0.86,
            bottom=primary_values,
            label=USER_TYPE_INTERVAL_LABELS["opportunistic"],
        )
        plt.bar(
            x_positions,
            elastic_values,
            width=0.86,
            bottom=primary_values + opportunistic_values,
            label=USER_TYPE_INTERVAL_LABELS["elastic"],
        )
        plt.bar(
            x_positions,
            long_trip_values,
            width=0.86,
            bottom=(
                primary_values
                + opportunistic_values
                + elastic_values
            ),
            label=USER_TYPE_INTERVAL_LABELS["long_trip"],
        )

        plt.xticks(
            x_positions,
            time_labels,
            rotation=90,
            fontsize=USER_COUNT_XTICK_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )
        plt.yticks(
            np.arange(0, common_interval_user_ymax + 2, 1),
            fontsize=USER_COUNT_YTICK_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )
        plt.ylim(0, common_interval_user_ymax + 1)
        plt.xlim(-0.6, len(x_positions) - 0.4)

        plt.xlabel(
            "15-Minute Interval",
            fontsize=USER_COUNT_AXIS_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )
        plt.ylabel(
            "Number of Different EV Users",
            fontsize=USER_COUNT_AXIS_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )
        plt.title(
            "Different EV Users Charging Within Each 15-Minute Interval\n"
            f"{stage_title} ({period_label})",
            fontsize=USER_COUNT_TITLE_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )
        plt.grid(axis="y", alpha=0.7)

        apply_plot_formatting(
            legend_loc="upper right",
            legend_bbox_to_anchor=(0.44, 0.97),
            legend_ncol=2,
        )

        # Reapply the larger sizes because apply_plot_formatting()
        # uses the common global font size.
        ax = plt.gca()

        ax.title.set_fontsize(USER_COUNT_TITLE_SIZE)
        ax.xaxis.label.set_fontsize(USER_COUNT_AXIS_SIZE)
        ax.yaxis.label.set_fontsize(USER_COUNT_AXIS_SIZE)

        for tick_label in ax.get_xticklabels():
            tick_label.set_fontsize(USER_COUNT_XTICK_SIZE)
            tick_label.set_fontweight("bold")

        for tick_label in ax.get_yticklabels():
            tick_label.set_fontsize(USER_COUNT_YTICK_SIZE)
            tick_label.set_fontweight("bold")

        legend = ax.get_legend()
        if legend is not None:
            for legend_text in legend.get_texts():
                legend_text.set_fontsize(USER_COUNT_LEGEND_SIZE)
                legend_text.set_fontweight("bold")

        plt.tight_layout()
        plt.savefig(
            os.path.join(
                GRAPH_DIR,
                (
                    f"{output_prefix}_part_{part_number:02d}_"
                    f"{period_file_label}.png"
                ),
            ),
            dpi=300,
            bbox_inches="tight",
        )
        plt.close()


plot_user_type_interval_parts(
    user_type_count_before_slot,
    "Before Optimization",
    "09b_different_users_by_type_before",
)

plot_user_type_interval_parts(
    user_type_count_after_slot,
    "After Optimization",
    "09c_different_users_by_type_after",
)

charger_util = user_slot_df.groupby("optimized_charger_pile")["charger_energy_kWh"].sum()

plt.figure(figsize=(9, 5))
plt.bar(charger_util.index.astype(str), charger_util.values)
plt.xlabel("Charger Pile")
plt.ylabel("Daily Energy Delivered (kWh)")
plt.title("Daily Energy Delivered by Charger Pile")
plt.grid(axis="y")
apply_plot_formatting()
plt.tight_layout()
plt.savefig(os.path.join(GRAPH_DIR, "10_charger_pile_energy.png"), dpi=300, bbox_inches="tight")
plt.close()

# Booked elastic scheduling visualization. To keep labels readable,
# only 10 elastic vehicles are shown per figure, and the 24-hour day is
# displayed vertically from top to bottom.
if len(elastic_notification_df) > 0:
    elastic_plot_df = (
        elastic_notification_df
        .copy()
        .sort_values(["assigned_arrival_and_plugin_time", "ev_notation"])
        .reset_index(drop=True)
    )

    def time_text_to_hour(value):
        minute_value = parse_time_to_minute(value)
        return float(minute_value) / 60.0

    n_elastic_figures = int(math.ceil(
        len(elastic_plot_df) / float(MAX_ELASTIC_USERS_PER_FIGURE)
    ))

    # Larger fonts used only for Figure 11.
    FIG11_TITLE_SIZE = 26
    FIG11_AXIS_SIZE = 23
    FIG11_TIME_TICK_SIZE = 21
    FIG11_EV_ID_SIZE = 19
    FIG11_LEGEND_SIZE = 21
    FIG11_PRICE_SIZE = 21

    for figure_index in range(n_elastic_figures):
        start_row = figure_index * MAX_ELASTIC_USERS_PER_FIGURE

        end_row = min(
            len(elastic_plot_df),
            (figure_index + 1) * MAX_ELASTIC_USERS_PER_FIGURE,
        )

        elastic_plot_batch = elastic_plot_df.iloc[
            start_row:end_row
        ].reset_index(drop=True)

        x_positions = np.arange(len(elastic_plot_batch))

        fig_width = max(
            10,
            1.3 * len(elastic_plot_batch) + 2,
        )

        fig_height = 12
        bar_width = 0.65

        fig, ax = plt.subplots(
            figsize=(fig_width, fig_height)
        )

        # ====================================================
        # DRAW EACH ELASTIC USER
        # ====================================================

        for i, row in elastic_plot_batch.iterrows():

            window_start_hour = time_text_to_hour(
                row["booked_window_start"]
            )

            window_end_hour = time_text_to_hour(
                row["booked_window_end"]
            )

            session_start_hour = time_text_to_hour(
                row["assigned_arrival_and_plugin_time"]
            )

            session_end_hour = time_text_to_hour(
                row["expected_charging_completion_time"]
            )

            # ------------------------------------------------
            # Booked elastic window
            # ------------------------------------------------

            ax.add_patch(
                Rectangle(
                    (
                        i - bar_width / 2.0,
                        window_start_hour,
                    ),
                    bar_width,
                    window_end_hour - window_start_hour,
                    alpha=0.25,
                    label=(
                        "Booked elastic window"
                        if i == 0
                        else None
                    ),
                )
            )

            # ------------------------------------------------
            # Optimized charging session
            # ------------------------------------------------

            ax.add_patch(
                Rectangle(
                    (
                        i - bar_width / 2.0,
                        session_start_hour,
                    ),
                    bar_width,
                    session_end_hour - session_start_hour,
                    alpha=0.90,
                    label=(
                        "Optimized charging session"
                        if i == 0
                        else None
                    ),
                )
            )

            # ------------------------------------------------
            # Tariff value
            #
            # Horizontal and slightly above the optimized
            # charging-session range.
            # ------------------------------------------------

            price_label_y = max(
                session_start_hour - 0.12,
                0.05,
            )

            ax.text(
                i,
                price_label_y,
                f"{float(row['final_elastic_tariff_LKR_kWh']):.1f}",
                ha="center",
                va="bottom",
                rotation=0,
                fontsize=FIG11_PRICE_SIZE,
                fontname=PLOT_FONT_NAME,
                fontweight="bold",
            )

        # ====================================================
        # AXIS SETTINGS
        # ====================================================

        ax.set_xlim(
            -0.75,
            len(elastic_plot_batch) - 0.25,
        )

        ax.set_xticks(
            x_positions
        )

        ax.set_xticklabels(
            elastic_plot_batch["ev_notation"],
            fontsize=FIG11_EV_ID_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )

        # 24-hour vertical axis:
        # 00:00 at top and 24:00 at bottom.
        ax.set_ylim(
            24,
            0,
        )

        ax.set_yticks(
            np.arange(0, 25, 1)
        )

        ax.set_xlabel(
            "Elastic EV user",
            fontsize=FIG11_AXIS_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )

        ax.set_ylabel(
            "Time of day (hour)",
            fontsize=FIG11_AXIS_SIZE,
            fontname=PLOT_FONT_NAME,
            fontweight="bold",
        )

        # ====================================================
        # TITLE AND OUTPUT NAME
        # ====================================================

        if n_elastic_figures == 1:

            ax.set_title(
                "Booked Elastic User Windows and Optimized Whole Sessions",
                fontsize=FIG11_TITLE_SIZE,
                fontname=PLOT_FONT_NAME,
                fontweight="bold",
            )

            output_name = (
                "11_elastic_user_schedule_windows.png"
            )

        else:

            ax.set_title(
                "Booked Elastic User Windows and Optimized Whole Sessions "
                f"(Users {start_row + 1}-{end_row})",
                fontsize=FIG11_TITLE_SIZE,
                fontname=PLOT_FONT_NAME,
                fontweight="bold",
            )

            output_name = (
                f"11_elastic_user_schedule_windows_part_"
                f"{figure_index + 1:02d}.png"
            )

        # ====================================================
        # FORMATTING
        # ====================================================

        ax.grid(
            axis="y"
        )

        apply_plot_formatting(
            legend_loc="upper right",
            legend_bbox_to_anchor=(
                0.98,
                0.98,
            ),
        )

        # Reapply the larger Figure 11 fonts after
        # the common plot formatter.
        ax.title.set_fontsize(
            FIG11_TITLE_SIZE
        )

        ax.xaxis.label.set_fontsize(
            FIG11_AXIS_SIZE
        )

        ax.yaxis.label.set_fontsize(
            FIG11_AXIS_SIZE
        )

        for tick_label in ax.get_yticklabels():

            tick_label.set_fontname(
                PLOT_FONT_NAME
            )

            tick_label.set_fontsize(
                FIG11_TIME_TICK_SIZE
            )

            tick_label.set_fontweight(
                "bold"
            )

        for tick_label in ax.get_xticklabels():

            tick_label.set_fontname(
                PLOT_FONT_NAME
            )

            tick_label.set_fontsize(
                FIG11_EV_ID_SIZE
            )

            tick_label.set_fontweight(
                "bold"
            )

        legend = ax.get_legend()

        if legend is not None:

            for legend_text in legend.get_texts():

                legend_text.set_fontname(
                    PLOT_FONT_NAME
                )

                legend_text.set_fontsize(
                    FIG11_LEGEND_SIZE
                )

                legend_text.set_fontweight(
                    "bold"
                )

        for annotation in ax.texts:

            annotation.set_fontname(
                PLOT_FONT_NAME
            )

            annotation.set_fontsize(
                FIG11_PRICE_SIZE
            )

            annotation.set_fontweight(
                "bold"
            )

        # ====================================================
        # SAVE FIGURE
        # ====================================================

        plt.tight_layout()

        plt.savefig(
            os.path.join(
                GRAPH_DIR,
                output_name,
            ),
            dpi=300,
            bbox_inches="tight",
        )

        plt.close()

line_graph(
    "12_elastic_load_and_pv.png",
    [
        (pv, "PV Generation"),
        (elastic_load_before, "Elastic Load Before"),
        (elastic_load_after, "Elastic Load After"),
    ],
    "Power (kW)",
    "Elastic User Load Placement Relative to PV Generation",
    # Figure 12: upper-right inside the axes.
    legend_loc="upper right",
    legend_bbox_to_anchor=(0.98, 0.98),
    legend_ncol=1,
)

# Combined primary-plus-elastic schedule overview so the booked elastic
# users can be visually compared against the fixed primary users.
if len(user_summary_df) > 0:
    def _time_text_to_hour_chart(value):
        return float(parse_time_to_minute(value)) / 60.0

    primary_plot_df = (
        user_summary_df[user_summary_df["user_type"] == "primary"]
        [["ev_notation", "optimized_start_time", "optimized_end_time"]]
        .copy()
        .sort_values(["optimized_start_time", "ev_notation"])
        .reset_index(drop=True)
    )

    elastic_schedule_plot_df = (
        elastic_notification_df[[
            "ev_notation",
            "booked_window_start",
            "booked_window_end",
            "assigned_arrival_and_plugin_time",
            "expected_charging_completion_time",
            "final_elastic_tariff_LKR_kWh",
        ]]
        .copy()
        .sort_values(["assigned_arrival_and_plugin_time", "ev_notation"])
        .reset_index(drop=True)
    ) if len(elastic_notification_df) > 0 else pd.DataFrame()

    primary_y = np.arange(len(primary_plot_df))
    elastic_y = np.arange(len(elastic_schedule_plot_df)) + len(primary_plot_df) + 2

    plt.figure(figsize=(15, max(10, 0.18 * (len(primary_plot_df) + len(elastic_schedule_plot_df) + 4))))

    if len(primary_plot_df) > 0:
        primary_start_h = primary_plot_df["optimized_start_time"].apply(_time_text_to_hour_chart)
        primary_end_h = primary_plot_df["optimized_end_time"].apply(_time_text_to_hour_chart)
        plt.barh(
            primary_y,
            primary_end_h - primary_start_h,
            left=primary_start_h,
            alpha=0.85,
            label="Primary fixed charging session",
        )

    if len(elastic_schedule_plot_df) > 0:
        elastic_window_start_h = elastic_schedule_plot_df["booked_window_start"].apply(_time_text_to_hour_chart)
        elastic_window_end_h = elastic_schedule_plot_df["booked_window_end"].apply(_time_text_to_hour_chart)
        elastic_session_start_h = elastic_schedule_plot_df["assigned_arrival_and_plugin_time"].apply(_time_text_to_hour_chart)
        elastic_session_end_h = elastic_schedule_plot_df["expected_charging_completion_time"].apply(_time_text_to_hour_chart)

        plt.barh(
            elastic_y,
            elastic_window_end_h - elastic_window_start_h,
            left=elastic_window_start_h,
            alpha=0.22,
            label="Elastic booked window",
        )
        plt.barh(
            elastic_y,
            elastic_session_end_h - elastic_session_start_h,
            left=elastic_session_start_h,
            alpha=0.95,
            label="Elastic optimized session",
        )

    combined_labels = list(primary_plot_df["ev_notation"])
    if len(elastic_schedule_plot_df) > 0:
        combined_labels += list(elastic_schedule_plot_df["ev_notation"])
    combined_y = list(primary_y) + list(elastic_y)

    if len(primary_plot_df) > 0 and len(elastic_schedule_plot_df) > 0:
        plt.axhline(len(primary_plot_df) + 0.5, linestyle="--", linewidth=1.5)
        plt.text(23.85, len(primary_plot_df) / 2.0, "Primary users", va="center", ha="right", fontsize=PLOT_FONT_SIZE)
        plt.text(23.85, len(primary_plot_df) + 1.2 + len(elastic_schedule_plot_df) / 2.0, "Elastic users", va="center", ha="right", fontsize=PLOT_FONT_SIZE)

    plt.yticks(combined_y, combined_labels, fontsize=PLOT_FONT_SIZE)
    plt.xlim(0, 24)
    plt.xticks(np.arange(0, 25, 1))
    plt.xlabel("Time of day (hour)")
    plt.ylabel("Primary and Elastic EV users")
    plt.title("Primary Fixed Sessions and Elastic User Placement Overview")
    plt.grid(axis="x")
    apply_plot_formatting(
        # Figure 13: lower-right inside the axes.
        legend_loc="lower right",
        legend_bbox_to_anchor=(0.98, 0.02),
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(GRAPH_DIR, "13_primary_and_elastic_schedule_overview.png"),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

# Elastic shift analysis by user.
if len(elastic_analysis_df) > 0:
    elastic_shift_plot_df = (
        elastic_analysis_df[["ev_notation", "shifted_minutes"]]
        .copy()
        .sort_values(["shifted_minutes", "ev_notation"])
        .reset_index(drop=True)
    )

    y_positions = np.arange(len(elastic_shift_plot_df))
    plt.figure(figsize=(12, max(8, 0.32 * len(elastic_shift_plot_df))))
    plt.barh(y_positions, elastic_shift_plot_df["shifted_minutes"])
    plt.axvline(0.0, linestyle="--", linewidth=1.5)
    plt.yticks(y_positions, elastic_shift_plot_df["ev_notation"], fontsize=PLOT_FONT_SIZE)
    plt.xlabel("Shifted minutes (positive = later than original, negative = earlier)")
    plt.ylabel("Elastic EV user")
    plt.title("Elastic User Rescheduling Distance from Original Start Time")
    plt.grid(axis="x")
    apply_plot_formatting()
    plt.tight_layout()
    plt.savefig(
        os.path.join(GRAPH_DIR, "14_elastic_shift_minutes_by_user.png"),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    # Source-energy allocation analysis for each elastic user.
    elastic_energy_plot_df = (
        elastic_analysis_df[[
            "ev_notation",
            "pv_energy_kWh",
            "grid_energy_kWh",
            "bess_energy_kWh",
        ]]
        .copy()
        .sort_values(["pv_energy_kWh", "ev_notation"], ascending=[False, True])
        .reset_index(drop=True)
    )

    x_positions = np.arange(len(elastic_energy_plot_df))
    plt.figure(figsize=(max(12, 0.38 * len(elastic_energy_plot_df)), 6))
    plt.bar(x_positions, elastic_energy_plot_df["pv_energy_kWh"], label="PV energy")
    plt.bar(
        x_positions,
        elastic_energy_plot_df["grid_energy_kWh"],
        bottom=elastic_energy_plot_df["pv_energy_kWh"],
        label="Grid energy",
    )
    plt.bar(
        x_positions,
        elastic_energy_plot_df["bess_energy_kWh"],
        bottom=(
            elastic_energy_plot_df["pv_energy_kWh"]
            + elastic_energy_plot_df["grid_energy_kWh"]
        ),
        label="BESS energy",
    )
    plt.xticks(x_positions, elastic_energy_plot_df["ev_notation"], rotation=90, fontsize=PLOT_FONT_SIZE)
    plt.xlabel("Elastic EV user")
    plt.ylabel("Delivered charger energy (kWh)")
    plt.title("Elastic User Energy Source Breakdown After Optimization")
    plt.grid(axis="y")
    apply_plot_formatting(
        # Figure 15: upper-right inside the axes.
        legend_loc="upper right",
        legend_bbox_to_anchor=(0.98, 0.98),
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(GRAPH_DIR, "15_elastic_energy_source_breakdown.png"),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    # Tariff analysis for Option 2: compare the primary base and final
    # elastic tariff, and show how the potential flexibility discount is
    # reduced to an effective discount according to solar placement.
    elastic_tariff_plot_df = (
        elastic_analysis_df[[
            "ev_notation",
            "base_rate_LKR_kWh",
            "final_tariff_LKR_kWh",
            "flexibility_discount_potential_LKR_kWh",
            "basic_flexibility_reward_LKR_kWh",
            "solar_scaled_flexibility_reward_LKR_kWh",
            "flexibility_discount_LKR_kWh",
            "solar_discount_LKR_kWh",
        ]]
        .copy()
        .sort_values(["final_tariff_LKR_kWh", "ev_notation"], ascending=[False, True])
        .reset_index(drop=True)
    )

    x_positions = np.arange(len(elastic_tariff_plot_df))
    width = 0.38
    plt.figure(figsize=(max(12, 0.38 * len(elastic_tariff_plot_df)), 6))
    plt.bar(
        x_positions - width / 2.0,
        elastic_tariff_plot_df["base_rate_LKR_kWh"],
        width=width,
        label="Session-average primary base rate",
    )
    plt.bar(
        x_positions + width / 2.0,
        elastic_tariff_plot_df["final_tariff_LKR_kWh"],
        width=width,
        label="Final elastic tariff",
    )
    plt.plot(
        x_positions,
        elastic_tariff_plot_df["flexibility_discount_potential_LKR_kWh"],
        linestyle="--",
        linewidth=1.5,
        label="Potential flexibility discount",
    )
    plt.plot(
        x_positions,
        elastic_tariff_plot_df["flexibility_discount_LKR_kWh"],
        marker="o",
        linewidth=1.5,
        label="Effective flexibility discount",
    )
    plt.plot(
        x_positions,
        elastic_tariff_plot_df["solar_discount_LKR_kWh"],
        marker="s",
        linewidth=1.5,
        label="Separate solar discount",
    )
    plt.xticks(x_positions, elastic_tariff_plot_df["ev_notation"], rotation=90, fontsize=PLOT_FONT_SIZE)
    plt.xlabel("Elastic EV user")
    plt.ylabel("Tariff / discount (LKR/kWh)")
    plt.title("Elastic Tariff Analysis: Solar-Scaled Flexibility Reward and Final Tariff")
    plt.grid(axis="y")
    apply_plot_formatting(
        # Figure 16: upper-right inside the axes. Use one column so the
        # legend remains narrow and can be moved easily with the anchor.
        legend_loc="upper right",
        legend_bbox_to_anchor=(0.98, 0.98),
        legend_ncol=1,
    )
    plt.tight_layout()
    plt.savefig(
        os.path.join(GRAPH_DIR, "16_elastic_tariff_analysis.png"),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()
    
    
# ============================================================
# PRINT SUMMARY
# ============================================================
print("\n========== FINAL EXACT-MINUTE 450 kW CHARGER MILP SUMMARY ==========")
print(summary_df)

print("\nCreated files:")
print(optimized_ev_profile_txt)
print(optimized_bess_profile_txt)
print(clean_user_csv)
print(station_slot_csv)
print(slot_summary_csv)
print(user_slot_csv)
print(user_summary_csv)
print(elastic_notification_csv)
print(elastic_analysis_csv)
print(charger_slot_csv)
print(charger_minute_csv)
print(minute_station_csv)
print(summary_csv)
print(dispatch_block_csv)
print(grid_price_input_csv)
print(excel_file)
print(GRAPH_DIR)

print("\nStation:")
print("Charger piles:", NUMBER_OF_CHARGER_PILES)
print("Each pile rating:", CHARGER_PILE_RATED_POWER_KW, "kW")
print("Station charging capacity:", STATION_POWER_CAPACITY, "kW")
print("Max exact active EV count before:", int(np.max(active_user_count_before_exact_minute)))
print("Max exact active EV count after:", max_after_exact_station_count)
print("Max exact charger active count after:", max_after_exact_charger_count)
print("Max exact charger power after:", round(max_after_exact_charger_power, 3), "kW")
print("Charger one-user violations after:", after_charger_one_user_violations)
print("Charger power violations after:", after_charger_power_violations)
print("Station count violations after:", after_station_count_violations)
print("Station power violations after:", after_station_power_violations)

print("\n========== GRID IMPORT RESULTS ==========")

# ------------------------------------------------------------
# Total daily grid-import energy
# ------------------------------------------------------------

print("\nTotal Grid Import Energy:")

print(
    "Before optimization:",
    round(GRID_IMPORT_ENERGY_BEFORE_KWH, 2),
    "kWh",
)

print(
    "After optimization :",
    round(GRID_IMPORT_ENERGY_AFTER_KWH, 2),
    "kWh",
)

print(
    "Energy reduction   :",
    round(
        GRID_IMPORT_ENERGY_BEFORE_KWH
        - GRID_IMPORT_ENERGY_AFTER_KWH,
        2,
    ),
    "kWh",
)

print(
    "Energy reduction percentage:",
    round(
        100.0
        * (
            GRID_IMPORT_ENERGY_BEFORE_KWH
            - GRID_IMPORT_ENERGY_AFTER_KWH
        )
        / max(GRID_IMPORT_ENERGY_BEFORE_KWH, 1e-6),
        2,
    ),
    "%",
)


# ------------------------------------------------------------
# Overall daily peak grid import
# ------------------------------------------------------------

print("\nOverall Peak Grid Import:")

print(
    "Before optimization:",
    round(GRID_IMPORT_PEAK_BEFORE_KW, 2),
    "kW",
)

print(
    "After optimization :",
    round(GRID_IMPORT_PEAK_AFTER_KW, 2),
    "kW",
)

print(
    "Peak reduction     :",
    round(
        GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_KW,
        2,
    ),
    "kW",
)

print(
    "Peak reduction percentage:",
    round(
        GRID_IMPORT_PEAK_REDUCTION_ACHIEVED_PERCENTAGE,
        2,
    ),
    "%",
)


# ------------------------------------------------------------
# Peak-period grid import: 18:30-22:30
# ------------------------------------------------------------

print("\nPeak-Period Grid Import (18:30-22:30):")

print(
    "Peak grid import before optimization:",
    round(
        GRID_IMPORT_PEAK_PERIOD_BEFORE_KW,
        2,
    ),
    "kW",
)

print(
    "Peak grid import after optimization :",
    round(
        GRID_IMPORT_PEAK_PERIOD_AFTER_KW,
        2,
    ),
    "kW",
)

PEAK_PERIOD_REDUCTION_KW = (
    GRID_IMPORT_PEAK_PERIOD_BEFORE_KW
    - GRID_IMPORT_PEAK_PERIOD_AFTER_KW
)

PEAK_PERIOD_REDUCTION_PERCENTAGE = (
    100.0
    * PEAK_PERIOD_REDUCTION_KW
    / max(
        GRID_IMPORT_PEAK_PERIOD_BEFORE_KW,
        1e-6,
    )
)

print(
    "Peak-period reduction:",
    round(
        PEAK_PERIOD_REDUCTION_KW,
        2,
    ),
    "kW",
)

print(
    "Peak-period reduction percentage:",
    round(
        PEAK_PERIOD_REDUCTION_PERCENTAGE,
        2,
    ),
    "%",
)


# ------------------------------------------------------------
# Grid limits
# ------------------------------------------------------------

print("\nGrid Limits:")

print(
    "Physical grid-import maximum:",
    round(GRID_IMPORT_MAX_KW, 2),
    "kW",
)

print(
    "Optimized grid-import cap:",
    round(OPTIMIZED_GRID_IMPORT_MAX_KW, 2),
    "kW",
)

print("\n========== PROFIT RESULTS ==========")

print(
    "Profit Before Optimization:",
    round(profit_before, 2),
    "LKR/day",
)

print(
    "Profit After Optimization :",
    round(profit_after, 2),
    "LKR/day",
)

print(
    "Profit Improvement        :",
    round(PROFIT_IMPROVEMENT_LKR, 2),
    "LKR/day",
)

print(
    "Profit Improvement Percentage:",
    round(PROFIT_IMPROVEMENT_PERCENTAGE, 2),
    "%",
)

print("\n========== PV UTILIZATION RESULTS ==========")

print(
    "Total Available PV Energy:",
    round(PV_TOTAL_ENERGY_KWH, 2),
    "kWh",
)

print("\nBefore Optimization:")

print(
    "PV to EV:",
    round(PV_TO_EV_BEFORE_KWH, 2),
    "kWh",
)

print(
    "PV to BESS:",
    round(PV_TO_BESS_BEFORE_KWH, 2),
    "kWh",
)

print(
    "Total PV Utilized:",
    round(PV_UTILIZED_BEFORE_KWH, 2),
    "kWh",
)

print(
    "PV Utilization:",
    round(PV_UTILIZATION_BEFORE_PERCENTAGE, 2),
    "%",
)


print("\nAfter Optimization:")

print(
    "PV to EV:",
    round(PV_TO_EV_AFTER_KWH, 2),
    "kWh",
)

print(
    "PV to BESS:",
    round(PV_TO_BESS_AFTER_KWH, 2),
    "kWh",
)

print(
    "Total PV Utilized:",
    round(PV_UTILIZED_AFTER_KWH, 2),
    "kWh",
)

print(
    "PV Utilization:",
    round(PV_UTILIZATION_AFTER_PERCENTAGE, 2),
    "%",
)


print("\nPV Utilization Improvement:")

print(
    round(
        PV_UTILIZATION_IMPROVEMENT_PERCENTAGE_POINTS,
        2,
    ),
    "percentage points",
)

print("\nTotal EV Energy Before:", round(np.sum(ev_load_before * dt), 2), "kWh")
print("Total EV Energy After:", round(np.sum(total_ev_after * dt), 2), "kWh")
print("Secondary Energy Before:", round(np.sum(secondary_load_before * dt), 2), "kWh")
print("Secondary Energy After:", round(np.sum(secondary_load_after * dt), 2), "kWh")
print("Elastic Energy Before:", round(np.sum(elastic_load_before * dt), 2), "kWh")
print("Elastic Energy After:", round(np.sum(elastic_load_after * dt), 2), "kWh")

print("\nPV to EV:", round(np.sum(pv_to_ev * dt), 2), "kWh")
print("PV to BESS:", round(np.sum(pv_to_bess * dt), 2), "kWh")
print("PV Export:", round(np.sum(pv_export * dt), 2), "kWh")
print("PV Curtailed:", round(np.sum(pv_curtailed * dt), 2), "kWh")

print("\nDynamic secondary users:", len(dynamic_secondary_users_df))
print("Booked elastic users:", len(elastic_users_df))
print("Maximum shifted dynamic secondary users allowed:", MAX_SHIFTED_SECONDARY_USERS_ALLOWED)
print("Actual shifted dynamic secondary users:", len(shifted_secondary_users_df))
print("Actual shifted dynamic secondary percentage:", round(actual_shifted_secondary_percentage, 2), "%")
print("Unshifted dynamic secondary users:", len(dynamic_secondary_users_df) - len(shifted_secondary_users_df))
print("Elastic window schedule violations:", elastic_window_violation_count)

print("\nExisting Dynamic Secondary Avg Tariff Before:", round(existing_secondary_avg_tariff, 2), "LKR/kWh")
print("Optimized Dynamic Secondary Avg Tariff After:", round(optimized_secondary_avg_tariff, 2), "LKR/kWh")
print("Optimized Elastic Avg Tariff After:", round(optimized_elastic_avg_tariff, 2), "LKR/kWh")
print("Secondary Solar Shift Percentage:", round(secondary_solar_shift_percentage, 2), "%")
print("Elastic Solar Shift Percentage:", round(elastic_solar_shift_percentage, 2), "%")