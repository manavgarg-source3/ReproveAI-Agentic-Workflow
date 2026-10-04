import sys
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

def test_url(url, desc):
    try:
        req = urllib.request.urlopen(url)
        code = req.getcode()
        body = req.read()
        content_type = req.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = json.loads(body.decode('utf-8'))
            cnt = len(data.get('items', data)) if isinstance(data, dict) else len(data)
            print(f"[OK {code}] {desc}: response items/keys = {cnt}")
            return data
        else:
            print(f"[OK {code}] {desc}: {len(body)} bytes ({content_type})")
            return None
    except Exception as e:
        print(f"[FAIL] {desc}: {e}")
        return None

print("=== TESTING LIVE SCIENTOMETRIC DASHBOARD (PORT 8000) ===")
test_url("http://localhost:8000/api/health", "Health Check")
stats = test_url("http://localhost:8000/api/stats", "KPI Stats")
docs = test_url("http://localhost:8000/api/documents?limit=5", "Documents Summary")

print("\n--- Testing Target Paper 1 (IISERs) ---")
p1 = test_url("http://localhost:8000/api/references?source_eid=2-s2.0-85118881384&sort_by=reference_no&sort_order=asc", "Paper 1 (IISERs)")
if p1:
    print(f"  Total references: {p1.get('total')}, Page items: {len(p1.get('items', []))}")
    for r in p1.get('items', []):
        print(f"    Ref #{r['reference_no']}: {r['reference_id']} | scopus_valid={r['scopus_link_valid']} | status={r['final_status']} | needs_review={r['needs_human_review']}")

print("\n--- Testing Target Paper 2 (Patent Analysis) ---")
p2 = test_url("http://localhost:8000/api/references?source_eid=2-s2.0-105042346360&sort_by=reference_no&sort_order=asc", "Paper 2 (Patent Analysis)")
if p2:
    print(f"  Total references: {p2.get('total')}, Page items: {len(p2.get('items', []))}")

print("\n--- Testing Status Filter (VALID_CORRECT) ---")
st = test_url("http://localhost:8000/api/references?status=VALID_CORRECT", "Filter: VALID_CORRECT")
if st:
    print(f"  Total matches: {st.get('total')}")

print("\n--- Testing Review Filter (needs_review=true) ---")
rev = test_url("http://localhost:8000/api/references?needs_review=true", "Filter: needs_review=true")
if rev:
    print(f"  Total matches: {rev.get('total')}")

print("\n--- Testing Scopus Unlinked Filter (scopus_linked=false) ---")
sc = test_url("http://localhost:8000/api/references?scopus_linked=false", "Filter: scopus_linked=false")
if sc:
    print(f"  Total matches: {sc.get('total')}")

print("\n--- Testing Frontend SPA Serving ---")
spa = test_url("http://localhost:8000/", "React SPA Root")

