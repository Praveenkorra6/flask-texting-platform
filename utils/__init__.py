import os
import json
import re
import pandas as pd

# Folder where all event JSONs will be stored
BASE_DIR = "event_data"

def normalize_us_number(raw):
    if pd.isna(raw):
        return None
    num = re.sub(r'\D', '', str(raw))
    if len(num) == 10:
        return '+1' + num
    elif len(num) == 11 and num.startswith('1'):
        return '+' + num
    return None


def get_event_path(event_id):
    """
    Get the full path to the event.json file for a given event_id.
    Creates the directory if it doesn't exist.
    """
    dir_path = os.path.join(BASE_DIR, str(event_id))
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "event.json")


def load_event(event_id):
    path = get_event_path(event_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.startswith("b'") or content.startswith('b"'):
                    print(f"Corrupted content found in {event_id}, deleting.")
                    os.remove(path)
                    return {}
                return json.loads(content)
        except Exception as e:
            print(f"[load_event error] {e}")
            os.remove(path)  # cleanup
            return {}
    return {}



def save_event(event_id, data):
    """
    Save the given data dict as JSON for the given event_id.
    """
    path = get_event_path(event_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def lock_event(event_id):
    """
    Mark the event as committed (locked).
    """
    data = load_event(event_id)
    data['committed'] = True
    save_event(event_id, data)


def is_event_locked(event_id):
    """
    Check if the event is already committed.
    """
    data = load_event(event_id)
    return data.get('committed', False)
