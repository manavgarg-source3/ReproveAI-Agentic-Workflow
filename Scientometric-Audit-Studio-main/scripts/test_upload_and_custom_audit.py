import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

print("=== 1. VERIFY FRONTEND ROOT HTML SERVES UPDATED BUNDLE ===")
r_root = requests.get("http://localhost:8000/")
assert r_root.status_code == 200, f"Root returned {r_root.status_code}"
assert "index-Bw7sZSef.js" in r_root.text, "New JS bundle not found in index.html!"
print("[PASS] index.html serves updated JS bundle: index-Bw7sZSef.js")

print("\n=== 2. TEST CSV FILE UPLOAD TO /api/custom-audit/run ===")
sample_csv_content = """Reference,Title,DOI
"1. Smith J., Johnson K. (2020). Quantum Computing Advances. Nature, 580: 12-18.","Quantum Computing Advances","10.1038/s41586-020-2000-0"
"2. Patel R. (2019). Machine Learning in Altmetrics. Scientometrics, 115: 45-60.","Machine Learning in Altmetrics",""
"3. Davis M. (2018). Neural Networks for Citation Mining. PLOS ONE, 13: e0198765.","Neural Networks for Citation Mining","10.1371/journal.pone.0198765"
"""

files = {
    'file': ('sample_references.csv', sample_csv_content.encode('utf-8'), 'text/csv')
}

resp = requests.post("http://localhost:8000/api/custom-audit/run", files=files, timeout=30)
assert resp.status_code == 200, f"Upload failed with {resp.status_code}: {resp.text}"
data = resp.json()
job_id = data['job_id']
print(f"[PASS] CSV Upload succeeded! Status: 200, Job ID: {job_id}")
print(f"  Total references processed: {data['stats']['total_references']}")
for r in data['items']:
    print(f"    Ref #{r['reference_no']}: DOI={r.get('normalized_doi')} | Status={r.get('final_status')} | NeedsReview={r.get('needs_human_review')}")

# Test downloading Excel report
excel_url = f"http://localhost:8000/api/custom-audit/download/{job_id}?format=excel"
r_excel = requests.get(excel_url, timeout=10)
assert r_excel.status_code == 200, f"Excel download failed: {r_excel.status_code}"
assert len(r_excel.content) > 5000, f"Excel report unexpectedly small: {len(r_excel.content)} bytes"
print(f"[PASS] Download Excel report: {len(r_excel.content)} bytes, Content-Type={r_excel.headers.get('content-type')}")

# Test downloading CSV export
csv_url = f"http://localhost:8000/api/custom-audit/download/{job_id}?format=csv"
r_csv = requests.get(csv_url, timeout=10)
assert r_csv.status_code == 200, f"CSV download failed: {r_csv.status_code}"
assert len(r_csv.content) > 100, f"CSV export unexpectedly small: {len(r_csv.content)} bytes"
print(f"[PASS] Download CSV export: {len(r_csv.content)} bytes, Content-Type={r_csv.headers.get('content-type')}")

print("\n=== 3. TEST SCOPUS LINK SUBMISSION (PAPER 1 - IISERs) ===")
resp_scopus = requests.post(
    "http://localhost:8000/api/custom-audit/run",
    data={'scopus_link': 'https://www.scopus.com/pages/publications/85118881384?origin=resultslist'},
    timeout=30
)
assert resp_scopus.status_code == 200, f"Scopus submission failed: {resp_scopus.status_code}: {resp_scopus.text}"
data_scopus = resp_scopus.json()
print(f"[PASS] Scopus link submission succeeded! Status: 200")
print(f"  Title: {data_scopus['source_info']['source_title']}")
print(f"  Total references: {data_scopus['stats']['total_references']} (Expected 14)")
print(f"  Scopus linked: {data_scopus['stats']['scopus_linked']}")
print(f"  Needs review: {data_scopus['stats']['needs_review']}")
assert data_scopus['stats']['total_references'] == 14, f"Expected 14 references, got {data_scopus['stats']['total_references']}"

print("\nALL CUSTOM AUDIT E2E TESTS COMPLETED WITH 100% SUCCESS!")
