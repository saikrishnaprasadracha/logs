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

    for file in ["auth.properties", "api.properties", "authz.properties"]:
        load_file(file)

    return props

def load_logmap_properties():
    logmap_props = {}
    with open("logmap.properties", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            logmap_props[key.strip()] = value.strip()
    return logmap_props

# Load logmap.properties for SERVICE_LOG_PATHS
SERVICE_LOG_PATHS = load_logmap_properties()




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
# SERVICE_LOG_PATHS = {
#     key: value for key, value in config.items()
#     if key not in {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "GOOGLE_API_KEY", "AUTHORIZED_USERS"}
# }

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

    # Check for ##execute## pattern
    execute_pattern = r"##execute##\s*(.+)"
    execute_match = re.search(execute_pattern, user_input, re.IGNORECASE)
    
    if execute_match:
        # Handle direct command execution
        cmd_to_execute = execute_match.group(1).strip()
        
        if not is_team_member:
            say(f"{membership_msg}\n❌ <@{user}> Sorry, you do not have permission to execute commands.", thread_ts=thread_ts)
            return
        
        # Get root message if in thread
        root_message = ""
        if "thread_ts" in event and event["thread_ts"] != event["ts"]:
            try:
                replies = client.conversations_replies(channel=channel_id, ts=event["thread_ts"])
                root_message = replies["messages"][0]["text"] if replies["messages"] else ""
            except Exception as e:
                print(f"Could not retrieve root message: {e}")
        
        # Execute the command
        try:
            result = subprocess.run(cmd_to_execute, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout.strip() or result.stderr.strip() or "(No output)"
            max_len = 1500
            if len(output) > max_len:
                output = output[:max_len] + "\n...[output truncated]"
            
            response_text = f"{membership_msg}\n🖥️ <@{user}> Command `{cmd_to_execute}` executed:\n```\n{output}\n```"
            
            # Add root message context if available
            if root_message:
                response_text += f"\n\n📄 *Root message context:*\n```{root_message[:500]}{'...' if len(root_message) > 500 else ''}```"
            
            say(response_text, thread_ts=thread_ts)
            
        except Exception as e:
            say(f"{membership_msg}\n❌ <@{user}> Failed to execute command `{cmd_to_execute}`: {e}", thread_ts=thread_ts)
        
        return

    # Check for ##recommendation## pattern
    recommendation_pattern = r"##recommendation##\s*(.*)"
    recommendation_match = re.search(recommendation_pattern, user_input, re.IGNORECASE)
    
    if recommendation_match:
        # Handle recommendation request
        service_name = recommendation_match.group(1).strip()
        
        if service_name:
            # Show recommendations for specific service
            if service_name in PREDEFINED_COMMANDS:
                commands = PREDEFINED_COMMANDS[service_name]
                cmd_list = "\n".join(f"- `{cmd}`" for cmd in commands)
                say(f"{membership_msg}\n📋 <@{user}> Recommended commands for `{service_name}`:\n{cmd_list}", thread_ts=thread_ts)
            else:
                available_services = ", ".join(f"`{name}`" for name in PREDEFINED_COMMANDS.keys())
                say(f"{membership_msg}\n⚠️ <@{user}> Service `{service_name}` not found. Available services: {available_services}", thread_ts=thread_ts)
        else:
            # Show all recommendations
            all_recommendations = []
            for service, commands in PREDEFINED_COMMANDS.items():
                cmd_list = "\n".join(f"  - `{cmd}`" for cmd in commands)
                all_recommendations.append(f"**{service}:**\n{cmd_list}")
            
            recommendations_text = "\n\n".join(all_recommendations)
            say(f"{membership_msg}\n📋 <@{user}> All predefined command recommendations:\n\n{recommendations_text}", thread_ts=thread_ts)
        
        return

    # Original functionality continues below
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
