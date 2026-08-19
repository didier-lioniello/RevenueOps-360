# Security policy

## Supported scope

This repository is a deterministic reference demonstration, not a hosted service. Reports are
accepted for the current `main` branch. No response SLA is promised.

## Reporting

Use the repository **Security** tab and **Report a vulnerability** to open a private advisory. If
private reporting is unavailable, open a minimal public issue requesting a private contact channel;
do not publish exploit details or sensitive data.

Include the affected file, impact, reproduction conditions, and a suggested mitigation when
available.

## Data boundary

The engine requires an explicit operator attestation: `metadata.synthetic` must be exactly `true`,
the label must say synthetic, and opportunity IDs must use the `SYN-OPP-*` fixture namespace. These
markers are not evidence that data is safe. The engine does **not** detect, redact, or anonymize PII,
customer data, secrets, or confidential text.

Do not use customer exports, CRM records, names, emails, company identifiers, credentials, or other
confidential information in issues, tests, examples, or reports. Unknown input fields are rejected,
but accepted aggregate fields are repeated in generated JSON and HTML and must still be handled
accordingly outside this demo.
