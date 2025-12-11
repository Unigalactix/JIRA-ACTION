import requests
import json
import os
from copilot_agent.lib.logger import setup_logger

logger = setup_logger("jira")


def post_jira_comment(issue_key, text, link_text=None, link_url=None):
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')

    if not base_url or not user_email or not api_token:
        raise RuntimeError("Jira environment variables are not set: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")

    url = f"{base_url}/rest/api/3/issue/{issue_key}/comment"
    auth = (user_email, api_token)
    headers = {"Content-Type": "application/json"}

    # Construct ADF paragraph content
    paragraph_content = [{"type": "text", "text": text}]
    
    if link_text and link_url:
        # Add a space before the link if text exists
        if text:
            paragraph_content.append({"type": "text", "text": " "})
        
        paragraph_content.append({
            "type": "text", 
            "text": link_text,
            "marks": [{"type": "link", "attrs": {"href": link_url}}]
        })

    # Use Atlassian Document Format to avoid 400s on strict Jira setups
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": paragraph_content
                }
            ]
        }
    }

    resp = requests.post(url, json=payload, auth=auth, headers=headers)
    try:
        resp.raise_for_status()
        logger.info(f"Posted comment to {issue_key}: {text[:50]}...")
    except requests.HTTPError as e:
        # Surface response text for easier debugging
        logger.error(f"Failed to post comment to {issue_key}: {resp.status_code} {resp.text}")
        raise requests.HTTPError(f"Jira comment failed: {resp.status_code} {resp.text}") from e


def get_transitions(issue_key):
    """Return available transitions for an issue with id and name."""
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    if not base_url or not user_email or not api_token:
        raise RuntimeError("Jira environment variables are not set: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")

    url = f"{base_url}/rest/api/3/issue/{issue_key}/transitions"
    auth = (user_email, api_token)
    headers = {"Accept": "application/json"}
    resp = requests.get(url, auth=auth, headers=headers)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f"Jira get transitions failed: {resp.status_code} {resp.text}") from e
    data = resp.json()
    return [{"id": t.get("id"), "name": t.get("name")} for t in data.get("transitions", [])]


def transition_issue(issue_key, target_status_name):
    """Transition an issue to a target status by name."""
    transitions = get_transitions(issue_key)
    match = next((t for t in transitions if (t.get("name") or "").lower() == target_status_name.lower()), None)
    if not match:
        raise ValueError(f"No transition named '{target_status_name}' available for issue {issue_key}. Available: {[t['name'] for t in transitions]}")

    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    url = f"{base_url}/rest/api/3/issue/{issue_key}/transitions"
    auth = (user_email, api_token)
    headers = {"Content-Type": "application/json"}
    payload = {"transition": {"id": match["id"]}}
    resp = requests.post(url, json=payload, auth=auth, headers=headers)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f"Jira transition failed: {resp.status_code} {resp.text}") from e
    return {"issueKey": issue_key, "status": target_status_name}


def get_issue_details(issue_key):
    """Fetch Jira issue summary and description."""
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    if not base_url or not user_email or not api_token:
        raise RuntimeError("Jira environment variables are not set: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")

    url = f"{base_url}/rest/api/3/issue/{issue_key}"
    auth = (user_email, api_token)
    headers = {"Accept": "application/json"}
    resp = requests.get(url, auth=auth, headers=headers)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f"Jira issue fetch failed: {resp.status_code} {resp.text}") from e
    data = resp.json()
    fields = data.get("fields", {})
    summary = fields.get("summary")
    description = fields.get("description")
    # Description may be in ADF; flatten simple text when possible
    desc_text = None
    if isinstance(description, dict) and description.get("content"):
        try:
            parts = []
            for block in description.get("content", []):
                for item in block.get("content", []):
                    if item.get("text"):
                        parts.append(item["text"])
            desc_text = "\n".join(parts) if parts else None
        except Exception:
            desc_text = None
    elif isinstance(description, str):
        desc_text = description
    return {"summary": summary, "description": desc_text}


def search_issues(jql: str, max_results: int = 20):
    """Search Jira issues and return key, summary, status, priority, assignee."""
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    if not base_url or not user_email or not api_token:
        raise RuntimeError("Jira environment variables are not set: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")

    url = f"{base_url}/rest/api/3/search"
    auth = (user_email, api_token)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": ["summary", "status", "priority", "assignee"]
    }
    resp = requests.post(url, json=payload, auth=auth, headers=headers)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f"Jira search failed: {resp.status_code} {resp.text}") from e
    out = []
    for i in resp.json().get("issues", []):
        f = i.get("fields", {})
        out.append({
            "key": i.get("key"),
            "summary": f.get("summary"),
            "status": (f.get("status") or {}).get("name"),
            "priority": (f.get("priority") or {}).get("name"),
            "assignee": (f.get("assignee") or {}).get("displayName"),
            "url": f"{base_url}/browse/{i.get('key')}"
        })
    return out
