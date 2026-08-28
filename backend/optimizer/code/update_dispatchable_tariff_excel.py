from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple


# ============================================================
# FILE SETTINGS
# ============================================================
# The project input files are stored in the inputs folder.

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_DIR / "inputs" / "grid_price_input_used.csv"

NUMBER_OF_SLOTS = 96
SLOTS_PER_HOUR = 4


# ============================================================
# COLUMN NAMES
# ============================================================
EXPORT_COLUMN_CANDIDATES = [
    "grid_export_price_LKR_kWh",
    "grid_export_price",
    "grid_export_nondispatchable_price_LKR_kWh",
]

IMPORT_COLUMN_CANDIDATES = [
    "grid_import_price_LKR_kWh",
    "grid_import_price",
]

DISPATCHABLE_COLUMN = "grid_export_dispatchable_price_LKR_kWh"


# ============================================================
# DISPATCHABLE-TARIFF SETTINGS
# ============================================================
# High-solar period:
# Keep the dispatchable tariff close to the hourly average
# normal-export tariff.
SOLAR_START_HOUR = 8
SOLAR_END_HOUR = 17
SOLAR_IMPORT_WEIGHT = 0.15

# Evening peak:
# Keep the dispatchable tariff close to the hourly average
# grid-import tariff.
PEAK_START_HOUR = 18
PEAK_END_HOUR = 23
PEAK_MIN_IMPORT_WEIGHT = 0.85

# Other hours:
# Move closer to import when the hourly average import tariff
# is relatively high.
OTHER_MIN_IMPORT_WEIGHT = 0.25
OTHER_MAX_IMPORT_WEIGHT = 0.90

# The dispatchable tariff must remain below the lowest import
# tariff among the four slots of each hour.
IMPORT_SAFETY_MARGIN_LKR_KWH = 0.01

# Prefer dispatchable tariff slightly above the hourly average
# normal-export tariff whenever this is feasible.
EXPORT_MARGIN_LKR_KWH = 0.01

ROUND_DECIMALS = 3
COMPARISON_TOLERANCE = 1e-9


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def normalize_header(value: str) -> str:
    return str(value).strip().lower()


def find_column(
    fieldnames: List[str],
    candidates: List[str],
    description: str,
) -> str:
    normalized_map = {
        normalize_header(name): name
        for name in fieldnames
    }

    for candidate in candidates:
        candidate_key = normalize_header(candidate)

        if candidate_key in normalized_map:
            return normalized_map[candidate_key]

    raise ValueError(
        f"Could not find the {description} column.\n"
        f"Accepted names: {', '.join(candidates)}\n"
        f"Columns found: {', '.join(fieldnames)}"
    )


def read_numeric_column(
    rows: List[Dict[str, str]],
    column_name: str,
) -> List[float]:
    values: List[float] = []

    for csv_row_number, row in enumerate(rows, start=2):
        raw_value = row.get(column_name)

        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid value in column '{column_name}' "
                f"at CSV row {csv_row_number}: {raw_value}"
            ) from exc

        if value < 0:
            raise ValueError(
                f"Negative tariff in column '{column_name}' "
                f"at CSV row {csv_row_number}."
            )

        values.append(value)

    return values


def calculate_hourly_averages(
    values: List[float],
) -> List[float]:
    averages: List[float] = []

    for hour in range(24):
        start_slot = hour * SLOTS_PER_HOUR
        end_slot = start_slot + SLOTS_PER_HOUR

        hourly_average = (
            sum(values[start_slot:end_slot])
            / SLOTS_PER_HOUR
        )

        averages.append(hourly_average)

    return averages


def calculate_target_weight(
    hour: int,
    average_import: float,
    minimum_hourly_average_import: float,
    maximum_hourly_average_import: float,
) -> Tuple[float, str]:
    """
    Return a weight between 0 and 1.

    Weight near 0:
        Dispatchable tariff is close to average export.

    Weight near 1:
        Dispatchable tariff is close to average import.
    """

    # High-solar hours
    if SOLAR_START_HOUR <= hour < SOLAR_END_HOUR:
        return SOLAR_IMPORT_WEIGHT, "High solar"

    import_spread = (
        maximum_hourly_average_import
        - minimum_hourly_average_import
    )

    if import_spread <= COMPARISON_TOLERANCE:
        import_price_score = 0.5
    else:
        import_price_score = (
            average_import
            - minimum_hourly_average_import
        ) / import_spread

    import_price_score = max(
        0.0,
        min(1.0, import_price_score),
    )

    weight = (
        OTHER_MIN_IMPORT_WEIGHT
        + (
            OTHER_MAX_IMPORT_WEIGHT
            - OTHER_MIN_IMPORT_WEIGHT
        )
        * import_price_score
    )

    period_type = "Normal period"

    # Evening peak hours
    if PEAK_START_HOUR <= hour < PEAK_END_HOUR:
        weight = max(
            weight,
            PEAK_MIN_IMPORT_WEIGHT,
        )
        period_type = "Peak period"

    weight = max(0.0, min(1.0, weight))

    return weight, period_type


def calculate_dispatchable_tariff(
    hour: int,
    export_slots: List[float],
    import_slots: List[float],
    minimum_hourly_average_import: float,
    maximum_hourly_average_import: float,
) -> Tuple[
    float,
    float,
    str,
    str,
    float,
    float,
    float,
    float,
]:
    """
    Calculate one constant dispatchable tariff for one hour.

    First calculate a target tariff from hourly averages:

        target
            = average_export
              + weight * (average_import - average_export)

    Then apply the strict import-price cap:

        dispatchable
            <= minimum import tariff among the four slots
               - safety margin

    Therefore, the same hourly dispatchable tariff cannot exceed
    the import tariff in any of the four 15-minute slots.
    """

    if len(export_slots) != SLOTS_PER_HOUR:
        raise ValueError(
            f"Hour {hour}: expected four export-price slots."
        )

    if len(import_slots) != SLOTS_PER_HOUR:
        raise ValueError(
            f"Hour {hour}: expected four import-price slots."
        )

    average_export = (
        sum(export_slots)
        / SLOTS_PER_HOUR
    )

    average_import = (
        sum(import_slots)
        / SLOTS_PER_HOUR
    )

    maximum_slot_export = max(export_slots)
    minimum_slot_import = min(import_slots)

    weight, period_type = calculate_target_weight(
        hour=hour,
        average_import=average_import,
        minimum_hourly_average_import=(
            minimum_hourly_average_import
        ),
        maximum_hourly_average_import=(
            maximum_hourly_average_import
        ),
    )

    target_tariff = (
        average_export
        + weight
        * (average_import - average_export)
    )

    # Strict upper limit:
    # the tariff must remain below every import tariff in the hour.
    strict_import_upper_bound = (
        minimum_slot_import
        - IMPORT_SAFETY_MARGIN_LKR_KWH
    )

    if strict_import_upper_bound < 0:
        raise ValueError(
            f"Hour {hour:02d}:00 has an import tariff below "
            f"the configured safety margin."
        )

    # Preferred lower limit:
    # remain above the hourly average export tariff when possible.
    preferred_export_lower_bound = (
        average_export
        + EXPORT_MARGIN_LKR_KWH
    )

    if (
        preferred_export_lower_bound
        <= strict_import_upper_bound
    ):
        dispatchable_tariff = min(
            max(
                target_tariff,
                preferred_export_lower_bound,
            ),
            strict_import_upper_bound,
        )

        status = (
            "Feasible: above average export and "
            "below every import slot"
        )

    else:
        # A conflict exists when the minimum import tariff is
        # already below the hourly average export tariff.
        #
        # The strict import condition is given priority.
        dispatchable_tariff = strict_import_upper_bound

        status = (
            "Conflict: strict import cap applied; "
            "cannot also remain above average export"
        )

    dispatchable_tariff = round(
        dispatchable_tariff,
        ROUND_DECIMALS,
    )

    # Rounding can move the result slightly upward.
    # Recheck against the minimum slot import tariff.
    rounding_step = 10 ** (-ROUND_DECIMALS)

    if dispatchable_tariff >= minimum_slot_import:
        dispatchable_tariff = round(
            minimum_slot_import - rounding_step,
            ROUND_DECIMALS,
        )

    return (
        dispatchable_tariff,
        round(weight, 4),
        period_type,
        status,
        average_export,
        average_import,
        maximum_slot_export,
        minimum_slot_import,
    )


def safely_overwrite_csv(
    file_path: Path,
    fieldnames: List[str],
    rows: List[Dict[str, str]],
) -> None:
    """
    Write to a temporary CSV first.

    Replace the original CSV only after the temporary file has
    been written successfully. No permanent second file is created.
    """

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            delete=False,
            dir=file_path.parent,
            prefix="grid_price_temp_",
            suffix=".csv",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            writer = csv.DictWriter(
                temporary_file,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )

            writer.writeheader()
            writer.writerows(rows)

        os.replace(
            temporary_path,
            file_path,
        )

    except PermissionError as exc:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise PermissionError(
            "The tariff CSV could not be replaced.\n"
            "Close grid_price_input_used.csv in Excel and "
            "stop any program currently using it, then run "
            "this script again."
        ) from exc

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise


# ============================================================
# MAIN PROGRAM
# ============================================================
def main() -> None:
    # The CSV must be in the project inputs folder.
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            "grid_price_input_used.csv was not found.\n\n"
            f"Expected location:\n{INPUT_FILE}\n\n"
            "Place grid_price_input_used.csv in the project inputs folder."
        )

    print(f"Input file found: {INPUT_FILE}")

    # --------------------------------------------------------
    # Read the CSV
    # --------------------------------------------------------
    with INPUT_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise ValueError(
                "The CSV file has no header row."
            )

        fieldnames = [
            str(name).strip()
            for name in reader.fieldnames
        ]

        rows: List[Dict[str, str]] = []

        for raw_row in reader:
            cleaned_row = {
                str(key).strip(): value
                for key, value in raw_row.items()
            }

            rows.append(cleaned_row)

    if len(rows) != NUMBER_OF_SLOTS:
        raise ValueError(
            f"The CSV must contain exactly "
            f"{NUMBER_OF_SLOTS} tariff rows.\n"
            f"Rows found: {len(rows)}"
        )

    # --------------------------------------------------------
    # Identify the input columns
    # --------------------------------------------------------
    export_column = find_column(
        fieldnames,
        EXPORT_COLUMN_CANDIDATES,
        "normal export tariff",
    )

    import_column = find_column(
        fieldnames,
        IMPORT_COLUMN_CANDIDATES,
        "grid import tariff",
    )

    if DISPATCHABLE_COLUMN not in fieldnames:
        fieldnames.append(DISPATCHABLE_COLUMN)

        for row in rows:
            row[DISPATCHABLE_COLUMN] = ""

    # --------------------------------------------------------
    # Read numeric tariff arrays
    # --------------------------------------------------------
    export_prices = read_numeric_column(
        rows,
        export_column,
    )

    import_prices = read_numeric_column(
        rows,
        import_column,
    )

    hourly_average_imports = (
        calculate_hourly_averages(
            import_prices
        )
    )

    minimum_hourly_average_import = min(
        hourly_average_imports
    )

    maximum_hourly_average_import = max(
        hourly_average_imports
    )

    # --------------------------------------------------------
    # Calculate and display hourly tariffs
    # --------------------------------------------------------
    print()
    print("Strict dispatchable-tariff calculation")
    print("-" * 150)
    print(
        f"{'Hour':<14}"
        f"{'Avg export':>13}"
        f"{'Avg import':>13}"
        f"{'Max export':>13}"
        f"{'Min import':>13}"
        f"{'Weight':>10}"
        f"{'Dispatchable':>16}"
        f"{'Period':>16}  "
        f"Status"
    )
    print("-" * 150)

    conflict_hours: List[int] = []

    for hour in range(24):
        start_slot = hour * SLOTS_PER_HOUR
        end_slot = start_slot + SLOTS_PER_HOUR

        export_slots = export_prices[
            start_slot:end_slot
        ]

        import_slots = import_prices[
            start_slot:end_slot
        ]

        (
            dispatchable_tariff,
            weight,
            period_type,
            status,
            average_export,
            average_import,
            maximum_slot_export,
            minimum_slot_import,
        ) = calculate_dispatchable_tariff(
            hour=hour,
            export_slots=export_slots,
            import_slots=import_slots,
            minimum_hourly_average_import=(
                minimum_hourly_average_import
            ),
            maximum_hourly_average_import=(
                maximum_hourly_average_import
            ),
        )

        # Repeat one constant hourly tariff across four slots.
        for slot in range(start_slot, end_slot):
            rows[slot][DISPATCHABLE_COLUMN] = (
                f"{dispatchable_tariff:.{ROUND_DECIMALS}f}"
            )

        # Final strict validation:
        # dispatchable tariff cannot exceed any import slot.
        for slot_offset, import_tariff in enumerate(
            import_slots
        ):
            if (
                dispatchable_tariff
                >
                import_tariff
                + COMPARISON_TOLERANCE
            ):
                absolute_slot = (
                    start_slot + slot_offset
                )

                raise RuntimeError(
                    "Strict import validation failed at "
                    f"slot {absolute_slot}.\n"
                    f"Dispatchable tariff: "
                    f"{dispatchable_tariff}\n"
                    f"Import tariff: {import_tariff}"
                )

        if status.startswith("Conflict"):
            conflict_hours.append(hour)

        hour_text = (
            f"{hour:02d}:00-"
            f"{hour + 1:02d}:00"
        )

        print(
            f"{hour_text:<14}"
            f"{average_export:>13.3f}"
            f"{average_import:>13.3f}"
            f"{maximum_slot_export:>13.3f}"
            f"{minimum_slot_import:>13.3f}"
            f"{weight:>10.4f}"
            f"{dispatchable_tariff:>16.3f}"
            f"{period_type:>16}  "
            f"{status}"
        )

    # --------------------------------------------------------
    # Overwrite the same CSV
    # --------------------------------------------------------
    safely_overwrite_csv(
        file_path=INPUT_FILE,
        fieldnames=fieldnames,
        rows=rows,
    )

    print("-" * 150)
    print()
    print("Tariff update completed successfully.")
    print(f"Updated same file: {INPUT_FILE}")
    print()
    print(
        "Verified: the dispatchable tariff does not "
        "exceed the import tariff in any 15-minute slot."
    )
    print(
        "Each hourly dispatchable tariff is repeated "
        "across four consecutive slots."
    )

    if conflict_hours:
        conflict_text = ", ".join(
            f"{hour:02d}:00-"
            f"{hour + 1:02d}:00"
            for hour in conflict_hours
        )

        print()
        print(
            "WARNING: During these hours, the lowest "
            "import tariff was too low to keep the "
            "dispatchable tariff above the hourly "
            "average export tariff:"
        )
        print(conflict_text)
        print(
            "The strict condition that dispatchable "
            "tariff must remain below import was given "
            "priority."
        )


if __name__ == "__main__":
    main()