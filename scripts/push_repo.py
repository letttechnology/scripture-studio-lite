import os
import subprocess
from dotenv import load_dotenv

load_dotenv('D:/workspace/scripture-studio/.env')
token = os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')

if token:
    remote_url = f"https://x-access-token:{token}@github.com/letttechnology/scripture-studio-lite.git"
    res = subprocess.run(['git', 'push', remote_url, 'main'], capture_output=True, text=True)
    if res.returncode == 0:
        print("Git push completed successfully.")
    else:
        print("Git push error:", res.stderr)
else:
    print("No token found in .env")
