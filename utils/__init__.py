import os
import json

# Folder where all event JSONs will be stored
BASE_DIR = "event_data"

def get_event_path(event_id):
    """
    Get the full path to the event.json file for a given event_id.
    Creates the directory if it doesn't exist.
    """
    dir_path = os.path.join(BASE_DIR, str(event_id))
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "event.json")


def load_event(event_id):
    """
    Load the event data from the JSON file.
    Returns an empty dict if the file doesn't exist or is corrupted.
    """
    path = get_event_path(event_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Could not decode JSON for event {event_id} - {e}")
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
