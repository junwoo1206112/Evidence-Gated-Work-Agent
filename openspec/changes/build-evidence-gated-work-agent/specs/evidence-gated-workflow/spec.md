# Evidence-Gated Workflow

## ADDED Requirements

### Requirement: Gate SHALL block plan creation when evidence is insufficient

The system SHALL NOT create a `plans`, `approvals`, or `executions` row when the evidence gate fails.

#### Scenario: Insufficient evidence

- **GIVEN** a request whose candidates are all below the score threshold
- **WHEN** `POST /api/runs` is called
- **THEN** the run status SHALL be `EVIDENCE_INSUFFICIENT`
- **AND** `plans`, `approvals`, and `executions` SHALL have 0 rows
- **AND** the response SHALL include a human-readable gate reason

#### Scenario: Conflicting evidence

- **GIVEN** two valid candidates with the same tagged `policy_key` and `policy_scope` but different normalized values
- **WHEN** the gate evaluates the candidates
- **THEN** the gate category SHALL be `conflict`
- **AND** the conflict SHALL list the document IDs and values
- **AND** no plan SHALL be created

### Requirement: Gate SHALL require distinct public citations

The system SHALL require at least two distinct `public_summary` documents with valid citations. Synthetic fixtures MUST NOT count toward this minimum.

#### Scenario: Synthetic-only citations

- **GIVEN** two valid synthetic fixtures and no valid public document
- **WHEN** the gate evaluates
- **THEN** the run SHALL be blocked
- **AND** the reason SHALL state that synthetic fixtures do not count

### Requirement: Planner MUST require a GatePass

`Planner.build_plan` MUST accept only a `GatePass` produced by `EvidenceGate.make_pass()`. A direct call without a GatePass MUST fail.

#### Scenario: Direct planner call

- **GIVEN** a caller that bypasses the gate
- **WHEN** it calls `build_plan(request, None)`
- **THEN** the call SHALL raise `TypeError`

### Requirement: Approval SHALL bind to the plan hash

An approval MUST store the approved plan hash. A second approval MUST be rejected with HTTP 409.

#### Scenario: Double approval

- **GIVEN** a run in `APPROVED` status
- **WHEN** `POST /api/runs/{id}/approval` is called again
- **THEN** the response SHALL be HTTP 409 `E_STATE_CONFLICT`
- **AND** exactly one approval row SHALL exist

### Requirement: Execution MUST require approval and an intact plan

The system MUST reject execution unless the run is `APPROVED`, an approval exists, the stored plan rehashes to the approved hash, and the evidence fingerprint/config/corpus hashes still match.

#### Scenario: Execution before approval

- **GIVEN** a run in `PENDING_APPROVAL`
- **WHEN** `POST /api/runs/{id}/executions` is called
- **THEN** the response SHALL be HTTP 409 `E_STATE_CONFLICT`
- **AND** `executions` SHALL remain 0 rows
- **AND** the denial SHALL be recorded in `audit_events`

#### Scenario: Tampered plan

- **GIVEN** an approved run whose stored `plan_json` was modified
- **WHEN** execution is requested
- **THEN** the response SHALL be HTTP 409 `E_PLAN_HASH_MISMATCH`
- **AND** no execution row SHALL be created

### Requirement: Execution SHALL be idempotent

The same idempotency key on a completed run MUST return the cached result without creating a new execution row or audit event. A different key MUST be rejected.

#### Scenario: Duplicate key

- **GIVEN** a completed run executed with key `K`
- **WHEN** execution is requested again with `K`
- **THEN** the response SHALL be HTTP 200 with `meta.replayed=true`
- **AND** `executions` SHALL remain 1 row

#### Scenario: Different key

- **GIVEN** a completed run
- **WHEN** execution is requested with a different key
- **THEN** the response SHALL be HTTP 409 `E_ALREADY_EXECUTED`
