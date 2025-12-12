import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("copilot_agent/.env")

def log(msg):
    print(msg)
    with open("results.txt", "a") as f:
        f.write(msg + "\n")

def test_search():
    if os.path.exists("results.txt"):
        os.remove("results.txt")
        
    log("Testing Jira Search with JQL via /rest/api/3/search/jql...")
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    
    auth = (user_email, api_token)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    target_url = f"{base_url}/rest/api/3/search/jql"
    log(f"Target URL: {target_url}")

    # 1. Payload with 'query' (Original)
    log("\n[1] Testing payload with 'query' key...")
    payload_1 = {
        "query": 'project = "KAN"',
        "maxResults": 1,
        "fields": ["summary"]
    }
    try:
        resp = requests.post(target_url, json=payload_1, auth=auth, headers=headers)
        log(f"Status: {resp.status_code}")
        log(f"Response: {resp.text[:500]}")
    except Exception as e:
        log(f"Error: {e}")

    # 2. Payload with 'jql' key
    log("\n[2] Testing payload with 'jql' key...")
    payload_2 = {
        "jql": 'project = "KAN"',
        "maxResults": 1,
        "fields": ["summary"]
    }
    try:
        resp = requests.post(target_url, json=payload_2, auth=auth, headers=headers)
        log(f"Status: {resp.status_code}")
        log(f"Response: {resp.text[:500]}")
    except Exception as e:
        log(f"Error: {e}")

     # 3. Payload with 'jql' key and NO fields (minimal)
    log("\n[3] Testing payload with 'jql' key (minimal)...")
    payload_3 = {
        "jql": 'project = "KAN"'
    }
    try:
        resp = requests.post(target_url, json=payload_3, auth=auth, headers=headers)
        log(f"Status: {resp.status_code}")
        log(f"Response: {resp.text[:500]}")
    except Exception as e:
        log(f"Error: {e}")

if __name__ == "__main__":
    test_search()
