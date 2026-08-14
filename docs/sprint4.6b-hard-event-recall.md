# Sprint 4.6B — Hard Event Recall Expansion

## Boundary

Sprint 4.6B improves hard-event recall without turning third-party challenger feeds into Candidate ingress.

4.6B.1 adds three precise C1 SearchPlans for hard-event discovery. The real SearchPlan rows remain private and are supplied to the Sheet Migration workflow through an Environment secret. Public code contains only the payload schema and validation logic.

4.6B.2 will evaluate press-wire discovery routes separately and keep them probationary until precision is demonstrated. Press-wire routes are not hard-required in 4.6B.1.

C5/arXiv query expansion is out of scope for 4.6B and remains a separate recall fix.

## Private migration payload

The `sprint_4_6_b1` migration requires environment variable `AILS_PRIVATE_MIGRATIONS_JSON` with this shape:

```json
{
  "sprint_4_6_b1": {
    "search_plans": [
      {
        "plan_id": "<private plan id>",
        "lane": "<private lane>",
        "region": "<region>",
        "language": "<language>",
        "priority": "P0",
        "query_template": "<private query text>",
        "cadence": "daily",
        "notes": "<notes>",
        "status": "active",
        "source_scope": "<scope>",
        "event_types": "<event types>",
        "time_window": "T/T-1",
        "exclusion_terms": "<exclusions>",
        "first_seen_only": "TRUE",
        "last_reviewed": "<YYYY-MM-DD>",
        "version": "<version>"
      }
    ],
    "worker_channel_plan_map_additions": {
      "C1": ["<same three plan ids>"]
    }
  }
}
```

Exactly three SearchPlans are required. Their IDs must match the C1 additions exactly. Each plan must be active, daily, P0, first-seen-only, and contain a non-empty private query.

## Mutation semantics

- SearchPlans rows are upserted by `plan_id` after exact header validation.
- Existing non-target SearchPlans are preserved.
- `worker_channel_plan_map_json.C1` is extended additively; existing C1/C2/C4/C6 routes are preserved.
- Re-running the migration is idempotent.
- Apply mode performs readback validation before the workflow proceeds to global schema validation.

## Acceptance

4.6B.1 is live-PASS only when:

1. public CI passes;
2. migration dry-run passes with the private payload;
3. apply passes;
4. all three SearchPlans read back exactly;
5. all three C1 worker routes appear in `worker_channel_plan_map_json`;
6. global schema validation passes;
7. a later Worker run leaves coverage rows for all three required routes.

The first six conditions establish configuration rollout. The seventh establishes operational rollout.
