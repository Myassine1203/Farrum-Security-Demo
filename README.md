# Farrum Agent Security Demo

A reproducible, local demonstration of policy enforcement around a simulated
agent action. It uses the Python standard library only and does not connect to
GitHub, an LLM provider, or any other external service.

## Requirements and quick start

- Python 3.9 or newer
- No installation or API keys required

From this directory, run:

```text
python -m trusted_execution.public_demo
```

The command uses temporary SQLite files and cleans them up after each
scenario. It does not read credentials or require network access.

## Demonstrated scenarios

1. **Unauthorized proposal:** `charge(amount=25)` is rejected because the
   policy permits only `refund`. The protected mock provider has zero calls.
2. **Authorized proposal:** `refund(amount=25)` is permitted, executed once
   using the local mock provider, and verified by reading its separate
   simulated outcome ledger.
3. **Authorization-context regression:** `refund(amount=150)` is approved
   while the limit is 200, then denied when the execution-time limit becomes
   100. The audit log explains the denial and the mock provider has zero calls.

Each run prints the proposal, policy decision, mock write-attempt count,
read-back result, and audit events. Expected final line:

```text
Result: 3/3 scenarios passed; 0 failed.
```

## Tests

The tests use Python's built-in `unittest`; there are no test dependencies:

```text
python -m unittest discover -s tests -v
```

The tests confirm the denial cases make no protected mock-provider calls and
the demo makes no HTTP request.

## What this demonstrates—and does not

The demo reuses the local execution engine's policy check, execution-time
revalidation, audit events, and separate mock-provider ledger. This is
**mock-provider enforcement**, not a real refund, GitHub write, or proof of
universal AI-agent security.

It does not authenticate approvers, isolate hostile code running in the same
process, prove resistance to alternate tool/credential access, or provide a
production authorization system. No AI model is called. The separate
GitHub/OpenAI integrations from the development repository are not included
in this standalone demo.
