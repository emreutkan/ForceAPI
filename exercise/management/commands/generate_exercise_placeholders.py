"""
Generate placeholder images for exercises (from exercise_list.json).
Replaces scripts/generate_placeholders.py — use: manage.py generate_exercise_placeholders.
"""
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify


class Command(BaseCommand):
    help = "Generate placeholder images for exercises. Requires exercise_list.json and Pillow (pip install Pillow)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=15,
            help="Max number of exercises from start of list (default: 15).",
        )
        parser.add_argument(
            "--extra",
            nargs="*",
            default=["Barbell Deadlift", "Barbell Squat", "Bench Press", "Push-ups", "Pull-ups"],
            help="Extra exercise names to include (default: common exercises).",
        )

    def handle(self, *args, **options):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self.stdout.write(
                self.style.ERROR("Pillow is required. Run: pip install Pillow")
            )
            return

        base_dir = settings.BASE_DIR
        json_path = os.path.join(base_dir, "exercise_list.json")
        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"exercise_list.json not found at {json_path}"))
            return

        with open(json_path, "r", encoding="utf-8") as f:
            exercises = json.load(f)

        limit = options["limit"]
        extra_names = options["extra"] or []
        selected = list(exercises[:limit])
        for name in extra_names:
            found = next((e for e in exercises if e["name"].lower() == name.lower()), None)
            if found and found not in selected:
                selected.append(found)

        media_root = os.path.join(settings.MEDIA_ROOT, "exercises") if hasattr(settings, "MEDIA_ROOT") else os.path.join(base_dir, "media", "exercises")
        os.makedirs(media_root, exist_ok=True)

        count = 0
        for exercise in selected:
            name = exercise["name"]
            slug = slugify(name)
            filename = os.path.join(media_root, f"{slug}.jpg")
            self._generate_one(name, filename, Image, ImageDraw, ImageFont)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Generated {count} placeholder images in {media_root}"))

    def _generate_one(self, text, filename, Image, ImageDraw, ImageFont):
        color = (
            random.randint(220, 255),
            random.randint(220, 255),
            random.randint(220, 255),
        )
        img = Image.new("RGB", (400, 400), color=color)
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 30)
        except OSError:
            font = ImageFont.load_default()

        words = text.split()
        lines = []
        current = []
        for word in words:
            test = " ".join(current + [word])
            if len(test) > 20:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))

        y = 200 - (len(lines) * 20)
        for line in lines:
            bbox = d.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            d.text(((400 - w) / 2, y), line, fill=(50, 50, 50), font=font)
            y += h + 10

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        img.save(filename)
        self.stdout.write(f"Generated {filename}")
