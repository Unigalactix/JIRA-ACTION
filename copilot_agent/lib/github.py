import os
import base64
import time
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

def commit_workflow(owner, repo, branch, workflow_content, issue_key=None):
    repository = get_repo(owner, repo)

    # Get main branch reference
    try:
        main_ref = repository.get_git_ref("heads/main")
        sha = main_ref.object.sha
        logger.info(f"Retrieved main branch SHA: {sha}")
    except GithubException as e:
        logger.error(f"Failed to get main branch ref: {e}")
        raise

    # Create new branch (if not exists)
    try:
        branch_ref = repository.get_git_ref(f"heads/{branch}")
        logger.info(f"Branch '{branch}' already exists.")
    except GithubException:
        branch_ref = repository.create_git_ref(ref=f"refs/heads/{branch}", sha=sha)
        logger.info(f"Created new branch: {branch}")
        if issue_key:
            try:
                post_jira_comment(issue_key, f"Created new branch: {branch}")
            except Exception:
                pass

    # Create blob and commit
    path = f".github/workflows/{repo}-ci.yml"
    blob = repository.create_git_blob(workflow_content, "utf-8")
    logger.info(f"Created blob for {path}")
    element = InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha)
    base_tree = repository.get_git_tree(sha)
    tree = repository.create_git_tree([element], base_tree=base_tree)
    logger.info("Created new tree for commit.")
    commit = repository.create_git_commit("Add CI/CD workflow", tree, [repository.get_git_commit(sha)])
    logger.info(f"Created commit: {commit.sha}")
    branch_ref.edit(sha=commit.sha)
    logger.info(f"Updated branch '{branch}' to commit {commit.sha}")
    if issue_key:
        try:
            post_jira_comment(issue_key, f"Committed workflow to {branch}", link_text="Commit", link_url=commit.html_url)
        except Exception:
            pass

    return {"commit_url": commit.html_url, "branch": branch}


def create_pull_request(owner, repo, branch, issue_key=None):
    """Create a Pull Request from the branch into main.
    Optionally include Jira issue key in the title/body.
    """
    repo_obj = get_repo(owner, repo)

    title = f"Add CI/CD Pipeline for keys {issue_key}"
    body = f"Auto-generated CI/CD pipeline for {issue_key}"

    pr = repo_obj.create_pull(
        title=title,
        body=body,
        head=branch,
        base="main",
    )
    logger.info(f"Created PR #{pr.number}: {pr.html_url}")
    if issue_key:
         try:
            post_jira_comment(issue_key, f"Created Pull Request #{pr.number}", link_text="View PR", link_url=pr.html_url)
         except Exception:
            pass
    return {"pr_url": pr.html_url, "pr_number": pr.number}


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
    issue = repo_obj.create_issue(title=title, body=body, assignee="copilot")
    logger.info(f"Created Copilot issue #{issue.number}: {title}")
    return {"issue_url": issue.html_url, "issue_number": issue.number}


def apply_text_patches(owner, repo, base_branch, new_branch, changes, issue_key=None):
    """Apply simple text replacements to files and commit on a new branch.

    changes: list of {"path": "relative/file/path", "find": "text", "replace": "text"}
    """
    repository = get_repo(owner, repo)

    # Get base ref and create new branch from it if missing
    base_ref = repository.get_git_ref(f"heads/{base_branch}")
    base_sha = base_ref.object.sha
    logger.info(f"Retrieved base branch '{base_branch}' SHA: {base_sha}")
    try:
        branch_ref = repository.get_git_ref(f"heads/{new_branch}")
        logger.info(f"Branch '{new_branch}' already exists.")
    except GithubException:
        branch_ref = repository.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_sha)
        logger.info(f"Created new branch: {new_branch}")
        if issue_key:
            try:
                post_jira_comment(issue_key, f"Created new branch for autofix: {new_branch}")
            except Exception:
                pass

    # Prepare blobs and tree elements for changed files
    elements = []
    for ch in changes:
        path = ch["path"]
        try:
            file = repository.get_contents(path, ref=base_branch)
            content = file.decoded_content.decode("utf-8")
            logger.info(f"Read content from {path}")
        except GithubException as e:
            logger.error(f"Cannot read file '{path}' from branch {base_branch}: {e}")
            raise RuntimeError(f"Cannot read file '{path}' from branch {base_branch}")

        new_content = content.replace(ch.get("find", ""), ch.get("replace", ""))
        blob = repository.create_git_blob(new_content, "utf-8")
        elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha))
        logger.info(f"Prepared blob for changes in {path}")

    # Create tree and commit against current branch tip
    branch_sha = branch_ref.object.sha
    base_tree = repository.get_git_tree(branch_sha)
    tree = repository.create_git_tree(elements, base_tree=base_tree)
    logger.info("Created new tree for commit.")
    commit = repository.create_git_commit("Apply automated fixes from Jira", tree, [repository.get_git_commit(branch_sha)])
    logger.info(f"Created commit: {commit.sha}")
    branch_ref.edit(sha=commit.sha)
    logger.info(f"Committed workflow to {new_branch}")
    if issue_key:
        try:
            post_jira_comment(issue_key, f"Committed patches to {new_branch}", link_text="Commit", link_url=commit.html_url)
        except Exception:
            pass
    return {"commit_url": commit.html_url, "branch": new_branch}


def post_pr_comment(owner, repo, pr_number, body):
    """Post a comment on a Pull Request (Issue)."""
    g = _get_github_instance()
    repository = g.get_repo(f"{owner}/{repo}")
    issue = repository.get_issue(pr_number)
    comment = issue.create_comment(body)
    return {"comment_url": comment.html_url, "id": comment.id}
