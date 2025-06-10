import os
import re
import subprocess
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# --- 🔧 Load multiple .properties files ---
def load_all_properties():
    props = {}

    def load_file(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()

    for file in ["auth.properties", "authz.properties"]:
        load_file(file)

    return props

# --- 📁 Load Config ---
config = load_all_properties()

SLACK_BOT_TOKEN = config["SLACK_BOT_TOKEN_execute"]
SLACK_APP_TOKEN = config["SLACK_APP_TOKEN_execute"]
AUTHORIZED_USERS = set(uid.strip() for uid in config.get("AUTHORIZED_USERS", "").split(",") if uid.strip())

# --- 🚀 Init Slack app ---
app = App(token=SLACK_BOT_TOKEN)

# --- 📦 Command execution handler ---
@app.event("app_mention")
def handle_execute(event, say, client):
    user = event["user"]
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    text = event.get("text", "")
    user_input = text.split(">", 1)[-1].strip()

    if user not in AUTHORIZED_USERS:
        say(f"❌ <@{user}> You are not authorized to run commands.", thread_ts=thread_ts)
        return

    if not user_input:
        say(f"⚠️ <@{user}> Please provide a command to run after `@execute`.", thread_ts=thread_ts)
        return

    # 🆕 Extract service name from user input like: dir #service-name
    service_match = re.search(r"#([a-zA-Z0-9_\-]+)", user_input)
    if service_match:
        service_name = service_match.group(1)
        user_input = re.sub(r"#([a-zA-Z0-9_\-]+)", "", user_input).strip()
    else:
        # Fallback to extract from root message if not specified
        try:
            replies = client.conversations_replies(channel=channel_id, ts=thread_ts)
            root_message = replies["messages"][0]["text"] if replies["messages"] else ""
            match = re.search(r"-\s*([a-zA-Z0-9\-]+)$", root_message)
            if not match:
                say(f"⚠️ <@{user}> Couldn't extract service name from message or user input.", thread_ts=thread_ts)
                return
            service_name = match.group(1)
        except Exception as e:
            say(f"⚠️ <@{user}> Failed to retrieve the service name: {e}", thread_ts=thread_ts)
            return

    # ▶️ Run the command
    try:
        result = subprocess.run(user_input, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip() or result.stderr.strip() or "(No output)"
        if len(output) > 1500:
            output = output[:1500] + "\n...[output truncated]"

        say(f"✅ <@{user}> Command executed for service `{service_name}`:\n```\n{output}\n```", thread_ts=thread_ts)
    except Exception as e:
        say(f"❌ <@{user}> Failed to run command `{user_input}`: {e}", thread_ts=thread_ts)

# --- 🏁 Start the app ---
if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
