import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  ExternalLink,
  Loader2,
  Search,
} from "lucide-react";
import "./styles.css";

type JobStatus = "queued" | "running" | "completed" | "failed";

type SourceOption = {
  id: string;
  label: string;
  available: boolean;
  reason?: string;
};

type SearchMetadata = {
  source_counts: Record<string, number>;
  skipped_sources: Record<string, string>;
  source_errors: Record<string, string>;
  duplicates_removed: number;
  final_count: number;
  csv_filename: string | null;
  timed_out: boolean;
};

type SearchStatus = {
  job_id: string;
  status: JobStatus;
  metadata: SearchMetadata | null;
  error: string | null;
};

type JobRow = {
  job_title: string | null;
  company_name: string | null;
  location: string | null;
  posting_date: string | null;
  job_url: string;
  source_website: string | null;
  employment_type: string | null;
};

type SearchResults = {
  job_id: string;
  rows: JobRow[];
  metadata: SearchMetadata;
};

type FormState = {
  keyword: string;
  location: string;
  distanceKm: number;
  resultsPerSource: number;
  freshnessValue: number;
  freshnessUnit: "hours" | "days";
  selectedSources: string[];
};

const defaultForm: FormState = {
  keyword: "Energiedaten",
  location: "Munich, Germany",
  distanceKm: 50,
  resultsPerSource: 25,
  freshnessValue: 24,
  freshnessUnit: "hours",
  selectedSources: ["linkedin", "indeed", "jobvector", "arbeitsagentur", "englishjobs", "devjobs"],
};

function App() {
  const [sources, setSources] = useState<SourceOption[]>([]);
  const [form, setForm] = useState<FormState>(defaultForm);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [rows, setRows] = useState<JobRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isSearching = status?.status === "queued" || status?.status === "running";
  const hoursOld = useMemo(() => {
    return form.freshnessUnit === "days"
      ? form.freshnessValue * 24
      : form.freshnessValue;
  }, [form.freshnessUnit, form.freshnessValue]);

  useEffect(() => {
    fetch("/api/sources")
      .then((response) => response.json())
      .then((data: { sources: SourceOption[] }) => setSources(data.sources))
      .catch(() => setMessage("Could not load source options."));
  }, []);

  useEffect(() => {
    if (!jobId || !isSearching) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      const nextStatus = await fetchJson<SearchStatus>(`/api/searches/${jobId}`);
      setStatus(nextStatus);
      if (nextStatus.status === "completed" || nextStatus.status === "failed") {
        window.clearInterval(intervalId);
        const result = await fetchJson<SearchResults>(`/api/searches/${jobId}/results`);
        setRows(result.rows);
      }
    }, 1600);

    return () => window.clearInterval(intervalId);
  }, [jobId, isSearching]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setRows([]);
    setStatus(null);
    setIsSubmitting(true);

    try {
      const response = await fetchJson<{ job_id: string; status: JobStatus }>(
        "/api/searches",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            keyword: form.keyword,
            location: form.location,
            sources: form.selectedSources,
            results_per_source: form.resultsPerSource,
            distance_km: form.distanceKm,
            hours_old: hoursOld,
          }),
        },
      );
      setJobId(response.job_id);
      setStatus({ job_id: response.job_id, status: response.status, metadata: null, error: null });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Search could not be started.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function updateSource(sourceId: string, checked: boolean) {
    setForm((current) => {
      const selectedSources = checked
        ? Array.from(new Set([...current.selectedSources, sourceId]))
        : current.selectedSources.filter((source) => source !== sourceId);
      return { ...current, selectedSources };
    });
  }

  return (
    <main className="app-shell">
      <section className="toolbar">
        <div>
          <p className="eyebrow">JobSpy search console</p>
          <h1>German job collector</h1>
        </div>
        <StatusPill status={status?.status} />
      </section>

      <form className="search-panel" onSubmit={handleSubmit}>
        <label className="field keyword-field">
          <span>Keyword</span>
          <input
            required
            value={form.keyword}
            onChange={(event) => setForm({ ...form, keyword: event.target.value })}
            placeholder="Energy Data Analyst"
          />
        </label>

        <label className="field">
          <span>Location</span>
          <input
            required
            value={form.location}
            onChange={(event) => setForm({ ...form, location: event.target.value })}
            placeholder="Munich, Germany"
          />
        </label>

        <label className="field compact-field">
          <span>Radius</span>
          <input
            min={0}
            max={200}
            type="number"
            value={form.distanceKm}
            onChange={(event) =>
              setForm({ ...form, distanceKm: Number(event.target.value) })
            }
          />
        </label>

        <label className="field compact-field">
          <span>Jobs/source</span>
          <input
            min={1}
            max={100}
            type="number"
            value={form.resultsPerSource}
            onChange={(event) =>
              setForm({ ...form, resultsPerSource: Number(event.target.value) })
            }
          />
        </label>

        <div className="field freshness-field">
          <span>Freshness</span>
          <div className="inline-control">
            <input
              min={1}
              max={720}
              type="number"
              value={form.freshnessValue}
              onChange={(event) =>
                setForm({ ...form, freshnessValue: Number(event.target.value) })
              }
            />
            <select
              value={form.freshnessUnit}
              onChange={(event) =>
                setForm({
                  ...form,
                  freshnessUnit: event.target.value as FormState["freshnessUnit"],
                })
              }
            >
              <option value="hours">hours</option>
              <option value="days">days</option>
            </select>
          </div>
        </div>

        <fieldset className="sources-field">
          <legend>Job boards</legend>
          <div className="source-list">
            {sources.map((source) => (
              <label
                className={`source-option ${!source.available ? "is-disabled" : ""}`}
                key={source.id}
                title={source.reason}
              >
                <input
                  type="checkbox"
                  disabled={!source.available || isSearching}
                  checked={form.selectedSources.includes(source.id)}
                  onChange={(event) => updateSource(source.id, event.target.checked)}
                />
                <span>{source.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <button className="primary-action" disabled={isSubmitting || isSearching} type="submit">
          {isSubmitting || isSearching ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
          <span>{isSearching ? "Searching" : "Search"}</span>
        </button>
      </form>

      {message ? <Notice tone="error" text={message} /> : null}
      {status?.error ? <Notice tone="error" text={status.error} /> : null}

      <Summary metadata={status?.metadata ?? null} jobId={jobId} status={status?.status} />
      <SourceErrorsPanel metadata={status?.metadata ?? null} />
      <ResultsTable rows={rows} />
    </main>
  );
}

function StatusPill({ status }: { status?: JobStatus }) {
  const label = status ?? "idle";
  return <div className={`status-pill status-${label}`}>{label}</div>;
}

function Summary({
  metadata,
  jobId,
  status,
}: {
  metadata: SearchMetadata | null;
  jobId: string | null;
  status?: JobStatus;
}) {
  if (!metadata && !jobId) {
    return null;
  }

  return (
    <section className="summary-band">
      <Metric label="LinkedIn" value={metadata?.source_counts.linkedin ?? "-"} />
      <Metric label="Indeed" value={metadata?.source_counts.indeed ?? "-"} />
      <Metric label="Jobvector" value={metadata?.source_counts.jobvector ?? "-"} />
      <Metric label="Arbeitsagentur" value={metadata?.source_counts.arbeitsagentur ?? "-"} />
      <Metric label="EnglishJobs" value={metadata?.source_counts.englishjobs ?? "-"} />
      <Metric label="DevJobs" value={metadata?.source_counts.devjobs ?? "-"} />
      <Metric label="Duplicates" value={metadata?.duplicates_removed ?? "-"} />
      <Metric label="Exported" value={metadata?.final_count ?? "-"} />
      {jobId && status === "completed" ? (
        <a className="download-link" href={`/api/searches/${jobId}/csv`}>
          <Download size={17} />
          <span>CSV</span>
        </a>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Notice({ tone, text }: { tone: "error" | "success"; text: string }) {
  const Icon = tone === "error" ? AlertCircle : CheckCircle2;
  return (
    <div className={`notice notice-${tone}`}>
      <Icon size={18} />
      <span>{text}</span>
    </div>
  );
}

function SourceErrorsPanel({ metadata }: { metadata: SearchMetadata | null }) {
  if (!metadata) return null;

  const errorSources = Object.entries(metadata.source_errors);
  const skippedSources = Object.entries(metadata.skipped_sources);

  if (errorSources.length === 0 && skippedSources.length === 0) {
    return null;
  }

  return (
    <section className="errors-panel">
      <h3>Scraping Issues</h3>
      {errorSources.length > 0 && (
        <div className="error-list">
          <h4>Errors</h4>
          <ul>
            {errorSources.map(([source, error]) => (
              <li key={source}>
                <strong>{source}:</strong> {error}
              </li>
            ))}
          </ul>
        </div>
      )}
      {skippedSources.length > 0 && (
        <div className="error-list">
          <h4>Skipped</h4>
          <ul>
            {skippedSources.map(([source, reason]) => (
              <li key={source}>
                <strong>{source}:</strong> {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function ResultsTable({ rows }: { rows: JobRow[] }) {
  if (rows.length === 0) {
    return (
      <section className="empty-state">
        <p>Results will appear here after a search completes.</p>
      </section>
    );
  }

  return (
    <section className="results-section">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Company</th>
              <th>Location</th>
              <th>Posted</th>
              <th>Source</th>
              <th>Type</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.job_url}>
                <td>{row.job_title ?? "-"}</td>
                <td>{row.company_name ?? "-"}</td>
                <td>{row.location ?? "-"}</td>
                <td>{row.posting_date ?? "-"}</td>
                <td>{row.source_website ?? "-"}</td>
                <td>{row.employment_type ?? "-"}</td>
                <td>
                  <a className="job-link" href={row.job_url} rel="noreferrer" target="_blank">
                    <ExternalLink size={16} />
                    <span>Open</span>
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : "Request failed.");
  }
  return response.json() as Promise<T>;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
