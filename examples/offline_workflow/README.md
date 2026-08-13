# Offline completed-export workflow

Install the Cernora wheel, then run:

```sh
python -m cernora.examples.offline_workflow /tmp/cernora-offline-example
```

The example reads only wheel resources and local ordinary files. It performs no network,
credential, agent-runtime, registry, or repository access. The printed outcome is `pass`.

The completed export is a packaged synthetic fixture. This example exercises Cernora’s
evaluation-core path; it does not launch an Agent, create a sandbox or capture a runtime
receipt.

`run.py` is the equivalent source-repository wrapper for readers who want to inspect the
minimal call site; it is not needed after wheel installation.
