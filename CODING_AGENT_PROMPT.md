# CODING IDE MASTER PROMPT — EventOps Autopilot

You are a senior Python/React engineer building a 5-hour hackathon MVP called **EventOps Autopilot**.

## First read
Read `README.md`, `ARCHITECTURE.md`, `WORKFLOWS.md`, `CONTRACTS.md`, `SIMULATION_AND_TESTS.md`, `FRONTEND_DESIGN.md`, `TEAM_EXECUTION.md` in that order. Treat `CONTRACTS.md` as canonical. Report contradictions before implementing; prefer source PS constraints over inferred features.

## Required outcome
A working React + FastAPI app: user submits a new event request, backend plans event, uses REAL Crustdata Person Search for speaker relevance, coordinates guests through a LOCAL simulator, receives simulated vendor quotations and commits sandbox orders, and deterministically verifies readiness. User can inject vendor cancellation, after which agent autonomously books eligible backup and verifier reports restored readiness. Every action is audited. Visible real-data vs simulated badges.

## Safety and competition restrictions
- NEVER contact external real people or vendors. Do not use real Gmail, phone, WhatsApp, LinkedIn, DMs or production procurement/payment APIs.
- Use Crustdata API with a backend-only key; do not invent its endpoint paths, payload schema, or data. If documentation unavailable, implement typed adapter interface and fail transparently; do not fake a live Crustdata call.
- Never claim real person agreed to be a guest. Local simulated guest responses only.
- Hard budget, capacity, deadlines and booking idempotency enforced in deterministic code, not prompt instructions.
- Never log secret values. Never put keys in frontend.

## Implementation sequence
1. Inspect repository and installed dependencies without reading `.env` secret values; read config key names only.
2. Create stable Pydantic schemas and SQLite tables with migrations/init path.
3. Create FastAPI endpoints per `CONTRACTS.md`, including `/api/events/{id}/simulate` and `/verify`.
4. Implement Crustdata adapter using verified API docs; normalize identity results with source ID and fetched time.
5. Implement deterministic guest simulator and vendor simulator with seeded fixtures; map synthetic behavior to guest candidate index, not real-world guest personality.
6. Implement capacity and budget optimizer (small-space enumeration acceptable), idempotent order tool and independent readiness verifier.
7. Implement a bounded LangGraph orchestrator; use LLM only for structured request/agenda and context-aware negotiation text; tool wrappers perform all mutations.
8. Create warm, editorial React frontend guided by `FRONTEND_DESIGN.md` and `frontend-preview.html`; use real backend states, not fake dashboard figures.
9. Add tests per `SIMULATION_AND_TESTS.md`; demonstrate successful event, cancellation recovery, impossible constraint.
10. Verify README instructions and provide a concise report of completed vs incomplete features.

## Agent workflow rules
- Graph: `validate → plan → discover guests → guest coordination → quote vendors → optimize → book → verify`; event signals enter `recover → verify`.
- Allow max three negotiation turns per guest and three recovery attempts per issue.
- Never busy-wait for human response; simulator produces local events; persist transitions.
- All confirmed bookings are `*_SIMULATED`; audit them with evidence IDs.
- Mark `READY_IN_SANDBOX` only on verifier pass, never on LLM statement.
- If unavailable, mark `BLOCKED` and include exact unsatisfied constraints.

## Implementation restrictions
- Prefer reliable minimal code over architecture complexity. Do not create six separate conversational agents or an unnecessary MCP server.
- Avoid real-time WebSockets until API/polling workflow works.
- Provide resilient loading and error states.
- If Crustdata API quota or authorization fails, return explicit provider error; don't silently substitute invented people.
- Do not generate production claims about cost savings or real bookings.

## Definition of done
- New event completes in sandbox through Crustdata-backed guest research and two types of local booking.
- Vendor cancellation causes persisted invalidation and persisted replacement.
- Budget, capacity, time and quantity constraints independently pass.
- No duplicate orders from retries.
- Frontend clearly shows action timeline, provenance, simulated badges and readiness blockers.
- Full system runs locally with explicit commands, tests and reproducible demo fixtures.

## Expected final developer response
List files changed, setup commands, exact endpoints, tests executed/results, API assumptions verified vs unverified, and any incomplete requirements. Do not imply live bookings or communications occurred.
