from fastapi import FastAPI, Request
from copilot_agent.lib.workflow_factory import generate_workflow
from copilot_agent.lib.github import commit_workflow, create_pull_request, apply_text_patches
from copilot_agent.lib.jira import post_jira_comment, transition_issue, get_issue_details, search_issues
import os
import time
import uuid
from dotenv import load_dotenv
import json
import base64
import requests

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    try:
        data = await req.json()
        issue_key = data.get("issueKey")
        repository = data.get("repository")
        language = data.get("language")
        build_cmd = data.get("buildCommand")
        test_cmd = data.get("testCommand")
        deploy_target = data.get("deployTarget")

        if not repository or not language:
            return {"status": "error", "message": "Missing required fields: repository, language"}

        # Generate workflow YAML
        workflow_content = generate_workflow(repository, language, build_cmd, test_cmd, deploy_target)

        # Commit workflow to GitHub
        owner, repo = repository.split("/")
        branch = f"add-ci-{repo}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        commit_info = commit_workflow(owner, repo, branch, workflow_content)

        # Create PR to main (current lib signature)
        pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)

        # If Jira issue contains auto-fix instructions, apply them in a follow-up PR
        autofix_result = None
        if issue_key:
            details = get_issue_details(issue_key)
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
            if changes:
                fix_branch = f"autofix-{issue_key.lower()}-{uuid.uuid4().hex[:8]}"
                try:
                    fix_commit = apply_text_patches(owner, repo, "main", fix_branch, changes)
                    fix_pr = create_pull_request(owner, repo, fix_commit["branch"], issue_key)
                    autofix_result = {"commit_url": fix_commit["commit_url"], "pr_url": fix_pr["pr_url"], "branch": fix_commit["branch"]}
                    try:
                        post_jira_comment(issue_key, f"Opened PR {fix_pr['pr_url']} with automated fixes extracted from description.")
                    except Exception:
                        pass
                except Exception:
                    # Non-fatal: continue without autofix
                    autofix_result = {"skipped": True}

        # Automatic Jira transition when PR(s) are opened
        if issue_key:
            try:
                transition_issue(issue_key, "In Review")
            except Exception:
                pass

        # Post back to Jira (only if issue_key provided); non-fatal if it fails
        if issue_key:
            try:
                post_jira_comment(issue_key, (
                    f"✅ Workflow created and PR opened.\n"
                    f"File: .github/workflows/{repo}-ci.yml\n"
                    f"Commit: {commit_info['commit_url']}\n"
                    f"PR: {pr_info['pr_url']}"
                ))
            except Exception:
                pass
        return {
            "status": "success",
            "commit_url": commit_info["commit_url"],
            "pr_url": pr_info["pr_url"],
            "autofix": autofix_result or {"message": "No valid auto-fix instructions found in Jira description."}
        }
    except Exception as e:
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
    except Exception as e:
        return {"status": "error", "message": f"Failed to query Jira: {e}"}

    if resp.status_code != 200:
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
    return {"status": "success", "count": len(issues), "issues": issues}
@app.post("/transition")
async def transition(req: Request):
    data = await req.json()
    issue_key = data.get("issueKey")
    target = data.get("targetStatus")
    if not issue_key or not target:
        return {"status": "error", "message": "Missing required fields: issueKey, targetStatus"}
    try:
        result = transition_issue(issue_key, target)
        return {"status": "success", "result": result}
    except Exception as e:
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
        return {"status": "success", "transitions": transitions}
    except Exception as e:
        return {"status": "error", "message": str(e)}
@app.post("/autofix")
async def autofix(req: Request):
    """Parse Jira issue, apply simple text fixes, commit and open PR."""
    data = await req.json()
    repository = data.get("repository")
    issue_key = data.get("issueKey")
    base_branch = data.get("baseBranch", "main")
    if not repository or not issue_key:
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
        return {"status": "error", "message": "No valid change instructions found in Jira description. Expected 'path=..., find=..., replace=...' lines."}

    branch = f"autofix-{issue_key.lower()}-{uuid.uuid4().hex[:8]}"
    try:
        commit_info = apply_text_patches(owner, repo, base_branch, branch, changes)
        pr = create_pull_request(owner, repo, commit_info["branch"], issue_key)
        try:
            post_jira_comment(issue_key, f"Opened PR {pr['pr_url']} with automated fixes: {summary}")
        except Exception:
            pass
        return {"status": "success", "commit_url": commit_info["commit_url"], "pr_url": pr["pr_url"], "branch": commit_info["branch"]}
    except Exception as e:
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
            print("No active issues found.")
            raise SystemExit(0)
        prio_order = {"Highest":0,"High":1,"Medium":2,"Low":3,"Lowest":4}
        issues.sort(key=lambda i: prio_order.get((i.get("priority") or "Medium"), 2))
        print("Active Jira issues:")
        for idx, i in enumerate(issues, start=1):
            print(f"{idx}. {i['key']} [{i.get('priority')}] - {i['summary']}")
        if args.selectAll:
            selected = list(range(1, len(issues)+1))
        else:
            try:
                sel = input("Select issue number(s) (comma-separated): ").strip()
                selected = [int(s) for s in sel.split(",") if s.strip().isdigit()]
            except Exception:
                print("Invalid selection")
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
                print(f"No valid change instructions found for {issue_key}; skipping.")
                continue
            branch = f"autofix-{issue_key.lower()}-{uuid.uuid4().hex[:8]}"
            try:
                commit_info = apply_text_patches(owner, repo, "main", branch, changes)
                pr = create_pull_request(owner, repo, commit_info["branch"], issue_key)
                print(f"Opened PR: {pr['pr_url']} for {issue_key}")
                try:
                    post_jira_comment(issue_key, f"Opened PR {pr['pr_url']} with automated fixes: {summary}")
                    transition_issue(issue_key, "In Review")
                except Exception:
                    pass
            except Exception as e:
                print(f"Failed to process {issue_key}: {e}")
        raise SystemExit(0)
    else:
        workflow_content = generate_workflow(
            args.repository, args.language, args.buildCommand, args.testCommand, args.deployTarget
        )
        owner, repo = args.repository.split("/")
        branch = f"add-ci-{repo}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        commit_info = commit_workflow(owner, repo, branch, workflow_content)
        pr_info = create_pull_request(owner, repo, commit_info["branch"], args.issueKey)
        if args.issueKey:
            try:
                post_jira_comment(
                    args.issueKey,
                    (
                        f"✅ Workflow created and PR opened.\n"
                        f"File: .github/workflows/{repo}-ci.yml\n"
                        f"Commit: {commit_info['commit_url']}\n"
                        f"PR: {pr_info['pr_url']}"
                    ),
                )
                try:
                    transition_issue(args.issueKey, "In Review")
                except Exception:
                    pass
            except Exception as e:
                print(f"Warning: Failed to post Jira comment for {args.issueKey}: {e}")
        print("Commit:", commit_info["commit_url"])
        print("PR:", pr_info["pr_url"])
