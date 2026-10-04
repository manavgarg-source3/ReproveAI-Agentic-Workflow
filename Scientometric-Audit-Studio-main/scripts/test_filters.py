import sys
import sqlite3
from src.web.db import query_references, get_kpi_stats, get_documents_summary

sys.stdout.reconfigure(encoding='utf-8')

print("=== 1. TEST KPI STATS ===")
stats = get_kpi_stats()
print(f"Total references: {stats['total_references']}")
print(f"Total documents: {stats['total_documents']}")
print(f"Scopus linked: {stats['scopus_linked']}")
print(f"Scopus unlinked: {stats['scopus_unlinked']}")
print(f"Needs review: {stats['needs_review']}")

print("\n=== 2. TEST SOURCE EID FILTER (PAPER 1 - IISERs) ===")
rows1, count1 = query_references(page=1, page_size=100, source_eid='2-s2.0-85118881384')
print(f"Paper 1 total references returned: {count1} (rows: {len(rows1)})")
for r in rows1:
    print(f"  Ref #{r['reference_no']}: {r['reference_id']} | scopus_valid={r['scopus_link_valid']} | status={r['final_status']} | needs_review={r['needs_human_review']}")

print("\n=== 3. TEST SOURCE EID FILTER (PAPER 2 - Patent Analysis) ===")
rows2, count2 = query_references(page=1, page_size=100, source_eid='2-s2.0-105042346360')
print(f"Paper 2 total references returned: {count2} (rows: {len(rows2)})")

print("\n=== 4. TEST SCOPUS_LINKED FILTER ===")
_, linked_count = query_references(scopus_linked="true")
_, unlinked_count = query_references(scopus_linked="false")
print(f"Linked: {linked_count}, Unlinked: {unlinked_count}, Sum: {linked_count + unlinked_count}")

print("\n=== 5. TEST NEEDS_REVIEW FILTER ===")
_, review_yes = query_references(needs_review="true")
_, review_no = query_references(needs_review="false")
print(f"Needs review: {review_yes}, Auto-approved: {review_no}, Sum: {review_yes + review_no}")

print("\n=== 6. TEST HAS_DOI FILTER ===")
_, has_doi_yes = query_references(has_doi="true")
_, has_doi_no = query_references(has_doi="false")
print(f"Has DOI: {has_doi_yes}, No DOI: {has_doi_no}, Sum: {has_doi_yes + has_doi_no}")

print("\n=== 7. TEST STATUS FILTER (VALID_CORRECT) ===")
_, valid_count = query_references(statuses=["VALID_CORRECT"])
print(f"VALID_CORRECT: {valid_count}")

print("\n=== 8. TEST SEARCH QUERY (CASE INSENSITIVITY) ===")
_, q_lower = query_references(search_query="patent")
_, q_upper = query_references(search_query="PATENT")
print(f"Search 'patent': {q_lower}, Search 'PATENT': {q_upper}")

_, q_author_l = query_references(search_query="singh")
_, q_author_u = query_references(search_query="SINGH")
print(f"Search 'singh': {q_author_l}, Search 'SINGH': {q_author_u}")

print("\n=== 9. TEST DOCUMENTS SUMMARY ===")
docs = get_documents_summary(limit=10)
print(f"Found {len(docs)} documents. Top document: {docs[0]['source_title']} ({docs[0]['ref_count']} refs)")

print("\nALL BACKEND DATABASE TESTS COMPLETED SUCCESSFULLY!")

