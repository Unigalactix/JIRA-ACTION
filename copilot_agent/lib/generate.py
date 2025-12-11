import os
import sys
import json
import uuid
# Adjust path to import from lib
sys.path.append(os.getcwd())
from copilot_agent.lib.jira import get_issue_details
from copilot_agent.lib.github import apply_text_patches

def main():
    issue_key = os.getenv("ISSUE_KEY")
    repo_full = os.getenv("REPOSITORY")
    
    if not issue_key or not repo_full:
        print("Error: ISSUE_KEY and REPOSITORY env vars required.")
        sys.exit(1)

    owner, repo = repo_full.split("/")

    print(f"Fetching details for {issue_key}...")
    try:
        details = get_issue_details(issue_key)
        summary = details.get("summary") or "Automated fix"
        description = (details.get("description") or "").strip()
    except Exception as e:
        print(f"Failed to fetch Jira details: {e}")
        # Build logic might continue or fail depending on requirements. 
        # For now, let's treat description as empty if failed.
        description = ""

    print(f"Processing agent instructions from description...")
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
        print("No specific 'find/replace' instructions found. Agent execution finished with no changes.")
        # In a real agent, this might invoke an LLM. Here we simulate the "Agent Step".
        # We will create a dummy file to prove the agent ran if no instructions were found.
        changes.append({
            "path": f"agent_trace_{uuid.uuid4().hex[:6]}.txt", 
            "find": "", 
            "replace": f"Agent ran for {issue_key} at {uuid.uuid4()}"
        })

    # Apply changes locally? 
    # The workflow asks to "Commit + push".
    # Since we are running in the runner, we can modify files directly in the checkout directory.
    # The `apply_text_patches` lib uses PyGithub to commit to a REMOTE branch.
    # The workflow wants: 
    # 1. Custom Agent Step (generate artifacts)
    # 2. github-script Create feature branch
    # 3. github-script Commit + push
    
    # So this script should just modify the files on disk (in the runner).
    # We will re-implement a local patcher here instead of using the PyGithub lib which does API commits.
    
    for ch in changes:
        path = ch["path"]
        print(f"Modifying {path}...")
        
        # Ensure dir exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        
        content = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            # If finding something in a new file, assume empty start
            pass
            
        find_text = ch.get("find", "")
        replace_text = ch.get("replace", "")
        
        if find_text:
            new_content = content.replace(find_text, replace_text)
        else:
            # If no find text behavior (append? overwrite?)
            # For this simple logic, if file didn't exist, we write replace_text
            # If file exists and find is empty, we append? Let's just overwrite for safety or append if specified.
            # User request didn't specify strict logic, assume simple replacement.
            new_content = replace_text
            
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    
    print("Agent generation complete.")

if __name__ == "__main__":
    main()
