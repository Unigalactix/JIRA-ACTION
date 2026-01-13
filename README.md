# Jira Autopilot & GitHub Automation Service 🚀

A comprehensive Python automation service that bridges Jira and GitHub. It acts as an autonomous agent that polls Jira for tickets, intelligently detects project requirements (Language, Repo), and generates remote CI/CD workflows via GitHub Pull Requests.

## Features ✨

*   **Autopilot Polling**: Automatically polls Jira every 60 seconds for new tickets.
*   **Dynamic Project Discovery**: Automatically detects all available Jira projects (no need to hardcode keys).
*   **Smart Language Detection**: Automatically parsing repository files to detect the tech stack:
    *   `package.json` → **Node.js**
    *   `*.csproj` / `*.sln` → **.NET**
    *   `requirements.txt` → **Python**
    *   `pom.xml` / `build.gradle` → **Java**
*   **Priority Queue**: Processes tickets based on Priority (Highest → Lowest).
*   **Stable PR Workflow**: Creates specific feature branches (`feature/copilot-{repo}`) and opens Pull Requests.
*   **Live Dashboard**: Real-time UI at `http://localhost:8000` showing:
    *   Active Queue & History
    *   **Live CI/CD Checks**: See the status of checks (e.g., "Build", "Tests") on the cards directly.
    *   Quick Links to Jira Tickets and GitHub PRs.
*   **Copilot Sub-PR Management**: Detects, un-drafts, and auto-merges Pull Requests created by `@copilot`.
*   **mcp-server**: Built-in Model Context Protocol server for AI Agents (VS Code Copilot, Claude Desktop, etc.).
*   **Security**: Integrated CodeQL scans.
*   **Dynamic Branching**: Automatically detects standard branches (`main`, `master`, `dev`).
*   **Container Ready**: Generates `Dockerfile` for all deployments.
*   **Persistent Logging**: Server activity is logged to console and system status.

## Prerequisites

*   **Python** (v3.8 or higher)
*   **Jira Account** (Cloud) with an API Token.
*   **GitHub Account** with a Personal Access Token having `repo`, `workflow`, and `read:user` scopes.

## Setup & Installation

1.  **Clone the repository**:
    
    ```bash
    git clone https://github.com/Unigalactix/JIRA-ACTION.git
    cd JIRA-ACTION
    ```

2.  **Install dependencies**:
    
    ```bash
    cd copilot_agent
    pip install -r requirements.txt
    ```

3.  **Configure Environment**: Create a `.env` file in the `copilot_agent` directory:
    
    ```bash
    GHUB_TOKEN=ghp_your_github_token_here
    GHUB_ORG=YourOrgName
    JIRA_BASE_URL=https://your-domain.atlassian.net
    JIRA_USER_EMAIL=your-email@example.com
    JIRA_API_TOKEN=your_jira_api_token
    JIRA_PROJECT_KEYS=PROJ,ECT
    DEFAULT_REPO=YourOrg/default-repo
    PORT=8000
    ```

## Usage

### Run Locally

```bash
cd copilot_agent
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

*   **Dashboard**: `http://localhost:8000`
*   **API Docs**: `http://localhost:8000/docs`
*   **Health Check**: `http://localhost:8000/health`

### Run with Docker 🐳

Build and run the containerized application:

```bash
docker build -t jira-automation-python .
docker run -p 8000:8000 --env-file copilot_agent/.env jira-automation-python
```

### Running Tests

Execute the tests:

```bash
cd copilot_agent
pytest
```

## Enhanced Atlassian Integration (Side-by-Side)

We support running the official `sooperset/mcp-atlassian` server alongside our agent to provide deep Jira/Confluence features to your AI assistant.

### Prerequisites
- **uv**: A fast Python package installer. [Install uv](https://github.com/astral-sh/uv)
- **VS Code**: With GitHub Copilot Chat extension installed.

### Setup Instructions

1.  **Configure Credentials**
    Ensure your `copilot_agent/.env` file has the following variables:
    ```bash
    JIRA_BASE_URL=https://your-domain.atlassian.net
    JIRA_USER_EMAIL=your-email@example.com
    JIRA_API_TOKEN=your-jira-token
    ```

2.  **Generate Configuration**
    Run the helper script to generate the config block for VS Code:
    ```bash
    python temp/generate_mcp_config.py
    ```

3.  **Apply Configuration**
    - Copy the JSON output from the script.
    - Open VS Code Settings.
    - Search for "MCP Settings" or edit the `vs-code-mcp-settings.json` file directly (location depends on your OS/Extension version).
    - Paste the configuration into the `mcpServers` object.

4.  **Verify**
    Restart VS Code or the Copilot Chat extension. You should now be able to ask Copilot things like:
    - *"List all high priority bugs"* (using the advanced Atlassian filtering)

## CI/CD Workflow Features
This agent supports a **Single Feature Branch** workflow with **Docker Integration**.

- **Workflow**: All automated changes are committed to `feature/copilot-{repo}`.
- **Docker**: Automatically generates `Dockerfile` for your project (Node.js, Python, .NET, Java) and builds it in CI.
- **Deployment**: Defaults to GitHub Pages but supports Azure Web Apps.
- **API Endpoints**:
    - `POST /generate`: Scaffolds the entire CI/CD pipeline + Dockerfile.
    - `POST /autofix`: Applies automated fixes from Jira tickets to the feature branch.
    - `POST /webhook`: Receives webhook events for automated processing.
    - `GET /api/status`: Returns current system status for dashboard.

## Architecture

The service follows an event-driven architecture:

### Workflow Diagram

```
User Creates Ticket in Jira
    ↓
Autopilot Scans for New Tickets (60s interval)
    ↓
Analyzes Ticket & Detects Repository/Language
    ↓
Checks if Workflow Already Exists
    ↓ (if not exists or needs fix)
GitHub Copilot: Writes Code & Creates PR
    ↓
CI/CD Pipeline Runs Tests
    ↓ (on success)
Autopilot: Auto-approves & Enables Auto-merge
    ↓
PR Gets Merged Automatically
    ↓
Webhook Updates Jira → Ticket Moved to Done
```

## Dashboard Features

The live dashboard shows:

- **Current Phase**: Scanning, Processing, or Waiting
- **Active Queue**: All tickets currently being processed
- **Current Ticket**: Detailed logs for the ticket being processed
- **Monitored PRs**: All PRs being watched with their CI check status
- **Recent History**: Last 10 processed tickets with success/failure status

## Configuration: Per-board Post-PR Status

You can configure a per-board (project) status that the service will transition Jira tickets to after a PR is created or verified. Create `config/board_post_pr_status.json` with a JSON object mapping project keys to desired status. Example:

```json
{
    "NDE": "In Review",
    "MKT": "In Development",
    "OPS": "In Progress"
}
```

## License

MIT
