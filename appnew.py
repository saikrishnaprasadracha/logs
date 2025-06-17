import os
import re
import subprocess
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from google import genai

# --- 🔧 Load config from multiple .properties files ---
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

    for file in ["auth.properties", "api.properties", "authz.properties", "logmap.properties"]:
        load_file(file)

    return props

# --- 🛠️ Predefined Commands by Service Tag ---
PREDEFINED_COMMANDS = {
    "auth-service": [
        "cd ..",
        "ls -l"
    ],
    "payment-service": [
        "whoami",
        "ls -l"
    ],
    "user-service": [
        "ls",
        "pwd"
    ],
    "demo-app-service": [
        "ls",
        "pwd"
    ]
}

# --- 📁 Load configurations ---
config = load_all_properties()

SLACK_BOT_TOKEN = config["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = config["SLACK_APP_TOKEN"]
GOOGLE_API_KEY = config["GOOGLE_API_KEY"]
AUTHORIZED_USERS = set(uid.strip() for uid in config.get("AUTHORIZED_USERS", "").split(",") if uid.strip())

# Extract only service log mappings
SERVICE_LOG_PATHS = {
    key: value for key, value in config.items()
    if key not in {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "GOOGLE_API_KEY", "AUTHORIZED_USERS"}
}

# --- 🚀 Init Slack app ---
app = App(token=SLACK_BOT_TOKEN)

# --- 🧠 Init Gemini client ---
genai_client = genai.Client(api_key=GOOGLE_API_KEY)

# --- 📢 Mention handler ---
@app.event("app_mention")
def handle_mention(event, say, client):
    user = event["user"]
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    text = event.get("text", "")
    user_input = text.split(">", 1)[-1].strip()

    is_team_member = user in AUTHORIZED_USERS
    membership_msg = f"👋 <@{user}> You are {'part of' if is_team_member else 'NOT part of'} the team."

    if not user_input or user_input.lower() in ["null", "none"]:
        available_services = "\n".join(f"- `{name}`" for name in SERVICE_LOG_PATHS)
        say(f"{membership_msg}\nHere is the list of services you have access to:\n{available_services}", thread_ts=thread_ts)
        return

    if "thread_ts" not in event or event["thread_ts"] == event["ts"]:
        say(f"{membership_msg}\n⚠️ <@{user}> Please reply to an alert message thread so I can analyze it.", thread_ts=thread_ts)
        return

    try:
        replies = client.conversations_replies(channel=channel_id, ts=event["thread_ts"])
        root_message = replies["messages"][0]["text"] if replies["messages"] else ""
    except Exception as e:
        say(f"⚠️ <@{user}> Could not retrieve the root message: {e}", thread_ts=thread_ts)
        return

    try:
        # Step 1: Extract service name from alert
        service_extraction_prompt = f"""
Extract only the service name from the following alert message.

Alert:
{root_message}

Output only the service name, nothing else.
"""
        first_response = genai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=service_extraction_prompt
        )
        service_name = first_response.text.strip()
        print(f"🧩 Extracted service: {service_name}")

        log_path = SERVICE_LOG_PATHS.get(service_name)
        if not log_path or not os.path.exists(log_path):
            say(f"{membership_msg}\n⚠️ <@{user}> Log file not found for service: `{service_name}`", thread_ts=thread_ts)
            return

        # Step 2: Read logs
        with open(log_path, "r", encoding="utf-8") as f:
            logs = f.read()[-20000:]

        # Step 3: Analyze alert using Gemini
        final_prompt = f"""
You are a helpful debugging assistant.

An alert was raised:
{root_message}

The user asked:
{user_input}

Logs from the service `{service_name}`:
{logs}

Instructions:
1. Check if the log content contains any error or trace that matches the alert message.
2. If there is a match, explain the exact connection between the alert and the logs.
3. If there is no match, still analyze the logs and report any issues, but mention that the alert seems unrelated to the logs.
4. Your output should include:
   - Whether the alert matches the logs
   - If matched, describe the root cause
   - If not matched, still summarize any other visible errors or warnings
"""
        final_response = genai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=final_prompt
        )
        summary = final_response.text.strip()

        # Step 4: Use predefined commands
        predefined_cmds = PREDEFINED_COMMANDS.get(service_name, [])

        # Step 5: Respond with explanation and commands
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Service:* `{service_name}`\n*Alert:* `{root_message}`\n\n*Summary:*\n```{summary}```"
                }
            }
        ]

        if predefined_cmds:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Select an action to run (click to execute):*"}
            })
            for i, cmd in enumerate(predefined_cmds):
                label = f"Run: {cmd[:40]}{'...' if len(cmd) > 40 else ''}"
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": label},
                            "value": cmd,
                            "action_id": f"run_command_{i}"
                        }
                    ]
                })

        say(
            text=f"{membership_msg}\n🧠 <@{user}> here's the analysis and available actions:",
            thread_ts=thread_ts,
            blocks=blocks
        )

    except Exception as e:
        say(f"❌ <@{user}> Error occurred: {e}", thread_ts=thread_ts)

# --- ▶️ Command run handler ---
@app.action(re.compile(r"run_command_\d+"))
def handle_run_command(ack, body, say):
    ack()
    cmd = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    thread_ts = body["message"].get("thread_ts", body["message"]["ts"])

    if user_id not in AUTHORIZED_USERS:
        say(f"❌ <@{user_id}> Sorry, you do not have permission to run shell commands.", thread_ts=thread_ts)
        return

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip() or result.stderr.strip() or "(No output)"
        max_len = 1500
        if len(output) > max_len:
            output = output[:max_len] + "\n...[output truncated]"

        say(f"🖥️ <@{user_id}> Command `{cmd}` executed:\n```\n{output}\n```", thread_ts=thread_ts)
    except Exception as e:
        say(f"❌ <@{user_id}> Failed to execute command `{cmd}`: {e}", thread_ts=thread_ts)

# --- ▶️ Start the app ---
if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
