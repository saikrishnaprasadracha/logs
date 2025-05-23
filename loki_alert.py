import random
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Your Slack tokens
app_token = "xapp-1-A08TAM80J7R-8943817507682-5889a163ff916fb8775d803e02e067eb642a89d1670e0ff66a9d650a3029e0ae"
slack_bot_token = "xoxb-8918255900677-8954258226385-OrJMizGriHW51l6Nvge0kOCW"

# Slack channel ID where alerts will be sent
channel_id = "C08T07J3D37"

# Initialize Slack app
app = App(token=slack_bot_token)

# Simulated logs (replace this with real logs if needed)
logs = [
    "ERROR: Connection to database failed after 3 attempts.",
    "WARNING: Disk usage exceeded 85% on server xyz.",
    "ERROR: Null pointer exception in module `user-handler`.",
    "INFO: Background sync completed successfully.",
    "WARNING: High memory usage detected in pod `ml-worker-4`.",
    "ERROR: Failed to fetch response from external API - timeout after 30s.",
]

# Pick a random error or warning
log_entry = random.choice([log for log in logs if "ERROR" in log or "WARNING" in log])

# Send alert when the script is run
def send_alert_on_start():
    app.client.chat_postMessage(channel=channel_id, text=f":rotating_light: *ALERT*: {log_entry}")

# Optional: Respond when mentioned in Slack
@app.event("app_mention")
def handle_mention(event, say):
    say(f":rotating_light: *Manual Alert Triggered*: {log_entry}")

if __name__ == "__main__":
    # Send alert immediately
    send_alert_on_start()

    # Start listening for mentions (optional)
    handler = SocketModeHandler(app, app_token)
    handler.start()
