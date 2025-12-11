from mcp.server.fastmcp import FastMCP
import subprocess
import os
import requests
from copilot_agent.lib.logger import setup_logger

logger = setup_logger("mcp_server")

# Initialize FastMCP server
mcp = FastMCP("my-mcp-server")

# Security: Whitelist allowed paths
ALLOWED_REPOS = [p.strip() for p in os.environ.get("ALLOWED_REPOS", "").split(",") if p.strip()]

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
    normalized_repo = os.path.normpath(repo_path)
    if not any(normalized_repo.startswith(os.path.normpath(allowed.strip())) for allowed in ALLOWED_REPOS if allowed.strip()):
        logger.warning(f"Access denied for path: {repo_path}")
        return {
            "status": "PERMISSION_DENIED", 
            "error": f"Access to {repo_path} is not allowed. Allowed paths: {ALLOWED_REPOS}"
        }
    
    logger.info(f"Running agent tests on: {repo_path}")

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
    normalized_repo = os.path.normpath(repo_path)
    if not any(normalized_repo.startswith(os.path.normpath(allowed.strip())) for allowed in ALLOWED_REPOS if allowed.strip()):
        logger.warning(f"Access denied for setup_pages on path: {repo_path}")
        return {
            "status": "PERMISSION_DENIED",
            "details": f"Access to {repo_path} is not allowed."
        }

    logger.info(f"Setting up GitHub Pages {project_type} for: {repo_path}")
    
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

