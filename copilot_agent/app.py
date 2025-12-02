from fastapi import FastAPI, Request
from lib.workflow_factory import generate_workflow
from lib.github import commit_workflow
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

    # Post back to Jira
    post_jira_comment(issue_key, f"✅ Workflow created:\nFile: .github/workflows/{repo}-ci.yml\nCommit: {commit_info['commit_url']}")

    return {"status": "success", "commit_url": commit_info["commit_url"]}
