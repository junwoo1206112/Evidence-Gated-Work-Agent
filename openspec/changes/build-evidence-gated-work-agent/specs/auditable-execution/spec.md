# Auditable Execution

## ADDED Requirements

### Requirement: Audit events MUST be append-only

`audit_events` MUST have `UNIQUE(run_id, seq)` and database triggers that abort UPDATE and DELETE. Each event MUST include `prev_hash` and `event_hash`.

#### Scenario: Direct audit update

- **GIVEN** an existing audit event
- **WHEN** a client attempts `UPDATE audit_events SET payload_json='{}'`
- **THEN** SQLite SHALL abort the statement
- **AND** the chain verification SHALL still pass

### Requirement: Denied requests SHALL be audited

Rejected approval/execution attempts MUST append a `DENIED_APPROVAL` or `DENIED_EXECUTION` event without changing run status. The number of denied events per run SHALL be capped to prevent audit amplification.

#### Scenario: Pre-approval execution

- **GIVEN** a `PENDING_APPROVAL` run
- **WHEN** execution is requested
- **THEN** the run status SHALL remain `PENDING_APPROVAL`
- **AND** a `DENIED_EXECUTION` event SHALL exist
- **AND** the audit seq SHALL remain contiguous

### Requirement: Mock execution SHALL be side-effect free

The executor MUST allow only `create_demo_draft` and `simulate_notification`. Results MUST include `simulated=true` and `external_side_effects=false`.

#### Scenario: Disallowed action

- **GIVEN** a plan whose `allowed_action` is not in the allowlist
- **WHEN** the executor runs
- **THEN** it SHALL raise `ExecutionPolicyError`
- **AND** no external call SHALL occur

### Requirement: Failures SHALL retry at most once

A first attempt failure SHALL transition `EXECUTING → FAILED → RETRYING` and run attempt 2. A second failure SHALL leave the run terminal `FAILED`. Attempt values MUST be server-generated 1..2.

#### Scenario: Fail once

- **GIVEN** `demo_mode=fail_once`
- **WHEN** execution runs
- **THEN** attempts SHALL be `FAILED`, `EXECUTED`
- **AND** the run status SHALL be `EXECUTED`

#### Scenario: Fail twice

- **GIVEN** `demo_mode=fail_twice`
- **WHEN** execution runs
- **THEN** both attempts SHALL be `FAILED`
- **AND** the run status SHALL be `FAILED`
- **AND** a further request with the same key SHALL be HTTP 409 `E_RETRY_LIMIT`

### Requirement: Interrupted execution SHALL be reconciled

On startup, runs stuck in `EXECUTING`/`RETRYING` longer than the threshold MUST be transitioned to `FAILED` with a `RECONCILED_INTERRUPTED` audit event.

#### Scenario: Stale run

- **GIVEN** a run in `EXECUTING` with an old `updated_at`
- **WHEN** `reconcile_stale_runs()` runs
- **THEN** the run SHALL be `FAILED`
- **AND** the audit chain SHALL remain valid

### Requirement: Health SHALL reflect real dependencies

`/health` SHALL return 200 only when the database check succeeds. It SHALL report schema version, corpus counts/hash, config hash, and the absence of LLM/network dependencies.

#### Scenario: Database failure

- **GIVEN** the database health check fails
- **WHEN** `/health` is called
- **THEN** the response SHALL be HTTP 503
- **AND** the body SHALL NOT claim `ok`
