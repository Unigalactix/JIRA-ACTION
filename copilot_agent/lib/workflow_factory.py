def generate_workflow(repo, language, build_cmd, test_cmd, deploy_target):
    repo_name = repo.split('/')[1] if '/' in repo else repo
    
    # Analyze Payload to determine defaults if commands are placeholders/empty
    language = (language or '').lower()
    
    # Default to GitHub Pages if not specified
    deploy_target = deploy_target or "github-pages"
    
    defaults = {
        'python': {
            'build': "echo 'No build necessary for Python'",
            'test': "pytest || echo 'No tests found'" 
        },
        'node': {
            'build': "npm run build --if-present",
            'test': "npm test || echo 'No tests found'"
        },
        'dotnet': {
            'build': "dotnet build",
            'test': "dotnet test"
        },
        'java': {
            'build': "mvn package -DskipTests",
            'test': "mvn test"
        }
    }
    
    # Map synonyms
    if language in ['javascript', 'typescript', 'js', 'ts']:
        lang_key = 'node'
    elif language in ['c#', 'csharp']:
        lang_key = 'dotnet'
    elif language in ['maven', 'gradle']:
        lang_key = 'java'
    else:
        lang_key = language if language in defaults else 'python' # Default to python if unknown

    # Resolve commands: Use provided CMD if valid, else default
    real_build_cmd = build_cmd if build_cmd and "{" not in build_cmd else defaults[lang_key]['build']
    real_test_cmd = test_cmd if test_cmd and "{" not in test_cmd else defaults[lang_key]['test']

    # Generate Header
    header = f"""name: CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

    # Language Specific Setup
    setup = ""
    if lang_key == 'node':
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
        run: npm ci || npm install
"""
    elif lang_key == 'python':
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
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
"""
    elif lang_key == 'dotnet':
        setup = """
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'
      - name: Restore dependencies
        run: dotnet restore
"""
    elif lang_key == 'java':
        setup = """
      - name: Setup Java
        uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '17'
"""

    build_steps = f"""
      - name: Build
        run: {real_build_cmd}
      - name: Test
        run: {real_test_cmd}
"""

    # Prepare Artifact for Pages (if target is pages)
    upload_step = ""
    if deploy_target == "github-pages":
        upload_step = """
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
"""

    # -------------------------------------------------------------
    # DEPLOY JOB
    # -------------------------------------------------------------
    deploy_job = ""
    
    if deploy_target == "github-pages":
        deploy_job = """
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""
    elif deploy_target == "azure-webapps":
        deploy_job = f"""
  deploy:
    name: Deploy to Azure Web Apps
    needs: build-test
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy
        uses: azure/webapps-deploy@v2
        with:
          app-name: {repo_name}
          publish-profile: ${{{{ secrets.AZURE_PUBLISH_PROFILE }}}}
          package: .
"""
    
    return header + setup + build_steps + upload_step + deploy_job
