import copilot_agent.lib.infra as infra

def generate_workflow(repo, language, build_cmd, test_cmd, deploy_target):
    # Check for GitHub Pages target
    if deploy_target == "github-pages":
        # infra.py expects "project_type", we map language to it
        return infra.generate_github_pages_workflow(language)

    repo_name = repo.split('/')[1] if '/' in repo else repo

    common_header = """
name: CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build-test-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

    language = (language or '').lower()

    if language in ['node', 'javascript', 'typescript']:  # Node.js
        setup = """
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Cache npm
        uses: actions/cache@v3
        with:
          path: ~/.npm
          key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
          restore-keys: ${{ runner.os }}-node-
      - name: Install dependencies
        run: npm ci
      - name: Security Scan
        run: npm audit
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
"""
    elif language in ['python']:  # Python
        setup = """
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Cache pip
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
          restore-keys: ${{ runner.os }}-pip-
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Security Scan
        run: |
          pip install bandit
          bandit -r .
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
"""
    elif language in ['dotnet', 'c#', 'csharp']:  # .NET
        setup = """
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'
      - name: Restore
        run: dotnet restore
      - name: Security Scan
        run: dotnet list package --vulnerable
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
"""
    elif language in ['java', 'maven', 'gradle']:  # Java
        setup = """
      - name: Setup Java
        uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '17'
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
"""
    else:  # Fallback generic
        setup = f"""
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
"""

    deploy = f"""
      - name: Deploy to {deploy_target}
        uses: azure/webapps-deploy@v2
        with:
          app-name: {repo_name}
          publish-profile: ${{{{ secrets.AZURE_PUBLISH_PROFILE }}}}
          package: .
"""

    return common_header + setup + deploy
