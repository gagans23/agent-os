---
name: write-unit-tests
description: Write focused unit tests for a function or module, covering happy path, edges, and failure modes.
triggers: [write, unit, tests, test, coverage, pytest, cases, testing]
---

## Procedure
1. Identify the unit under test and its observable contract: inputs, outputs,
   side effects, and raised errors.
2. Enumerate cases: **happy path**, **boundaries** (empty, zero, max, off-by-one),
   **invalid input / error paths**, and any **state/idempotency** concerns.
3. Write one small, independent, deterministic test per case — descriptive name,
   arrange/act/assert, no hidden coupling between tests.
4. Assert on behavior and public outputs, not on private internals.
5. Match the project's framework and conventions (e.g. pytest); keep fixtures minimal.
6. List any case you could NOT test and why (e.g. needs a real network/credential).

## Pitfalls
- Don't test the implementation's internals — tests should survive a refactor.
- Avoid nondeterminism (time, randomness, network); inject or fake it.
- One behavior per test; don't pile unrelated assertions into one case.
- Don't fabricate a passing result — tests must actually be runnable.

## Verification
- Each test is independent and deterministic, with a clear name.
- Happy path, at least one boundary, and at least one error case are covered.
- Tests assert public behavior and would catch the bug they target.
