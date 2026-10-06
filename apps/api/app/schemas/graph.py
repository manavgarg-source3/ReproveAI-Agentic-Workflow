from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class NodeType(str, Enum):
    RESEARCH_CASE = "RESEARCH_CASE"
    PAPER = "PAPER"
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    SOURCE = "SOURCE"
    EXPERIMENT = "EXPERIMENT"
    METHOD = "METHOD"
    RESULT = "RESULT"
    ARTIFACT = "ARTIFACT"
    DATASET = "DATASET"
    MODEL = "MODEL"
    CHECKPOINT = "CHECKPOINT"
    CONFIGURATION = "CONFIGURATION"
    ENVIRONMENT = "ENVIRONMENT"
    REPRODUCTION_TARGET = "REPRODUCTION_TARGET"
    REPRODUCTION_PLAN = "REPRODUCTION_PLAN"
    EXECUTION = "EXECUTION"
    OBSERVED_RESULT = "OBSERVED_RESULT"
    COMPARISON = "COMPARISON"
    DISCREPANCY = "DISCREPANCY"
    INVESTIGATION = "INVESTIGATION"
    HYPOTHESIS = "HYPOTHESIS"
    DIAGNOSTIC_PLAN = "DIAGNOSTIC_PLAN"
    DIAGNOSTIC_EXECUTION = "DIAGNOSTIC_EXECUTION"
    HYPOTHESIS_TEST = "HYPOTHESIS_TEST"
    STATE_TRANSITION = "STATE_TRANSITION"

class EdgeType(str, Enum):
    CONTAINS = "CONTAINS"
    HAS_CLAIM = "HAS_CLAIM"
    HAS_EXPERIMENT = "HAS_EXPERIMENT"
    HAS_METHOD = "HAS_METHOD"
    HAS_RESULT = "HAS_RESULT"
    CITES = "CITES"
    SUPPORTED_BY = "SUPPORTED_BY"
    PARTIALLY_SUPPORTED_BY = "PARTIALLY_SUPPORTED_BY"
    SOURCE_OF = "SOURCE_OF"
    USES_ARTIFACT = "USES_ARTIFACT"
    USES_DATASET = "USES_DATASET"
    USES_MODEL = "USES_MODEL"
    USES_CHECKPOINT = "USES_CHECKPOINT"
    USES_CONFIGURATION = "USES_CONFIGURATION"
    REQUIRES_ENVIRONMENT = "REQUIRES_ENVIRONMENT"
    MAPS_TO = "MAPS_TO"
    TARGETS = "TARGETS"
    PLANS = "PLANS"
    EXECUTED_AS = "EXECUTED_AS"
    PRODUCED = "PRODUCED"
    OBSERVED_AS = "OBSERVED_AS"
    COMPARED_WITH = "COMPARED_WITH"
    GENERATED_DISCREPANCY = "GENERATED_DISCREPANCY"
    INVESTIGATES = "INVESTIGATES"
    HAS_HYPOTHESIS = "HAS_HYPOTHESIS"
    TESTED_BY = "TESTED_BY"
    HAS_DIAGNOSTIC_PLAN = "HAS_DIAGNOSTIC_PLAN"
    EXECUTED_DIAGNOSTIC = "EXECUTED_DIAGNOSTIC"
    TEST_RESULT = "TEST_RESULT"
    CAUSED_STATE_TRANSITION = "CAUSED_STATE_TRANSITION"
    DERIVED_FROM = "DERIVED_FROM"
    HAS_PROVENANCE = "HAS_PROVENANCE"

class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    node_type: NodeType
    entity_id: str
    label: str
    source_table: str
    created_at: datetime
    source_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    source_node_id: str
    edge_type: EdgeType
    target_node_id: str
    created_at: datetime
    provenance: str
    source_entity_id: str | None = None
    source_hash: str | None = None

class GraphSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    graph_snapshot_id: str
    research_case_id: str
    graph_version: str
    generated_at: datetime
    graph_hash: str
    node_count: int
    edge_count: int
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()

