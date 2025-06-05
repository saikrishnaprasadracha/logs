import time
import re
import shutil
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# --- 🔐 Slack Config ---
SLACK_BOT_TOKEN = ""
CHANNEL_ID = "C08U5B1A64C"

client = WebClient(token=SLACK_BOT_TOKEN)

# --- 🔍 Regex for alert and log request detection ---
alert_pattern = re.compile(r":rotating_light:\s+\*ALERT\*:\s+ERROR:.*?-.*", re.IGNORECASE)
log_request_pattern = re.compile(r"(LOG REQUEST|SHOW LOG|STATUS):\s*([a-zA-Z0-9_-]+)", re.IGNORECASE)

# --- ⏱️ Start from now ---
last_ts = str(time.time())

# --- 🗂️ Mapping of service to source file paths ---
service_files = {
    "demo-app-service": "D:/client_4/test/apifail.log",
    "auth-service": "D:/client_4/test/sync.log",
    "user-service": "D:/client_4/test/usernull.log"
}

# --- 📁 Destination directory for logs ---
destination_folder = "D:/client_4/check"
os.makedirs(destination_folder, exist_ok=True)

# --- 🛠️ Extract service tag from alert text ---
def extract_service(text):
    match = re.search(r"-\s*([a-zA-Z0-9_-]+)\s*$", text)
    if match:
        return match.group(1)
    return "Unknown"

# --- 📥 Move file from source to destination ---
def copy_service_log(service_tag):
    src = service_files.get(service_tag)
    if not src:
        print(f"⚠️ No file mapped for service: {service_tag}")
        return
    dest = os.path.join(destination_folder, f"{service_tag}.log")
    try:
        shutil.copy(src, dest)
        print(f"📁 Copied: {src} → {dest}")
    except Exception as e:
        print(f"❌ Error copying file for {service_tag}: {e}")

# --- 📡 Poll Slack for new alerts and requests ---
def poll_channel():
    global last_ts
    try:
        response = client.conversations_history(channel=CHANNEL_ID, limit=10)
        messages = response.get("messages", [])

        for message in reversed(messages):
            ts = message.get("ts")
            text = message.get("text", "")

            if ts > last_ts:
                # 🚨 ALERT pattern
                if alert_pattern.search(text):
                    service = extract_service(text)
                    print(f"🚨 ALERT detected: {text}")
                    print(f"🔧 Service: {service}")
                    copy_service_log(service)

                # 📄 LOG REQUEST pattern
                else:
                    match = log_request_pattern.search(text)
                    if match:
                        service = match.group(2)
                        print(f"📄 LOG REQUEST detected: {text}")
                        print(f"📂 Requested Service: {service}")
                        copy_service_log(service)

                last_ts = ts

    except SlackApiError as e:
        print("Slack API error:", e)

# --- 🔁 Loop and monitor ---
if __name__ == "__main__":
    print("🔁 Monitoring channel for alerts and log requests...")
    while True:
        poll_channel()
        time.sleep(10)
