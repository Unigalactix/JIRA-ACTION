import os
import base64
import time
import requests
from github import Github, InputGitTreeElement, GithubException
from copilot_agent.lib.logger import setup_logger
from copilot_agent.lib.jira import post_jira_comment

logger = setup_logger("github")


def _get_github_instance():
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN or GHUB_TOKEN environment variable is not set")
    return Github(token)

def get_repo(owner, repo_name):
    g = _get_github_instance()
    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
        logger.info(f"Successfully retrieved repository: {owner}/{repo_name}")
        return repo
    except GithubException as e:
        logger.error(f"Failed to get repository {owner}/{repo_name}: {e}")
        raise

def assign_issue_to_copilot(owner, repo, issue_number, pat_token=None):
    """
    Assigns a GitHub issue to Copilot using REST API.
    Ref: https://github.blog/changelog/2025-12-03-assign-issues-to-copilot-using-the-api/
    """
    if pat_token is None:
        pat_token = os.getenv('GHUB_TOKEN') or os.getenv('GITHUB_TOKEN')
    
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/assignees"
    headers = {
        "Authorization": f"token {pat_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {"assignees": ["copilot"]}
    
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def commit_files(owner, repo, branch, files, message, issue_key=None):
    """
    Commit multiple files to a branch. Creates branch if it doesn't exist.
    files: dict of { "path/to/file": "content_string" }
    """
    repository = get_repo(owner, repo)
    
    # 1. Get Base SHA (default branch) for new branches, or Current SHA for existing
    parent_sha = None
    default_branch = repository.default_branch
    try:
        branch_ref = repository.get_git_ref(f"heads/{branch}")
        parent_sha = branch_ref.object.sha
        logger.info(f"Branch '{branch}' exists. Appending to {parent_sha}")
    except GithubException:
        # Branch doesn't exist, get default branch
        try:
            # Note: PyGithub requires "heads/" prefix, but default_branch is typically just "main" or "master"
            base_ref = repository.get_git_ref(f"heads/{default_branch}")
            parent_sha = base_ref.object.sha
            logger.info(f"Branch '{branch}' new. Baselining from {default_branch} {parent_sha}")
        except GithubException as e:
             logger.error(f"Cannot find default branch {default_branch}: {e}")
             raise

    # 2. Create Blobs & Tree
    elements = []
    for path, content in files.items():
        blob = repository.create_git_blob(content, "utf-8")
        elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha))
    
    base_tree = repository.get_git_tree(parent_sha)
    tree = repository.create_git_tree(elements, base_tree=base_tree)
    
    # 3. Create Commit
    parent_commit = repository.get_git_commit(parent_sha)
    commit = repository.create_git_commit(message, tree, [parent_commit])
    logger.info(f"Created commit {commit.sha}")

    # 4. Update Reference
    try:
        if branch_ref:
            branch_ref.edit(sha=commit.sha)
            logger.info(f"Updated branch {branch}")
        else:
            repository.create_git_ref(ref=f"refs/heads/{branch}", sha=commit.sha)
            logger.info(f"Created branch {branch}")
            
    except UnboundLocalError:
        # branch_ref was undefined, meaning we are creating a new branch
        try:
            repository.create_git_ref(ref=f"refs/heads/{branch}", sha=commit.sha)
            logger.info(f"Created branch {branch}")
        except GithubException as e:
            if e.status == 422:
                # Reference already exists (race condition)
                logger.warning(f"Branch {branch} checked as new but now exists (race condition). updating...")
                try:
                    branch_ref = repository.get_git_ref(f"heads/{branch}")
                    branch_ref.edit(sha=commit.sha)
                    logger.info(f"Updated branch {branch} after race condition")
                except GithubException as e2:
                    logger.error(f"Failed to recover from race condition for {branch}: {e2}")
                    raise
            else:
                 logger.error(f"Failed to create branch {branch}: {e}")
                 raise

    # Notify Jira
    if issue_key:
        try:
            post_jira_comment(
                issue_key, 
                f"Committed changes to `{branch}`.\nMessage: {message}",
                link_text="View Commit",
                link_url=commit.html_url
            )
        except Exception:
            pass

    return {"commit_url": commit.html_url, "branch": branch, "sha": commit.sha}

def create_pull_request(owner, repo, branch, issue_key=None):
    """
    Create a Pull Request or return existing one.
    """
    repo_obj = get_repo(owner, repo)
    default_branch = repo_obj.default_branch
    
    # Check for existing PR
    pulls = repo_obj.get_pulls(state='open', head=f"{owner}:{branch}", base=default_branch)
    for pr in pulls:
        logger.info(f"Found existing PR #{pr.number} for {branch}")
        if issue_key:
            try:
                pass 
            except Exception:
                pass
        return {"pr_url": pr.html_url, "pr_number": pr.number, "is_new": False}

    title = f"Copilot Fixes: {issue_key}" if issue_key else f"Copilot Automations ({branch})"
    body = f"Automated changes by Copilot Agent.\n\nRelated Issue: {issue_key}"

    pr = repo_obj.create_pull(
        title=title,
        body=body,
        head=branch,
        base=default_branch,
    )
    logger.info(f"Created PR #{pr.number}: {pr.html_url}")
    
    if issue_key:
         try:
            post_jira_comment(issue_key, f"Created Pull Request #{pr.number}", link_text="View PR", link_url=pr.html_url)
         except Exception:
            pass
            
    return {"pr_url": pr.html_url, "pr_number": pr.number, "is_new": True}


def post_pr_comment(owner, repo, pr_number, body):
    """Post a comment on a Pull Request (Issue)."""
    g = _get_github_instance()
    repository = g.get_repo(f"{owner}/{repo}")
    issue = repository.get_issue(pr_number)
    comment = issue.create_comment(body)
    return {"comment_url": comment.html_url, "id": comment.id}

def create_copilot_issue(owner, repo, issue_key, summary, description):
    """Create a GitHub Issue to trigger Copilot Agent.
    """
    repo_obj = get_repo(owner, repo)

    title = f"[{issue_key}] Fix: {summary}"
    description = description or "No details provided."
    body = (
        f"@copilot please fix this issue based on the following requirements.\n\n"
        f"**Jira Issue**: {issue_key}\n"
        f"**Description**:\n{description}\n"
    )

    # Create the issue
    # assignee="copilot" is often invalid if the app/bot user cannot be assigned directly or isn't a repo member.
    issue = repo_obj.create_issue(title=title, body=body)
    logger.info(f"Created Copilot issue #{issue.number}: {title}")
    
    # Try to assign copilot (requires PAT permissions)
    # Try to assign copilot (requires PAT permissions)
    try:
        assign_issue_to_copilot(owner, repo, issue.number)
        logger.info(f"Assigned @copilot to issue #{issue.number}")
    except Exception as e:
        logger.warning(f"Failed to assign @copilot to issue #{issue.number}: {e}")
        
    return {"issue_url": issue.html_url, "issue_number": issue.number}
