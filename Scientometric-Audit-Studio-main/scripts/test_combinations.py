import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def query(params):
    url = f"http://localhost:8000/api/references?{params}"
    req = urllib.request.urlopen(url)
    return json.loads(req.read().decode('utf-8'))

print("=== COMBINATIONS TEST ===")

# Test 1: Paper 1 alone
res1 = query("source_eid=2-s2.0-85118881384&page_size=100")
print(f"Test 1 - Paper 1 alone: {res1['total']} references (expected 14)")
assert res1['total'] == 14, f"Expected 14, got {res1['total']}"

# Test 2: Paper 1 + Scopus unlinked
res2 = query("source_eid=2-s2.0-85118881384&scopus_linked=false&page_size=100")
unlinked_refs = [r['reference_no'] for r in res2['items']]
print(f"Test 2 - Paper 1 Scopus unlinked: {res2['total']} refs -> citations {unlinked_refs} (expected 5, 10, 12, 13)")
assert set(unlinked_refs) == {5, 10, 12, 13}, f"Unexpected unlinked refs: {unlinked_refs}"

# Test 3: Paper 1 + Needs review
res3 = query("source_eid=2-s2.0-85118881384&needs_review=true&page_size=100")
review_refs = [r['reference_no'] for r in res3['items']]
print(f"Test 3 - Paper 1 Needs Review: {res3['total']} refs -> citations {review_refs} (expected 2, 5, 10, 12, 13, 14)")
assert set(review_refs) == {2, 5, 10, 12, 13, 14}, f"Unexpected review refs: {review_refs}"

# Test 4: Paper 2 alone
res4 = query("source_eid=2-s2.0-105042346360&page_size=100")
print(f"Test 4 - Paper 2 alone: {res4['total']} references (expected 35)")
assert res4['total'] == 35, f"Expected 35, got {res4['total']}"

# Test 5: Paper 2 + Scopus unlinked
res5 = query("source_eid=2-s2.0-105042346360&scopus_linked=false&page_size=100")
unlinked_p2 = [r['reference_no'] for r in res5['items']]
print(f"Test 5 - Paper 2 Scopus unlinked: {res5['total']} refs -> citations {unlinked_p2}")
assert set(unlinked_p2) == {1, 7, 8, 18, 19, 21, 22, 23, 34, 35}, f"Unexpected Paper 2 unlinked: {unlinked_p2}"

# Test 6: Case insensitivity
res6a = query("q=altmetric&page_size=10")
res6b = query("q=ALTMETRIC&page_size=10")
print(f"Test 6 - Case insensitivity 'altmetric': {res6a['total']} vs 'ALTMETRIC': {res6b['total']}")
assert res6a['total'] == res6b['total'], "Case sensitivity mismatch!"

print("\nALL COMBINATION AND VERIFICATION TESTS PASSED WITH 100% ACCURACY!")
