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

def add_label_to_issue(owner, repo, issue_number, labels):
    """Add labels to an issue.
    Ref: provided user script
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    payload = {"labels": labels}
    
    response = requests.post(url, headers=headers, json=payload)
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
                # 422 could mean "Reference already exists" OR "Validation Failed"
                logger.warning(f"Branch check-new failed with 422 (Race Condition or Invalid?). GitHub Message: {e.data}")
                
                try:
                    # Attempt recovery: Update the existing ref
                    # Try standar format first
                    try:
                        branch_ref = repository.get_git_ref(f"heads/{branch}")
                    except GithubException:
                        # Fallback: Try with full refs prefix if simple heads fails
                        logger.info(f"get_git_ref(heads/{branch}) failed (404?). Trying refs/heads/{branch}")
                        branch_ref = repository.get_git_ref(f"refs/heads/{branch}")
                    
                    branch_ref.edit(sha=commit.sha)
                    logger.info(f"Updated branch {branch} after race condition")
                    
                except GithubException as e2:
                    logger.error(f"Failed to recover from race condition for {branch}: {e2}. Original 422 data: {e.data}")
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
    
    # Assign to Copilot & Add Labels (PRs are technically Issues in API)
    try:
        assign_issue_to_copilot(owner, repo, pr.number)
        logger.info(f"Assigned @copilot to PR #{pr.number}")
    except Exception as e:
        logger.warning(f"Failed to assign @copilot to PR #{pr.number}: {e}")

    try:
        add_label_to_issue(owner, repo, pr.number, ["copilot", "jira-sync"])
        logger.info(f"Added labels to PR #{pr.number}")
    except Exception as e:
        logger.warning(f"Failed to add labels to PR #{pr.number}: {e}")

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
    try:
        assign_issue_to_copilot(owner, repo, issue.number)
        logger.info(f"Assigned @copilot to issue #{issue.number}")
    except Exception as e:
        logger.warning(f"Failed to assign @copilot to issue #{issue.number}: {e}")
        
    # Add labels per reference implementation
    try:
        add_label_to_issue(owner, repo, issue.number, ["copilot", "jira-sync"])
        logger.info(f"Added labels to issue #{issue.number}")
    except Exception as e:
         logger.warning(f"Failed to add labels to issue #{issue.number}: {e}")

    return {"issue_url": issue.html_url, "issue_number": issue.number}


def get_latest_workflow_run_for_ref(repo_name, ref):
    """
    Get the latest workflow run for a specific ref (branch or SHA).
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/actions/runs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    params = {
        "branch": ref,
        "per_page": 1,
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("workflow_runs"):
            return data["workflow_runs"][0]
        return None
    except Exception as e:
        logger.warning(f"Failed to get workflow runs for {repo_name}:{ref}: {e}")
        return None


def get_jobs_for_run(repo_name, run_id):
    """
    Get all jobs for a workflow run.
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/jobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return data.get("jobs", [])
    except Exception as e:
        logger.warning(f"Failed to get jobs for run {run_id}: {e}")
        return []


def find_copilot_sub_pr(repo_name, main_pr_number):
    """
    Find a Copilot-created sub-PR that references the main PR.
    """
    from copilot_agent.app import COPILOT_USERNAME
    
    owner, repo = repo_name.split("/")
    repository = get_repo(owner, repo)
    
    try:
        # Get all open PRs
        pulls = repository.get_pulls(state='open')
        
        for pr in pulls:
            # Check if this is a Copilot PR (by author or title)
            if pr.user and pr.user.login == COPILOT_USERNAME:
                # Check if it references our main PR in body or title
                if pr.body and f"#{main_pr_number}" in pr.body:
                    return {
                        "number": pr.number,
                        "html_url": pr.html_url,
                        "title": pr.title,
                        "draft": pr.draft,
                        "created_at": pr.created_at.isoformat() if pr.created_at else None,
                        "labels": [{"name": label.name} for label in pr.labels],
                    }
        
        return None
    except Exception as e:
        logger.warning(f"Failed to find Copilot sub-PR for {repo_name}#{main_pr_number}: {e}")
        return None


def get_pull_request_details(repo_name, pull_number):
    """
    Get details of a specific pull request.
    """
    owner, repo = repo_name.split("/")
    repository = get_repo(owner, repo)
    
    try:
        pr = repository.get_pull(pull_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "state": pr.state,
            "merged": pr.merged,
            "draft": pr.draft,
            "html_url": pr.html_url,
            "head": {
                "ref": pr.head.ref,
                "sha": pr.head.sha,
            },
            "base": {
                "ref": pr.base.ref,
            }
        }
    except Exception as e:
        logger.error(f"Failed to get PR details for {repo_name}#{pull_number}: {e}")
        raise


def is_pull_request_merged(repo_name, pull_number):
    """
    Check if a pull request is merged.
    """
    owner, repo = repo_name.split("/")
    repository = get_repo(owner, repo)
    
    try:
        pr = repository.get_pull(pull_number)
        return {"merged": pr.merged}
    except Exception as e:
        logger.warning(f"Failed to check if PR is merged {repo_name}#{pull_number}: {e}")
        return {"merged": False}


def mark_pull_request_ready_for_review(repo_name, pull_number):
    """
    Mark a draft PR as ready for review.
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pull_number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    data = {"draft": False}
    
    try:
        response = requests.patch(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        logger.info(f"Marked PR #{pull_number} as ready for review")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to mark PR #{pull_number} ready: {e}")
        return {"ok": False, "error": str(e)}


def approve_pull_request(repo_name, pull_number):
    """
    Approve a pull request.
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pull_number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "event": "APPROVE",
        "body": "Auto-approved by Autopilot"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        logger.info(f"Approved PR #{pull_number}")
        return {"ok": True}
    except Exception as e:
        logger.warning(f"Failed to approve PR #{pull_number}: {e}")
        return {"ok": False, "error": str(e)}


def enable_pull_request_auto_merge(repo_name, pull_number, merge_method="SQUASH"):
    """
    Enable auto-merge for a pull request using GraphQL API.
    """
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    
    # First get the PR node ID
    owner, repo = repo_name.split("/")
    repository = get_repo(owner, repo)
    
    try:
        pr = repository.get_pull(pull_number)
        pr_node_id = pr.raw_data.get('node_id')
        
        if not pr_node_id:
            return {"ok": False, "message": "Could not get PR node_id"}
        
        # Use GraphQL to enable auto-merge
        graphql_url = "https://api.github.com/graphql"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        query = """
        mutation($pullRequestId: ID!, $mergeMethod: PullRequestMergeMethod!) {
          enablePullRequestAutoMerge(input: {
            pullRequestId: $pullRequestId,
            mergeMethod: $mergeMethod
          }) {
            pullRequest {
              id
              autoMergeRequest {
                enabledAt
              }
            }
          }
        }
        """
        
        variables = {
            "pullRequestId": pr_node_id,
            "mergeMethod": merge_method
        }
        
        response = requests.post(
            graphql_url,
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            logger.warning(f"GraphQL errors enabling auto-merge: {data['errors']}")
            return {"ok": False, "message": str(data['errors'])}
        
        logger.info(f"Enabled auto-merge for PR #{pull_number}")
        return {"ok": True}
        
    except Exception as e:
        logger.warning(f"Failed to enable auto-merge for PR #{pull_number}: {e}")
        return {"ok": False, "message": str(e)}


def merge_pull_request(repo_name, pull_number, method="squash"):
    """
    Merge a pull request immediately.
    """
    owner, repo = repo_name.split("/")
    repository = get_repo(owner, repo)
    
    try:
        pr = repository.get_pull(pull_number)
        result = pr.merge(merge_method=method)
        
        if result.merged:
            logger.info(f"Merged PR #{pull_number}")
            return {"merged": True}
        else:
            logger.warning(f"Failed to merge PR #{pull_number}: {result.message}")
            return {"merged": False, "message": result.message}
            
    except Exception as e:
        logger.error(f"Failed to merge PR #{pull_number}: {e}")
        return {"merged": False, "message": str(e)}


def get_active_org_prs_with_jira_keys(org):
    """
    Get all open PRs in an organization that have Jira keys in their title or body.
    """
    import re
    from copilot_agent.app import JIRA_KEY_PATTERN
    
    token = os.getenv("GHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    g = _get_github_instance()
    
    active_prs = []
    
    try:
        org_obj = g.get_organization(org)
        repos = org_obj.get_repos()
        
        for repo in repos:
            try:
                pulls = repo.get_pulls(state='open')
                
                for pr in pulls:
                    # Look for Jira keys using configurable pattern
                    matches = []
                    if pr.title:
                        matches.extend(re.findall(JIRA_KEY_PATTERN, pr.title))
                    if pr.body:
                        matches.extend(re.findall(JIRA_KEY_PATTERN, pr.body))
                    
                    if matches:
                        active_prs.append({
                            "jiraKey": matches[0],  # Use first match
                            "prUrl": pr.html_url,
                            "repoName": repo.full_name,
                            "branch": pr.head.ref,
                            "headSha": pr.head.sha,
                        })
            except Exception as e:
                logger.warning(f"Failed to get PRs for repo {repo.full_name}: {e}")
                continue
        
        return active_prs
        
    except Exception as e:
        logger.error(f"Failed to get active PRs for org {org}: {e}")
        return []
