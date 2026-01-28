# UTrack Backend Deployment Guide

This guide covers step-by-step production deployment of the UTrack backend API.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Server Setup](#initial-server-setup)
3. [SSL Certificate Setup](#ssl-certificate-setup)
4. [Environment Configuration](#environment-configuration)
5. [Database Setup](#database-setup)
6. [Deployment](#deployment)
7. [Post-Deployment](#post-deployment)
8. [Backup Procedures](#backup-procedures)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Ubuntu 20.04+ or similar Linux distribution
- Docker and Docker Compose installed
- Domain name pointing to your server IP
- SSH access to the server
- Basic knowledge of Linux commands

---

## Initial Server Setup

### 1. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add your user to docker group
sudo usermod -aG docker $USER
```

### 3. Clone Repository

```bash
git clone <your-repository-url> utrack_backend
cd utrack_backend
```

---

## SSL Certificate Setup

### Option 1: Let's Encrypt with Certbot (Recommended)

#### Initial Certificate Request

1. **Start nginx without SSL first** (temporarily modify nginx.conf to only listen on port 80)

2. **Request certificate**:
```bash
docker-compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d api.utrack.irfanemreutkan.com
```

3. **Update nginx.conf** to use the certificates (already configured)

4. **Restart nginx**:
```bash
docker-compose restart nginx
```

#### Automatic Renewal

The certbot container in docker-compose.yml is configured to automatically renew certificates every 12 hours. Certificates are renewed automatically when they're within 30 days of expiration.

### Option 2: Manual Certificate Installation

If you have certificates from another source:

1. Place certificates in `/etc/letsencrypt/live/api.utrack.irfanemreutkan.com/`
2. Update nginx.conf paths if different
3. Ensure certificates are mounted in docker-compose.yml

---

## Environment Configuration

### 1. Create .env File

```bash
cp .env.example .env
nano .env
```

### 2. Configure Required Variables

**Critical settings for production:**

```env
LOCALHOST=False
SECRET_KEY=<generate-secure-key>
ALLOWED_HOSTS=api.utrack.irfanemreutkan.com
CSRF_TRUSTED_ORIGINS=https://api.utrack.irfanemreutkan.com

# Database
POSTGRES_USER=utrack_user
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=utrack_db
DB_HOST=db
DB_PORT=5432

# Email (required for password reset)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# Frontend URL (for email links)
FRONTEND_URL=https://your-mobile-app-deep-link-or-web-url

# Social Auth
APPLE_KEY_ID=your-apple-key-id
APPLE_TEAM_ID=your-apple-team-id
APPLE_CLIENT_ID=your-apple-client-id
APPLE_PRIVATE_KEY=your-apple-private-key-content

# Optional: Error Tracking
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

### 3. Generate Secret Key

```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

---

## Database Setup

### 1. Start Database

```bash
docker-compose up -d db
```

### 2. Wait for Database to be Ready

```bash
docker-compose ps db
# Wait until status shows "healthy"
```

### 3. Run Migrations

```bash
docker-compose exec web python manage.py migrate
```

### 4. Create Superuser (Optional)

```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Load Initial Data (Optional)

```bash
docker-compose exec web python manage.py populate_exercises
docker-compose exec web python manage.py populate_supplements
docker-compose exec web python manage.py seed_achievements
```

---

## Deployment

### 1. Build and Start Services

```bash
# Build images
docker-compose build

# Start all services
docker-compose --profile postgres up -d
```

### 2. Collect Static Files

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### 3. Verify Services

```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs -f web
docker-compose logs -f nginx

# Test health endpoint
curl https://api.utrack.irfanemreutkan.com/api/health/
```

### 4. Verify SSL

```bash
# Check SSL certificate
openssl s_client -connect api.utrack.irfanemreutkan.com:443 -servername api.utrack.irfanemreutkan.com

# Or use online tools:
# https://www.ssllabs.com/ssltest/
```

---

## Post-Deployment

### 1. Test API Endpoints

```bash
# Health check
curl https://api.utrack.irfanemreutkan.com/api/health/

# Test registration (should work)
curl -X POST https://api.utrack.irfanemreutkan.com/api/user/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password1":"Test123!@#","password2":"Test123!@#"}'
```

### 2. Monitor Logs

```bash
# Follow all logs
docker-compose logs -f

# Follow specific service
docker-compose logs -f web
docker-compose logs -f nginx
```

### 3. Set Up Log Rotation

Logs are automatically rotated by the application (10MB max, 10 backups). Monitor disk space:

```bash
df -h
du -sh logs/
```

---

## Backup Procedures

### Automated Backups

#### Option 1: Cron Job (Recommended)

Create a cron job to run backups daily:

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * cd /path/to/utrack_backend && ./scripts/backup_database.sh
```

#### Option 2: Manual Backup

```bash
# Run backup script
./scripts/backup_database.sh

# Backups are stored in ./backups/ directory
# Old backups (>30 days) are automatically deleted
```

### Restore from Backup

```bash
# List available backups
ls -lh backups/

# Restore (WARNING: This replaces current database)
./scripts/restore_database.sh backups/utrack_backup_20240101_120000.sql.gz
```

### Backup Retention

- Default retention: 30 days
- Configure via `RETENTION_DAYS` environment variable
- Backups are compressed (.gz) to save space

---

## Monitoring

### Health Checks

The API includes a health check endpoint:

```bash
curl https://api.utrack.irfanemreutkan.com/api/health/
```

Response includes:
- Overall status
- Database connectivity
- Cache connectivity
- Environment info

### Log Monitoring

Monitor logs for errors:

```bash
# Check error logs
tail -f logs/errors.log

# Check request logs
tail -f logs/requests.log
```

### Sentry Integration (Optional)

If Sentry DSN is configured:
1. Errors are automatically sent to Sentry
2. Set up alerts in Sentry dashboard
3. Monitor error rates and trends

### Server Monitoring

Monitor server resources:

```bash
# CPU and memory
htop

# Disk usage
df -h

# Docker stats
docker stats
```

---

## Troubleshooting

### Common Issues

#### 1. SSL Certificate Errors

**Problem**: nginx fails to start due to missing certificates

**Solution**:
- Ensure certificates exist: `ls /etc/letsencrypt/live/api.utrack.irfanemreutkan.com/`
- Check certificate paths in nginx.conf
- Verify certbot volumes are mounted in docker-compose.yml

#### 2. Database Connection Errors

**Problem**: Application can't connect to database

**Solution**:
- Check database is running: `docker-compose ps db`
- Verify DATABASE_URL in .env
- Check database logs: `docker-compose logs db`
- Ensure DB_HOST is 'db' when using Docker

#### 3. Static Files Not Loading

**Problem**: Static files return 404

**Solution**:
- Run collectstatic: `docker-compose exec web python manage.py collectstatic --noinput`
- Check nginx static file paths
- Verify volumes are mounted correctly

#### 4. Rate Limiting Too Strict

**Problem**: Users hitting rate limits

**Solution**:
- Check rate limit settings in `utrack/settings.py`
- Adjust throttle rates if needed
- Consider Redis for distributed rate limiting

#### 5. Email Not Sending

**Problem**: Password reset emails not received

**Solution**:
- Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env
- Check email logs: `docker-compose logs web | grep -i email`
- Test SMTP connection manually
- For Gmail, use App Password (not regular password)

### Debug Mode

**NEVER enable DEBUG in production**, but for troubleshooting:

1. Temporarily set `DEBUG=True` in .env
2. Check detailed error pages
3. **Remember to set back to False**

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f nginx
docker-compose logs -f db

# Last 100 lines
docker-compose logs --tail=100 web

# Search logs
docker-compose logs web | grep ERROR
```

### Restarting Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart web
docker-compose restart nginx

# Rebuild and restart
docker-compose up -d --build web
```

---

## Rollback Procedures

### Rollback Code Changes

```bash
# Checkout previous version
git checkout <previous-commit-hash>

# Rebuild and restart
docker-compose build web
docker-compose up -d web
```

### Rollback Database

```bash
# Restore from backup
./scripts/restore_database.sh backups/utrack_backup_YYYYMMDD_HHMMSS.sql.gz
```

### Emergency Shutdown

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v
```

---

## Security Checklist

Before going live, verify:

- [ ] `DEBUG=False` in production
- [ ] `SECRET_KEY` is strong and unique
- [ ] `ALLOWED_HOSTS` is set correctly
- [ ] SSL certificates are valid and auto-renewing
- [ ] Database passwords are strong
- [ ] Email credentials are configured
- [ ] Firewall rules are set (only ports 80, 443 open)
- [ ] SSH keys are used (password auth disabled)
- [ ] Regular backups are scheduled
- [ ] Error tracking is configured (Sentry)
- [ ] Logs are monitored
- [ ] Rate limiting is configured
- [ ] Security headers are enabled

---

## Maintenance

### Regular Tasks

1. **Weekly**: Review error logs
2. **Monthly**: Check disk usage and clean old backups
3. **Quarterly**: Review and update dependencies
4. **As needed**: Update SSL certificates (auto-renewed)

### Updating Dependencies

```bash
# Update requirements
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt

# Rebuild containers
docker-compose build
docker-compose up -d
```

### Database Migrations

```bash
# Create migrations (development)
python manage.py makemigrations

# Apply migrations (production)
docker-compose exec web python manage.py migrate
```

---

## Support

For issues:
1. Check logs first
2. Review this troubleshooting guide
3. Check GitHub issues
4. Contact support team

---

## Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Nginx Documentation](https://nginx.org/en/docs/)
