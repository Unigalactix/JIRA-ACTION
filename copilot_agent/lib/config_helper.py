import os
import json
from pathlib import Path

def generate_vs_code_config(root_dir: Path) -> dict:
    """
    Generates the VS Code MCP configuration dictionary by merging
    the template with environment variables.
    """
    env_path = root_dir / "copilot_agent" / ".env"
    template_path = root_dir / "mcp_config_template.json"
    
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    
    if not template_path.exists():
        return {"error": f"Template not found at {template_path}"}

    # Read template
    with open(template_path, 'r') as f:
        config = json.load(f)
    
    # Inject variables
    atlassian_env = config.get("mcpServers", {}).get("atlassian", {}).get("env", {})
    for key, value in atlassian_env.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            if var_name in env_vars:
                atlassian_env[key] = env_vars[var_name]
            elif var_name in os.environ:
                 atlassian_env[key] = os.environ[var_name]
            # else leave as is or set to empty? keeping as is allows user to see what's missing
    
    return config
