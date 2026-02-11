#!/usr/bin/env python
"""Cross-platform startup script for Django server."""
import os
import sys
import platform
import subprocess
from pathlib import Path


def is_windows():
    """Check if running on Windows."""
    return platform.system() == 'Windows'

def venv_exists():
    """Check if virtual environment exists."""
    venv_path = Path('venv')
    if is_windows():
        return (venv_path / 'Scripts' / 'python.exe').exists()
    else:
        return (venv_path / 'bin' / 'python').exists()

def create_venv():
    """Create virtual environment and install requirements."""
    print("Creating virtual environment...")
    subprocess.run([sys.executable, '-m', 'venv', 'venv'], check=True)
    
    venv_python = get_venv_python()
    req_file = Path('requirements.txt')
    
    if req_file.exists():
        print(f"Installing dependencies from {req_file}...")
        # Use -m pip to ensure we use the venv's pip
        subprocess.run([str(venv_python), '-m', 'pip', 'install', '-r', str(req_file)], check=True)
    else:
        print("Warning: requirements.txt not found. Skipping installation.")
def get_venv_python():
    """Get the path to the venv Python interpreter."""
    venv_path = Path('venv')
    if is_windows():
        return venv_path / 'Scripts' / 'python.exe'
    else:
        return venv_path / 'bin' / 'python'

def run_server():
    """Run the Django development server."""
    # Check/create venv
    if not venv_exists():
        create_venv()
    else:
        print("Virtual environment found!")
    
    # Get venv Python
    venv_python = get_venv_python()
    
    # Build command
    if is_windows():
  
        cmd = [str(venv_python), 'manage.py', 'runserver', '192.168.1.2:8000']
    else:
        cmd = [str(venv_python), 'manage.py', 'runserver']
    
    # Run the server
    subprocess.run(cmd)

if __name__ == '__main__':
    run_server()

