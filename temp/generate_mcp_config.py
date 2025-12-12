import sys
import json
from pathlib import Path

# Add project root to sys.path so we can import from copilot_agent
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

from copilot_agent.lib.config_helper import generate_vs_code_config

def main():
    root_dir = Path(__file__).parent.parent
    
    config = generate_vs_code_config(root_dir)
    
    if "error" in config:
        print(f"Error: {config['error']}")
        return

    # Output
    print("\n" + "="*50)
    print("GENERATED MCP CONFIGURATION FOR VS CODE / GITHUB COPILOT")
    print("="*50)
    print("Add this to your VS Code MCP settings (settings.json or vs-code-mcp-settings.json):")
    print(json.dumps(config, indent=2))
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
