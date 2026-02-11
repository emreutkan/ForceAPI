import subprocess
import os
import json
import sys

# Configuration
VENV_PYTHON = os.path.join("venv", "Scripts", "python.exe")
OUTPUT_FILE = "datadump_clean.json"

def run_dump():
    print(f"--- Generating Migration Dump from SQLite ---")

    # 1. Force UTF-8 for this session (fixes emoji/💪 issues)
    os.environ["PYTHONUTF8"] = "1"

    # 2. Build the command
    # We exclude contenttypes and auth.Permission to avoid EC2 conflicts
    cmd = [
        VENV_PYTHON, "manage.py", "dumpdata",
        "--natural-foreign",
        "--natural-primary",
        "--indent", "4",
        "-e", "contenttypes",
        "-e", "auth.Permission"
    ]

    try:
        print("Executing dumpdata...")
        # Run command and capture output
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error during dump: {stderr}")
            return

        # 3. Clean and Save the data
        # We load it into a Python object first to ensure the JSON is valid
        data = json.loads(stdout)
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"--- SUCCESS ---")
        print(f"File created: {OUTPUT_FILE}")
        print("You can now SCP this file to your EC2 instance.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    run_dump()