"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

interface ReportMetadata {
  report_id: string;
  report_version: number;
  report_hash: string;
  status: string;
}

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function AssuranceReportPage() {
  const params = useSearchParams();
  const [caseId, setCaseId] = useState(params.get("research_case_id") ?? "");
  const [token, setToken] = useState("");
  const [report, setReport] = useState<ReportMetadata | null>(null);
  const [history, setHistory] = useState<ReportMetadata[]>([]);
  const [html, setHtml] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function request(path: string, method = "GET") {
    const response = await fetch(`${apiUrl}/api/v1${path}`, {
      method, headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
    });
    if (!response.ok) {
      const body: { detail?: string } = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? "The report could not be loaded.");
    }
    return response;
  }

  async function showReport(metadata: ReportMetadata) {
    const response = await request(`/reports/${encodeURIComponent(metadata.report_id)}/html`);
    setHtml(await response.text());
    setReport(metadata);
  }

  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await work(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Report request failed."); }
    finally { setBusy(false); }
  }

  async function loadHistory() {
    const response = await request(`/research-cases/${encodeURIComponent(caseId)}/reports`);
    const records: ReportMetadata[] = await response.json();
    setHistory(records);
    return records;
  }

  async function download(format: "json" | "html") {
    if (!report) return;
    const response = await request(`/reports/${encodeURIComponent(report.report_id)}/${format}`);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.report_id}.${format}`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900 p-6 md:p-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <Link href="/" className="text-sm font-semibold tracking-widest text-slate-600">REPROVE</Link>
          <h1 className="text-3xl font-semibold mt-3">Scientific Assurance Report</h1>
          <p className="text-slate-600 mt-2">Review persisted evidence, reproduction outcomes, uncertainty, and provenance.</p>
        </header>
        <form className="rounded-lg border border-slate-200 bg-white p-6 space-y-4" onSubmit={(event) => {
          event.preventDefault();
          void action(async () => {
            const response = await request(`/reports/${encodeURIComponent(caseId)}/generate`, "POST");
            await showReport(await response.json() as ReportMetadata);
            await loadHistory();
          });
        }}>
          <label className="block">Research case ID
            <input required value={caseId} onChange={(event) => setCaseId(event.target.value)} className="block w-full border border-slate-300 rounded p-2 mt-1" />
          </label>
          <label className="block">Access token
            <input type="password" autoComplete="off" required value={token} onChange={(event) => setToken(event.target.value)} className="block w-full border border-slate-300 rounded p-2 mt-1" />
          </label>
          <p className="text-sm text-slate-600">Reviewer or admin access is required to generate a report. The token is kept only in this page’s memory.</p>
          <div className="flex gap-3 flex-wrap">
            <button disabled={busy} className="bg-slate-900 text-white rounded px-4 py-2 disabled:opacity-50">{busy ? "Working…" : "Generate from persisted evidence"}</button>
            <button type="button" disabled={busy || !caseId || !token} className="border rounded px-4 py-2 disabled:opacity-50" onClick={() => void action(async () => {
              const records = await loadHistory();
              if (records[0]) await showReport(records[0]);
              else setError("No report versions exist for this case yet.");
            })}>View report history</button>
          </div>
        </form>
        {error && <p role="alert" className="my-4 border border-red-300 bg-red-50 p-4 rounded">{error}</p>}
        {history.length > 0 && <nav aria-label="Report history" className="my-5 flex gap-3 flex-wrap">
          {history.map((entry) => <button key={entry.report_id} disabled={busy} onClick={() => void action(() => showReport(entry))} className="border rounded bg-white p-2">Version {entry.report_version} · {entry.status}</button>)}
        </nav>}
        {report && <section className="mt-6">
          <div className="flex gap-3 mb-4 flex-wrap">
            <button disabled={busy} onClick={() => void action(() => download("json"))} className="border rounded bg-white px-4 py-2">Export JSON</button>
            <button disabled={busy} onClick={() => void action(() => download("html"))} className="border rounded bg-white px-4 py-2">Export HTML</button>
          </div>
          <iframe title={`Scientific Assurance Report version ${report.report_version}`} sandbox="" srcDoc={html} className="w-full h-[1800px] border border-slate-200 rounded-lg bg-white" />
        </section>}
      </div>
    </main>
  );
}

export default function ReportsPage() {
  return <Suspense fallback={<p className="p-8">Loading report page…</p>}><AssuranceReportPage /></Suspense>;
}
