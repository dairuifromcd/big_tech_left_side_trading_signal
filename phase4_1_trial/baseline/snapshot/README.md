# Local US equity technical observations

Python 3.13 virtual environment: `source .venv/bin/activate`. No new dependencies.

## Phase 3 usage

```sh
.venv/bin/python -m src.monitor
.venv/bin/python -m src.monitor --input reports/yahoo_nine_prices_20261030_141537.json
.venv/bin/python -m unittest discover -v
.venv/bin/python -m tests.simulate_states
```

Default input is the verified Phase 2 snapshot. Its paired diagnostic and SHA256
must match. OFFLINE_SNAPSHOT reports describe the capture's completed session,
not a current live quote. Backdated snapshots cannot replace newer persisted state.

`--fetch` explicitly invokes the unchanged Phase 2 serial collector (5-second
start intervals, extra 30 seconds per batch, no retry, stop on 429). This mode
is implemented but was not live-executed during Phase 3. No scheduler or trading API.

Reports: `reports/monitor_indicators_*.json` and `.md`. Formal state:
`state/monitor_state.json`. Fixed synthetic scenarios: `simulations/`, never formal
state. Override `--state` and `--output-dir` for isolated experiments. Corrupt state
fails closed: preserve/recover a verified backup; do not delete state to hide errors.

## Calculation and evidence policy

- All indicators use Adj Close. Close is display/evidence only.
- Drawdown includes the target session and uses the last 252 validated sessions;
  a verified young listing uses its full history. Exact tied highs choose latest date.
- RSI14 seeds the first 14 changes (15 prices), then Wilder smooths all available
  history. Zero loss means100; zero gain means0; entirely flat means50. The finite
  two-year warmup may differ slightly from a vendor with a longer seed history.
- SMA50/200 require exactly enough completed prices; unavailable values are null
  with INSUFFICIENT_HISTORY. No shorter replacement window.
- Float64 throughout; rounding only for display. Revision comparison uses abs
  tolerance1e-8 and relative tolerance1e-10 on overlapping **dates**, not rolling hashes.
  Tests independently use Decimal weighted sums and hand-checkable references.
- Observation tiers use -10/-20/-30 percent, inclusive. Significant deepening is
  `--significant-pp` (default1.0 percentage point), accumulated since the last event.
  Baselines establish previously touched levels but never emit new threshold events.
  Reentry into touched levels and new levels are retained separately even on a
  multi-level crossing. Revisions suppress market-drop events and recompute metrics.
- SHA256 detects accidental evidence changes; it does not verify Yahoo prices
  independently. SPCX remains YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED. Its supplied
  2026-06-16 Close conflict ($211.39 vs $201.80) establishes no Adj Close correction.
  All its tiers/metrics are provisional, and SMA200 remains unavailable until ready.
- Calendar is the existing bounded2024–2028 schedule, including published early
  closes. Future emergency closures need updates. Incomplete sessions are explicitly
  retained/excluded; invalid prices or missing sessions fail validation.
- State writes are atomic. Phase 4 adds `fcntl.flock` transaction protection and
  validated backup rotation; no database or scheduled monitoring service.

Technical observations have no investment-value grade or buying-price recommendation.

## Phase 4 isolated reliability acceptance

```sh
# One authorized live collection; do not repeat to force a successful result.
.venv/bin/python -m src.phase4 --fetch
# Repeat offline using the price evidence from that run.
.venv/bin/python -m src.phase4 --input phase4_trial/reports/collection/yahoo_nine_prices_TIMESTAMP.json
# Five consecutive historical sessions, in a fresh isolated directory.
.venv/bin/python -m src.phase4 --replay --output-dir phase4_trial/replay
.venv/bin/python -m unittest discover -v
```

The default Phase 4 state is `phase4_trial/state/monitor_state.json`. Initialize
it once from a validated Phase 3 baseline; never overwrite an existing trial.
The Phase 4 runner refuses the formal `state/monitor_state.json` path. All trial
collectors, monitor reports, JSON/Markdown audit reports, replay data and states
stay in `phase4_trial/`. A successful result with SPCX is PASS_PROVISIONAL.

Locks cover read/compute/commit and the optional live fetch. Lock files must not
be deleted: `flock` releases automatically on process termination. An isolated
state path gets its own lock. Updates validate the full candidate before commit,
back up the prior validated state, fsync files and directories, then atomically
replace. Up to three versioned, SHA256-checked backups are retained next to each
state. Failure after replacement may leave a **complete new** state; reports
compare hashes rather than claiming every exception means nothing was committed.

Corrupt state stops the run. Recovery is never automatic. After inspecting the
backup/version and selecting a specific file, explicit isolated recovery is:

```sh
.venv/bin/python -m src.phase4 --state phase4_trial/state/monitor_state.json --recover-backup PATH_TO_VERIFIED_BACKUP
```

Recovery validates envelope hash, version and all stored indicators, quarantines
damaged bytes, and atomically restores the selected complete state under lock.
For ambiguous backups, stop and select the correct verified checkpoint manually.
Never reset state to obtain FIRST_BASELINE or remove a live process's lock file.

The state contains a deterministic event ledger, committed with the stock data.
No wall-clock timestamps enter event IDs. Reports can fail after a successful
commit; the ledger remains recoverable and the same input cannot re-emit events.
No external notifications are delivered in DRY_RUN.

Historical replay truncates every symbol at the replay date and revalidates it
at that session's close. It is labeled OFFLINE_REPLAY, not a live discovery.
The date-stamped source diagnostics are reused for security identity evidence;
all price/calendar checks are rerun. Real cross-day operation remains
PENDING_LIVE_VALIDATION until executed on separate real trading days.

Limitations: one Yahoo price source; SPCX dispute unresolved; calendar ends2028
and cannot predict emergency closures. Backups/locks are local-filesystem tools,
not guarantees against disk loss, malicious edits, or external clients bypassing
the documented lock contract. Recovery is a deliberate rollback and downstream
consumers must reconcile previously consumed event IDs before resuming delivery.
