import os
import json
import random
from PIL import Image, ImageDraw, ImageFont
from django.utils.text import slugify
import sys

# Add project root to path
sys.path.append(os.getcwd())

def generate_placeholder(text, filename):
    # Create a new image with a random pastel background color
    color = (
        random.randint(220, 255),
        random.randint(220, 255),
        random.randint(220, 255)
    )
    img = Image.new('RGB', (400, 400), color=color)
    d = ImageDraw.Draw(img)

    # Try to load a font, fallback to default
    try:
        # Try finding arial on Windows
        font = ImageFont.truetype("arial.ttf", 30)
    except IOError:
        font = ImageFont.load_default()

    # Simple text wrapping
    words = text.split()
    lines = []
    current_line = []

    # wrap text logic
    for word in words:
        test_line = ' '.join(current_line + [word])
        # approximate width check (char count is a rough proxy if font metrics unavailable)
        if len(test_line) > 20:
             lines.append(' '.join(current_line))
             current_line = [word]
        else:
            current_line.append(word)
    if current_line:
        lines.append(' '.join(current_line))

    # Draw centered text
    # Start y position roughly centered
    y = 200 - (len(lines) * 20)

    for line in lines:
        # Get bounding box
        bbox = d.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        d.text(((400 - w) / 2, y), line, fill=(50, 50, 50), font=font)
        y += h + 10

    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    img.save(filename)
    print(f"Generated {filename}")

def main():
    try:
        with open('exercise_list.json', 'r') as f:
            exercises = json.load(f)
    except FileNotFoundError:
        print("exercise_list.json not found!")
        return

    # Select first 10 exercises + some popular ones
    selected_exercises = exercises[:15]

    target_names = ["Barbell Deadlift", "Barbell Squat", "Bench Press", "Push-ups", "Pull-ups"]
    for name in target_names:
        found = next((e for e in exercises if e['name'].lower() == name.lower()), None)
        if found and found not in selected_exercises:
            selected_exercises.append(found)

    media_root = os.path.join(os.getcwd(), 'media', 'exercises')

    count = 0
    for exercise in selected_exercises:
        name = exercise['name']
        # Match the model's upload_to logic: slugified name + extension
        slug = slugify(name)
        filename = os.path.join(media_root, f"{slug}.jpg")
        generate_placeholder(name, filename)
        count += 1

    print(f"Successfully generated {count} placeholder images in {media_root}")

if __name__ == "__main__":
    main()
