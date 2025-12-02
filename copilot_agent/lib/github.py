from github import Github
import os


def commit_workflow(owner, repo, branch, workflow_content):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set")

    g = Github(token)
    repository = g.get_repo(f"{owner}/{repo}")

    # Get main branch reference
    main_ref = repository.get_git_ref("heads/main")
    sha = main_ref.object.sha

    # Create new branch (if not exists)
    try:
        repository.get_git_ref(f"heads/{branch}")
    except Exception:
        repository.create_git_ref(ref=f"refs/heads/{branch}", sha=sha)

    # Create blob and commit
    path = f".github/workflows/{repo}-ci.yml"
    blob = repository.create_git_blob(workflow_content, "utf-8")
    tree = repository.create_git_tree([
        {"path": path, "mode": "100644", "type": "blob", "sha": blob.sha}
    ], base_tree=sha)
    commit = repository.create_git_commit("Add CI/CD workflow", tree, [repository.get_git_commit(sha)])
    repository.get_git_ref(f"heads/{branch}").edit(commit.sha)

    return {"commit_url": f"https://github.com/{owner}/{repo}/commit/{commit.sha}"}
