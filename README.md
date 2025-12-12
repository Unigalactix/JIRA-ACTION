# Copilot Agent & Jira Integration

This project implements a GitHub Copilot Agent capable of interacting with Jira.

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
This agent now supports a **Single Feature Branch** workflow with **Docker Integration**.

- **Workflow**: All automated changes are committed to `feature/copilot-{repo}`.
- **Docker**: Automatically generates `Dockerfile` for your project (Node.js, Python, .NET, Java) and builds it in CI.
- **Deployment**: Defaults to GitHub Pages but supports Azure Web Apps.
- **Commands**:
    - `POST /generate`: Scaffolds the entire CI/CD pipeline + Dockerfile.
    - `POST /autofix`: Applies automated fixes from Jira tickets to the feature branch.
