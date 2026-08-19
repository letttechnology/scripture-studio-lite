import urllib.request, json, sys, os

def get_env_token():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('GH_TOKEN='):
                    return line.strip().split('=', 1)[1].strip('"\'')
    return None

def fetch_issue(repo_owner, repo_name, issue_num):
    token = get_env_token()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_num}"
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Python-App')
    if token:
        req.add_header('Authorization', f'token {token}')
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Issue #{data.get('number')}: {data.get('title')}")
            print(f"State: {data.get('state')}")
            print(f"Body:\n{data.get('body')}")
    except Exception as e:
        print(f"Error fetching issue: {e}", file=sys.stderr)

if __name__ == '__main__':
    issue_id = sys.argv[1] if len(sys.argv) > 1 else '52'
    fetch_issue('letttechnology', 'interlinear-bible-tracker', issue_id)
