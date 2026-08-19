import urllib.request, json, sys, os

def get_env_token():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('GH_TOKEN='):
                    return line.strip().split('=', 1)[1].strip('"\'')
    return None

def create_issue(title, body, repo_owner="letttechnology", repo_name="interlinear-bible-tracker"):
    token = get_env_token()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
    headers = {
        'User-Agent': 'Python-App',
        'Content-Type': 'application/json'
    }
    if token:
        headers['Authorization'] = f'token {token}'

    payload = json.dumps({'title': title, 'body': body}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Successfully created issue #{data.get('number')}: {data.get('html_url')}")
            return data
    except Exception as e:
        print(f"Error creating issue: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    title = "Bug Report: Antigravity IDE CLI Environment Permission and PATH Failures"
    body = """### Summary
When executing CLI commands (`python`, `gh`) inside the Antigravity IDE environment, execution fails due to missing PATH definitions, OS file permission restrictions (`UnauthorizedAccessException`), and access denial on `C:\\Users\\blue1\\AppData\\Roaming\\GitHub CLI\\config.yml`.

### Error Logs
1. `python` command execution:
```
python : The term 'python' is not recognized as the name of a cmdlet, function, script file, or operable program.
```

2. `gh` CLI execution:
```
warning: failed to load config: open C:\\Users\\blue1\\AppData\\Roaming\\GitHub CLI\\config.yml: Access is denied.
failed to create root command: failed to read configuration: open C:\\Users\\blue1\\AppData\\Roaming\\GitHub CLI\\config.yml: Access is denied.
```

3. Direct Python binary invocation:
```
Access is denied (System.UnauthorizedAccessException)
```

4. API Network calls:
```
Post "https://api.github.com/graphql": context deadline exceeded
```

### Environment
- OS: Windows 10/11
- Agent: Google Antigravity AI Coder
- Workspace: d:\\workspace\\interlinear-bible-project
"""
    create_issue(title, body)
