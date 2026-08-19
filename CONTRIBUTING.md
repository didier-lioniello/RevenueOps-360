# Contributing

Contributions that improve formula clarity, validation, accessibility, or deterministic testing are
welcome.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest
python -m build --wheel --no-isolation
python -m pip_audit -r requirements-dev.txt --strict
python -m revenueops build-site --output-dir docs
git diff --exit-code -- docs
```

When a development dependency changes, edit `requirements-dev.in` and regenerate the checked-in
lock with the exact command recorded at the top of `requirements-dev.txt`. Install and audit only
the generated lock.

```bash
pip-compile --allow-unsafe --generate-hashes --resolver=backtracking --strip-extras \
  --output-file=requirements-dev.txt requirements-dev.in
```

The conventional `.in`/`.txt` pair lets Dependabot update the direct constraint and compiled lock
in the same pull request. CI recompiles the lock and rejects any drift.

## Pull requests

- Keep runtime behavior deterministic and standard-library only unless a dependency is justified.
- Add formula and edge-case tests for every analytics change.
- Keep recommendations as explicit rules with evidence paths; do not add an LLM.
- Update the README and generated demo when inputs, formulas, or output fields change.
- Use only fictional, explicitly labeled synthetic data. The attestation fields are not PII or
  secret detection; never add customer exports, PII, credentials, or private product details.
- Do not describe this repository as production-ready and do not turn scenario outputs into promises.

Contributions are licensed under the MIT License.
