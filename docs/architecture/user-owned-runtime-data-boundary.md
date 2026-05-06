# User-Owned Runtime Data Boundary

Status: Planned

AgentOS is local-first by default and user-owned by design. Phase 2 must make
the boundary between user-managed records and AgentOS-managed runtime state
explicit before adding more capabilities.

## Canonical Paths

Local development default:

```text
./agentos-data/user
./agentos-data/state
./agentos-data/cache
```

Installed or VM default:

```text
/var/lib/agentos/user
/var/lib/agentos/state
/var/cache/agentos
/run/agentos
```

Docker preview default:

```text
host ./agentos-data/user -> container /var/lib/agentos/user
host ./agentos-data/state -> container /var/lib/agentos/state
```

Existing `workspaces/<name>/artifacts` paths remain valid prototype artifacts,
but Phase 2 features should move user-visible records and generated outputs
toward the user-owned boundary.

## User-Owned Data

These paths are expected to be visible, exportable, removable, and manageable by
the user:

- workspaces
- generated files and artifacts
- exported activity logs
- diagnostics bundles
- user-provided notes, transcripts, and records
- Gmail or inbox fixtures explicitly provided by the user
- acceptance outputs

## AgentOS-Managed State

These paths are internal runtime state and may be recreated or repaired by
AgentOS:

- runtime sockets
- process state
- internal caches
- temp files
- service lock files
- generated indexes that can be rebuilt from user-owned records

## Secret-Managed Data

These values must not default to plaintext shared folders:

- API keys
- Telegram bot tokens
- OAuth access or refresh tokens
- provider credentials
- mailbox credentials

Secret material should come from runtime environment, OS keyring/secret store,
or a permission-restricted AgentOS env file. Status, activity, diagnostics, and
records must redact secret values.

## Records Contract

User-owned records should include source metadata whenever possible:

- source type
- created timestamp
- original path or adapter reference
- derived artifact path
- model or tool that produced a derived artifact, when available

Indexes and summaries are derived artifacts. They should link back to source
records and remain rebuildable or removable.

## Acceptance

The boundary is acceptable when Phase 2 smokes can show:

- a configured user-owned data root
- a generated user-visible output under that root
- an internal state path separate from user-owned records
- redacted status for missing or configured secrets
- cleanup checks that do not treat stale user-owned records as hidden temp debt

