-- Schema of the fleet-era tables production still holds (captured 2026-09-28
-- from their stores at e14de4e6, before those stores were deleted). Until a
-- host-action drops them, scoped reset must classify them; this is what the
-- test in tests/test_scoped_identity_reset.py creates. Do not edit by hand.

CREATE TABLE cloud_automation_controls (
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    definition_digest TEXT NOT NULL,
    cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds >= 1),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    desired_state TEXT NOT NULL CHECK (desired_state IN ('active', 'paused', 'stopped')),
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (universe_id, automation_id)
);

CREATE TABLE cloud_automation_slice_triggers (
    trigger_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    activation_epoch INTEGER NOT NULL,
    activation_subject_ref TEXT NOT NULL,
    activation_subject_digest TEXT NOT NULL,
    slice_ordinal INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'claimed', 'admitted', 'emitted')),
    due_at TEXT NOT NULL,
    claim_expires_at TEXT,
    request_id TEXT,
    admission_id TEXT,
    branch_task_id TEXT UNIQUE,
    trigger_digest TEXT NOT NULL,
    previous_terminal_receipt_id TEXT,
    record_json TEXT NOT NULL,
    UNIQUE (universe_id, automation_id, activation_epoch, slice_ordinal)
);

CREATE TABLE cloud_automation_terminal_receipts (
    receipt_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL UNIQUE,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    activation_epoch INTEGER NOT NULL,
    slice_ordinal INTEGER NOT NULL,
    receipt_digest TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE cloud_automation_continuations (
    continuation_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state = 'prepared'),
    continuation_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (universe_id, automation_id)
);

CREATE TABLE cloud_execution_continuations (
    continuation_id TEXT PRIMARY KEY,
    work_item_kind TEXT NOT NULL CHECK (work_item_kind = 'agent_invocation'),
    work_item_id TEXT NOT NULL UNIQUE,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state = 'prepared'),
    continuation_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL
);

CREATE TABLE background_branch_bindings (
    binding_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    authorizing_principal_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE background_branch_attempts (
    attempt_id TEXT PRIMARY KEY,
    logical_attempt_key TEXT NOT NULL UNIQUE,
    binding_id TEXT NOT NULL,
    binding_generation INTEGER NOT NULL CHECK (binding_generation >= 1),
    lifecycle TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_at_utc_micros INTEGER NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    FOREIGN KEY(binding_id)
        REFERENCES background_branch_bindings(binding_id)
        ON DELETE RESTRICT
);

CREATE TABLE background_branch_authority_owners (
    owner_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    transition_generation INTEGER NOT NULL CHECK (transition_generation >= 1),
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_at_utc_micros INTEGER NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY(owner_kind, owner_id)
);

CREATE INDEX idx_background_branch_bindings_status
    ON background_branch_bindings(status, binding_id);

CREATE INDEX idx_background_branch_attempts_binding
    ON background_branch_attempts(binding_id, attempt_id);

CREATE INDEX idx_background_branch_attempts_lifecycle_updated
    ON background_branch_attempts(
        lifecycle, updated_at_utc_micros, attempt_id
    );

CREATE INDEX idx_background_branch_authority_owners_state_updated
    ON background_branch_authority_owners(
        state, updated_at_utc_micros, owner_kind, owner_id
    );
