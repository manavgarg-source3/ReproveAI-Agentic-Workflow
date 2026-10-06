import json
from fastapi.testclient import TestClient
from app.main import app

def test_chain():
    required_types = {
        "CLAIM",
        "EXPERIMENT",
        "REPRODUCTION_TARGET",
        "EXECUTION",
        "OBSERVED_RESULT",
        "COMPARISON",
        "DISCREPANCY",
        "HYPOTHESIS",
        "DIAGNOSTIC_PLAN",
        "DIAGNOSTIC_EXECUTION",
        "HYPOTHESIS_TEST"
    }
    client = TestClient(app)
    cases = ["CASE-0E65DDF568F431BF", "CASE-7CEE6CC024C17E21", "CASE-7E41D1591DC1CFA7", "CASE-CCD5B322607E3603", "rc_123"]
    for case_id in cases:
        response = client.get(f"/api/v1/graph/{case_id}")
        if response.status_code != 200: continue
            
        graph = response.json()
        types = {n['node_type'] for n in graph['nodes']}
        print(f"Case {case_id} node types:", types)
        missing = required_types - types
        if not missing:
            print(f"All required node types present in case {case_id}! Minimum chain verified.")
            return

    print("No case has the full chain!")

test_chain()
