# EventOps Autopilot — ContextCon IIT Bombay build handoff

**Mission:** turn a natural-language event request into a **verified, executable sandbox event arrangement** with expert guest sourcing from real Crustdata identity data, simulated guest communication, procurement, and autonomous disruption recovery.

**Read in this order:**
1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — scope, system structure, decision boundaries, data flow, deployment.
2. [`WORKFLOWS.md`](WORKFLOWS.md) — exact example execution, state transitions, failure recovery.
3. [`CONTRACTS.md`](CONTRACTS.md) — API, Pydantic data contracts, tool interfaces, persistence.
4. [`SIMULATION_AND_TESTS.md`](SIMULATION_AND_TESTS.md) — fixtures, edge cases, acceptance tests and demo script.
5. [`FRONTEND_DESIGN.md`](FRONTEND_DESIGN.md) — warm UI design system, layouts, interactions.
6. [`CODING_AGENT_PROMPT.md`](CODING_AGENT_PROMPT.md) — paste into your coding IDE to implement.
7. [`TEAM_EXECUTION.md`](TEAM_EXECUTION.md) — four-person parallel build plan and integration gates.
8. [`frontend-preview.html`](frontend-preview.html) — browser-openable **static, illustrative** warm UI preview; not connected to backend.

## Non-negotiable competition constraints (source: uploaded ContextCon PDF)
- **5-hour coding window:** 31 Oct 2026, 10:30 AM–3:30 PM IST. Repository + 2-minute screen recording due by 3:30 PM.
- **Mandatory:** actually use Crustdata API and its **people/company canonical identity graph**; support source evidence and data provenance.
- **NO outreach to external real people during the event**, even if a real guest would be willing. Guest and vendor messaging are **local/sandbox simulations only**. Authorized Crustdata calls are permitted.
- Judged on **end-to-end autonomous completion, verification/data integrity, robustness to unexpected tool responses, clarity of 2-minute demo**.
- **Never claim real guests or vendors are booked.** UI must visibly distinguish `LIVE_DATA` identity discovery from `SIMULATED` bookings.

## MVP success definition
For a new event brief, the service:
1. Parses and validates constraints.
2. Searches real Crustdata people data for relevant experts; stores person IDs and evidence.
3. Obtains 1–2 confirmations **from guest simulator** and records schedule/terms.
4. Selects and confirms sandbox food/equipment reservations inside the budget.
5. Detects an injected cancellation, selects eligible backup, commits replacement with idempotency key.
6. Re-reads persisted records, computes readiness objectively, and produces an audit trail.

**P1 if stable:** attendance surge/capacity reoptimization, campaign brief (social copy + reel storyboard), sponsor/collaborator research via Crustdata company search. **Out of scope:** real mail/WhatsApp, actual payments, social posting, poster image/video generation, real guest availability, cloud game deployment.

## Suggested tech
React/Vite/TypeScript + Tailwind or CSS; FastAPI + Pydantic + SQLite + LangGraph; single LLM through one adapter; Crustdata REST; deterministic guest/vendor simulator; simple constrained optimizer and independent verifier.

## Repo target
```
/backend/app/{main.py,schemas.py,db.py,settings.py}
/backend/app/agent/{graph.py,prompts.py,model.py}
/backend/app/services/{crustdata.py,guest.py,vendor.py,optimizer.py,verification.py,promotion.py}
/backend/app/simulator/{guest_simulator.py,vendor_simulator.py,fixtures.py}
/backend/tests/{test_happy_path.py,test_recovery.py,test_constraints.py}
/frontend/src/{App.tsx,api.ts,types.ts,components/,pages/}
```

> This handoff contains plans, contracts and a **visual static prototype**, not a completed integrated product.
