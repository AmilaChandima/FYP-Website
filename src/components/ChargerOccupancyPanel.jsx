import { Clock3, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { formatDateLabel, formatTime12 } from "../utils/time";

function minuteFromTime(value) {
  const [hour = "0", minute = "0"] = String(value || "00:00").split(":");
  const total = Number(hour) * 60 + Number(minute);
  return Number.isFinite(total) ? Math.max(0, Math.min(1439, total)) : 0;
}

function normalizeMinuteEntries(occupancy, minute) {
  const entries = occupancy?.[String(minute)] ?? occupancy?.[minute] ?? [];
  return Array.isArray(entries) ? entries : [];
}

export default function ChargerOccupancyPanel({
  occupancy,
  slotOperation = [],
  targetDate,
  available = true,
}) {
  const [selectedTime, setSelectedTime] = useState("10:30");
  const selectedMinute = minuteFromTime(selectedTime);

  const minuteEntries = useMemo(
    () => normalizeMinuteEntries(occupancy, selectedMinute),
    [occupancy, selectedMinute]
  );

  const occupiedByCharger = useMemo(() => {
    const map = new Set();
    minuteEntries.forEach((entry) => {
      const chargerId = Number(typeof entry === "object" ? entry?.chargerId : entry);
      if (chargerId >= 1 && chargerId <= 10) map.add(chargerId);
    });
    return map;
  }, [minuteEntries]);

  const occupiedCount = occupiedByCharger.size;
  const selectedTimeLabel = formatTime12(selectedTime);

  const selectedSlotIndex = Math.min(95, Math.floor(selectedMinute / 15));
  const selectedSlot = useMemo(() => {
    if (!Array.isArray(slotOperation) || slotOperation.length === 0) return null;
    return (
      slotOperation.find((item) => Number(item?.slotIndex) === selectedSlotIndex) ||
      slotOperation[selectedSlotIndex] ||
      null
    );
  }, [slotOperation, selectedSlotIndex]);

  const formatEnergy = (value) => `${Number(value || 0).toFixed(1)} kWh`;

  const gridImportEnergy = Number(selectedSlot?.gridImportEnergyKWh || 0);
  const gridExportEnergy = Number(selectedSlot?.gridExportEnergyKWh || 0);
  const bessChargeEnergy = Number(selectedSlot?.bessChargeEnergyKWh || 0);
  const bessDischargeEnergy = Number(selectedSlot?.bessDischargeEnergyKWh || 0);

  const gridExchangeValue = gridImportEnergy > 1e-6
    ? `Import · ${formatEnergy(gridImportEnergy)}`
    : gridExportEnergy > 1e-6
      ? `Export · ${formatEnergy(gridExportEnergy)}`
      : "No exchange · 0.0 kWh";

  const exportModeValue = gridExportEnergy > 1e-6
    ? String(selectedSlot?.exportMode || "Export")
    : "No export";

  const batteryOperationValue = bessChargeEnergy > 1e-6
    ? `Charging · ${formatEnergy(bessChargeEnergy)}`
    : bessDischargeEnergy > 1e-6
      ? `Discharging · ${formatEnergy(bessDischargeEnergy)}`
      : "Idle · 0.0 kWh";

  return (
    <article className="admin-panel charger-occupancy-panel">
      <div className="charger-occupancy-heading">
        <div>
          <p>SELECTED-TIME FORECAST</p>
          <h2>Tomorrow Operation & Charger Status</h2>
          <span>Select a time tomorrow to view the optimized slot values and charger occupancy.</span>
        </div>

        <label className="charger-occupancy-time-picker">
          <span><Clock3 size={17} /> Select tomorrow time</span>
          <input
            type="time"
            step="60"
            value={selectedTime}
            onChange={(event) => setSelectedTime(event.target.value || "00:00")}
          />
          <small>{targetDate ? formatDateLabel(targetDate) : "Tomorrow"}</small>
        </label>
      </div>

      {!available ? (
        <div className="charger-occupancy-unavailable">
          <XCircle size={20} />
          <div>
            <strong>Charger occupancy data is not available for this optimizer run.</strong>
            <span>Run the optimization again to generate the exact-minute charger status.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="charger-occupancy-compact-summary">
            <div>
              <strong>{selectedTimeLabel}</strong>
              <span>Selected time</span>
            </div>
            <div>
              <strong>{occupiedCount}</strong>
              <span>Occupied</span>
            </div>
            <div>
              <strong>{10 - occupiedCount}</strong>
              <span>Available</span>
            </div>
          </div>

          {selectedSlot && (
            <div className="selected-slot-results-grid">
              <div className="selected-slot-result-card">
                <span>Slot Number</span>
                <strong>{selectedSlot.slotNumber}</strong>
              </div>
              <div className="selected-slot-result-card">
                <span>PV Generation</span>
                <strong>{formatEnergy(selectedSlot.pvGenerationEnergyKWh)}</strong>
              </div>
              <div className="selected-slot-result-card">
                <span>EV Demand</span>
                <strong>{formatEnergy(selectedSlot.evDemandEnergyKWh)}</strong>
              </div>
              <div className="selected-slot-result-card">
                <span>Grid Import / Export</span>
                <strong>{gridExchangeValue}</strong>
              </div>
              <div className="selected-slot-result-card">
                <span>Export Mode</span>
                <strong>{exportModeValue}</strong>
              </div>
              <div className="selected-slot-result-card">
                <span>Battery Operation</span>
                <strong>{batteryOperationValue}</strong>
              </div>
            </div>
          )}

          <div className="admin-charger-mini-grid charger-occupancy-mini-grid">
            {Array.from({ length: 10 }, (_, index) => {
              const chargerId = index + 1;
              const isOccupied = occupiedByCharger.has(chargerId);

              return (
                <div
                  key={chargerId}
                  className={`admin-charger-mini ${isOccupied ? "charging" : "available"}`}
                >
                  <span>{String(chargerId).padStart(2, "0")}</span>
                  <i />
                  <strong>{isOccupied ? "Occupied" : "Available"}</strong>
                </div>
              );
            })}
          </div>
        </>
      )}
    </article>
  );
}
