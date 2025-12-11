from fastapi import FastAPI, Request
from copilot_agent.lib.workflow_factory import generate_workflow
from copilot_agent.lib.config_helper import generate_vs_code_config
from pathlib import Path
from copilot_agent.lib.github import commit_workflow, create_pull_request, apply_text_patches, post_pr_comment, create_copilot_issue
from copilot_agent.lib.jira import post_jira_comment, transition_issue, get_issue_details, search_issues
from copilot_agent.lib.logger import setup_logger
import os
import time
import uuid
from dotenv import load_dotenv
import json
import base64
import requests

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = setup_logger("app")
app = FastAPI()

@app.on_event("startup")
def startup_event():
    logger.info("Starting Copilot Agent...")
    
    # Auto-generate MCP Config for visibility
    try:
        root_dir = Path(__file__).parent.parent
        config = generate_vs_code_config(root_dir)
        if "error" not in config:
            logger.info("----------------------------------------------------------------")
            logger.info("MCP CONFIGURATION (Copy to VS Code settings.json):")
            logger.info(json.dumps(config, indent=2))
            logger.info("----------------------------------------------------------------")
    except Exception as e:
        logger.warning(f"Failed to generate MCP config on startup: {e}")

@app.get("/health")
def health():
    logger.info("Health check requested")
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    try:
        data = await req.json()
        logger.info(f"Received webhook: {json.dumps(data)}")
        issue_key = data.get("issueKey")
        repository = data.get("repository")
        language = data.get("language")
        build_cmd = data.get("buildCommand")
        test_cmd = data.get("testCommand")
        deploy_target = data.get("deployTarget")

        if not repository or not language:
            logger.error("Missing required fields: repository, language in webhook payload")
            return {"status": "error", "message": "Missing required fields: repository, language"}

        # ---------------------------------------------------------
        # 1. Fetch Jira Issue Context
        # ---------------------------------------------------------
        summary = f"Task for {issue_key}"
        description = ""
        if issue_key:
            try:
                details = get_issue_details(issue_key)
                summary = details.get("summary") or summary
                description = details.get("description") or ""
            except Exception as e:
                logger.warning(f"Failed to fetch Jira details for {issue_key}: {e}")

        owner, repo = repository.split("/")

        # ---------------------------------------------------------
        # 2. Trigger Copilot Agent (Native)
        # ---------------------------------------------------------
        # Create a GitHub Issue assigned to @copilot
        copilot_issue_info = {"issue_url": "skipped", "issue_number": -1}
        try:
            copilot_issue_info = create_copilot_issue(owner, repo, issue_key, summary, description)
            logger.info(f"Created Copilot Issue: {copilot_issue_info['issue_url']}")
        except Exception as e:
            logger.error(f"Failed to create Copilot Issue: {e}")

        # ---------------------------------------------------------
        # 3. Create CI/CD Pipeline (Standard)
        # ---------------------------------------------------------
        # NOTIFY: Copilot assigned
        if issue_key and copilot_issue_info.get("issue_url") != "skipped":
            try:
                post_jira_comment(
                    issue_key, 
                    "Copilot Agent has been assigned to fix the code.",
                    link_text="Tracking Issue",
                    link_url=copilot_issue_info["issue_url"]
                )
            except Exception as e:
                logger.warning(f"Failed to post Jira comment about Copilot assignment for {issue_key}: {e}")

        workflow_content = generate_workflow(repository, language, build_cmd, test_cmd, deploy_target)
        branch = f"add-ci-{repo}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        commit_info = commit_workflow(owner, repo, branch, workflow_content, issue_key=issue_key)
        pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)

        # ---------------------------------------------------------
        # 3.5 Trigger Copilot via PR Comment
        # ---------------------------------------------------------
        try:
            copilot_prompt = (
                f"@copilot please review this PR and fix any issues.\n\n"
                f"**Task**: {summary}\n"
                f"**Description**: {description}\n"
                f"**Jira Issue**: {issue_key}"
            )
            post_pr_comment(owner, repo, pr_info["pr_number"], copilot_prompt)
            logger.info(f"Posted Copilot comment on PR {pr_info['pr_url']}")
        except Exception as e:
            logger.warning(f"Failed to post Copilot comment on PR {pr_info['pr_url']}: {e}")

        # ---------------------------------------------------------
        # 4. Feedback to Jira - Granular Updates
        # ---------------------------------------------------------
        if issue_key:
            # NOTIFY: CI Created
            try:
                post_jira_comment(
                    issue_key, 
                    f"CI/CD Pipeline created at {repo}-ci.yml.",
                    link_text="Commit",
                    link_url=commit_info["commit_url"]
                )
                logger.info(f"Posted Jira comment about CI creation for {issue_key}")
            except Exception as e:
                logger.warning(f"Failed to post Jira comment about CI creation for {issue_key}: {e}")
            
            # NOTIFY: PR Opened
            try:
                post_jira_comment(
                    issue_key, 
                    "Pull Request opened for review.",
                    link_text="View PR",
                    link_url=pr_info["pr_url"]
                )
                transition_issue(issue_key, "In Review")
                logger.info(f"Posted Jira comment and transitioned {issue_key} to 'In Review'")
            except Exception as e:
                logger.warning(f"Failed to post Jira comment or transition {issue_key} for PR: {e}")

        return {
            "status": "success",
            "copilot_issue": copilot_issue_info.get("issue_url"),
            "ci_pr": pr_info["pr_url"]
        }
    except Exception as e:
        logger.exception("Error in webhook processing:")
        return {"status": "error", "message": str(e)}

@app.post("/generate")
async def generate_pipeline(req: Request):
    try:
        data = await req.json()
        logger.info(f"Received generate request: {json.dumps(data)}")
        issue_key = data.get("issueKey")
        repository = data.get("repository")
        language = data.get("language")
        build_cmd = data.get("buildCommand")
        test_cmd = data.get("testCommand")
        deploy_target = data.get("deployTarget")

        if not repository or not language:
            logger.error("Missing required fields: repository, language in generate payload")
            return {"status": "error", "message": "Missing required fields: repository, language"}

        # ---------------------------------------------------------
        # 1. Fetch Jira Issue Context (if issue_key provided)
        # ---------------------------------------------------------
        summary = f"Task for {issue_key}" if issue_key else "CI/CD Pipeline Generation"
        description = ""
        if issue_key:
            try:
                details = get_issue_details(issue_key)
                summary = details.get("summary") or summary
                description = details.get("description") or ""
            except Exception as e:
                logger.warning(f"Failed to fetch Jira details for {issue_key}: {e}")

        owner, repo = repository.split("/")

        # ---------------------------------------------------------
        # 2. Create CI/CD Pipeline
        # ---------------------------------------------------------
        workflow_content = generate_workflow(repository, language, build_cmd, test_cmd, deploy_target)
        branch = f"add-ci-{repo}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        commit_info = commit_workflow(owner, repo, branch, workflow_content, issue_key=issue_key)
        pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)
        logger.info(f"Generated workflow, committed to {commit_info['commit_url']}, and opened PR {pr_info['pr_url']}")

        # ---------------------------------------------------------
        # 2.5 Trigger Copilot via PR Comment (if issue_key provided)
        # ---------------------------------------------------------
        if issue_key:
            try:
                copilot_prompt = (
                    f"@copilot please review this PR and fix any issues.\n\n"
                    f"**Task**: {summary}\n"
                    f"**Description**: {description}\n"
                    f"**Jira Issue**: {issue_key}"
                )
                post_pr_comment(owner, repo, pr_info["pr_number"], copilot_prompt)
                logger.info(f"Posted Copilot comment on PR {pr_info['pr_url']}")
            except Exception as e:
                logger.warning(f"Failed to post Copilot comment on PR {pr_info['pr_url']}: {e}")

        # ---------------------------------------------------------
        # 3. Feedback to Jira - Granular Updates (if issue_key provided)
        # ---------------------------------------------------------
        if issue_key:
            try:
                post_jira_comment(
                    issue_key, 
                    f"CI/CD Pipeline created at {repo}-ci.yml.",
                    link_text="Commit",
                    link_url=commit_info["commit_url"]
                )
                logger.info(f"Posted Jira comment about CI creation for {issue_key}")
            except Exception as e:
                logger.warning(f"Failed to post Jira comment about CI creation for {issue_key}: {e}")
            
            try:
                post_jira_comment(
                    issue_key, 
                    "Pull Request opened for review.",
                    link_text="View PR",
                    link_url=pr_info["pr_url"]
                )
                transition_issue(issue_key, "In Review")
                logger.info(f"Posted Jira comment and transitioned {issue_key} to 'In Review'")
            except Exception as e:
                logger.warning(f"Failed to post Jira comment or transition {issue_key} for PR: {e}")

        return {
            "status": "success",
            "ci_pr": pr_info["pr_url"]
        }
    except Exception as e:
        logger.exception("Error in generate pipeline processing:")
        return {"status": "error", "message": str(e)}

@app.post("/issues")
async def list_issues(req: Request):
    """List Jira issues using JQL and env credentials."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    jql = data.get("jql") or "project = D2 AND statusCategory != Done ORDER BY priority DESC, updated DESC"
    max_results = int(data.get("maxResults", 25))

    base_url = os.getenv("JIRA_BASE_URL")
    email = os.getenv("JIRA_USER_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")
    if not base_url or not email or not api_token:
        logger.error("Missing Jira env vars: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")
        return {"status": "error", "message": "Missing Jira env vars: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN"}

    auth = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    try:
        resp = requests.post(
            f"{base_url}/rest/api/3/search",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            data=json.dumps({
                "jql": jql,
                "maxResults": max_results,
                "fields": ["summary", "status", "assignee", "priority"],
            }),
            timeout=30,
        )
        logger.info(f"Jira search request for JQL '{jql}' completed with status {resp.status_code}")
    except Exception as e:
        logger.exception(f"Failed to query Jira with JQL '{jql}':")
        return {"status": "error", "message": f"Failed to query Jira: {e}"}

    if resp.status_code != 200:
        logger.error(f"Jira search returned non-200 status: {resp.status_code}, response: {resp.text}")
        return {"status": "error", "code": resp.status_code, "message": resp.text}

    issues = []
    for i in resp.json().get("issues", []):
        f = i.get("fields", {})
        issues.append({
            "key": i.get("key"),
            "summary": f.get("summary"),
            "status": (f.get("status") or {}).get("name"),
            "priority": (f.get("priority") or {}).get("name"),
            "assignee": (f.get("assignee") or {}).get("displayName"),
            "url": f"{base_url}/browse/{i.get('key')}",
        })
    prio_order = {"Highest":0, "High":1, "Medium":2, "Low":3, "Lowest":4}
    issues.sort(key=lambda x: prio_order.get((x.get("priority") or "Medium"), 2))
    logger.info(f"Found {len(issues)} Jira issues for JQL '{jql}'")
    return {"status": "success", "count": len(issues), "issues": issues}

@app.post("/transition")
async def transition(req: Request):
    data = await req.json()
    issue_key = data.get("issueKey")
    target = data.get("targetStatus")
    logger.info(f"Received transition request for {issue_key} to {target}")
    if not issue_key or not target:
        logger.error("Missing required fields: issueKey, targetStatus for transition")
        return {"status": "error", "message": "Missing required fields: issueKey, targetStatus"}
    try:
        result = transition_issue(issue_key, target)
        logger.info(f"Successfully transitioned {issue_key} to {target}")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.exception(f"Error transitioning issue {issue_key} to {target}:")
        return {"status": "error", "message": str(e)}

@app.post("/transitions")
async def list_transitions(req: Request):
    """List available transitions for a Jira issue to help choose a valid target status."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    issue_key = data.get("issueKey")
    if not issue_key:
        return {"status": "error", "message": "Missing required field: issueKey"}
    try:
        transitions = []
        for t in get_transitions(issue_key):
            name = (t.get("to") or {}).get("name") or t.get("name")
            transitions.append({
                "id": t.get("id"),
                "name": name,
            })
        logger.info(f"Listed {len(transitions)} transitions for {issue_key}")
        return {"status": "success", "transitions": transitions}
    except Exception as e:
        logger.exception(f"Error listing transitions for issue {issue_key}:")
        return {"status": "error", "message": str(e)}
@app.post("/autofix")
async def autofix(req: Request):
    """Parse Jira issue, apply simple text fixes, commit and open PR."""
    data = await req.json()
    repository = data.get("repository")
    issue_key = data.get("issueKey")
    base_branch = data.get("baseBranch", "main")
    logger.info(f"Received autofix request for {repository}, issue {issue_key}")
    if not repository or not issue_key:
        logger.error("Missing required fields: repository, issueKey for autofix")
        return {"status": "error", "message": "Missing required fields: repository, issueKey"}

    owner, repo = repository.split("/")
    details = get_issue_details(issue_key)
    summary = details.get("summary") or "Automated fix"
    description = (details.get("description") or "").strip()

    # Naive instruction parsing: expect lines like 'path=..., find=..., replace=...'
    changes = []
    for line in description.splitlines():
        parts = [p.strip() for p in line.split(",")]
        entry = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                entry[k.strip()] = v.strip()
        if entry.get("path") and (entry.get("find") is not None) and (entry.get("replace") is not None):
            changes.append({"path": entry["path"], "find": entry.get("find", ""), "replace": entry.get("replace", "")})

    if not changes:
        logger.warning(f"No valid change instructions found in Jira description for {issue_key}. Expected 'path=..., find=..., replace=...' lines.")
        return {"status": "error", "message": "No valid change instructions found in Jira description. Expected 'path=..., find=..., replace=...' lines."}

    branch = f"autofix-{issue_key.lower()}-{uuid.uuid4().hex[:8]}"
    try:
        commit_info = apply_text_patches(owner, repo, base_branch, branch, changes, issue_key=issue_key)
        pr = create_pull_request(owner, repo, commit_info["branch"], issue_key)
        logger.info(f"Applied text patches and opened PR {pr['pr_url']} for autofix {issue_key}")
        
        # Trigger Copilot via PR Comment
        try:
            copilot_prompt = (
                f"@copilot please review this auto-fix PR and make further improvements.\n\n"
                f"**Task**: {summary}\n"
                f"**Description**: {description}\n"
                f"**Jira Issue**: {issue_key}"
            )
            post_pr_comment(owner, repo, pr["pr_number"], copilot_prompt)
            logger.info(f"Posted Copilot comment on PR for autofix {issue_key}")
        except Exception as e:
            logger.warning(f"Failed to post Copilot comment on PR for autofix {issue_key}: {e}")

        try:
            post_jira_comment(
                issue_key, 
                f"Opened PR with automated fixes: {summary}",
                link_text="View Auto-Fix PR",
                link_url=pr["pr_url"]
            )
            transition_issue(issue_key, "In Review")
            logger.info(f"Posted Jira comment and transitioned {issue_key} to 'In Review' for autofix PR")
        except Exception as e:
            logger.warning(f"Failed to post Jira comment or transition {issue_key} for autofix PR: {e}")
            pass
        return {"status": "success", "commit_url": commit_info["commit_url"], "pr_url": pr["pr_url"], "branch": commit_info["branch"]}
    except Exception as e:
        logger.exception("Error in autofix processing:")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Copilot Agent CLI")
    parser.add_argument("repository", nargs="?", help="Target repository in owner/repo format")
    parser.add_argument("language", nargs="?", help="Project language (node|python|dotnet|java)")
    parser.add_argument("buildCommand", nargs="?", help="Build command to use")
    parser.add_argument("testCommand", nargs="?", help="Test command to use")
    parser.add_argument("deployTarget", nargs="?", help="Deployment target label")
    parser.add_argument("--issueKey", dest="issueKey", help="Optional Jira issue key")
    parser.add_argument("--list", dest="listIssues", action="store_true", help="List active Jira tickets and select interactively")
    parser.add_argument("--project", dest="projectKey", help="Jira project key (e.g., KAN) for listing")
    parser.add_argument("--selectAll", dest="selectAll", action="store_true", help="Process all listed tickets")

    args = parser.parse_args()
    if args.listIssues:
        project = args.projectKey or "KAN"
        jql = f"project = {project} AND statusCategory != Done ORDER BY priority DESC, updated DESC"
        issues = search_issues(jql, max_results=50)
        if not issues:
            logger.info("No active issues found.")
            raise SystemExit(0)
        prio_order = {"Highest":0,"High":1,"Medium":2,"Low":3,"Lowest":4}
        issues.sort(key=lambda i: prio_order.get((i.get("priority") or "Medium"), 2))
        logger.info("Active Jira issues:")
        for idx, i in enumerate(issues, start=1):
            logger.info(f"{idx}. {i['key']} [{i.get('priority')}] - {i['summary']}")
        if args.selectAll:
            selected = list(range(1, len(issues)+1))
        else:
            try:
                sel = input("Select issue number(s) (comma-separated): ").strip()
                selected = [int(s) for s in sel.split(",") if s.strip().isdigit()]
            except Exception:
                logger.error("Invalid selection")
                raise SystemExit(1)
        for s in selected:
            if s < 1 or s > len(issues):
                continue
            issue_key = issues[s-1]["key"]
            owner, repo = (args.repository or "Unigalactix/DEMOGITCOP").split("/")
            details = get_issue_details(issue_key)
            summary = details.get("summary") or "Automated fix"
            description = (details.get("description") or "").strip()
            changes = []
            for line in description.splitlines():
                parts = [p.strip() for p in line.split(",")]
                entry = {}
                for p in parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        entry[k.strip()] = v.strip()
                if entry.get("path") and (entry.get("find") is not None) and (entry.get("replace") is not None):
                    changes.append({"path": entry["path"], "find": entry.get("find", ""), "replace": entry.get("replace", "")})
            if not changes:
                logger.warning(f"No valid change instructions found for {issue_key}; skipping.")
                continue
            branch = f"autofix-{issue_key.lower()}-{uuid.uuid4().hex[:8]}"
            try:
                commit_info = apply_text_patches(owner, repo, "main", branch, changes, issue_key=issue_key)
                pr = create_pull_request(owner, repo, commit_info["branch"], issue_key)
                logger.info(f"Opened PR: {pr['pr_url']} for {issue_key}")

                # Trigger Copilot via PR Comment
                try:
                    copilot_prompt = (
                        f"@copilot please review this auto-fix PR and make further improvements.\n\n"
                        f"**Task**: {summary}\n"
                        f"**Description**: {description}\n"
                        f"**Jira Issue**: {issue_key}"
                    )
                    post_pr_comment(owner, repo, pr["pr_number"], copilot_prompt)
                    logger.info(f"Posted Copilot comment on PR for autofix {issue_key}")
                except Exception as e:
                    logger.warning(f"Warning: Failed to post Copilot comment for {issue_key}: {e}")

                try:
                    post_jira_comment(issue_key, f"Opened PR {pr['pr_url']} with automated fixes: {summary}")
                    transition_issue(issue_key, "In Review")
                    logger.info(f"Posted Jira comment and transitioned {issue_key} to 'In Review' for autofix PR")
                except Exception as e:
                    logger.warning(f"Failed to post Jira comment or transition {issue_key} for autofix PR: {e}")
                    pass
            except Exception as e:
                logger.error(f"Failed to process {issue_key}: {e}")
        raise SystemExit(0)
    else:
        workflow_content = generate_workflow(
            args.repository, args.language, args.buildCommand, args.testCommand, args.deployTarget
        )
        owner, repo = args.repository.split("/")
        branch = f"add-ci-{repo}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        commit_info = commit_workflow(owner, repo, branch, workflow_content, issue_key=args.issueKey)
        pr_info = create_pull_request(owner, repo, commit_info["branch"], args.issueKey)
        target_file = f".github/workflows/{repo}-ci.yml" # Assuming a standard path for logging
        logger.info(f"Workflow file generated at: {target_file}")
        if args.issueKey:
            try:
                # ---------------------------------------------------------
                # Trigger Copilot via PR Comment
                # ---------------------------------------------------------
                summary = f"Task for {args.issueKey}"
                description = ""
                try:
                    details = get_issue_details(args.issueKey)
                    summary = details.get("summary") or summary
                    description = details.get("description") or ""
                except Exception as e:
                    logger.warning(f"Failed to fetch Jira details for {args.issueKey}: {e}")

                copilot_prompt = (
                    f"@copilot please review this PR and fix any issues.\n\n"
                    f"**Task**: {summary}\n"
                    f"**Description**: {description}\n"
                    f"**Jira Issue**: {args.issueKey}"
                )
                try:
                    post_pr_comment(owner, repo, pr_info["pr_number"], copilot_prompt)
                    logger.info(f"Posted Copilot comment on PR {pr_info['pr_url']}")
                except Exception as e:
                    logger.warning(f"Warning: Failed to post Copilot comment: {e}")
                
                # NOTIFY: Granular
                try:
                    post_jira_comment(
                        args.issueKey,
                        "Workflow created and pushed.",
                        link_text="Commit",
                        link_url=commit_info['commit_url']
                    )
                    post_jira_comment(
                        args.issueKey,
                        "Pull Request opened.",
                        link_text="View PR",
                        link_url=pr_info['pr_url']
                    )
                    transition_issue(args.issueKey, "In Review")
                    logger.info(f"Posted granular Jira comments and transitioned {args.issueKey}")
                except Exception as e:
                    logger.warning(f"Failed to post final Jira updates for {args.issueKey}: {e}")
                    pass
            except Exception as e:
                logger.warning(f"Warning: Failed to post Jira comment for {args.issueKey}: {e}")
        logger.info(f"Commit: {commit_info['commit_url']}")
        logger.info(f"PR: {pr_info['pr_url']}")
    
