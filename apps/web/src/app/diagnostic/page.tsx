"use client";

import { useState } from "react";
import { approveDiagnostic, executeDiagnostic, evaluateDiagnostic, listInvestigations, getHypothesisTests, DiagnosticApproval, DiagnosticExecution, HypothesisTest, DiscrepancyInvestigation, DEFAULT_EXECUTION_POLICY } from "@/lib/api";

export default function DiagnosticPage() {
  const [targetId, setTargetId] = useState("");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [approval, setApproval] = useState<DiagnosticApproval | null>(null);
  const [execution, setExecution] = useState<DiagnosticExecution | null>(null);
  const [hypothesisTest, setHypothesisTest] = useState<HypothesisTest | null>(null);
  const [investigations, setInvestigations] = useState<DiscrepancyInvestigation[]>([]);
  const [tests, setTests] = useState<HypothesisTest[]>([]);
  const [isBusy, setIsBusy] = useState(false);

  // Minimal stub for a plan
  const stubPlan = {
    diagnostic_plan_id: "DP-TEST",
    hypothesis_id: "H-TEST",
    objective: "Test via UI",
    question: "Does this work?",
    test_type: "CONTROLLED_DIAGNOSTIC",
    change_type: "CODE_PATCH",
    target_path: "evaluate.py",
    original_state: "0.50",
    proposed_state: "0.75",
    decision_rule: "METRIC_INCREASES",
    alternative_observation: "N/A",
    status: "READY"
  };

  async function handleApprove() {
    setIsBusy(true); setError(null);
    try {
      const app = await approveDiagnostic(targetId, baselineRunId, stubPlan);
      setApproval(app);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approval failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleExecute() {
    if (!approval) return;
    setIsBusy(true); setError(null);
    try {
      const exec = await executeDiagnostic(targetId, approval.approval_id, stubPlan, DEFAULT_EXECUTION_POLICY);
      setExecution(exec);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Execution failed");
    } finally {
      setIsBusy(false);
    }
  }
  
  async function handleEvaluate() {
    if (!execution) return;
    setIsBusy(true); setError(null);
    try {
      const result = await evaluateDiagnostic(targetId, execution.diagnostic_execution_id);
      setHypothesisTest(result);
      const invs = await listInvestigations(targetId);
      setInvestigations(invs);
      const ts = await getHypothesisTests(targetId, result.hypothesis_id);
      setTests(ts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="min-h-screen overflow-hidden bg-slate-50 p-10">
      <div className="mx-auto max-w-2xl bg-white p-6 rounded shadow">
        <h1 className="text-2xl font-bold mb-4">Step 10: Diagnostic Execution & Evaluation</h1>
        
        <div className="grid gap-4 mb-6">
          <label className="block">
            <span className="text-sm font-semibold">Target ID</span>
            <input className="w-full border p-2 rounded mt-1" value={targetId} onChange={e => setTargetId(e.target.value)} />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold">Baseline Run ID</span>
            <input className="w-full border p-2 rounded mt-1" value={baselineRunId} onChange={e => setBaselineRunId(e.target.value)} />
          </label>
        </div>
        
        <div className="flex gap-4 mb-6">
          <button 
            className="px-4 py-2 bg-indigo-600 text-white rounded disabled:opacity-50"
            disabled={isBusy || !targetId || !baselineRunId}
            onClick={handleApprove}
          >
            Approve Plan
          </button>
          
          <button 
            className="px-4 py-2 bg-emerald-600 text-white rounded disabled:opacity-50"
            disabled={isBusy || !approval}
            onClick={handleExecute}
          >
            Execute Diagnostic
          </button>
          
          <button 
            className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
            disabled={isBusy || !execution || (execution.status !== "COMPLETED" && execution.status !== "FAILED" && execution.status !== "BLOCKED")}
            onClick={handleEvaluate}
          >
            Evaluate
          </button>
        </div>

        {error && <div className="p-4 bg-red-100 text-red-800 rounded mb-4">{error}</div>}

        {approval && (
          <div className="p-4 bg-slate-100 rounded mb-4 text-sm border-l-4 border-indigo-600">
            <p className="font-bold">Approval ID: {approval.approval_id}</p>
            <p>Status: {approval.status}</p>
          </div>
        )}

        {execution && (
          <div className="p-4 bg-slate-100 rounded mb-4 text-sm border-l-4 border-emerald-600">
            <p className="font-bold">Execution ID: {execution.diagnostic_execution_id}</p>
            <p>Status: {execution.status}</p>
            <p>Outcome: {execution.outcome ?? "Pending"}</p>
            {execution.decision_reason && <p>Reason: {execution.decision_reason}</p>}
          </div>
        )}
        
        {hypothesisTest && (
          <div className="p-4 bg-slate-100 rounded text-sm border-l-4 border-blue-600">
            <p className="font-bold">Evaluation ID: {hypothesisTest.id}</p>
            <p>Evidence Strength: {hypothesisTest.evidence_strength}</p>
            <p>Hypothesis Status Changed: {hypothesisTest.prior_status} ➜ {hypothesisTest.resulting_status}</p>
            <p>Reason: {hypothesisTest.decision_reason}</p>
            
            {tests.length > 0 && (
              <div className="mt-4">
                <h3 className="font-bold border-b pb-1 mb-2">Test History</h3>
                <ul className="space-y-2">
                  {tests.map(t => (
                    <li key={t.id} className="bg-white p-2 border rounded">
                      <p><strong>Outcome:</strong> {t.diagnostic_outcome} | <strong>Status:</strong> {t.resulting_status}</p>
                      <p className="text-gray-500 text-xs">{new Date(t.created_at).toLocaleString()}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {investigations.length > 0 && (
              <div className="mt-4">
                <h3 className="font-bold border-b pb-1 mb-2">Investigation States</h3>
                <ul className="space-y-2">
                  {investigations.map(inv => (
                    <li key={inv.investigation_id} className="bg-white p-2 border rounded">
                      <p><strong>Status:</strong> {inv.status}</p>
                      <div className="pl-4 mt-2 border-l-2">
                        {inv.hypotheses.map(h => (
                           <p key={h.hypothesis_id} className="text-xs">Hypothesis {h.hypothesis_id.split("-")[1]}: {h.status}</p>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
