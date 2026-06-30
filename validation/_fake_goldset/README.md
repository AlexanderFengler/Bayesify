# `_fake_goldset/` — fabricated demo data, NEVER a measurement

Every file here is a **fabricated** `HumanReport` (`origin: fake_llm`) plus its paired engine
`ScoredResult` (under `_engine/`). They exist so the whole validation pipeline — metrics, report,
and the calibration page — can be wired up and critiqued **before any real expert rates a paper**.

These numbers are **not** a measurement of the engine's accuracy:

- the "human" side is machine-authored, so it agrees with the engine too readily (systematically
  optimistic vs real experts);
- the set is tiny, so every metric is flagged *preliminary*.

The honesty firewall (`bayesify/core/validation/harness.py`) guarantees this data can **never**
produce the public `VALIDATION.md`: a non-`blind_human` record under the real `validation/goldset/`
is a hard `FakeDataInRealGoldset`, and emitting `VALIDATION.md` from a demo report is a hard
`FakeDataInPublicReport`. The demo writes only `VALIDATION.demo.md` with a loud FAKE-DATA header.

Regenerate with `pixi run demo-data`. Run the demo dry-run with `pixi run validate`.

The real gold set (`validation/goldset/`, `origin: blind_human`) is produced by blind expert rating
under `validation/protocol.md` at milestone M7 — it does not exist yet.
