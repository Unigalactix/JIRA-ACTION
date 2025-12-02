# Copilot Agent (Python)

Automates CI/CD workflow creation in GitHub based on Jira tickets. Exposes a FastAPI webhook that receives Jira Automation payloads, generates a GitHub Actions workflow, commits it on a new branch, and posts a comment back to the Jira issue.

## Project Structure

```
copilot_agent/
├─ app.py
├─ requirements.txt
├─ lib/
│  ├─ workflow_factory.py
│  ├─ github.py
│  └─ jira.py
```

## Environment Variables

Set these in your environment or via a `.env` loader:

```
GITHUB_TOKEN=<your-github-token>
JIRA_BASE_URL=https://yourtenant.atlassian.net
JIRA_USER_EMAIL=automation-bot@yourcompany.com
JIRA_API_TOKEN=<jira-api-token>
```

## Install & Run

```
pip install -r requirements.txt
uvicorn app:app --reload --port 3000
```

## Webhook

POST to `/webhook` with JSON body like:

```
{
  "issueKey": "PROJ-123",
  "repository": "owner/repo",
  "language": "node",
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployTarget": "azure-webapps"
}
```

## Notes
- Requires default branch `main` in the target repo.
- Commits workflow to `.github/workflows/<repo>-ci.yml` on a newly created branch `add-ci-<timestamp>`.
- Jira comment includes the commit URL.
 - `.env` is loaded automatically via `python-dotenv`.

## Flow Chart

```mermaid
flowchart TD
  A[Jira Automation Webhook]\nPOST /webhook --> B[Parse Payload]
  B --> C{Validate Fields}
  C -- missing repo/language --> E[Return error]
  C -- ok --> D[Generate Workflow YAML]
  D --> F[Get repo main SHA]
  F --> G[Create branch add-ci-<timestamp>]
  G --> H[Commit .github/workflows/<repo>-ci.yml]
  H --> I[Push commit]
  I --> L[Create PR to main]
  L --> J[Post Jira comment with commit & PR URLs]
  L --> N[CI/CD runs on PR]
  N --> O[Merge & Deploy]
```
