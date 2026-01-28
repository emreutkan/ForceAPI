#!/bin/bash
# Initialize Let's Encrypt certificates
# Usage: ./scripts/init-letsencrypt.sh

set -e

DOMAIN="api.utrack.irfanemreutkan.com"
EMAIL="${1:-your-email@example.com}"  # Pass email as first argument

echo "Initializing Let's Encrypt certificate for $DOMAIN"
echo "Email: $EMAIL"

# Create directories for certbot
mkdir -p certbot_data certbot_www

# Start nginx temporarily (without SSL) to serve ACME challenge
echo "Starting nginx for ACME challenge..."
docker-compose up -d nginx

# Wait for nginx to be ready
sleep 5

# Request certificate
echo "Requesting certificate from Let's Encrypt..."
docker-compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN"

echo ""
echo "Certificate obtained successfully!"
echo ""
echo "Next steps:"
echo "1. Ensure nginx.conf is configured to use SSL (already done)"
echo "2. Restart nginx: docker-compose restart nginx"
echo "3. Verify SSL: curl https://$DOMAIN/api/health/"
