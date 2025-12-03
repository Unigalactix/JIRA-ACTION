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

### CLI usage

You can also run the agent without the webhook and directly create a branch + PR:

```
python app.py owner/repo node "npm run build" "npm test" azure-webapps --issueKey PROJ-123
```

Requires environment variables set (see below). The CLI prints the commit and PR URLs and, when `--issueKey` is provided, posts a Jira comment.

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
 - Set GitHub repo secret `COPILOT_AGENT_URL` for the `Trigger Copilot Agent` workflow.

## GitHub Actions

This repository includes two workflows:

- `.github/workflows/ci.yml`: Lints (ruff), runs Bandit security scan, and executes pytest on `copilot_agent` when PRs or pushes target `main`.
- `.github/workflows/trigger-agent.yml`: Manual dispatch that posts a JSON payload to the agent's `/webhook`. Configure `COPILOT_AGENT_URL` repo secret to point to your running agent (e.g., `https://server:3000`).

### Starting the agent

```
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 3000
```

### Example Jira Automation rule

Use a "Send web request" action to POST to your agent:

```
POST https://your-agent-host:3000/webhook
Content-Type: application/json

{
  "issueKey": "{{issue.key}}",
  "repository": "owner/repo",
  "language": "node",
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployTarget": "azure-webapps"
}
```

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
