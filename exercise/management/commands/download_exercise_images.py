"""
Download exercise images from the free-exercise-db repo.
Uses exercise_list.json (same as populate_exercises). Run after populate_exercises
so the JSON exists, or use a fixture. No standalone script needed — manage.py does it.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify


REMOTE_DB_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
REMOTE_IMAGE_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"


class Command(BaseCommand):
    help = "Download exercise images from free-exercise-db. Requires exercise_list.json (run populate_exercises first if needed)."

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        json_path = os.path.join(base_dir, "exercise_list.json")
        media_root = os.path.join(settings.MEDIA_ROOT, "exercises") if hasattr(settings, "MEDIA_ROOT") else os.path.join(base_dir, "media", "exercises")

        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"exercise_list.json not found at {json_path}. Run populate_exercises first (or ensure the file exists)."))
            return

        with open(json_path, "r", encoding="utf-8") as f:
            local_exercises = json.load(f)

        self.stdout.write("Fetching remote exercise DB...")
        try:
            req = urllib.request.Request(REMOTE_DB_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                remote_db = json.loads(resp.read().decode())
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch remote DB: {e}"))
            return

        remote_map = {}
        for item in remote_db:
            if "name" in item:
                remote_map[self._normalize(item["name"])] = item
        self.stdout.write(f"Loaded {len(remote_map)} remote exercises.")

        os.makedirs(media_root, exist_ok=True)
        success = 0
        fail = 0

        for exercise in local_exercises:
            name = exercise.get("name", "")
            if not name:
                continue
            slug = slugify(name)
            match = self._find_match(name, remote_map)
            if not match:
                self.stdout.write(f"No match for '{name}'")
                fail += 1
                continue
            images = match.get("images", [])
            if not images:
                fail += 1
                continue
            image_name = images[0]
            ext = os.path.splitext(image_name)[1]
            target_path = os.path.join(media_root, f"{slug}{ext}")
            url = f"{REMOTE_IMAGE_BASE}{urllib.parse.quote(image_name)}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as resp:
                    with open(target_path, "wb") as out:
                        out.write(resp.read())
                success += 1
                self.stdout.write(f"Downloaded: {name}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed {name}: {e}"))
                fail += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Downloaded {success} images, failed/skipped {fail}."))

    @staticmethod
    def _normalize(name):
        return re.sub(r"[^\w\s]", "", name.lower()).strip()

    def _find_match(self, local_name, remote_map):
        norm = self._normalize(local_name)
        if norm in remote_map:
            return remote_map[norm]
        local_tokens = set(norm.split())
        best_match, best_score = None, 0
        for remote_name, data in remote_map.items():
            remote_tokens = set(remote_name.split())
            inter = local_tokens.intersection(remote_tokens)
            if not inter:
                continue
            score = len(inter) / len(local_tokens.union(remote_tokens))
            if score > best_score:
                best_score, best_match = score, data
        return best_match if best_score > 0.6 else None
