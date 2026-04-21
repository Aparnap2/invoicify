# ADR-007: Trust Battery Decay Policy

## Status

Accepted

## Date

2026-04-21

## Context

The Trust Battery system currently handles vendor trust scoring for invoice auto-approval. However, there's no explicit policy for trust degradation when vendors:
- Have fraud detected
- Accumulate consecutive errors
- Remain inactive for extended periods

## Decision

We will implement a Trust Battery Decay Policy with three triggers:

### Trigger 1: Fraud Detection
- If fraud is detected on any invoice, vendor trust immediately drops to PROBATION tier
- All auto-approval privileges are revoked
- Human review required for all future invoices until trust rebuilds

### Trigger 2: Consecutive Errors
- If a vendor accumulates 3+ consecutive errors, drop one trust tier
- Example: CORE → STANDARD, STANDARD → PROBATION
- Error streak resets after any successful invoice

### Trigger 3: Inactivity Decay
- If vendor has no invoices for 90+ days, drop one trust tier
- This ensures trust levels reflect current vendor behavior, not historical performance

## Implementation

```python
class TrustDecayPolicy:
    FRAUD_DETECTED = "reset_to_PROBATION"
    CONSECUTIVE_ERRORS_3 = "drop_one_tier"
    INACTIVITY_90_DAYS = "drop_one_tier"
    
    def apply(self, vendor: Vendor, event: TrustEvent) -> TrustLevel:
        if event.type == "fraud_detected":
            return TrustLevel.PROBATION
        if event.consecutive_errors >= 3:
            return vendor.trust_level.downgrade()
        if event.days_inactive >= 90:
            return vendor.trust_level.downgrade()
        return vendor.trust_level
```

## Consequences

### Positive
- Trust levels remain accurate and reflect current risk
- Automatic risk mitigation for dormant or problematic vendors
- Compliance with audit requirements for trust-based decisions

### Negative
- Vendors may need re-verification after inactivity
- Additional complexity in trust calculation

## References

- Trust Battery implementation: `apps/agent-core/src/trust/battery.py`
- Fraud Gate: `apps/agent-core/src/risk/fraud_gate.py`
