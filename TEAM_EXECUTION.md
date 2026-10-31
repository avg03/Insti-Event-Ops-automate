# TEAM EXECUTION — 4-person sprint handoff

## Phase 0: before parallel coding (15–20 min)
- Agree on `EventBrief`, `GuestCandidate`, `VendorOffer`, `VendorOrder`, `Issue`, `ReadinessResult`, `AuditEvent` in `CONTRACTS.md`.
- Agree on `event_id`, enum values, prices in integer INR, timezone-aware timestamps, and `SIMULATION_MODE`.
- Choose ONE sample unknown event and ONE failure scenario for integration test.
- Designate the orchestration member as integration owner; no member changes core schemas without announcing it.

## Parallel tasks
| Owner | Files | Must expose | Unit test |
|---|---|---|---|
| A: Guest intelligence | `services/crustdata.py`, `services/guest.py`, `simulator/guest_simulator.py` | `search_speakers`, `send_guest_invitation`, `confirm_guest_booking` | declined/conditional/accepted; evidence preservation |
| B: Vendor procurement | `services/vendor.py`, `services/optimizer.py`, `simulator/vendor_simulator.py` | `get_vendor_quotes`, `commit_vendor_order`, `recover_vendor` | budget, delivery, hold expiry, retry |
| C: Backend orchestration | `main.py`, `schemas.py`, `db.py`, `agent/graph.py`, `services/verification.py` | REST endpoints, state and audit, recovery graph | happy path + event trigger |
| D: Frontend/demo | React UI components, forms, status cards, timeline, procurement/guest cards | `POST /events`, polling, simulator trigger | render planned/ready/blocked and simulated labels |

## Integration gates
1. **Gate A:** `POST /api/events` creates record and `GET` returns state (even without agent).
2. **Gate B:** Guest Crustdata adapter returns normalized candidate with provenance; simulated invite persists.
3. **Gate C:** Vendor simulator returns 2+ offers and saves confirmed sandbox order; budget verifier passes.
4. **Gate D:** Orchestrator connects both and reaches READY_IN_SANDBOX.
5. **Gate E:** Cancellation trigger changes order, recovery confirms replacement, independent verifier passes.
6. **Gate F:** UI shows complete run; record 2-minute video before code freeze.

## Budget timeboxing (five hours from code start)
- 0:00–0:25 align contracts, boot skeleton + preflight dependencies.
- 0:25–1:55 parallel modules, one thin path each.
- 1:55–3:00 integrate guest + vendor happy path, inspect logs.
- 3:00–3:55 cancellation recovery, idempotency, budget tests.
- 3:55–4:35 polish demo, case variants, 2-minute recording.
- 4:35–5:00 README, repo checks and submission buffer.

## Cut list if behind schedule
Cut: campaign art generation → campaign brief → attendance scaling → guest fee negotiation → frontend polish. **Do not cut:** real Crustdata call, simulated confirmed arrangements, independent verifier, one successful cancellation recovery, and recorded demo.
