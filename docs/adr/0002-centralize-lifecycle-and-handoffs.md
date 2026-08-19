---
status: proposed
---

# Centralize lifecycle state and handoffs

The orchestrator remains the authority for ticket lifecycle and records a
structured handoff receipt after every phase. Agents do not exchange durable
peer-to-peer work messages: central receipts preserve inspectability, recovery,
and policy enforcement without adding a second distributed coordination system.
