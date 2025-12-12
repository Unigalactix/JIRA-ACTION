import os
import json
import asyncio
import re
from copilot_agent.lib.logger import setup_logger
from copilot_agent.lib.jira import search_issues, get_issue_details, transition_issue, post_jira_comment, get_issue_comments
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
                await self.check_in_review_tickets()
            except Exception as e:
                logger.error(f"Autopilot loop error: {e}")
            
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False

    async def poll_and_process(self):
        """Fetch high priority tickets and process the first one found."""
        project_keys_env = os.getenv("JIRA_PROJECT_KEYS")
        
        jql = ""
        if project_keys_env and project_keys_env.upper() != "ALL":
            project_keys = project_keys_env.split(",")
            projects_jql = ",".join([f'"{k.strip()}"' for k in project_keys if k.strip()])
            jql = f'project in ({projects_jql}) AND status = "To Do" ORDER BY priority DESC, created ASC'
        else:
            # Query all projects
            jql = 'status = "To Do" ORDER BY priority DESC, created ASC'
        
        try:
            logger.debug(f"Polling Jira with JQL: {jql}")
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
            return

        try:
            # 1. Fetch Details & Parse Context
            details = get_issue_details(issue_key)
            description = details.get("description") or ""
            
            config = self._parse_context(issue_key, description)
            
            # 2. Enrich with Auto-Detection (if needed)
            repo_name = config.get("repository")
            if not repo_name:
                default_repo = os.getenv("DEFAULT_REPO")
                logger.error(f"Failed to determine repository. DEFAULT_REPO env var is: '{default_repo}'")
                raise ValueError(f"Could not determine Repository for {issue_key}. Please configure DEFAULT_REPO in .env or add JSON to ticket.")
            
            owner, repo = repo_name.split("/")
            gh_repo = get_repo(owner, repo)
            
            # Detect Language
            # Map GitHub language to our internal keys
            lang_map = {
                "c#": "dotnet",
                "csharp": "dotnet",
                "javascript": "node",
                "typescript": "node",
                "python": "python",
                "java": "java"
            }

            if not config.get("language"):
                lang = gh_repo.language
                if lang:
                    normalized = lang.lower()
                    config["language"] = lang_map.get(normalized, normalized) # Default to raw name if no map
                    logger.info(f"Auto-detected language for {issue_key}: {lang} -> {config['language']}")
                else:
                    config["language"] = "python" # Fallback
            
            # Detect Deploy Target (Heuristic)
            # Default to github-pages if not specified, unless overridden
            if not config.get("deployTarget"):
                config["deployTarget"] = "github-pages"
                # Check if we should switch to azure? 
                # User asked: "SET DEPLOY TARGET TO GITHUB PAGES BY DEFAULT"
                # We can still check for index.html purely for logging but default is set.
                try:
                    gh_repo.get_contents("index.html")
                    logger.info(f"Confirmed static site (index.html found) for {issue_key}")
                except GithubException:
                    pass 

            # 3. Execute Job
            payload = {
                "issueKey": issue_key,
                "repository": repo_name,
                "language": config["language"],
                "deployTarget": config.get("deployTarget"),
                # Remove defaults so workflow_factory uses its smart defaults
                "buildCommand": config.get("buildCommand"), 
                "testCommand": config.get("testCommand")
            }
            
            logger.info(f"Autopilot executing job for {issue_key}: {json.dumps(payload)}")
            post_jira_comment(issue_key, f"Autopilot engaging.\nTarget: {repo_name}\nConfig: {json.dumps(payload, indent=2)}")
            
            await self.process_callback(payload)
            
        except Exception as e:
            logger.error(f"Autopilot failed to process {issue_key}: {e}")
            post_jira_comment(issue_key, f"Autopilot failed: {e}")

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
                if config["repository"]:
                     logger.info(f"Using Global DEFAULT_REPO: {config['repository']}")
        
        return config

    async def check_in_review_tickets(self):
        """Watchdog: Check status of tickets in 'In Review'."""
        try:
            # Find tickets in 'In Review'
            project_keys_env = os.getenv("JIRA_PROJECT_KEYS")
            jql = ""
            if project_keys_env and project_keys_env.upper() != "ALL":
                project_keys = project_keys_env.split(",")
                projects_jql = ",".join([f'"{k.strip()}"' for k in project_keys if k.strip()])
                jql = f'project in ({projects_jql}) AND status = "In Review"'
            else:
                 jql = 'status = "In Review"'

            issues = search_issues(jql, max_results=20)
            if not issues:
                return

            for issue in issues:
                await self.check_ticket_status(issue["key"])
                
        except Exception as e:
            logger.warning(f"Watchdog error: {e}")

    async def check_ticket_status(self, issue_key):
        """Check if linked PR is merged."""
        try:
            comments = get_issue_comments(issue_key)
            pr_url = None
            
            # Find PR URL in comments
            # Looking for "View PR" link or similar
            for c in reversed(comments):
                # Simple regex or string find
                match = re.search(r'https://github.com/([^/]+)/([^/]+)/pull/(\d+)', c["body"])
                if match:
                    pr_url = match.group(0)
                    owner, repo, pr_number = match.group(1), match.group(2), match.group(3)
                    
                    # check status
                    gh_repo = get_repo(owner, repo)
                    pr = gh_repo.get_pull(int(pr_number))
                    
                    if pr.merged:
                        logger.info(f"Watchdog: PR {pr_number} for {issue_key} is MERGED. Transitioning to Done.")
                        post_jira_comment(issue_key, f"Pull Request #{pr_number} merged! Task complete.")
                        transition_issue(issue_key, "Done")
                    elif pr.state == 'closed':
                        logger.info(f"Watchdog: PR {pr_number} for {issue_key} is CLOSED but NOT merged.")
                        # Optional: Transition back to To Do?
                    else:
                        logger.debug(f"Watchdog: PR {pr_number} for {issue_key} is {pr.state}.")
                    return # Found latest PR, stop checking comments
            
        except Exception as e:
             logger.warning(f"Watchdog failed for {issue_key}: {e}")
