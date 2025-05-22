import re
import requests
from requests.auth import HTTPBasicAuth
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from google import genai

# --- Config: Replace these values ---
SLACK_BOT_TOKEN = "xxxxxxxxxxx"
SLACK_APP_TOKEN = "xxxxxxxxxxx"
GOOGLE_API_KEY = "xxxxxxxxxxxx"

LOKI_USER = "1213619"
LOKI_PASS = "glc_eyJvIjoiMTQyODE5MyIsIm4iOiJyZWFkLWxva2ktcmVhZCIsImsiOiI1Nzg4MjZjdjk4Q0MycVFoSkhOOGF2R1EiLCJtIjp7InIiOiJ1cyJ9fQ=="
LOKI_URL = "https://logs-prod-028.grafana.net/loki/api/v1/query_range"

# --- Known containers ---
CONTAINERS = ["jovial_booth", "loving_chatelet"]
DEFAULT_CONTAINER = "jovial_booth"

# --- Initialize Clients ---
genai_client = genai.Client(api_key=GOOGLE_API_KEY)
app = App(token=SLACK_BOT_TOKEN)

# --- Detect container name from text ---
def detect_container(text):
    for container in CONTAINERS:
        if container in text:
            return container
    return DEFAULT_CONTAINER

# --- Fetch logs from Loki without time or line limits ---
def fetch_loki_logs(container_name):
    params = {
        "query": f'{{container_name="{container_name}"}}',
        "direction": "BACKWARD"
    }

    response = requests.get(LOKI_URL, params=params, auth=HTTPBasicAuth(LOKI_USER, LOKI_PASS))

    if response.status_code != 200:
        return f"[Error fetching logs] Status: {response.status_code} {response.text}"

    data = response.json()
    streams = data.get("data", {}).get("result", [])

    if not streams:
        return "[No logs found]"

    logs = []
    for stream in streams:
        for entry in stream.get("values", []):
            _, log_line = entry
            logs.append(log_line)

    return "\n".join(logs)

# --- Handle Slack mentions ---
@app.event("app_mention")
def handle_mention(event, say):
    user = event["user"]
    text = event["text"]
    cleaned_text = text.split(">", 1)[-1].strip()

    try:
        # Detect container
        container_name = detect_container(cleaned_text)

        # Fetch logs
        logs = fetch_loki_logs(container_name)

        # Gemini prompt
        prompt = f"""You are a helpful debugging assistant.

Container: `{container_name}`

Here are the latest logs:
{logs}

Now, based on the logs and this user question, provide helpful insight:
{cleaned_text}
"""

        # Gemini response
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt]
        )

        say(f"<@{user}> {response.text}")

    except Exception as e:
        say(f"<@{user}> Something went wrong: {e}")

# --- Start Slack Bot ---
if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
