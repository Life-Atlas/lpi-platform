import os
import random
import uuid

import requests

# --- CONFIGURATION REQUIRED ---
# Point this to the local ingest endpoint (e.g., "http://localhost:8000/api/v1/signals/")
API_INGEST_URL = "http://localhost:8001/api/v1/signals/"

# JWT for the auth middleware — NEVER hardcode a token here (even a local
# one trains bad habits and trips secret scanners). Export it instead:
#   PowerShell: $env:LPI_TEST_JWT = "<token from supabase status / your login>"
#   bash:       export LPI_TEST_JWT=<token>
AUTH_TOKEN = os.environ.get("LPI_TEST_JWT", "")
if not AUTH_TOKEN:
    raise SystemExit("Set LPI_TEST_JWT env var before running this script.")

HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {AUTH_TOKEN}"}

SMILE_PHASES = [
    "reality-emulation",
    "concurrent-engineering",
    "collective-intelligence",
    "contextual-intelligence",
    "continuous-intelligence",
    "perpetual-wisdom",
]


def generate_and_post_events():
    if API_INGEST_URL == "<ENTER_API_URL_HERE>":
        print("❌ ERROR: Please update API_INGEST_URL at the top of the script before running.")
        return

    print(f"🔄 Targeting Activity Signals Ingest API at: {API_INGEST_URL}")

    event_types = [
        "goal_created",
        "goal_updated",
        "smile_phase_changed",
        "priority_updated",
        "goal_completed",
    ]

    print("🚀 Generating 20 structural platform telemetry signals to test the API...")

    success_count = 0
    fail_count = 0

    for i in range(20):
        event = random.choice(event_types)

        # Mocking a baseline goal context payload
        payload = {"goal_id": str(uuid.uuid4()), "title": f"Mock Integration Goal {i + 1}"}

        if event == "goal_created":
            payload.update(
                {"initial_priority": random.randint(4, 8), "initial_phase": "reality-emulation"}
            )
        elif event == "goal_updated":
            payload.update(
                {"updated_property": "description", "delta_length": random.randint(15, 120)}
            )
        elif event == "smile_phase_changed":
            current_phase_idx = random.randint(0, 4)
            payload.update(
                {
                    "old_phase": SMILE_PHASES[current_phase_idx],
                    "new_phase": SMILE_PHASES[current_phase_idx + 1],
                }
            )
        elif event == "priority_updated":
            payload.update(
                {
                    "previous_priority": random.randint(1, 5),
                    "target_priority": random.randint(6, 10),
                }
            )
        elif event == "goal_completed":
            payload.update(
                {
                    "terminal_phase": "perpetual-wisdom",
                    "achievement_metric": "completed_ahead_of_schedule",
                }
            )

        # Stripped of id, user_id, and timestamp as the server now handles them securely
        signal_entry = {
            "stream": "goal_registry",
            "event_type": event,
            "payload": payload,
            "source": "simulated",
        }

        try:
            response = requests.post(API_INGEST_URL, json=signal_entry, headers=HEADERS)

            if response.status_code in [200, 201]:
                print(f"✅ [SUCCESS] Sent '{event}' - API Responded: {response.status_code}")
                success_count += 1
            else:
                print(
                    f"❌ [FAILED] Sent '{event}' - API Responded: {response.status_code} - {response.text}"
                )
                fail_count += 1

        except Exception as e:
            print(f"⚠️ [CONNECTION ERROR] Could not reach API: {str(e)}")
            break

    print(
        f"\n🏁 API Testing Complete! Successful POSTs: {success_count} | Failed POSTs: {fail_count}"
    )


if __name__ == "__main__":
    generate_and_post_events()
