def generate_workflow(repo, language, build_cmd, test_cmd, deploy_target):
    return f"""
name: CI/CD Pipeline

on:
  push:
    branches: [ main ]

jobs:
  build-test-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup {language}
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm install
      - name: Build
        run: {build_cmd}
      - name: Test
        run: {test_cmd}
      - name: Deploy to {deploy_target}
        uses: azure/webapps-deploy@v2
        with:
          app-name: {repo.split('/')[1]}
          publish-profile: ${{{{ secrets.AZURE_PUBLISH_PROFILE }}}}
          package: .
"""
