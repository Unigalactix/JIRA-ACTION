"""
Configuration constants and settings for the application.
"""
import os

# Timing Configuration
AUTOPILOT_INTERVAL_SECONDS = int(os.getenv("AUTOPILOT_INTERVAL_SECONDS", "60"))
DASHBOARD_POLL_INTERVAL_MS = int(os.getenv("DASHBOARD_POLL_INTERVAL_MS", "3000"))
CI_CHECK_INTERVAL_SECONDS = int(os.getenv("CI_CHECK_INTERVAL_SECONDS", "30"))
MILLISECONDS_PER_SECOND = 1000

# GitHub Configuration
COPILOT_USERNAME = os.getenv("COPILOT_USERNAME", "copilot")

# Jira Configuration
JIRA_KEY_PATTERN = os.getenv("JIRA_KEY_PATTERN", r'\b([A-Z]{2,10}-\d+)\b')

# Dashboard Configuration
MAX_ERROR_COUNT = 5
MAX_POLL_INTERVAL_MS = 30000
