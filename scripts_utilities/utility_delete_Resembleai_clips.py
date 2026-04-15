import os
import time
import requests
import json
from typing import List, Dict, Any

# --- Configuration Placeholders (Read from Environment or PyCharm Settings) ---
PROJECT_UUID_DEFAULT = "3333"  # <-- Update this with your actual Project UUID!

# --- Constants ---
API_BASE_URL = "https://app.resemble.ai/api/v2/projects"
PAGE_SIZE = 100
DELETE_DELAY_SECONDS = 0.1


def get_all_clip_uuids(project_uuid: str, api_key: str) -> List[str]:
    """
    Uses 'requests' to retrieve all clip UUIDs, explicitly targeting the 'items' key
    for clips and 'num_pages' for pagination, based on API response confirmation.
    """
    all_clip_uuids: List[str] = []
    page = 1
    total_pages = 1  # Will be updated by the first response

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    print(f"\nScanning Project: {project_uuid} for clips...")

    while page <= total_pages:
        try:
            url = f"{API_BASE_URL}/{project_uuid}/clips?page={page}&page_size={PAGE_SIZE}"

            # Use verify=False to ignore certificate issues
            response = requests.get(url, headers=headers, verify=False)

            if response.status_code == 200:
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    print(f"🛑 Error: Received non-JSON response. Body: {response.text[:100]}...")
                    break

                if data.get('success'):

                    # --- CRITICAL FIX ---
                    clips = data.get('items', [])  # Clips are under 'items'
                    total_pages = data.get('num_pages', 1)  # Pagination is directly available
                    # --------------------

                    current_uuids = [clip['uuid'] for clip in clips if 'uuid' in clip]

                    all_clip_uuids.extend(current_uuids)

                    print(
                        f"  Page {page}/{total_pages} retrieved ({len(current_uuids)} clips). Total found: {len(all_clip_uuids)}")

                    page += 1
                else:
                    error_msg = data.get('error', 'Unknown Error in JSON response')
                    print(f"🛑 Error retrieving clips on page {page}. API response: {error_msg}")
                    break
            else:
                print(f"🛑 Error retrieving clips on page {page}. HTTP Status: {response.status_code}")
                print(f"  Response Body: {response.text[:200]}...")
                break

        except requests.exceptions.RequestException as e:
            print(f"🛑 Fatal request error during clip retrieval: {e}")
            break
        except Exception as e:
            print(f"🛑 Unknown error during clip retrieval: {e}")
            break

    print(f"\nFound a total of {len(all_clip_uuids)} clips ready for deletion.")
    return all_clip_uuids


def delete_clips(project_uuid: str, clip_uuids: List[str], api_key: str):
    """
    Loops through the list of clip UUIDs and deletes each one using 'requests.delete'.
    """
    total_to_delete = len(clip_uuids)
    if total_to_delete == 0:
        print("No clips to delete. Done.")
        return

    print(f"\nStarting deletion of {total_to_delete} clips...")

    deleted_count = 0

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    for i, clip_uuid in enumerate(clip_uuids):
        try:
            url = f"{API_BASE_URL}/{project_uuid}/clips/{clip_uuid}"

            # Use requests.delete to send the DELETE request
            response = requests.delete(url, headers=headers, verify=False)

            if response.status_code == 200:
                deleted_count += 1
                print(f"  [SUCCESS] Deleted clip {i + 1}/{total_to_delete}: {clip_uuid}")
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', f"HTTP {response.status_code} Error")
                except json.JSONDecodeError:
                    error_msg = f"HTTP {response.status_code} Error (Non-JSON response)"

                print(f"  [FAILED!] Clip {i + 1}/{total_to_delete}: {clip_uuid}. Error: {error_msg}")

        except Exception as e:
            print(f"  [FAILED!] Clip {i + 1}/{total_to_delete}: {clip_uuid}. Exception: {e}")

        time.sleep(DELETE_DELAY_SECONDS)

    print(f"\n--- Deletion Summary ---")
    print(f"Total Clips Found: {total_to_delete}")
    print(f"Total Clips Deleted: {deleted_count}")
    print(f"Total Clips Failed: {total_to_delete - deleted_count}")
    print("------------------------")


def main():
    """Main execution function with safety check and configuration loading."""

    # 1. Load configuration from environment variables
    RESEMBLEAI_API_KEY = os.getenv("RESEMBLEAI_API_KEY")
    PROJECT_UUID = "57f17ce4"

    print("\n" + "#" * 50)
    print("## RESEMBLE.AI PROJECT CLIP DELETION SCRIPT ##")
    print("#" * 50)

    # 2. Check for required configuration
    if not RESEMBLEAI_API_KEY:
        print("\n🛑 ERROR: RESEMBLEAI_API_KEY environment variable not set.")
        print("Please set this in your PyCharm Run Configuration under 'Environment variables'.")
        return

    if PROJECT_UUID == PROJECT_UUID_DEFAULT:
        print(
            "\n⚠️ WARNING: PROJECT_UUID is set to the default placeholder. Please hardcode your target UUID in the script before running.")
        return

    # 3. Safety Check
    confirmation = input(
        f"\n🛑 WARNING: This will permanently delete ALL clips in project {PROJECT_UUID}."
        "\nType 'YES' to proceed with deletion: "
    )

    if confirmation.upper() != 'YES':
        print("\nAborted by user. No clips were deleted.")
        return

    # 4. Execution
    clip_list = get_all_clip_uuids(PROJECT_UUID, RESEMBLEAI_API_KEY)

    # Pass the API key to the delete function
    delete_clips(PROJECT_UUID, clip_list, RESEMBLEAI_API_KEY)


if __name__ == "__main__":
    main()