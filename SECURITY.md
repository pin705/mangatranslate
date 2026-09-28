# Security Policy

## Reporting a vulnerability

Please do **not** open a public GitHub issue for anything you believe is a security problem.

Preferred channel: GitHub's private vulnerability reporting — open the repository's **Security** tab and choose
**Report a vulnerability**. That keeps the report, discussion and fix coordinated until a patch is released.

Include what you can of:

- the affected component (`apps/web`, `services/api`, `services/worker`, `infra`) and, if possible, the commit;
- a description of the issue and its impact;
- step-by-step reproduction or a proof of concept;
- any suggested fix (optional).

## What to expect

- Acknowledgement within **7 days**.
- An assessment and, where confirmed, a coordinated fix or mitigation. We aim to release patches within **90
  days**, sooner for actively exploited classes.
- Public credit in the release notes if you want it — say so in your report.

## Scope

**In scope:** code in this repository and the deployment configuration it ships with (`infra/`).

**Out of scope:** volumetric or denial-of-service attacks, social engineering, attacks against third-party
services (AI providers, payOS, Cloudflare, SMTP relay) rather than this software, and anything requiring access
to a user's own account or device.

## Supported versions

Only the latest `main` branch and the container images built from it (`ghcr.io/<owner>/<repo>/{api,worker,web}`)
receive security fixes. If you run an older checkout, update before reporting.

## Already implemented

The implemented controls — session handling, upload hardening, CSP, rate limits, audit logging, secret
management — are documented in [docs/SECURITY.md](docs/SECURITY.md).
