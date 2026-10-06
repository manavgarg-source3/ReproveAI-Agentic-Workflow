# Step 10 prerequisite review

Step 10 is not implemented or approved. Earlier completion reports overstated
the guarantees in the current source. This review records the concrete conflict
between freezing Steps 1–9 and safely reusing them for diagnostic execution.

## Reproduced behaviors

Focused Python checks used synthetic records and temporary SQLite databases.
They did not execute research code or diagnostics.

1. With AUTH_MODE unset, `_authenticated_principal(None, None, None)` returns
   `local-development-reviewer` with `reproduction_approver` privileges.
2. After `ExecutionRepository.revoke`, `load('approvals', id)` returns the old
   JSON payload with `status=APPROVED` and `revoked_at=null`. Revocation updates
   separate SQL columns, while execution reloads the stale JSON payload.
3. Comparison returns VERIFIED for identical numbers despite UNKNOWN dataset
   and evaluation protocol compatibility.
4. Comparison returns NOT_REPRODUCED with tolerance 0.01 and no tolerance basis
   or source. Unknown context does not prevent this verdict.
5. Investigation generates DATASET, PREPROCESSING, and CONFIGURATION hypotheses
   even with zero supporting evidence. Configuration changes are category names
   such as DATASET, not parameter paths and old/new values. Decision rules are
   narrative instructions without executable numeric criteria.
6. Extraction of `accuracy=0.74` followed by `accuracy=0.76` returns EXTRACTED
   with 0.74 rather than AMBIGUOUS.

The temporary-database cleanup reported a Windows file-lock error after these
checks completed. This audit is not a passing regression suite.

## Additional source findings

- Run GET re-extracts observations and creates new comparison IDs; it does not
  consume a stable persisted Step 7 observation.
- Investigation POST recomputes a comparison without persisting that comparison,
  leaving its referenced comparison ID without a durable source record.
- Step 6 hardcodes ORIGINAL execution type.
- Worker recovery marks claimed jobs interrupted without checking lease expiry;
  heartbeat renewal and queued-job restart scheduling are absent.
- Cancellation publishes CANCELLED before worker collection/cleanup completes.
  Container identity is held only in a process-local dictionary.
- Run persistence uses INSERT OR REPLACE and therefore has no database guard
  against overwriting terminal records.

## Minimum prerequisite repair scope requiring a freeze exception

1. Step 6: default to authenticated mode, validate credentials, apply authorization
   to diagnostic access/cancellation, make revocation authoritative after restart,
   and enforce durable atomic terminal-state and cancellation handling. Extend
   the same worker to accept approved diagnostic execution metadata.
2. Step 7: preserve ambiguity and durable observation identity, validate evidence
   provenance, and consume bounded immutable output bytes.
3. Step 8: require sufficient context and justified tolerance before scientific
   verdicts; preserve stable references to immutable published/observed records.
4. Step 9: consume the stored comparison, generate evidence-linked hypotheses,
   and add explicit, hashable configuration changes and deterministic decision
   rules to diagnostic plan revisions. Existing draft plans remain blocked until
   those details are established and approved.

Original runs, outputs, targets, environments, artifacts, and historical
investigations must remain intact. Tests that currently require permissive
behavior need correction; they must not be preserved by production bypasses.

After those repairs, Step 10 can add its approval bindings, immutable diagnostic
snapshots, worker integration, Step 7 observations, append-only decisions and
reviews, UI, and real Docker supported/rejected/inconclusive fixtures.

No Evidence Graph, Assurance Report, or Scientometric Engine changes are needed.
