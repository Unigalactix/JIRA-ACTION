import yaml
import os

def generate_github_pages_workflow(project_type="html") -> str:
    """
    Generates a GitHub Actions workflow for deploying to GitHub Pages.
    """
    workflow = {
        "name": "Deploy to GitHub Pages",
        "on": {
            "push": {
                "branches": ["main"]
            },
            "workflow_dispatch": {}
        },
        "permissions": {
            "contents": "read",
            "pages": "write",
            "id-token": "write"
        },
        "concurrency": {
            "group": "pages",
            "cancel-in-progress": False
        },
        "jobs": {
            "deploy": {
                "environment": {
                    "name": "github-pages",
                    "url": "${{ steps.deployment.outputs.page_url }}"
                },
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"name": "Checkout", "uses": "actions/checkout@v4"},
                    {"name": "Setup Pages", "uses": "actions/configure-pages@v5"},
                    {"name": "Upload artifact", "uses": "actions/upload-pages-artifact@v3", "with": {"path": "."}},
                    {"name": "Deploy to GitHub Pages", "id": "deployment", "uses": "actions/deploy-pages@v4"}
                ]
            }
        }
    }
    
    # Simple customization based on type
    if project_type == "node":
         # Add node build steps if needed, for now standard static serve is safe default for simple React builds outputting to build/
         # This is a basic template.
         pass

    return yaml.dump(workflow, sort_keys=False)
