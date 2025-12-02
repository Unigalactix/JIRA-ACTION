# Governance & Security Ruleset (Guide)

This repository includes baseline governance and security automation.

## Branch Protection & Reviews
- Protect `main` with required PR reviews and status checks.
- Enforce signed commits and disallow force pushes.
- Require up-to-date branches before merging.

## Automated Security
- CodeQL scanning (`.github/workflows/codeql.yml`).
- Dependabot updates (`.github/dependabot.yml`).
- Enable secret scanning and Dependabot security updates in repo settings.

## CI Quality Gates (Recommended)
- Linting, unit tests, and coverage thresholds in workflows.
- Optional SAST / DAST tools depending on stack.

## AI Usage Guidelines
- Limit AI tools to non-sensitive code paths or use redaction.
- Log AI-generated changes and require reviewer approval.
- Avoid sending secrets, PII, or proprietary data to external models.

## Next Steps
- Add GitHub Rulesets (Org/Repo settings) to enforce checks.
- Expand CodeQL languages as the stack grows.
- Add Docker image scanning if containers are used.
