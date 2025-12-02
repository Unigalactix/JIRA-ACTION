import requests
import os


def post_jira_comment(issue_key, text):
    base_url = os.getenv('JIRA_BASE_URL')
    user_email = os.getenv('JIRA_USER_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')

    if not base_url or not user_email or not api_token:
        raise RuntimeError("Jira environment variables are not set: JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN")

    url = f"{base_url}/rest/api/3/issue/{issue_key}/comment"
    auth = (user_email, api_token)
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, json={"body": text}, auth=auth, headers=headers)
    resp.raise_for_status()
