#!/bin/bash
set -e

echo "Starting UTrack Bootstrap"

# Top of your manual bootstrap.sh
echo "Cleaning up Docker to make room for Manual installation..."
sudo systemctl stop docker || true
docker compose down || true

# 1. Set variables
PROJECT_DIR="/home/ubuntu/utrack-backend"
REPO_URL="https://github.com/emreutkan/utrack-be"

# 2. Install system dependencies
echo "Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib git libpq-dev python3-dev nginx

# 3. Clone repository
echo "Setting up project directory..."
if [ ! -d "$PROJECT_DIR" ]; then
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown ubuntu:ubuntu "$PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
else
    echo "Repository already exists, skipping clone..."
fi

cd "$PROJECT_DIR"

# 4. Create venv
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3.12 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn psycopg2-binary

# 5. Handle Secrets
echo "Creating initial .env file..."
cat > .env <<EOF
SECRET_KEY=$SECRET_KEY
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DB_HOST=localhost
DB_PORT=5432
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS
APPLE_KEY_ID=$APPLE_KEY_ID
APPLE_TEAM_ID=$APPLE_TEAM_ID
APPLE_CLIENT_ID=$APPLE_CLIENT_ID
APPLE_PRIVATE_KEY=$APPLE_PRIVATE_KEY
DEPLOY_HOST=$DEPLOY_HOST
LOCALHOST=${LOCALHOST:-False}
EOF

# 6. Setup PostgreSQL database
echo "Setting up PostgreSQL database..."
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$POSTGRES_DB"; then
    sudo -u postgres psql <<EOF
CREATE DATABASE $POSTGRES_DB;
CREATE USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';
ALTER ROLE $POSTGRES_USER SET client_encoding TO 'utf8';
ALTER ROLE $POSTGRES_USER SET default_transaction_isolation TO 'read committed';
ALTER ROLE $POSTGRES_USER SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
EOF
    echo "Database created!"
else
    echo "Database already exists!"
fi

# 7. Setup Gunicorn systemd service
echo "Setting up Gunicorn service..."
sudo tee /etc/systemd/system/utrack.service > /dev/null <<'EOF'
[Unit]
Description=UTrack Django application
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=__PROJECT_DIR__
EnvironmentFile=__PROJECT_DIR__/.env
ExecStart=__PROJECT_DIR__/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:__PROJECT_DIR__/utrack.sock \
    --timeout 120 \
    --log-level debug \
    utrack.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Replace placeholder with actual project directory
sudo sed -i "s|__PROJECT_DIR__|$PROJECT_DIR|g" /etc/systemd/system/utrack.service

# 8. Setup Nginx configuration
echo "Setting up Nginx..."

# Nginx server_name: OCI instance public IP or hostname
SERVER_HOST="${DEPLOY_HOST}"
if [ -n "$SERVER_HOST" ]; then
    FINAL_HOST="$SERVER_HOST"
else
    FINAL_HOST="${ALLOWED_HOSTS:-*}"
fi

# Quoting 'EOF' prevents Bash from messing with the contents
sudo tee /etc/nginx/sites-available/utrack > /dev/null <<'EOF'
server {
    listen 80;
    server_name __NGINX_HOST__;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /home/ubuntu/utrack-backend/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/utrack-backend/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/utrack-backend/utrack.sock;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
    }

    client_max_body_size 100M;
}
EOF

# Swap the placeholder for the actual host variable
sudo sed -i "s/__NGINX_HOST__/$FINAL_HOST/g" /etc/nginx/sites-available/utrack

# 9. Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/utrack /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 10. Set permissions and Start Services
echo "Setting permissions..."
sudo chmod 755 /home/ubuntu
sudo chmod 755 "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/media"
sudo chown -R ubuntu:www-data "$PROJECT_DIR"
sudo chmod -R 775 "$PROJECT_DIR"

# 11. Finalizing
sudo systemctl daemon-reload
sudo systemctl enable utrack
sudo systemctl restart utrack
sudo systemctl restart nginx

echo "Bootstrap complete!"