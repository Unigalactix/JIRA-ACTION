from fastapi import FastAPI, Request
from lib.workflow_factory import generate_workflow
from lib.github import commit_workflow, create_pull_request
from lib.jira import post_jira_comment
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    issue_key = data.get("issueKey")
    repository = data.get("repository")
    language = data.get("language")
    build_cmd = data.get("buildCommand")
    test_cmd = data.get("testCommand")
    deploy_target = data.get("deployTarget")

    if not repository or not language:
        return {"error": "Missing required fields"}

    # Generate workflow YAML
    workflow_content = generate_workflow(repository, language, build_cmd, test_cmd, deploy_target)

    # Commit workflow to GitHub
    owner, repo = repository.split("/")
    branch = f"add-ci-{int(os.times()[4])}"
    commit_info = commit_workflow(owner, repo, branch, workflow_content)

    # Create PR to main
    pr_info = create_pull_request(owner, repo, commit_info["branch"], issue_key)

    # Post back to Jira
    post_jira_comment(issue_key, (
        f"✅ Workflow created and PR opened.\n"
        f"File: .github/workflows/{repo}-ci.yml\n"
        f"Commit: {commit_info['commit_url']}\n"
        f"PR: {pr_info['pr_url']}"
    ))
    return {"status": "success", "commit_url": commit_info["commit_url"], "pr_url": pr_info["pr_url"]}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Copilot Agent CLI")
    parser.add_argument("repository", help="Target repository in owner/repo format")
    parser.add_argument("language", help="Project language (node|python|dotnet|java)")
    parser.add_argument("buildCommand", help="Build command to use")
    parser.add_argument("testCommand", help="Test command to use")
    parser.add_argument("deployTarget", help="Deployment target label")
    parser.add_argument("--issueKey", dest="issueKey", help="Optional Jira issue key")

    args = parser.parse_args()

    workflow_content = generate_workflow(
        args.repository, args.language, args.buildCommand, args.testCommand, args.deployTarget
    )

    owner, repo = args.repository.split("/")
    branch = f"add-ci-{int(os.times()[4])}"
    commit_info = commit_workflow(owner, repo, branch, workflow_content)
    pr_info = create_pull_request(owner, repo, commit_info["branch"], args.issueKey)

    if args.issueKey:
        post_jira_comment(
            args.issueKey,
            (
                f"✅ Workflow created and PR opened.\n"
                f"File: .github/workflows/{repo}-ci.yml\n"
                f"Commit: {commit_info['commit_url']}\n"
                f"PR: {pr_info['pr_url']}"
            ),
        )

    print("Commit:", commit_info["commit_url"])
    print("PR:", pr_info["pr_url"])
