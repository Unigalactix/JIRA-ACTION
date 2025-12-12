
import os
import sys

# Add parent directory to path so we can import copilot_agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from copilot_agent.lib.jira import search_issues
from dotenv import load_dotenv

load_dotenv("copilot_agent/.env")

def verify():
    print("Verifying copilot_agent.lib.jira.search_issues...")
    try:
        issues = search_issues('project="KAN"', max_results=1)
        print(f"Success! Found {len(issues)} issues.")
        for i in issues:
            print(f"- {i['key']}: {i['summary']}")
    except Exception as e:
        print(f"FAILED: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Server Response: {e.response.text}")

if __name__ == "__main__":
    verify()
