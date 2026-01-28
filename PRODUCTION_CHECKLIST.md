# Production Launch Checklist

Use this checklist to ensure everything is ready before launching to production.

## Pre-Launch Checklist

### Security
- [ ] `SECRET_KEY` is set to a strong, unique value (not default)
- [ ] `DEBUG=False` in production (automatically set when `LOCALHOST=False`)
- [ ] `ALLOWED_HOSTS` is configured with your domain(s)
- [ ] `CSRF_TRUSTED_ORIGINS` includes your HTTPS domain(s)
- [ ] SSL certificates are installed and valid
- [ ] HTTPS redirect is working (HTTP → HTTPS)
- [ ] Security headers are enabled (automatically enabled in production)
- [ ] Database credentials are strong and secure
- [ ] Email credentials are configured (for password reset)
- [ ] API keys (Apple, Google) are configured
- [ ] `.env` file is NOT committed to version control

### Environment Configuration
- [ ] `.env` file is created from `.env.example`
- [ ] All required environment variables are set
- [ ] `LOCALHOST=False` for production
- [ ] Database connection string is correct
- [ ] Email settings are configured and tested
- [ ] Frontend URL is set correctly (for email links)
- [ ] Social auth credentials are configured

### Database
- [ ] PostgreSQL database is created
- [ ] Database migrations are applied (`python manage.py migrate`)
- [ ] Initial data is loaded (exercises, supplements, achievements)
- [ ] Database backup script is tested
- [ ] Automated backup schedule is configured (cron job)

### SSL/HTTPS
- [ ] Let's Encrypt certificates are obtained
- [ ] Certificates are mounted in Docker volumes
- [ ] nginx SSL configuration is correct
- [ ] HTTP to HTTPS redirect is working
- [ ] SSL certificate auto-renewal is configured
- [ ] Test SSL with: `openssl s_client -connect api.utrack.irfanemreutkan.com:443`

### Application
- [ ] Static files are collected (`python manage.py collectstatic`)
- [ ] Application starts without errors
- [ ] Health check endpoint works: `/api/health/`
- [ ] All services are running (web, db, nginx)
- [ ] Logs are being written correctly
- [ ] Error tracking is configured (Sentry - optional)

### API Testing
- [ ] Health check endpoint returns healthy status
- [ ] User registration works
- [ ] User login works and returns JWT tokens
- [ ] JWT token refresh works
- [ ] Password reset email is sent and received
- [ ] Social auth (Google/Apple) works
- [ ] Workout CRUD operations work
- [ ] Supplement tracking works
- [ ] Body measurements work
- [ ] Achievements system works
- [ ] Rate limiting works correctly
- [ ] Error responses follow standardized format

### Monitoring & Logging
- [ ] Error logs are being written
- [ ] Request logs are being written
- [ ] Log rotation is working
- [ ] Health check endpoint is accessible
- [ ] Sentry is configured (optional)
- [ ] Monitoring alerts are set up (optional)

### Performance
- [ ] Static files are served efficiently
- [ ] Gzip compression is enabled (nginx)
- [ ] Database queries are optimized
- [ ] Rate limiting is configured appropriately
- [ ] Response times are acceptable (<500ms for most endpoints)

### Documentation
- [ ] API documentation is accessible at `/api/docs/`
- [ ] README.md is updated with production info
- [ ] DEPLOYMENT.md is complete
- [ ] `.env.example` documents all variables
- [ ] Mobile app developers have API documentation

### Backup & Recovery
- [ ] Backup script is tested and works
- [ ] Restore script is tested and works
- [ ] Backup retention policy is configured (30 days default)
- [ ] Backup schedule is set up (daily recommended)
- [ ] Backup storage location is secure
- [ ] Restore procedure is documented

### Mobile App Integration
- [ ] API base URL is documented for mobile app
- [ ] Authentication flow is documented
- [ ] Error handling format is documented
- [ ] Rate limiting information is documented
- [ ] API endpoints are tested from mobile app perspective

## Post-Launch Monitoring

### First 24 Hours
- [ ] Monitor error logs for any issues
- [ ] Check response times
- [ ] Verify SSL certificates are working
- [ ] Monitor database performance
- [ ] Check backup completion
- [ ] Monitor rate limiting (any false positives?)

### First Week
- [ ] Review error patterns
- [ ] Check disk usage (logs, backups)
- [ ] Verify backup restoration works
- [ ] Monitor API usage patterns
- [ ] Review security logs

## Quick Verification Commands

```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs -f web

# Test health endpoint
curl https://api.utrack.irfanemreutkan.com/api/health/

# Test SSL
openssl s_client -connect api.utrack.irfanemreutkan.com:443

# Check disk usage
df -h
du -sh logs/ backups/

# Verify backups
ls -lh backups/
```

## Emergency Contacts

- **Server Issues**: [Your server admin contact]
- **Database Issues**: [Your DBA contact]
- **SSL Issues**: [Your DevOps contact]
- **Application Issues**: [Your dev team contact]

## Rollback Plan

If critical issues occur:

1. **Stop services**: `docker-compose down`
2. **Restore database**: `./scripts/restore_database.sh backups/utrack_backup_YYYYMMDD_HHMMSS.sql.gz`
3. **Rollback code**: `git checkout <previous-commit>`
4. **Rebuild**: `docker-compose build && docker-compose up -d`

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed rollback procedures.
