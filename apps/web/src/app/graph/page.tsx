"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

interface GraphNode {
  id: string;
  node_type: string;
  label: string;
}

interface GraphEdge {
  id: string;
  source_node_id: string;
  edge_type: string;
  target_node_id: string;
}

interface GraphSnapshot {
  research_case_id: string;
  graph_snapshot_id: string;
  node_count: number;
  edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

function GraphViewContent() {
  const searchParams = useSearchParams();
  const research_case_id = searchParams.get("research_case_id");
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!research_case_id) return;
    fetch(`http://localhost:8000/api/v1/graph/${research_case_id}`)
      .then((res) => {
        if (!res.ok) throw new Error("Graph not found or failed to load");
        return res.json() as Promise<GraphSnapshot>;
      })
      .then(setGraph)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Graph failed to load"));
  }, [research_case_id]);

  if (!research_case_id) return <div className="p-8">Please provide a ?research_case_id= param</div>;
  if (error) return <div className="p-8 text-red-500">{error}</div>;
  if (!graph) return <div className="p-8">Loading graph...</div>;

  const nodesByType = graph.nodes.reduce<Record<string, GraphNode[]>>((acc, node) => {
    acc[node.node_type] = acc[node.node_type] || [];
    acc[node.node_type].push(node);
    return acc;
  }, {});

  return (
    <div className="p-8 font-mono text-sm max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Evidence & Provenance Graph</h1>
      <div className="mb-8 p-4 bg-slate-100 rounded">
        <div><strong>Research Case ID:</strong> {graph.research_case_id}</div>
        <div><strong>Snapshot ID:</strong> {graph.graph_snapshot_id}</div>
        <div><strong>Nodes:</strong> {graph.node_count} | <strong>Edges:</strong> {graph.edge_count}</div>
      </div>

      <div className="flex gap-8 flex-wrap">
        {Object.entries(nodesByType).map(([type, nodes]) => (
          <div key={type} className="border border-slate-300 rounded p-4 flex-1 min-w-[300px]">
            <h2 className="text-lg font-bold border-b border-slate-300 pb-2 mb-2">{type}</h2>
            <div className="flex flex-col gap-2">
              {nodes.map((node) => {
                const outEdges = graph.edges.filter((edge) => edge.source_node_id === node.id);
                return (
                  <div key={node.id} className="bg-white p-2 border border-slate-200 rounded shadow-sm">
                    <div className="font-semibold truncate" title={node.label}>{node.label}</div>
                    <div className="text-xs text-slate-500 mb-1">{node.id}</div>
                    {outEdges.length > 0 && (
                      <div className="text-xs">
                        <div className="text-slate-400">Outgoing:</div>
                        <ul className="list-disc list-inside">
                          {outEdges.map((edge) => {
                            const target = graph.nodes.find((node) => node.id === edge.target_node_id);
                            return (
                              <li key={edge.id}>
                                <span className="text-blue-600">{edge.edge_type}</span> &rarr; {target ? target.label : edge.target_node_id}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function GraphView() {
  return (
    <Suspense fallback={<div className="p-8">Loading Graph UI...</div>}>
      <GraphViewContent />
    </Suspense>
  );
}
