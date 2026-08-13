# Coding task completed-export example

Run one deterministic, offline example from an installed Cernora wheel:

```sh
python -m cernora.examples.coding_task ./coding-run backend-v1
```

Valid case IDs are `backend-v1`, `frontend-v1`, and `fail-closed-v1`. The output directory
must not already exist. A successful run prints `pass` after Bundle v2 import, evaluation,
and strict persisted-result reload.

Candidates and completed exports are packaged synthetic fixtures. The example does not run
candidate code or an Agent, create a sandbox, capture runtime observations or validate an
Experiment Harness.
