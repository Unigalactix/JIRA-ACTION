import os
import json
import asyncio
import re
from copilot_agent.lib.logger import setup_logger
from copilot_agent.lib.jira import search_issues, get_issue_details, transition_issue, post_jira_comment
from copilot_agent.lib.github import get_repo
from github import GithubException

logger = setup_logger("autopilot")

class Autopilot:
    def __init__(self, process_callback):
        self.process_callback = process_callback
        self.running = False
        self.interval = 60  # Default 60s
    
    async def start(self):
        """Start the background polling loop."""
        self.running = True
        logger.info("Autopilot started. Polling Jira for tasks...")
        while self.running:
            try:
                await self.poll_and_process()
            except Exception as e:
                logger.error(f"Autopilot loop error: {e}")
            
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False

    async def poll_and_process(self):
        """Fetch high priority tickets and process the first one found."""
        project_keys = os.getenv("JIRA_PROJECT_KEYS", "KAN").split(",")
        projects_jql = ",".join([f'"{k.strip()}"' for k in project_keys if k.strip()])
        
        # Fetch To Do items from all configured projects
        jql = f'project in ({projects_jql}) AND status = "To Do" ORDER BY priority DESC, created ASC'
        
        try:
            issues = search_issues(jql, max_results=100)
        except Exception as e:
            logger.warning(f"Failed to poll Jira: {e}")
            return

        if not issues:
            logger.debug("No 'To Do' tickets found.")
            return

        # Log summary of found tickets
        active_keys = [i.get("key") for i in issues]
        logger.info(f"Autopilot: Found {len(issues)} active tickets: {', '.join(active_keys)}")

        # Prioritize (Already sorted by JQL, but ensuring strict priority)
        # JQL "priority DESC" usually handles this, but let's be safe.
        prio_order = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}
        issues.sort(key=lambda x: prio_order.get((x.get("priority") or "Medium"), 2))

        # Pick the top one
        ticket = issues[0]
        logger.info(f"Autopilot: Locked on ticket {ticket['key']} ({ticket['priority']})")
        
        await self.process_ticket(ticket)

    async def process_ticket(self, ticket):
        issue_key = ticket["key"]
        
        # Transition to In Progress to lock it
        try:
            transition_issue(issue_key, "In Progress")
        except Exception as e:
            logger.warning(f"Could not transition {issue_key} to In Progress: {e}")
            # If we can't transition, we might be fighting another agent or user. Skip.
            return

        try:
            # 1. Fetch Details & Parse Context
            details = get_issue_details(issue_key)
            description = details.get("description") or ""
            
            config = self._parse_context(issue_key, description)
            
            # 2. Enrich with Auto-Detection (if needed)
            repo_name = config.get("repository")
            if not repo_name:
                raise ValueError(f"Could not determine Repository for {issue_key}. Please configure DEFAULT_REPO or add JSON to ticket.")
            
            owner, repo = repo_name.split("/")
            gh_repo = get_repo(owner, repo)
            
            # Detect Language
            if not config.get("language"):
                lang = gh_repo.language
                if lang:
                    config["language"] = lang.lower()
                    logger.info(f"Auto-detected language for {issue_key}: {config['language']}")
                else:
                    config["language"] = "python" # Fallback
            
            # Detect Deploy Target (Heuristic)
            if not config.get("deployTarget"):
                try:
                    # Check for index.html at root -> GitHub Pages
                    gh_repo.get_contents("index.html")
                    config["deployTarget"] = "github-pages"
                    logger.info(f"Auto-detected deploy target for {issue_key}: github-pages")
                except GithubException:
                    pass # Not found
                
                # Default to azure-webapps if still unknown
                # if not config.get("deployTarget"):
                #    config["deployTarget"] = "azure-webapps"
                pass # Use factory default (github-pages)

            # 3. Execute Job
            payload = {
                "issueKey": issue_key,
                "repository": repo_name,
                "language": config["language"],
                "deployTarget": config.get("deployTarget"),
                "buildCommand": config.get("buildCommand", "echo 'No build'"), # Defaults
                "testCommand": config.get("testCommand", "echo 'No test'")
            }
            
            logger.info(f"Autopilot executing job for {issue_key}: {json.dumps(payload)}")
            post_jira_comment(issue_key, f"Autopilot engaging.\nTarget: {repo_name}\nConfig: {json.dumps(payload, indent=2)}")
            
            # Call the app's processing logic (injected callback)
            # This needs to be async or run in thread if blocking. 
            # Assuming process_callback is async or fast.
            await self.process_callback(payload)
            
        except Exception as e:
            logger.error(f"Autopilot failed to process {issue_key}: {e}")
            post_jira_comment(issue_key, f"Autopilot failed: {e}")
            # Move back to To Do or stick in In Progress? 
            # Use 'In Review' to signal it needs human attention maybe?
            # Or leave in In Progress so we don't loop-fail it.

    def _parse_context(self, issue_key, description):
        """Extract config from JSON block or use Smart Defaults."""
        config = {}
        
        # 1. Try JSON Block
        json_match = re.search(r'```json\s*({.*?})\s*```', description, re.DOTALL)
        if json_match:
            try:
                config = json.loads(json_match.group(1))
                logger.info(f"Parsed JSON config from description for {issue_key}")
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON block in {issue_key}")

        # 2. Smart Defaults: Repository
        if not config.get("repository"):
            # Try Project-Specific Default
            project_key = issue_key.split("-")[0]
            env_key = f"DEFAULT_REPO_{project_key}"
            config["repository"] = os.getenv(env_key)
            
            # Fallback to Global Default
            if not config["repository"]:
                config["repository"] = os.getenv("DEFAULT_REPO")
        
        return config
