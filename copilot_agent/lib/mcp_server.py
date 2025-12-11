from mcp.server.fastmcp import FastMCP
import subprocess
import os

# Initialize FastMCP server
mcp = FastMCP("my-mcp-server")

@mcp.tool()
def agent_tests(repo_path: str) -> dict:
    """
    Running Tests on MCP Server.
    Runs pytest, flake8, and bandit on the specified repository path.
    Enforces security by checking ALLOWED_REPOS environment variable.
    """
    # ---------------------------------------------------------
    # SECURITY: Whitelist Enforcement
    # ---------------------------------------------------------
    allowed_repos_env = os.environ.get("ALLOWED_REPOS", "")
    if not allowed_repos_env:
        # Secure by default: if no whitelist is set, allow nothing.
        return {
            "status": "PERMISSION_DENIED",
            "details": "Server configuration error: ALLOWED_REPOS environment variable is not set. No paths are authorized."
        }

    allowed_paths = [p.strip().lower() for p in allowed_repos_env.split(",") if p.strip()]
    normalized_target = os.path.abspath(repo_path).lower()

    is_allowed = False
    for safe_path in allowed_paths:
        # Check if the target is the safe path or a subdirectory of it
        # We add os.sep to ensure /foo-bar doesn't match /foo
        safe_path_abs = os.path.abspath(safe_path).lower()
        if normalized_target == safe_path_abs or normalized_target.startswith(safe_path_abs + os.sep):
            is_allowed = True
            print(f"[AUDIT] Access GRANTED for path: {repo_path}")
            break
    
    if not is_allowed:
        print(f"[AUDIT] Access DENIED for path: {repo_path}")
        return {
            "status": "PERMISSION_DENIED",
            "details": f"Path '{repo_path}' is not in the ALLOWED_REPOS verify list."
        }

    if not os.path.exists(repo_path):
        return {
            "status": "ERROR",
            "details": f"Path does not exist: {repo_path}"
        }

    # Store original directory to switch back if needed, 
    # though usually for a tool run we might just run commands in that dir
    # rather than changing global process state which is risky in async.
    # However, to strictly follow the user's logic, we will run commands with cwd.
    
    commands = [
        ["pytest", "-q"],
        ["flake8", "."],
        ["bandit", "-r", "."]
    ]
    
    results = []
    failed = False
    
    for cmd in commands:
        try:
            # Using subprocess.run with cwd argument is safer than os.chdir
            # which affects the whole process
            result = subprocess.run(
                cmd, 
                cwd=repo_path,
                capture_output=True, 
                text=True,
                check=False
            )
            
            results.append({
                "command": " ".join(cmd),
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            })
            
            if result.returncode != 0:
                failed = True
                # The user's original logic returned early on failure.
                # We will preserve that behavior.
                return {
                    "status": "FAILED",
                    "details": results
                }
                
        except Exception as e:
             return {
                "status": "ERROR",
                "details": str(e)
            }

    return {
        "status": "PASSED",
        "details": results
    }

import copilot_agent.lib.infra as infra

@mcp.tool()
def setup_pages(repo_path: str, project_type: str = "html") -> dict:
    """
    Sets up GitHub Pages deployment for the repository.
    Generates a .github/workflows/pages.yml file.
    Enforces security by checking ALLOWED_REPOS.
    """
    # ---------------------------------------------------------
    # SECURITY: Whitelist Enforcement
    # ---------------------------------------------------------
    allowed_repos_env = os.environ.get("ALLOWED_REPOS", "")
    if not allowed_repos_env:
         return {
            "status": "PERMISSION_DENIED",
            "details": "Server configuration error: ALLOWED_REPOS environment variable is not set."
        }

    allowed_paths = [p.strip().lower() for p in allowed_repos_env.split(",") if p.strip()]
    normalized_target = os.path.abspath(repo_path).lower()
    
    is_allowed = False
    for safe_path in allowed_paths:
        safe_path_abs = os.path.abspath(safe_path).lower()
        if normalized_target == safe_path_abs or normalized_target.startswith(safe_path_abs + os.sep):
            is_allowed = True
            break
            
    if not is_allowed:
        return {
            "status": "PERMISSION_DENIED",
            "details": f"Path '{repo_path}' is not in the ALLOWED_REPOS verify list."
        }

    try:
        workflows_dir = os.path.join(repo_path, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        
        workflow_content = infra.generate_github_pages_workflow(project_type)
        target_file = os.path.join(workflows_dir, "pages.yml")
        
        with open(target_file, "w") as f:
            f.write(workflow_content)
            
        return {
            "status": "SUCCESS",
            "details": f"Created GitHub Pages workflow at {target_file}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "details": str(e)
        }

if __name__ == "__main__":
    mcp.run()

