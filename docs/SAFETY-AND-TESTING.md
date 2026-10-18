# Safety, testing and deployment rules

## Threat model

A Content Manager workspace includes untrusted YAML, JSON, PNG, ZIP imports and potentially symlinked directories. It may be run by an administrator next to production plugin content. Primary risks: unintended overwrite, malicious paths, unknown parser behavior, resource exhaustion, allocation reuse, live-server races, unsafe model/texture references and cross-plugin schema drift.

## Mandatory invariants

1. **No mutation on import, scan, preview or validation.** Snapshot live allocation manifests before sandbox compilation. Validation may use temporary allocation copies only.
2. **No direct mutation of world entities, bank balances, market stock, trade journals, player inventory or stored showroom layout data** as part of ordinary content editing.
3. **No overwrite without diff approval.** Generated models, textures and item keys must be owned by a recipe or explicitly selected to replace; human edits require three-way merge.
4. **No ID reuse as cleanup.** VoxelCore content IDs and render/block/glyph allocations are stable; runtime-owned manifests must not be compacted, reset or silently replaced.
5. **No unsupported YAML keys.** Separate Studio-only metadata from plugin runtime files. Exact version-pin schema adapters and preserve unknown fields.
6. **No unbounded generator output.** Cap file count, geometry elements, decompressed asset bytes, nested YAML aliases, path depth and executable work.
7. **No unattended publication.** User selects target and approves exact output/backup policy. A remote server is never contacted by default.
8. **No arbitrary native execution from a content pack.** Resource JSON/YAML and recipes are data, not scriptable eval. External importers require explicit trust and isolation.
9. **No false previews.** Surface scene renderer limitations for shader overlays/portraits, atlas behavior, game physics, lighting and animation timing.
10. **No hidden cross-platform assumptions.** Prevent Windows case-folding collisions and unsafe reserved names; normalize paths and UTF-8; test on Windows first.

## Path/persistence protection

Only explicit allowlisted roots may be read or written. Resolve and normalize *existing parent* real paths; reject symlink/junction escapes and ZIP-slip traversal; enforce same-filesystem atomic replace when available, otherwise use a recovery-safe copy-and-verify transaction. Reject case-insensitive duplicates for output portability.

Use a per-project writer lock and revision preconditions. For mixed files, do node-scoped patching with snapshots of before/after. Snapshot includes content, model JSON, textures, touched config files, and relevant allocation manifests. Never overwrite a snapshot referenced by an active recovery journal. On restart, detect incomplete transactions and recover before another publish.

Protected files by default: `plugins/VoxelCore/render-allocations.yml`, `block-allocations.yml`, `glyph-allocations.yml`, and world/runtime state. Compiler may update legitimate allocation manifests only in **explicit approved build/publish stages**, with preflight backup and deterministic diff. Never remove tombstones or renumber slots as an optimization.

## Local service security

Bind to `127.0.0.1` (and optionally `::1`), use ephemeral port and unguessable session token passed via launch handshake. Verify Origin/Host and require token for write endpoints and event streams. Never bind `0.0.0.0` by default. No wildcard CORS or unauthenticated POST. CSRF-safe token strategy. Prohibit HTTP asset fetch to arbitrary remote URLs or local network SSRF. Keep secrets out of repo, logs, recipes and generated ZIPs.

Remote bridge (future): deploy with separate explicit pairing, strong credential rotation, least-privilege allowed root, command allowlist, hash/revision handshake, audit and TLS/tunnel. The plugin's presence alone must not authorize a GUI connection. No remote world editing in the first release.

## Build isolation and compatibility

Use Java 25 to load current VoxelCore pack compiler. Pin dependency commits/checksums. Run the *real* Java pack validator in a sandbox. Compare no-op validation's source hashes before and after; tests fail if anything changed. Support version profiles only if explicitly known by `JavaPackTarget`, not broad guessed ranges.

A clean pack validation does not prove VoxelFurniture or VoxelVehicles runtime property parsing succeeds. Add adapter parser unit tests plus a real Paper staging run for each officially supported plugin build; report adapter status separately. If VoxelCore Java pack builds for MC 1.12 but a current addon cannot run there, do not imply addon compatibility.

## Automated verification pyramid

| Level | Scenarios |
|---|---|
| Pure domain tests | ID normalization, graph edges/cycles, recipe expansion, deterministic sort, format-safe variable substitution |
| Parsers/adapters | Real snippets from each repo, unknown fields, invalid values, inheritance null/false/empty semantics |
| Model tests | Parent/texture alias resolution, UV/tint, missing particle texture, JSON model cycles, filename collision |
| File tests | CST comment preservation, mixed YAML, undo/redo, external edit during save, symlink path, crash recovery |
| Generator golden | Oak + multi-wood outputs, wool 16 palette, 2-axis matrix, nested animated state, idempotence, changed source |
| Compiler comparison | VoxelCore validate/build on copied workspace; same target+inputs => same hashes; expected atlas diagnostics |
| GUI end-to-end | Create, search, edit, model preview, keyboard navigation, bulk exclusion, diff approval and undo |
| Server integration | Content reload, resource-pack apply, furniture placed state, vehicle preview/chest/tint, restart persistence |
| Fault injection | Mid-transaction power-loss simulation, read-only path, locked file, full disk, malformed PNG, concurrent writer |

**Runtime test corpus:** Use synthetic freely redistributable PNG/JSON and test fixtures in this repo. User's actual Voxel pack/assets are imported from their own filesystem and remain local; do not commit private server configuration or third-party licensed game assets.

## Deployment state machine

```text
DRAFT -> PLANNED -> VALIDATED -> STAGED -> REVIEWED
                                        -> APPROVED
                                        -> SNAPSHOTTED
                                        -> PUBLISHED -> VERIFIED
                                         \-- failure -> RESTORING -> ROLLED_BACK
```

`APPLY` for an offline authored project is separate from `PUBLISH` to a live server installation. Generation only stages source changes. Build produces a compiler-owned ZIP. On failed validation: do not publish. On failed publish: restore original files and keep journal. Live reload is an explicitly requested follow-up step; until a bridge API is proven, print appropriate manual commands, not an assumed hot-reload operation.

## Performance constraints (targets, to validate)

- 10,000 item/blocks definitions and 50,000 reference edges without blocking the UI event loop.
- Bulk generation handles 1,000 planned outputs with bounded concurrency, progressive diagnostics and cancellation. Absolute operation cap configurable only under an explicit review.
- Incremental graph reindex of changed files; cache previews by input/version/hash; do not parse entire asset tree for every keystroke.
- Avoid synchronous 3D texture uploads during editor typing. Dispose GPU resources and limit texture dimensions.
- Pack compilation may be expensive: run in isolated worker process with cancellable progress and resource/time ceilings. Avoid freezing a Minecraft server main thread; use local machine service for heavy generation.

## Traceability

Every shipped feature has a roadmap phase, a documented compatible plugin version, schema fixture, golden expected output and automated test. Every publish includes timestamp, source/output hashes, target profile, generator recipe IDs, applied change list and a restorable snapshot ID. A successful CI build is necessary but not sufficient for in-game correctness.
