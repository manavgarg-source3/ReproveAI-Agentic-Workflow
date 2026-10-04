import urllib.request
import urllib.parse
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=== TESTING /api/custom-audit/run ENDPOINT ===")

data = urllib.parse.urlencode({
    'scopus_link': 'https://www.scopus.com/pages/publications/85118881384?origin=resultslist'
}).encode('utf-8')

req = urllib.request.Request(
    'http://localhost:8000/api/custom-audit/run',
    data=data,
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)

try:
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print(f"Status: {resp.getcode()}")
        print(f"Job ID: {res.get('job_id')}")
        print(f"Source Title: {res.get('source_info', {}).get('source_title')}")
        print(f"Total References: {res.get('stats', {}).get('total_references')}")
        print(f"Scopus Linked: {res.get('stats', {}).get('scopus_linked')}")
        print(f"Excel download URL: {res.get('excel_download_url')}")
        print(f"CSV download URL: {res.get('csv_download_url')}")

        job_id = res.get('job_id')

        # Test download excel
        excel_req = urllib.request.urlopen(f"http://localhost:8000/api/custom-audit/download/{job_id}?format=excel")
        print(f"Excel download status: {excel_req.getcode()}, length: {len(excel_req.read())} bytes")

        # Test download csv
        csv_req = urllib.request.urlopen(f"http://localhost:8000/api/custom-audit/download/{job_id}?format=csv")
        print(f"CSV download status: {csv_req.getcode()}, length: {len(csv_req.read())} bytes")

        print("\nALL CUSTOM AUDIT API TESTS PASSED!")
except Exception as e:
    print(f"FAILED: {e}")

