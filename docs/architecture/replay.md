# Deterministic market replay

The first Phase 11 replay slice consumes one non-empty stream of closed candles for exactly one instrument and
timeframe. Inputs must have unique chronological UTC-normalized timestamps. A candle becomes visible only at its
interval close (`timestamp + timeframe_seconds`), matching the platform's closed-candle availability boundary.

`ReplayEngine.step()` emits one immutable frame and advances the prefix. `snapshot()` returns only that emitted prefix;
it cannot expose later candles. An explicit aware-time `seek()` uses close availability, supports forward or backward
navigation, and never includes a candle whose close is later than the requested time.

Checkpoints contain a SHA-256 identity of the complete ordered dataset and the next event index. Restore rejects a
different dataset or an out-of-range cursor, allowing deterministic restart without silently applying a cursor to
changed evidence. The digest is an integrity identity, not authentication or authorization.

Replay sessions persist dataset identity, instrument/timeframe identity, cursor, total event count, checkpoint time,
and an optimistic version. Creation is idempotent only for identical dataset evidence. Checkpoint updates atomically
require the expected version, dataset digest, and an in-range cursor; stale writers and changed datasets fail closed.
Database constraints independently enforce non-negative versions/cursors and cursor-within-total invariants.

The replay coordinator reconstructs an engine through an injected immutable-dataset loader before every operation and
revalidates digest, instrument, timeframe, and event count against persisted evidence. Step and seek require the caller's
expected version and save the resulting checkpoint atomically. Read-only snapshots restore the exact persisted prefix;
terminal steps and no-op seeks do not manufacture a new version.

Replay datasets are persisted as immutable, content-addressed closed-candle payloads. Storage is idempotent for identical
content. Every load reconstructs the typed candles and recomputes the engine digest while also checking stream metadata
and timestamp bounds, so database corruption or metadata/payload drift fails closed before a coordinator can emit data.
The dataset repository directly implements the coordinator's loader protocol and therefore supports restart recovery
without relying on a process-local candle cache.

The authenticated replay API lets operators register a bounded dataset, create a session, and issue version-checked
step or seek mutations. Viewers and operators can read the persisted prefix, but viewer credentials cannot mutate replay
state. Missing resources return `404`, stale versions or integrity conflicts return `409`, and unavailable persistence
fails closed with `503`. Replay contracts and handlers live in a dedicated router whose factory receives the application
database and authentication dependencies explicitly; application bootstrap retains only composition and shared security
middleware. Replay operations have no execution authority.

Authenticated viewers can discover recent dataset metadata and replay sessions through stable newest-first lists. Both
lists require bounded `limit`/`offset` pagination (maximum 100 records); dataset discovery revalidates each returned
content-addressed payload before exposing its metadata. Dataset candle payloads are never returned by discovery.

The responsive `/replay` console keeps its bearer credential in tab-scoped session storage, discovers the authenticated
role, permits viewer prefix inspection, and enables step/seek controls only for operators. Its document is served with a
restrictive content security policy and no-store caching. A dependency-free SVG chart renders at most the latest 100
closed candles from the already-authorized prefix, with an accessible textual description and tabular evidence. It
deliberately has no execution controls. Operators can select a local JSON file (bounded to 5 MB in the browser), register
the validated content-addressed dataset through the API, and atomically open a new replay session; file contents are not
placed in browser storage.

After authentication, the console retrieves up to 25 recent replay sessions and renders them into a safe DOM-backed
picker. Choosing an item copies its UUID into the explicit session field; loading remains a deliberate user action. The
list can be refreshed after concurrent session creation without reloading the page.

Operators can launch bounded server playback from the console at 0.5, 1, 2, or 5 candles per second. The browser sends
the current optimistic version and remaining bounded step count, polls authenticated task status, refreshes only the
authorized prefix, and disables conflicting step/seek controls. Explicit stop and hidden-tab suspension call the server
stop endpoint rather than merely abandoning a browser timer.

The console also retrieves the latest 10 persisted playback runs for the loaded session. It renders task identifiers,
outcomes, frame counts, resulting versions, and localized start times through text-only DOM construction; history is
refreshed after session load, task start, and terminal or stopped playback.

While playback is active, session selection and loading are disabled. Disconnecting, replacing the session through a
new dataset, or otherwise switching context first awaits the authenticated stop endpoint; if stop fails, the console
keeps the credential and current context so the operator does not silently abandon a server-owned task.

Playback startup has an explicit pending state that disables duplicate starts, disconnect, dataset replacement, and
session changes until the server accepts or rejects the task. Once accepted, optional prefix/history refresh failures
do not erase ownership state or misreport the scheduler start as failed; stop success likewise remains authoritative
even if a subsequent display refresh is unavailable.

Status polling uses bounded exponential retry after transport or API failures and retains the active ownership state and
stop control. Prefix rendering failures are non-authoritative: a running task continues to be polled, while a terminal
task still transitions the console out of active playback even if its final prefix or history refresh is unavailable.

The server-side `ReplayScheduler` provides an injectable orchestration primitive for 0.1–100 candles per second and
1–10,000 steps per run. It checks the starting optimistic version, advances serially through the coordinator, invokes a
required commit callback after every emitted frame, and reports `complete`, `stopped`, or `step_limit`. Its injected
clock, sleeper, and stop predicate make cadence and shutdown deterministic in tests. A restart resumes from the last
committed checkpoint rather than an in-memory scheduler cursor.

`ReplayTaskManager` supplies the first single-process ownership boundary around that scheduler. It permits at most one
active task per replay session, validates its immutable request before launch, exposes running and terminal status,
supports cooperative stop, records failures without leaking exception details, and stops all owned tasks during
application shutdown. Completed sessions may be started again only through a new bounded request; the persisted replay
checkpoint, rather than task-manager memory, remains the restart authority.

Operators can start or stop this bounded playback through authenticated APIs, while viewers and operators can inspect
its status. Start returns an accepted running task, duplicate active ownership conflicts, unknown tasks return not found,
and application shutdown interrupts scheduler waits before closing database resources.

Every accepted task receives a server-generated identifier and persists its bounded request, running state, terminal
outcome, frame count, resulting replay version, and timestamps. Terminal transitions update only a matching running row,
making duplicate terminal writes fail closed. Authenticated users can page through newest-first history for a session;
the history contains no candle payloads or exception details. An authenticated task-ID endpoint retrieves one durable
run directly and overlays fresher process-owned state only when the in-memory owner has the same task identifier.

The current-playback read first consults the process owner and falls back to the latest persisted run after restart.
Every response includes `process_owned`; a persisted `running` row with `process_owned=false` is historical evidence of
an orphan, not a claim that another scheduler is active. Stop remains process-local and never pretends to control a task
that this process does not own.

This evidence is durable task history, not a distributed job registry. Cross-process leases, orphaned-running-task
recovery, multi-stream synchronization, analytical overlays, and richer dataset discovery remain later Phase 11 work.
