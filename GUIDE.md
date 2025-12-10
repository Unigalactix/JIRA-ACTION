# Copilot Agent: End-to-End Setup Guide (Windows PowerShell)

This guide walks you through preparing GitHub + Jira, running the agent locally, testing the webhook, and optional deployment. Commands are PowerShell-ready.

## 1. Prerequisites
- Python 3.10+ installed and available in PATH
- GitHub Personal Access Token with `repo` scope
- Jira Cloud/API credentials
- Optional: ngrok for local tunnel; Azure App Service for deployment

## 2. Configure secrets
Create a `.env` file in the project root with:
```
GHUB_TOKEN=<your-github-pat>
JIRA_BASE_URL=https://<your-domain>.atlassian.net
JIRA_USER_EMAIL=<your-email>
JIRA_API_TOKEN=<your-jira-api-token>
```
For Azure Web Apps deployment, add this repo secret in the target GitHub repository:
- `AZURE_PUBLISH_PROFILE` (content of the publish profile XML)

## 3. Install & run locally
From the project root:
```powershell
pip install -r "c:\Users\RajeshKodaganti(Quad\Downloads\GITHUB\JIRA-ACTION\copilot_agent\requirements.txt"
$env:PYTHONPATH = "$PWD"; python -m uvicorn copilot_agent.app:app --reload --port 3000
```
The agent serves `POST /webhook`.

## 4. Optional: expose locally via ngrok
```powershell
ngrok http 3000
```
Use the generated URL for Jira Automation, e.g., `https://<ngrok-id>.ngrok.io/webhook`.

## 5. Create Jira Automation
- Trigger: Issue transitioned/updated (your choice)
- Action: Send web request (POST) to `https://<ngrok-id>.ngrok.io/webhook`
- Headers: `Content-Type: application/json`
- Body (JSON):
```
{
  "issueKey": "KAN-1",
  "repository": "<owner>/<repo>",
  "language": "node",
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployTarget": "azure-webapps"
}
```

## 6. Test the webhook locally
```powershell
$body = '{
  "issueKey": "PROJ-123",
  "repository": "<owner>/<repo>",
  "language": "node",
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployTarget": "azure-webapps"
}'

curl -Method POST -Uri "http://localhost:3000/webhook" -ContentType "application/json" -Body $body
```
Expected results:
- New branch: `add-ci-<repo>-<timestamp>-<uuid8>` in the target repo
- PR opened to `main`
- Jira comment with commit/PR URLs (if `issueKey` provided)

## 7. CLI alternative
You can run the agent via CLI without Jira:
```powershell
python copilot_agent/app.py <owner>/<repo> node "npm run build" "npm test" azure-webapps --issueKey KAN-1
```

## 8. Governance essentials
- Enable branch protection on `main` (require PR review + status checks)
- Ensure repo secrets present (`AZURE_PUBLISH_PROFILE` if deploying)
- Confirm CodeQL + Dependabot are active (check Actions + Security tabs)

## 9. Workflow tuning
- `language`: one of `node | python | dotnet | java`
- Provide accurate `buildCommand` and `testCommand`
- Ensure generated workflow includes build, unit tests, lint, SAST, and SonarQube gates

## 10. Deploy the agent (optional)
Azure App Service:
```powershell
# Configure App Settings: GHUB_TOKEN, JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN
# Startup command (in Azure):
uvicorn copilot_agent.app:app --host 0.0.0.0 --port 8000
```
Set Jira Automation webhook to: `https://<your-app>.azurewebsites.net/webhook`.

## 11. Prevent duplicate PRs (optional)
- Use deterministic branch names (e.g., `add-ci-<issueKey>`) per issue
- Before creating, check for an open PR referencing the same `issueKey` and reuse it

## 12. Optional enhancements
- Validate Jira webhook signatures or use a shared secret
- Add labels/reviewers in PR creation (extend `lib.github.create_pull_request`)
- Use `repository_dispatch` for decoupled automation and audit trail
- Add structured logs for an audit trail
- Add post-merge CD job (Azure Web Apps or GitHub Pages) in the generated workflow

## 13. Troubleshooting
- 401/403 from GitHub: verify `GITHUB_TOKEN` scope and repo access
- PR not created: check default branch is `main` and permissions
- Jira comment missing: ensure `issueKey` was provided and Jira creds valid
- Local errors: run with `--reload` to see stack traces; verify `.env` loaded