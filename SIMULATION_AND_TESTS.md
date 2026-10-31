# SIMULATION, EDGE CASES & ACCEPTANCE TESTS

## Simulation design rules
- **All external party responses are invented test scenarios.** Never present them as actual replies from Crustdata people.
- Separate identity match `canonical_person_id` from a synthetic behavior mapping by index (e.g. first shortlisted candidate = persona `GUEST_A`).
- Simulator uses seeded predictable data plus selectable test profiles. It must support **unfamiliar event briefs**, not only a hardcoded ML event.
- Explicit `SIMULATION_MODE=true`. Block all live messages/payments in this mode.

## Example guest personas (synthetic)
```json
{
  "scenario_id":"guest_reschedule_then_cancel",
  "personas":[
    {"alias":"GUEST_A","behavior":"conditional","request":{"start_after":"16:30","honorarium_inr":3000},"later_event":"GUEST_CANCELLED"},
    {"alias":"GUEST_B","behavior":"decline","reason":"schedule_conflict"},
    {"alias":"GUEST_C","behavior":"accept","honorarium_inr":2500},
    {"alias":"GUEST_D","behavior":"accept","honorarium_inr":3000}
  ],
  "negotiation_max_rounds":3
}
```

## Example vendor catalogue (fully fictional; prices not market claims)
```json
{
  "vendors":[
    {"id":"cater_a","service":"catering","capacity":150,"total_price_inr":10000,"delivery_time":"2026-11-12T15:30:00+05:30","dietary_tags":["vegetarian_option"],"cancellation_fee_inr":0,"behavior":"cancel_on_trigger"},
    {"id":"cater_b","service":"catering","capacity":160,"total_price_inr":10700,"delivery_time":"2026-11-12T15:45:00+05:30","dietary_tags":["vegetarian_option"],"hold_minutes":60,"behavior":"reliable_backup"},
    {"id":"cater_c","service":"catering","capacity":200,"total_price_inr":12000,"delivery_time":"2026-11-12T16:30:00+05:30","dietary_tags":[],"behavior":"late_delivery"},
    {"id":"av_a","service":"av","capacity":150,"total_price_inr":3000,"delivery_time":"2026-11-12T14:30:00+05:30","behavior":"reliable"}
  ]
}
```

## Acceptance tests
| ID | Input / failure | Expected verifier / system behavior |
|---|---|---|
| HP01 | Valid event, guest replies accept/conditional, valid vendors | `READY_IN_SANDBOX`, correct evidence/ledger |
| G01 | First candidate declines | Invite next relevant candidate, no fake confirmation |
| G02 | Candidate demands fee above cap | Negotiate within cap or reject, do not exceed budget |
| G03 | Guest cancels after confirmation | Release calendar slot, invite backup, re-verify |
| G04 | Replayed identical guest reply | Process once by unique inbound message ID |
| C01 | Crustdata returns empty result | `BLOCKED` or evidence-limited; no fabricated candidate |
| C02 | Crustdata timeout/rate-limit | Bounded retry and explicit error classification |
| V01 | Primary vendor cancels after booking | Replacement booking confirmed or precisely blocked |
| V02 | Held replacement has expired | Do not activate stale hold; fetch new quote |
| V03 | Two simultaneous booking retries | Exactly one committed order due to idempotency |
| V04 | Supplier fails dietary requirement | Offer rejected regardless of low cost |
| B01 | Replacement pushes cost above hard budget | Reject replacement; seek alternative or block |
| B02 | Cancellation fee incurred | Fee counted against spend/commitment before replanning |
| A01 | Attendance 120→145, venue 150 | Resize available resources and reverify |
| A02 | Attendance 120→175, venue 150 | Stop at registration cap or `BLOCKED_CAPACITY`; no false readiness |
| D01 | AV arrives after required deadline | Reject order as unfit |
| F01 | Provider returns malformed JSON | Validation error logged; try safe fallback, never call success |
| F02 | Failed booking call but DB committed | Lookup by idempotency key, do not double book |
| X01 | Impossible event constraints | `BLOCKED` + exact failed constraints |

## Test structure
```
backend/tests/
  test_request_validation.py
  test_guest_coordination.py
  test_vendor_optimization.py
  test_idempotency.py
  test_attendance.py
  test_cancellation_recovery.py
  test_readiness_verifier.py
```

Use unit tests for optimizer/verification, integration tests with SQLite and mock Crustdata adapter, and one optional live identity lookup smoke test (do not require API credit in CI).

## Verify judge-facing evidence
- Every displayed identity claim should have a stored Crustdata source ID/time.
- Every guest/vendor booking should show **simulated confirmation ID**, agreed terms, and timestamp.
- Show pre-failure and post-recovery readiness; expose audit log entries rather than relying on model narrative.
- Outcome metrics: `required_guest_confirmations`, `confirmed_vendor_categories`, `budget_remaining`, `recovery_steps`, `time_to_sandbox_recovery`, `unresolved_blockers`.
- Do **not** claim simulated discounts or time savings as measured real savings.
