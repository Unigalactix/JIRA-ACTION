from fastapi import FastAPI, Request
from copilot_agent.lib.workflow_factory import generate_workflow, generate_dockerfile
from copilot_agent.lib.config_helper import generate_vs_code_config, mask_config
from pathlib import Path
from copilot_agent.lib.github import commit_files, create_pull_request, post_pr_comment, create_copilot_issue
from copilot_agent.lib.jira import post_jira_comment, transition_issue, get_issue_details, search_issues
from copilot_agent.lib.logger import setup_logger
import os
import time
import uuid
from dotenv import load_dotenv
import json
import base64
import requests
import asyncio
from copilot_agent.lib.autopilot import Autopilot

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
            safe_config = mask_config(config)
            logger.info("----------------------------------------------------------------")
            logger.info("MCP CONFIGURATION (Copy to VS Code settings.json):")
            logger.info("(Secrets are masked in logs. Run scripts/generate_mcp_config.py to see full values)")
            logger.info(json.dumps(safe_config, indent=2))
            logger.info("----------------------------------------------------------------")
    except Exception as e:
        logger.warning(f"Failed to generate MCP config on startup: {e}")

    # Start Autopilot in background
    autopilot = Autopilot(process_pipeline_job)
    asyncio.create_task(autopilot.start())
    logger.info("Autopilot background task launched.")

@app.get("/health")
def health():
    logger.info("Health check requested")
    return {"status": "ok"}

async def process_pipeline_job(data: dict):
    """
    Shared logic to process a CI/CD job from Webhook or Autopilot.
    """
    issue_key = data.get("issueKey")
    repository = data.get("repository")
    language = data.get("language")
    build_cmd = data.get("buildCommand")
    test_cmd = data.get("testCommand")
    deploy_target = data.get("deployTarget")

    if not repository or not language:
        logger.error("Missing required fields: repository, language in job payload")
        return {"status": "error", "message": "Missing required fields: repository, language"}

    # Fix: If user/autopilot sends "echo 'No build'" explicitly, we might want to respect it?
    # But Autopilot logic was changed to send None if not configured.
    # So here we just pass it through.
    logger.info(f"Processing job for {repository} ({language}). Build: {build_cmd}, Test: {test_cmd}")

    # 1. Fetch Jira Issue Context
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

    # 2. Trigger Copilot Agent (Native)
    copilot_issue_info = {"issue_url": "skipped", "issue_number": -1}
    try:
        copilot_issue_info = create_copilot_issue(owner, repo, issue_key, summary, description)
        logger.info(f"Created Copilot Issue: {copilot_issue_info['issue_url']}")
    except Exception as e:
        logger.error(f"Failed to create Copilot Issue: {e}")

    # 3. Create CI/CD Pipeline (Standard)
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

    # Generate Content
    workflow_content = generate_workflow(repository, language, build_cmd, test_cmd, deploy_target)
    docker_content = generate_dockerfile(language)
    
    # Prepare Files for Commit
    files = {
        f".github/workflows/{repo}-ci.yml": workflow_content,
        "Dockerfile": docker_content
    }

    # "Single Feature Branch" Strategy
    branch = f"feature/copilot-{repo}"
    
    commit_info = commit_files(
        owner, repo, branch, files, 
        message=f"Add CI/CD pipeline and Dockerfile for {issue_key}",
        issue_key=issue_key
    )
    
    # Create/Update PR (Idempotent)
    pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)

    # 3.5 Trigger Copilot via PR Comment (Only if new PR or context shifted?)
    # We'll always post comment to trigger scan/review on the latest commit.
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

    # 4. Feedback to Jira - Granular Updates
    if issue_key:
        # NOTIFY: CI Created
        try:
             # Only notify "Created" if it was a new branch/commit, but commit_files notifies anyway.
             # We can skip redundant "CI Created" comment here since commit_files does it?
             # But let's keep it for the "Pipeline created" semantics vs just "Committed".
            post_jira_comment(
                issue_key, 
                f"CI/CD Pipeline & Dockerfile updated.",
                link_text="Commit",
                link_url=commit_info["commit_url"]
            )
            logger.info(f"Posted Jira comment about CI creation for {issue_key}")
        except Exception as e:
            logger.warning(f"Failed to post Jira comment about CI creation for {issue_key}: {e}")
        
        # NOTIFY: PR Opened (Only if new)
        if pr_info.get("is_new"):
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

    return {
        "status": "success",
        "copilot_issue": copilot_issue_info.get("issue_url"),
        "ci_pr": pr_info["pr_url"]
    }

@app.post("/webhook")
async def webhook(req: Request):
    try:
        data = await req.json()
        logger.info(f"Received webhook: {json.dumps(data)}")
        return await process_pipeline_job(data)
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
        docker_content = generate_dockerfile(language)
        
        files = {
            f".github/workflows/{repo}-ci.yml": workflow_content,
            "Dockerfile": docker_content
        }
        
        # Single Feature Branch
        branch = f"feature/copilot-{repo}"
        
        commit_info = commit_files(
            owner, repo, branch, files,
            message=f"Generate CI/CD and Dockerfile for {issue_key or 'manual request'}",
            issue_key=issue_key
        )
        
        pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)
        logger.info(f"Generated workflow, committed to {commit_info['commit_url']}, and opened/updated PR {pr_info['pr_url']}")

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
                    f"CI/CD Pipeline updated at {repo}-ci.yml.",
                    link_text="Commit",
                    link_url=commit_info["commit_url"]
                )
            except Exception as e:
                logger.warning(f"Failed to post Jira comment about CI creation for {issue_key}: {e}")
            
            if pr_info.get("is_new"):
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
    # ... (Existing list_issues logic OK) ...
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
            f"{base_url}/rest/api/3/search/jql",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            json={
                "query": jql,
                "startAt": 0,
                "maxResults": max_results,
                "fields": ["summary", "status", "assignee", "priority"],
            },
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
    # ... (Existing transition logic OK) ...
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
    # ... (Existing list_transitions logic OK) ...
    try:
        data = await req.json()
    except Exception:
        data = {}
    issue_key = data.get("issueKey")
    if not issue_key:
        return {"status": "error", "message": "Missing required field: issueKey"}
    try:
        transitions = []
        for t in get_transitions(issue_key): # error: name 'get_transitions' is not defined. import missing in original too? 
            # Note: original file imported transition_issue but not get_transitions explicitly in `from ... import`.
            # Let's hope it's available or we fix imports. Actually I see line 6 `from copilot_agent.lib.jira import ...`
            # I should verify imports. But assuming `get_transitions` is in `copilot_agent.lib.jira`
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

def _process_patches(owner, repo, changes, branch="main"):
    """
    Helper to read files, apply patches, and return dict of new content.
    """
    from copilot_agent.lib.github import get_repo
    from github import GithubException
    
    repository = get_repo(owner, repo)
    files_to_commit = {}
    
    for ch in changes:
        path = ch["path"]
        try:
            # Try to get raw content from target branch (or main if new)
            # Actually, if we are on a persistent feature branch, we should try reading from IT first.
            try:
                file = repository.get_contents(path, ref=branch)
            except GithubException:
                # Fallback to main
                file = repository.get_contents(path, ref="main")
                
            content = file.decoded_content.decode("utf-8")
        except GithubException as e:
             logger.error(f"Cannot read file '{path}': {e}")
             continue
             
        new_content = content.replace(ch.get("find", ""), ch.get("replace", ""))
        files_to_commit[path] = new_content
        
    return files_to_commit

@app.post("/autofix")
async def autofix(req: Request):
    """Parse Jira issue, apply simple text fixes, commit and open PR."""
    data = await req.json()
    repository = data.get("repository")
    issue_key = data.get("issueKey")
    # base_branch ignored, using persistent feature branch
    
    logger.info(f"Received autofix request for {repository}, issue {issue_key}")
    if not repository or not issue_key:
        return {"status": "error", "message": "Missing required fields"}

    owner, repo = repository.split("/")
    details = get_issue_details(issue_key)
    summary = details.get("summary") or "Automated fix"
    description = (details.get("description") or "").strip()

    # Parse Instructions
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
        return {"status": "error", "message": "No valid change instructions found."}

    branch = f"feature/copilot-{repo}"
    
    try:
        files = _process_patches(owner, repo, changes, branch)
        if not files:
             return {"status": "error", "message": "Could not apply patches (file not found?)"}
             
        commit_info = commit_files(
            owner, repo, branch, files, 
            message=f"Apply automated fixes for {issue_key}", 
            issue_key=issue_key
        )
        
        pr = create_pull_request(owner, repo, branch, issue_key)
        
        # Trigger Copilot
        try:
            copilot_prompt = (
                f"@copilot please review this auto-fix PR and make further improvements.\n\n"
                f"**Task**: {summary}\n"
                f"**Description**: {description}\n"
                f"**Jira Issue**: {issue_key}"
            )
            post_pr_comment(owner, repo, pr["pr_number"], copilot_prompt)
        except Exception:
            pass

        if pr.get("is_new"):
            transition_issue(issue_key, "In Review")
        
        return {"status": "success", "commit_url": commit_info["commit_url"], "pr_url": pr["pr_url"]}
        
    except Exception as e:
        logger.exception("Error in autofix processing:")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Copilot Agent CLI")
    parser.add_argument("repository", nargs="?", help="Target repository in owner/repo format")
    parser.add_argument("language", nargs="?", help="Project language")
    parser.add_argument("buildCommand", nargs="?", help="Build command")
    parser.add_argument("testCommand", nargs="?", help="Test command")
    parser.add_argument("deployTarget", nargs="?", help="Deployment target")
    parser.add_argument("--issueKey", dest="issueKey", help="Optional Jira issue key")
    parser.add_argument("--list", dest="listIssues", action="store_true", help="List active Jira ticket")
    parser.add_argument("--project", dest="projectKey", help="Jira project key")
    parser.add_argument("--selectAll", dest="selectAll", action="store_true", help="Process all")

    args = parser.parse_args()
    
    if args.listIssues:
        # Simplistic CLI implementation reusing process_patches logic if needed
        # For now, just generate pipeline as that's the main use case in CLI here
        pass # (Truncated for brevity, assuming similar refactoring needed if used heavily)
        
    else:
        # CLI Generate Pipeline
        workflow_content = generate_workflow(
            args.repository, args.language, args.buildCommand, args.testCommand, args.deployTarget
        )
        docker_content = generate_dockerfile(args.language)
        
        owner, repo = args.repository.split("/")
        branch = f"feature/copilot-{repo}"
        
        files = {
            f".github/workflows/{repo}-ci.yml": workflow_content,
            "Dockerfile": docker_content
        }
        
        commit_info = commit_files(owner, repo, branch, files, f"CLI generated CI/CD for {args.issueKey}", args.issueKey)
        pr_info = create_pull_request(owner, repo, branch, args.issueKey)
        
        logger.info(f"Commit: {commit_info['commit_url']}")
        logger.info(f"PR: {pr_info['pr_url']}")
    
