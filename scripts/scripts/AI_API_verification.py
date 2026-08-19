import os
import time
import requests
from dotenv import load_dotenv

# Load variables from the .env file in the current directory
load_dotenv()

# Function to dynamically generate an OAuth2 Access Token for Vertex AI
def get_vertex_token():
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        print(f"[!] Could not fetch Vertex AI OAuth token: {e}")
        return None

# Get current GCP settings
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip()
LOCATION = os.getenv("GCP_LOCATION", "us-central1").strip()


# ==============================================================================
# PROVIDERS CONFIGURATION (Reads keys directly from os.getenv)
# ==============================================================================
PROVIDERS = [
    # {
    #     "name": "Groq",
    #     "url": "https://api.groq.com/openai/v1/chat/completions",
    #     "api_key": os.getenv("GROQ_API_KEY"),
    #     "model": "llama-3.3-70b-versatile",
    # },
    # {
    #     "name": "OpenRouter (Free Auto-Router)",
    #     "url": "https://openrouter.ai/api/v1/chat/completions",
    #     "api_key": os.getenv("OPENROUTER_API_KEY"),
    #     "model": "openrouter/free",  # <-- Automatically picks available free models
    # },
    # {
    #     "name": "Mistral AI",
    #     "url": "https://api.mistral.ai/v1/chat/completions",
    #     "api_key": os.getenv("MISTRAL_API_KEY"),
    #     "model": "open-mistral-nemo",
    # },
    # {
    #     "name": "Google AI Studio",
    #     "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    #     "api_key": os.getenv("GOOGLE_API_KEY"),
    #     "model": "gemini-3.5-flash",
    # },

    ### requires fee might be worth it for prod 
    # {
    #     "name": "OpenAI",
    #     "url": "https://api.openai.com/v1/chat/completions",
    #     "api_key": os.getenv("OPENAI_API_KEY"),
    #     "model": "gpt-4o-mini",
    # },
    # {
    #         "name": "Together AI",
    #         "url": "https://api.together.xyz/v1/chat/completions",
    #         "api_key": os.getenv("TOGETHER_API_KEY"),
    #         "model": "Qwen/Qwen3.5-9B",  # Active model on Together AI
    #     },
    # {
    #         "name": "Cerebras",
    #         "url": "https://api.cerebras.ai/v1/chat/completions",
    #         "api_key": os.getenv("CEREBRAS_API_KEY"),
    #         "model": "gemma-4-31b",
    #     },
]

# Add a safety check to prevent sending empty project URLs
if PROJECT_ID:
    PROVIDERS.append({
        "name": "Google Cloud Vertex AI",
        "url": f"https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/openapi/chat/completions",
        "api_key": get_vertex_token(),
        "model": "google/gemini-3.5-flash",
    })
else:
    print("[!] Skipped Vertex AI: GCP_PROJECT_ID is missing from .env")

USER_PROMPT = "Explain what rate limits are in one short sentence."
# ==============================================================================


def query_provider(provider: dict, prompt: str) -> None:
    name = provider["name"]
    url = provider["url"]
    api_key = provider["api_key"]
    model = provider["model"]

    print(f"\n==================================================")
    print(f" Testing Provider: {name} ({model})")
    print(f"==================================================")

    # If the key is missing from the .env file, skip this provider
    if not api_key:
        print(f"[!] Skipped: No API key found for '{name}' in .env file.")
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        headers_dict = response.headers

        # Extract standard rate limit headers
        rem_requests = (
            headers_dict.get("x-ratelimit-remaining-requests")
            or headers_dict.get("x-ratelimit-remaining")
            or "N/A"
        )
        rem_tokens = headers_dict.get("x-ratelimit-remaining-tokens", "N/A")
        reset_tokens = headers_dict.get("x-ratelimit-reset-tokens", "N/A")

        print(f"--> HTTP Status: {response.status_code}")
        print(f"--> Remaining Requests: {rem_requests}")
        print(f"--> Remaining Tokens:   {rem_tokens}")

        # ----------------------------------------------------------------------
        # HANDLE RATE LIMITS (HTTP 429)
        # ----------------------------------------------------------------------
        if response.status_code == 429:
            retry_after = headers_dict.get(
                "retry-after", reset_tokens.replace("s", "")
            )
            try:
                wait_time = float(retry_after)
            except ValueError:
                wait_time = 2.0

            print(f"[!] Rate Limit Hit (429)! Waiting {wait_time}s to retry...")
            time.sleep(wait_time)
            return query_provider(provider, prompt)

        # ----------------------------------------------------------------------
        # HANDLE ERRORS OR PRINT SUCCESS
        # ----------------------------------------------------------------------
        if response.status_code != 200:
            print(f"[X] Request Failed: {response.text}")
            return

        data = response.json()
        ai_message = data["choices"][0]["message"]["content"]

        print(f"\n[Response from {name}]:")
        print(ai_message.strip())

    except Exception as e:
        print(f"[X] Error contacting {name}: {e}")


def main():
    print(f"Starting multi-provider test from .env file...")
    for provider in PROVIDERS:
        query_provider(provider, USER_PROMPT)


if __name__ == "__main__":
    main()