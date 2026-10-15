# Farrum Agent Security Demo

## Run

```text
python -m trusted_execution.public_demo
```

Python 3.9+ is required. There are no third-party dependencies, credentials,
API keys, paid services, or external requests. The command runs from this
repository alone and stores scenario state only in temporary SQLite files.

## Expected result

The demonstration runs three fixed cases:

1. A forbidden `charge` proposal is denied, with zero protected mock writes.
2. An allowed `refund` proposal executes once against the local mock provider
   and is verified by reading the provider's independent simulated ledger.
3. A `refund` approved under a maximum of 200 is rejected after the current
   maximum changes to 100. Audit evidence records the execution-time policy
   rejection, with zero protected mock writes.

The console report shows each proposal, the decision and denial reason, call
count, verification result, and audit trail. A successful run ends with:

```text
Result: 3/3 scenarios passed; 0 failed.
```

## Architecture and limitations

The standalone package contains the existing execution engine, policy,
SQLite audit store, and simulated provider needed for the demo. Each scenario
uses fresh temporary state. The test suite also verifies that denied cases
never call the provider and that `urllib.request.urlopen` is never called.

This illustrates one local policy-enforcement boundary; it is not universal
agent security. It does not provide authenticated human approvals, process
isolation, protection from arbitrary code or alternate tools in the same
process, or a production authorization guarantee. The mock provider is not a
real external service. No GitHub or LLM client is included.

Run tests without installing packages:

```text
python -m unittest discover -s tests -v
```
