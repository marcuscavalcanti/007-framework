# Pilot report: stopped early by the provider's rate limit (2026-11-12)

## Run
- **Start:** 2026-11-12T18:48:40Z, after `dry_run_v3.py` passed all nine checks.
- **What ran:** `run_pilot_v4.sh` at 2 jobs (Amendments 5 to 8), on the pinned v1.7.0 code. The pilot set's SHA-256 is
  `1eaa2df0…`, there were 248 planned cells, and the Codex CLI was 0.160.1.
- **Stop:** `invalid-budget` at 2026-11-12T20:07:59Z, after 64 calls: 38 valid and 26 invalid. The budget was 10% of 248, that is 25.
- **The 26 invalid cells** all failed the same way.
  - **The error:** the agent exited with code 1. The native runner classed every one as `native-error-rate-limit`, in both arms.
  - **When:** every call that finished from 20:00:49Z on was refused. The last valid cell finished at 19:59:21Z.
- **Spend:**
  - **Measured:** US$7.10 at list price, the sum of the costs of the valid cells.
  - **Charged by the controller:** US$59.10, because each refused call without a measured cost is charged its US$2 reserve.

## What the pre-registration says, applied as written
- **PREREG-PILOT:** an early stop is reported, nothing is frozen, and the next step goes back to the maintainer.
- **DECISIONS.md, part 1:** a failure after the first paid attempt is final. No attempt is redone, and no later release reopens this
  question: this executor, this margin, these repositories.
- **The answer** (DECISIONS.md parts 5 and 6): **NO, reason NO-STOPPED, cause: the provider (rate limit).** It reads "not shown". It
  says nothing about whether the lower effort pays.

## Disclosure
- **What was looked at:** to diagnose the stop, the operator (Claude) printed the median cost and agent time of the valid cells per
  repository and arm. That is a secondary measure.
- **What was not looked at:** no pass share or acceptance per arm. Nothing was frozen or analysed. The 38 valid cells stay as they
  are, with their hashes, and enter no analysis.

## For the instrument
- A provider rate limit is an outage that hits both arms alike. It is not a failed attempt.
- 1.7.0 and 1.8.0 count it toward the invalid budget, so a short outage ends a paid study.
- A later release should pause the run on `native-error-rate-limit`, as a planned stop, instead of spending cells. Any further study
  should pre-register that handling.

## Addendum (2026-11-12, maintainer)
- **Cause of the refusals:** the ChatGPT account's Codex quota was exhausted. It was not a short outage. The answer stays NO-STOPPED
  with the provider as cause.
- **What follows:** Codex studies wait until the quota is back ([PROGRAM.md](../PROGRAM.md)).
