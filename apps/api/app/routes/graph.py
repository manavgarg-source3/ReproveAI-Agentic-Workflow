from fastapi import APIRouter, HTTPException
from app.schemas.graph import GraphSnapshot
from app.services.execution.sandbox import execution_service
from app.services.graph_builder import build_graph

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

@router.get("/{research_case_id}", response_model=GraphSnapshot)
async def get_graph(research_case_id: str):
    # 1. Fetch analysis response/research case from db
    rc_payload = execution_service.repository.load_research_case(research_case_id)
    if not rc_payload:
        raise HTTPException(status_code=404, detail="Research case not found")
        
    # 2. Build graph
    graph_snapshot = build_graph(research_case_id, rc_payload, execution_service.repository)
    
    # 3. Persist it
    execution_service.repository.put_graph_snapshot(
        graph_snapshot.graph_snapshot_id,
        research_case_id,
        graph_snapshot.model_dump(mode="json"),
        graph_snapshot.generated_at.isoformat()
    )
    
    return graph_snapshot

@router.get("/{research_case_id}/provenance/{node_id}")
async def get_provenance(research_case_id: str, node_id: str):
    rc_payload = execution_service.repository.load_research_case(research_case_id)
    if not rc_payload:
        raise HTTPException(status_code=404, detail="Research case not found")
        
    graph_snapshot = build_graph(research_case_id, rc_payload, execution_service.repository)
    
    node = next((n for n in graph_snapshot.nodes if n.id == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
        
    in_edges = [e for e in graph_snapshot.edges if e.target_node_id == node_id]
    out_edges = [e for e in graph_snapshot.edges if e.source_node_id == node_id]
    
    return {
        "node": node.model_dump(mode="json"),
        "in_edges": [e.model_dump(mode="json") for e in in_edges],
        "out_edges": [e.model_dump(mode="json") for e in out_edges]
    }
