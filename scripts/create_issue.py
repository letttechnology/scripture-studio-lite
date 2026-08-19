import urllib.request, json, sys, os, argparse

def get_env_token():
    paths = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    ]
    for env_path in paths:
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('GH_TOKEN='):
                        return line.strip().split('=', 1)[1].strip('"\'')
    return None

def create_issue(title, body, repo_owner="letttechnology", repo_name="scripture-studio-lite", labels=None):
    token = get_env_token()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
    headers = {
        'User-Agent': 'Python-App',
        'Content-Type': 'application/json'
    }
    if token:
        headers['Authorization'] = f'token {token}'

    issue_data = {'title': title, 'body': body}
    if labels:
        issue_data['labels'] = labels

    payload = json.dumps(issue_data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            url_res = data.get('html_url')
            print(f"Successfully created issue #{data.get('number')}: {url_res}")
            return data
    except Exception as e:
        print(f"Error creating issue: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create GitHub Issue")
    parser.add_argument('--title', required=True, help="Issue title")
    parser.add_argument('--body', required=True, help="Issue body")
    parser.add_argument('--repo', default="scripture-studio-lite", help="Repository name")
    parser.add_argument('--owner', default="letttechnology", help="Repository owner")
    parser.add_argument('--labels', nargs='*', help="Issue labels")
    args = parser.parse_args()

    create_issue(args.title, args.body, repo_owner=args.owner, repo_name=args.repo, labels=args.labels)
