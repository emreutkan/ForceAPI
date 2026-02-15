import sys
import re
import json
import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
import time

# Try to import slugify, fallback to simple version if not found
try:
    from django.utils.text import slugify
except ImportError:
    import re
    def slugify(value):
        value = str(value)
        value = re.sub(r'[^\w\s-]', '', value.lower())
        return re.sub(r'[-\s]+', '-', value).strip('-_')

# Configuration
LOCAL_EXERCISES_PATH = 'exercise_list.json'
REMOTE_DB_URL = 'https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json'
REMOTE_IMAGE_BASE_URL = 'https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/'
MEDIA_ROOT = os.path.join(os.getcwd(), 'media', 'exercises')

def fetch_remote_db():
    print(f"Fetching remote database from {REMOTE_DB_URL}...")
    try:
        with urllib.request.urlopen(REMOTE_DB_URL) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching remote DB: {e}")
        return []

def load_local_exercises():
    print(f"Loading local exercises from {LOCAL_EXERCISES_PATH}...")
    try:
        with open(LOCAL_EXERCISES_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Local exercise list not found.")
        return []

def download_image(image_name, target_path):
    # Encode the image name for URL
    url = f"{REMOTE_IMAGE_BASE_URL}{urllib.parse.quote(image_name)}"
    try:
        # User-Agent is often required key for GitHub raw content to avoid 403 sometimes,
        # though usually raw.githubusercontent is fine. Adding just in case.
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(target_path, 'wb') as out_file:
                out_file.write(response.read())
        return True
    except urllib.error.HTTPError as e:
        # print(f"    Failed to download {image_name}: {e.code}")
        return False
    except Exception as e:
        print(f"    Error downloading {image_name}: {e}")
        return False

def normalize_name(name):
    return re.sub(r'[^\w\s]', '', name.lower()).strip()

def find_best_match(local_name, remote_map):
    norm_local = normalize_name(local_name)

    # 1. Exact match (normalized)
    if norm_local in remote_map:
        return remote_map[norm_local]

    # 2. Token overlap match
    local_tokens = set(norm_local.split())
    best_match = None
    best_score = 0

    for remote_name, data in remote_map.items():
        remote_tokens = set(remote_name.split())

        # Calculate Jaccard similarity or simple overlap
        intersection = local_tokens.intersection(remote_tokens)
        if not intersection:
            continue

        score = len(intersection) / len(local_tokens.union(remote_tokens))

        # Boost score if the "core" movement name is present?
        # Too complex for now, just simple overlap

        if score > best_score:
            best_score = score
            best_match = data

    # Threshold for acceptance?
    if best_score > 0.6: # fairly strict to avoid wrong images
        # print(f"    Fuzzy match: '{local_name}' -> '{best_match['name']}' (Score: {best_score:.2f})")
        return best_match

    return None

def main():
    # Ensure media directory exists
    os.makedirs(MEDIA_ROOT, exist_ok=True)

    remote_db = fetch_remote_db()
    if not remote_db:
        print("Could not load remote database. Exiting.")
        return

    local_exercises = load_local_exercises()
    if not local_exercises:
        return

    # Create a mapping of remote exercises (normalized name -> data)
    remote_map = {}
    for item in remote_db:
        if 'name' in item:
            remote_map[normalize_name(item['name'])] = item

    print(f"Loaded {len(remote_map)} remote exercises.")

    success_count = 0
    fail_count = 0

    for exercise in local_exercises:
        name = exercise.get('name', '')
        if not name:
            continue

        slug = slugify(name)
        # target match
        match = find_best_match(name, remote_map)

        if match:
             images = match.get('images', [])
             if images:
                 image_source = images[0] # Take first image
                 ext = os.path.splitext(image_source)[1]
                 target_filename = f"{slug}{ext}"
                 target_path = os.path.join(MEDIA_ROOT, target_filename)

                 print(f"Downloading for '{name}' -> '{match['name']}' : {image_source}...")
                 if download_image(image_source, target_path):
                     success_count += 1
                 else:
                     fail_count += 1
             else:
                 print(f"No images found in remote DB for matched '{match['name']}'")
                 fail_count += 1
        else:
            print(f"No match found for '{name}'")
            fail_count += 1

    print(f"\nDone. Downloaded {success_count} images. Failed/Skipped {fail_count}.")

if __name__ == "__main__":
    main()
