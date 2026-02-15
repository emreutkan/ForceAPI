#!/bin/bash
set -e

echo "Starting UTrack Docker Bootstrap"

# 1. Clean up Manual Installation (bootstrap.sh) if it was set up before
echo "Cleaning up Manual services to avoid port conflicts..."
sudo systemctl stop utrack || true
sudo systemctl disable utrack || true
sudo systemctl stop nginx || true
sudo systemctl disable nginx || true

# Stop host Postgres if exists since we are using Docker Postgres on 5432
sudo systemctl stop postgresql || true

# 2. Set variables
PROJECT_DIR="/home/ubuntu/utrack-backend"
REPO_URL="https://github.com/emreutkan/utrack-be"

# 3. Install Docker and Docker Compose
echo "Installing Docker engine..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common git

# Add Docker's official GPG key & repository
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# 4. Manage Permissions
# Allow 'ubuntu' user to run docker without sudo
sudo usermod -aG docker ubuntu

# 5. Setup Project Directory
echo "Setting up project directory..."
if [ ! -d "$PROJECT_DIR" ]; then
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown ubuntu:ubuntu "$PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
else
    echo "Repository already exists..."
fi

cd "$PROJECT_DIR"

# 6. Create required directories for Volumes
# This prevents Docker from creating them as 'root' later
mkdir -p staticfiles media logs

# 7. Create initial .env for Docker
# Note: DB_HOST is 'db' (the docker service name), not 'localhost'
echo "Creating initial .env file..."
cat > .env <<EOF
SECRET_KEY=$SECRET_KEY
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgres://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS
LOCALHOST=${LOCALHOST:-False}
APPLE_KEY_ID=$APPLE_KEY_ID
APPLE_TEAM_ID=$APPLE_TEAM_ID
APPLE_CLIENT_ID=$APPLE_CLIENT_ID
APPLE_PRIVATE_KEY=$APPLE_PRIVATE_KEY
DEPLOY_HOST=$DEPLOY_HOST
EOF

echo "Docker Bootstrap complete!"
echo "NOTE: You may need to log out and log back in (or restart SSH) for docker group changes to take effect."