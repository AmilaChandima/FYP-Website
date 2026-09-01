import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  FileSpreadsheet,
  Play,
  RefreshCcw,
  UploadCloud,
  ExternalLink,
  DatabaseZap,
  BellRing,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PriceChart from "../../components/PriceChart";
import ChargerOccupancyPanel from "../../components/ChargerOccupancyPanel";
import { useStationData } from "../../context/StationDataContext";
import {
  checkOptimizerHealth,
  cancelOptimizerRun,
  getLatestOptimizerResult,
  getOptimizerHistory,
  getOptimizerJob,
  publishTomorrowPriceAndNotify,
  startOptimizerRun,
} from "../../services/optimizerApi";
import { formatDateLabel, getTomorrowDateKey } from "../../utils/time";

const ACTIVE_JOB_KEY = "solarcharge_admin_optimizer_active_job_v1";

const INPUTS = [
  { key: "pv", filename: "pv.txt", title: "Forecast PV Generation", accept: ".txt,text/plain", description: "Tomorrow's PV generation profile." },
  { key: "primaryElastic", filename: "Primary_Elastic_EV_Users.xlsx", title: "Primary & Elastic EV Users", accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", description: "Generate this from Admin → Bookings: fixed base users plus tomorrow's website bookings." },
  { key: "gridPrice", filename: "grid_price_input_used.csv", title: "Forecast Grid Price Input", accept: ".csv,text/csv", description: "Tomorrow's 96-slot grid import and export price signals." },
];

function money(value) {
  return `Rs. ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function energy(value) {
  return `${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`;
}

export default function AdminOptimization() {
  const navigate = useNavigate();
  const station = useStationData();
  const [files, setFiles] = useState({});
  const [backendOnline, setBackendOnline] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [history, setHistory] = useState([]);
  const [restoring, setRestoring] = useState(true);
  const tomorrow = getTomorrowDateKey();
  const allReady = INPUTS.every((input) => files[input.key] instanceof File);
  const running = job?.status === "queued" || job?.status === "running";

  async function refreshHistory() {
    try {
      const items = await getOptimizerHistory(12);
      setHistory(Array.isArray(items) ? items : []);
    } catch {
      setHistory([]);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function restoreOptimizerState() {
      try {
        await checkOptimizerHealth();
        if (cancelled) return;
        setBackendOnline(true);

        // Always restore the most recent completed result first. This keeps the
        // key results visible even when a newer job is currently running or failed.
        try {
          const latest = await getLatestOptimizerResult();
          if (!cancelled && latest?.jobId) {
            setResult(latest);
            station.setTomorrowOptimizationDraft(latest.priceSignal);
          }
        } catch {
          // No completed run yet. This is a valid first-use state.
        }

        const savedJobId = sessionStorage.getItem(ACTIVE_JOB_KEY);
        if (savedJobId) {
          try {
            const savedJob = await getOptimizerJob(savedJobId);
            if (cancelled) return;
            setJob(savedJob);
            if (savedJob.status === "success" && savedJob.result) {
              setResult(savedJob.result);
              station.setTomorrowOptimizationDraft(savedJob.result.priceSignal);
            } else if (savedJob.status === "error") {
              setError(savedJob.error || "The optimizer failed.");
            } else if (savedJob.status === "cancelled") {
              sessionStorage.removeItem(ACTIVE_JOB_KEY);
              setMessage("The previous optimization run was cancelled.");
            }
          } catch {
            sessionStorage.removeItem(ACTIVE_JOB_KEY);
          }
        }

        await refreshHistory();
      } catch {
        if (!cancelled) setBackendOnline(false);
      } finally {
        if (!cancelled) setRestoring(false);
      }
    }

    restoreOptimizerState();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!job?.jobId || !running) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const next = await getOptimizerJob(job.jobId);
        setJob(next);
        if (next.status === "success") {
          setResult(next.result);
          setError("");
          sessionStorage.setItem(ACTIVE_JOB_KEY, next.result.jobId);
          station.setTomorrowOptimizationDraft(next.result.priceSignal);
          refreshHistory();
          window.clearInterval(timer);
        } else if (next.status === "error") {
          setError(next.error || "The optimizer failed.");
          window.clearInterval(timer);
        } else if (next.status === "cancelled") {
          sessionStorage.removeItem(ACTIVE_JOB_KEY);
          setError("");
          setMessage("Optimization cancelled. You can change the inputs and start a new run.");
          window.clearInterval(timer);
        }
      } catch (pollError) {
        setError(pollError.message);
        window.clearInterval(timer);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.jobId, running]);

  const metrics = result?.metrics;
  const priceStats = useMemo(() => metrics ? [
    { label: "Forecast revenue", value: money(metrics.forecastTotalRevenueLKR) },
    { label: "Forecast profit", value: money(metrics.forecastTotalProfitLKR) },
    { label: "Grid import", value: energy(metrics.forecastGridImportEnergyKWh) },
    { label: "Grid export", value: energy(metrics.forecastGridExportEnergyKWh) },
  ] : [], [metrics]);

  function selectFile(key, file) {
    if (!file) return;
    setFiles((current) => ({ ...current, [key]: file }));
    setError("");
    setMessage("");
  }

  async function runOptimization() {
    if (!allReady) return;
    setError("");
    setMessage("");
    try {
      const started = await startOptimizerRun(files);
      sessionStorage.setItem(ACTIVE_JOB_KEY, started.jobId);
      setJob({ ...started, phase: "Uploading validated forecast inputs", progress: 5 });
    } catch (runError) {
      setError(runError.message);
    }
  }

  async function cancelOptimization() {
    if (!job?.jobId || !running || cancelling) return;
    setCancelling(true);
    setError("");
    setMessage("");
    try {
      const cancelledJob = await cancelOptimizerRun(job.jobId);
      setJob(cancelledJob);
      sessionStorage.removeItem(ACTIVE_JOB_KEY);
      setMessage("Optimization cancelled. You can change the inputs and start a new run.");
    } catch (cancelError) {
      setError(cancelError.message || "The optimization could not be cancelled.");
    } finally {
      setCancelling(false);
    }
  }

  async function publishAndNotify() {
    if (!result?.jobId) return;
    setPublishing(true);
    setError("");
    setMessage("");
    try {
      const published = await publishTomorrowPriceAndNotify(result.jobId);
      await station.syncPublishedPrices();
      const delivered = published;

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

  function clearRun() {
    if (running) return;
    setFiles({});
    setError("");
    setMessage("");
  }

  async function openKeyResults(jobId) {
    setError("");
    try {
      const previous = await getOptimizerJob(jobId);
      if (previous.status !== "success" || !previous.result) {
        throw new Error(previous.error || "This optimizer run does not contain completed results.");
      }
      setJob(previous);
      setResult(previous.result);
      sessionStorage.setItem(ACTIVE_JOB_KEY, jobId);
      station.setTomorrowOptimizationDraft(previous.result.priceSignal);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (viewError) {
      setError(viewError.message);
    }
  }

  return (
    <div className="admin-page optimization-live-page">
      <div className="admin-page-heading">
        <div>
          <p>PYTHON MILP OPTIMIZER</p>
          <h1>Tomorrow Forecast & Price Optimization</h1>
          <span>Upload the three forecast inputs for {formatDateLabel(tomorrow)}</span>
        </div>
      </div>

      <div className={`optimizer-backend-status ${backendOnline === false ? "offline" : ""}`}>
        <DatabaseZap />
        <div>
          <strong>{backendOnline === false ? "Optimizer backend is offline" : backendOnline === true ? "Python optimizer backend connected" : "Checking optimizer backend..."}</strong>
          <p>{backendOnline === false ? "Start the FastAPI backend on port 8000 before running optimization." : "The web interface runs the original optimizer in the backend; results shown here come from the newly generated output files."}</p>
        </div>
      </div>

      {restoring && (
        <section className="optimizer-running-card">
          <div className="optimizer-spinner" />
          <div><h2>Restoring previous optimization results...</h2><p>Completed results are being reloaded from the optimizer backend.</p></div>
        </section>
      )}

      <section className="admin-upload-grid three-inputs">
        {INPUTS.map((input) => {
          const file = files[input.key];
          return (
            <label className={`admin-upload-card ${file ? "ready" : ""}`} key={input.key}>
              <input type="file" accept={input.accept} disabled={running} onChange={(event) => selectFile(input.key, event.target.files?.[0])} />
              <span className="admin-upload-icon">{file ? <CheckCircle2 /> : <UploadCloud />}</span>
              <strong>{input.title}</strong>
              <p>{input.description}</p>
              <small>{file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : `Required: ${input.filename}`}</small>
            </label>
          );
        })}
      </section>

      <section className="admin-run-panel optimizer-run-bar">
        <div>
          <strong>Input readiness: {INPUTS.filter((input) => files[input.key]).length}/3 files</strong>
          <span>All uploaded values and optimizer outputs represent forecasts for tomorrow.</span>
        </div>
        <div className="admin-run-actions">
          <button className="admin-reset-button" disabled={running} onClick={clearRun}><RefreshCcw size={17} /> Clear</button>
          {running && (
            <button
              className="admin-secondary-button"
              style={{ color: "#ff9f9f", borderColor: "rgba(255, 93, 93, 0.32)" }}
              disabled={cancelling}
              onClick={cancelOptimization}
            >
              <XCircle size={18} /> {cancelling ? "Cancelling..." : "Cancel Optimization"}
            </button>
          )}
          <button className="admin-primary-button" disabled={!allReady || running || backendOnline === false} onClick={runOptimization}><Play size={18} /> Run Optimization & Get Prices</button>
        </div>
      </section>

      {running && (
        <section className="optimizer-running-card">
          <div className="optimizer-spinner" />
          <div>
            <span>OPTIMIZER RUNNING</span>
            <h2>{job?.phase || "Running optimization..."}</h2>
            <p>The MILP model is running for tomorrow's forecast. Use Cancel Optimization if you need to stop this run; do not close the backend terminal while it is active.</p>
            <div className="optimizer-progress-track"><i style={{ width: `${Math.max(8, job?.progress || 0)}%` }} /></div>
          </div>
        </section>
      )}

      {error && (
        <div className="optimizer-error-panel">
          <AlertTriangle />
          <div><strong>Optimization error</strong><pre>{error}</pre></div>
        </div>
      )}

      {message && <div className="admin-action-message success-message"><CheckCircle2 /> {message}</div>}

      {result && (
        <section className="admin-optimization-results optimizer-actual-results">
          <div className="admin-results-heading">
            <div>
              <p>TOMORROW FORECAST OUTPUT</p>
              <h2>Optimization Results — {formatDateLabel(result.targetDate)}</h2>
              
            </div>
            <div className="optimization-result-actions">
              <button className="admin-secondary-button" onClick={() => navigate(`/admin/optimization/results/${result.jobId}`)}>Full Detailed Results <ExternalLink size={17} /></button>
              <button className="admin-primary-button combined-publish-button" disabled={publishing} onClick={publishAndNotify}><BellRing size={17} /> {publishing ? "Publishing & Notifying..." : `Publish Tomorrow Price & Notify Flexible Customers (${result.websiteElasticNotificationCount || 0})`}</button>
            </div>
          </div>

          <div className="optimizer-key-results-grid">
            {priceStats.map((item) => <article key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>Forecast for tomorrow</small></article>)}
          </div>

          <article className="admin-panel tomorrow-result-panel">
            <div className="admin-panel-heading">
              <div><h2>Generated 15-Minute Public Price Signal</h2><p>Forecast public charging price for tomorrow.</p></div>
              <div className="forecast-price-range"><span>Low Rs. {metrics.priceMinimumLKRkWh.toFixed(2)}</span><span>Avg Rs. {metrics.priceAverageLKRkWh.toFixed(2)}</span><span>High Rs. {metrics.priceMaximumLKRkWh.toFixed(2)}</span></div>
            </div>
            <PriceChart prices={result.priceSignal} variant="forecast" />
          </article>

          <ChargerOccupancyPanel
            occupancy={result.chargerOccupancy}
            slotOperation={result.slotOperation}
            available={result.chargerOccupancyAvailable !== false && Boolean(result.chargerOccupancy)}
            targetDate={result.targetDate}
          />

          <div className="optimizer-summary-note">
            <Cpu />
            <div><strong>Forecast operating summary</strong><p>Peak grid import: {Number(metrics.forecastPeakGridImportKW).toFixed(1)} kW · EV energy: {Number(metrics.forecastTotalEVEnergyKWh).toFixed(1)} kWh · PV energy: {Number(metrics.forecastPVEnergyKWh).toFixed(1)} kWh · Forecast EV users: {metrics.forecastEVUsers}.</p></div>
          </div>
        </section>
      )}

      {history.length > 0 && (
        <section className="admin-panel" style={{ marginTop: 22 }}>
          <div className="admin-panel-heading">
            <div><h2>Previous Optimization Runs</h2></div>
          </div>
          <div className="forecast-download-row" style={{ flexWrap: "wrap", justifyContent: "flex-start" }}>
            {history.map((item) => (
              <div key={item.jobId} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button className="admin-secondary-button" onClick={() => openKeyResults(item.jobId)}>
                  {formatDateLabel(item.targetDate)} · {item.generatedAt ? new Date(item.generatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : item.jobId}
                </button>
                <button className="admin-secondary-button" onClick={() => navigate(`/admin/optimization/results/${item.jobId}`)}>Full Results <ExternalLink size={15} /></button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
