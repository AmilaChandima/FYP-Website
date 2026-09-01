import { ArrowLeft, Download, AlertTriangle, CheckCircle2, BellRing } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AdminForecastChart from "../../components/AdminForecastChart";
import PriceChart from "../../components/PriceChart";
import ChargerOccupancyPanel from "../../components/ChargerOccupancyPanel";
import { getOptimizerJob, publishTomorrowPrice } from "../../services/optimizerApi";
import { useStationData } from "../../context/StationDataContext";
import { formatDateLabel } from "../../utils/time";
import { applyElasticOptimizerNotifications } from "../../services/bookings";

function metric(value, suffix = "") {
  return `${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

function money(value) {
  return `Rs. ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function AdminOptimizationResults() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const station = useStationData();
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    getOptimizerJob(jobId)
      .then((job) => {
        if (job.status !== "success" || !job.result) throw new Error(job.error || "This optimizer run has not completed successfully.");
        setResult(job.result);
        sessionStorage.setItem("solarcharge_admin_optimizer_active_job_v1", job.result.jobId);
      })
      .catch((err) => setError(err.message));
  }, [jobId]);

  async function publishAndNotify() {
    if (!result?.jobId) return;
    setPublishing(true);
    setError("");
    setMessage("");
    try {
      const published = await publishTomorrowPrice(result.jobId);
      await station.syncPublishedPrices();
      const delivered = applyElasticOptimizerNotifications(result);

      let notificationSummary = "No website-linked flexible notifications were present in this optimizer run.";
      if (delivered.deliveredCount > 0) {
        notificationSummary = `${delivered.deliveredCount} flexible customer notification${delivered.deliveredCount === 1 ? "" : "s"} delivered.`;
      } else if (delivered.totalWebsiteNotifications > 0) {
        notificationSummary = `${delivered.totalWebsiteNotifications} website notification record${delivered.totalWebsiteNotifications === 1 ? " was" : "s were"} found, but no matching browser booking was available.`;
      }

      setMessage(`Tomorrow's forecast price for ${formatDateLabel(published.tomorrowDate)} is now visible to customers. ${notificationSummary}`);
    } catch (publishError) {
      setError(publishError.message);
    } finally {
      setPublishing(false);
    }
  }

  if (error && !result) return <div className="admin-page"><div className="optimizer-error-panel"><AlertTriangle /><div><strong>Unable to load results</strong><pre>{error}</pre></div></div></div>;
  if (!result) return <div className="admin-page"><section className="optimizer-running-card"><div className="optimizer-spinner" /><div><h2>Loading forecast analysis...</h2></div></section></div>;

  const { metrics: m, charts } = result;
  const downloadBase = `/api/optimizer/jobs/${jobId}`;

  return (
    <div className="admin-page detailed-forecast-page">
      <div className="admin-page-heading">
        <div>
          <p>FULL FORECAST ANALYSIS</p>
          <h1>Tomorrow's Charging Station Operation</h1>
          <span>{formatDateLabel(result.targetDate)} · Results from the completed Python optimizer run. Charts contain optimized/forecast values only.</span>
        </div>
        <div className="admin-heading-actions">
          <button className="admin-secondary-button" onClick={() => navigate("/admin/optimization")}><ArrowLeft size={17} /> Back to Key Results</button>
          <button className="admin-primary-button combined-publish-button" disabled={publishing} onClick={publishAndNotify}><BellRing size={17} /> {publishing ? "Publishing & Notifying..." : `Publish Tomorrow Price & Notify Flexible Customers (${result.websiteElasticNotificationCount || 0})`}</button>
          <a className="admin-primary-button admin-button-link" href={`${downloadBase}/download-all`}><Download size={17} /> Download Full Result Files</a>
        </div>
      </div>

      {error && result && (
        <div className="optimizer-error-panel">
          <AlertTriangle />
          <div><strong>Unable to publish tomorrow's price and notifications</strong><pre>{error}</pre></div>
        </div>
      )}

      {message && <div className="admin-action-message success-message"><CheckCircle2 /> {message}</div>}

      <section className="forecast-analysis-metrics">
        <article><span>Total forecast revenue</span><strong>{money(m.forecastTotalRevenueLKR)}</strong></article>
        <article><span>Total forecast profit</span><strong>{money(m.forecastTotalProfitLKR)}</strong></article>
        <article><span>Grid import energy</span><strong>{metric(m.forecastGridImportEnergyKWh, " kWh")}</strong></article>
        <article><span>Grid export energy</span><strong>{metric(m.forecastGridExportEnergyKWh, " kWh")}</strong></article>
        <article><span>Peak grid import</span><strong>{metric(m.forecastPeakGridImportKW, " kW")}</strong></article>
        <article><span>Total EV energy</span><strong>{metric(m.forecastTotalEVEnergyKWh, " kWh")}</strong></article>
      </section>

      <article className="admin-panel forecast-chart-panel full-width-chart">
        <div className="admin-panel-heading"><div><h2>Generated Public Price Signal</h2><p>96 optimized prices for tomorrow.</p></div></div>
        <PriceChart prices={result.priceSignal} variant="forecast" />
      </article>

      <ChargerOccupancyPanel
        occupancy={result.chargerOccupancy}
        slotOperation={result.slotOperation}
        available={result.chargerOccupancyAvailable !== false && Boolean(result.chargerOccupancy)}
        targetDate={result.targetDate}
      />

      <section className="forecast-chart-grid">
        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>Optimized EV Charging Load</h2><p>Forecast charging demand by user category and total station EV load.</p></div></div>
          <AdminForecastChart data={charts.evLoad} yLabel="kW" valueSuffix=" kW" series={[
            { key: "primary_load_after_kW", label: "Primary", color: "#78e82f" },
            { key: "dynamic_secondary_load_after_kW", label: "Secondary", color: "#46a6ff" },
            { key: "elastic_load_after_kW", label: "Elastic", color: "#b57cff" },
            { key: "total_ev_load_after_kW", label: "Total EV", color: "#ffffff", width: 3 },
          ]} />
        </article>

        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>Grid Import & Export</h2><p>Forecast optimized power exchange with the grid.</p></div></div>
          <AdminForecastChart data={charts.gridFlow} yLabel="kW" valueSuffix=" kW" series={[
            { key: "grid_import_after_kW", label: "Grid import", color: "#ffb74d" },
            { key: "grid_export_total_kW", label: "Grid export", color: "#42d3a5" },
          ]} />
        </article>

        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>PV Generation & Allocation</h2><p>Forecast solar generation and optimized allocation to EVs, BESS and grid export.</p></div></div>
          <AdminForecastChart data={charts.pvAllocation} yLabel="kW" valueSuffix=" kW" series={[
            { key: "pv_generation_kW", label: "PV generation", color: "#ffd54f", width: 3 },
            { key: "pv_to_ev_kW", label: "PV → EV", color: "#78e82f" },
            { key: "pv_to_bess_kW", label: "PV → BESS", color: "#46a6ff" },
            { key: "pv_to_grid_kW", label: "PV → Grid", color: "#42d3a5" },
          ]} />
        </article>

        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>BESS Operation</h2><p>Forecast optimized charging and discharging power.</p></div></div>
          <AdminForecastChart data={charts.bessPower} yLabel="kW" valueSuffix=" kW" series={[
            { key: "bess_charge_kW", label: "BESS charge", color: "#46a6ff" },
            { key: "bess_to_ev_kW", label: "BESS → EV", color: "#78e82f" },
            { key: "bess_to_grid_kW", label: "BESS → Grid", color: "#42d3a5" },
            { key: "bess_discharge_total_kW", label: "Total discharge", color: "#ff8a65", width: 3 },
          ]} />
        </article>

        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>BESS State of Charge</h2><p>Forecast energy stored in the BESS throughout tomorrow.</p></div></div>
          <AdminForecastChart data={charts.soc} yLabel="kWh" valueSuffix=" kWh" series={[
            { key: "soc_after_kWh", label: "SOC", color: "#b57cff", width: 3 },
          ]} />
        </article>

        <article className="admin-panel forecast-chart-panel">
          <div className="admin-panel-heading"><div><h2>Forecast Active EV Users</h2><p>Optimized active users across tomorrow's 15-minute intervals.</p></div></div>
          <AdminForecastChart data={charts.activeUsers} yLabel="Users" series={[
            { key: "charging_primary_count", label: "Primary", color: "#78e82f" },
            { key: "charging_opportunistic_count", label: "Opportunistic", color: "#46a6ff" },
            { key: "charging_elastic_count", label: "Elastic", color: "#b57cff" },
            { key: "charging_long_trip_count", label: "Long trip", color: "#ffb74d" },
            { key: "max_exact_active_user_count_after", label: "Total active", color: "#ffffff", width: 3 },
          ]} />
        </article>
      </section>

      <article className="admin-panel forecast-chart-panel full-width-chart">
        <div className="admin-panel-heading"><div><h2>Forecast Slot Profit & Customer Revenue Components</h2><p>15-minute optimized profit with elastic and dynamic-secondary charging revenue components.</p></div></div>
        <AdminForecastChart data={charts.slotProfit} yLabel="LKR" valueSuffix=" LKR" series={[
          { key: "slot_profit_LKR", label: "Slot profit", color: "#78e82f", width: 3 },
          { key: "elastic_revenue_LKR", label: "Elastic revenue", color: "#b57cff" },
          { key: "dynamic_secondary_revenue_LKR", label: "Secondary revenue", color: "#46a6ff" },
        ]} />
      </article>

      <div className="forecast-download-row">
        <a href={`${downloadBase}/files/slot_summary_results.csv`}><Download size={16} /> slot_summary_results.csv</a>
        <a href={`${downloadBase}/files/final_milp_summary.csv`}><Download size={16} /> final_milp_summary.csv</a>
        <a href={`${downloadBase}/files/elastic_user_notifications.csv`}><Download size={16} /> elastic_user_notifications.csv</a>
      </div>
    </div>
  );
}
