# Gmail OAuth Testing Setup - Complete Guide

## 🎯 Overview

This guide provides a complete setup for testing Gmail OAuth integration with the AP Intake system using isolated test environments to avoid conflicts with your production setup.

## 📁 Files Created

### 1. Configuration Files
- **`.env.test`** - Test environment configuration with placeholder credentials
- **`docker-compose.test.yml`** - Full test environment with non-conflicting ports
- **`docker-compose.simple.yml`** - Core services only (postgres, redis, minio)

### 2. Docker Configuration
- **`Dockerfile`** - Updated with click dependency and proper Python packages
- **`start-test.sh`** - Custom startup script for test environment

### 3. Testing Tools
- **`test-gmail-setup.sh`** - Automated testing script (executable)
- **`GMAIL_OAUTH_TESTING_GUIDE.md`** - Comprehensive Gmail OAuth setup guide

## 🚀 Quick Start

### Option 1: Automated Setup (Recommended)
```bash
# Run complete setup and testing
./test-gmail-setup.sh

# Or run specific steps
./test-gmail-setup.sh --setup     # Setup environment only
./test-gmail-setup.sh --test      # Test Gmail OAuth
./test-gmail-setup.sh --generate  # Generate test invoice
```

### Option 2: Manual Setup
```bash
# 1. Copy test environment
cp .env.test .env.local

# 2. Start core services
docker-compose -f docker-compose.simple.yml up -d

# 3. Start API and worker
docker-compose -f docker-compose.test.yml up -d api worker

# 4. Generate test invoice
python scripts/create_test_invoice.py --scenario standard --count 1 --output-dir test_invoices
```

## 🔧 Port Configuration

### Test Environment Ports (No Conflicts)
| Service | Test Port | Production Port |
|---------|-----------|-----------------|
| API     | 8001      | 8000            |
| Frontend| 3001      | 3000            |
| PostgreSQL| 5433     | 5432            |
| Redis   | 6381      | 6379            |
| MinIO API| 9004     | 9000            |
| MinIO Console| 9005  | 9001            |

## 📧 Gmail OAuth Setup Steps

### 1. Configure Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or use existing one
3. Enable Gmail API
4. Create OAuth 2.0 Client ID
5. Add authorized redirect URI: `http://localhost:8001/api/v1/gmail/oauth/callback`

### 2. Update Test Environment
Edit `.env.local` (copy of `.env.test`):
```bash
# Replace with your actual Gmail OAuth credentials
GMAIL_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-actual-client-secret

# Update other settings as needed
GMAIL_TEST_EMAIL=your-test-email@gmail.com
```

### 3. Initialize Gmail OAuth
```bash
# 1. Authorize the application
open http://localhost:8001/api/v1/gmail/auth

# 2. Start watching for emails
curl -X POST http://localhost:8001/api/v1/gmail/watch \
  -H "Content-Type: application/json" \
  -d '{"topic_name": "projects/your-project/topics/ap-intake-emails"}'
```

## 🧪 Testing Workflow

### 1. Send Test Email
```bash
# Use the generated test invoice
# Send email with PDF attachment to your authorized Gmail address
# Subject should contain "invoice" keyword
```

### 2. Monitor Processing
```bash
# Check API logs
docker-compose -f docker-compose.test.yml logs -f api

# Check worker logs
docker-compose -f docker-compose.test.yml logs -f worker

# Monitor Gmail watch status
curl http://localhost:8001/api/v1/gmail/watch/status
```

### 3. Verify Results
- **Dashboard**: http://localhost:3001 (when frontend is running)
- **API Docs**: http://localhost:8001/docs
- **MinIO Console**: http://localhost:9005 (minioadmin/minioadmin123)

## 🔍 Troubleshooting

### Common Issues

1. **Port Conflicts**
   ```bash
   # Check what's running on ports
   netstat -tulpn | grep :8000
   netstat -tulpn | grep :3000
   
   # Use test ports instead
   # API: 8001, Frontend: 3001, etc.
   ```

2. **Gmail OAuth Errors**
   ```bash
   # Check OAuth configuration
   curl http://localhost:8001/api/v1/gmail/auth/status
   
   # Verify redirect URI matches Google Cloud Console
   # Should be: http://localhost:8001/api/v1/gmail/oauth/callback
   ```

3. **Docker Issues**
   ```bash
   # Rebuild containers
   docker-compose -f docker-compose.test.yml build --no-cache
   
   # Check container logs
   docker-compose -f docker-compose.test.yml logs api
   ```

4. **Email Not Processing**
   ```bash
   # Check Gmail watch is active
   curl http://localhost:8001/api/v1/gmail/watch/status
   
   # Verify email contains "invoice" in subject
   # Check PDF attachment is valid
   ```

### Debug Commands
```bash
# Check all services
docker-compose -f docker-compose.test.yml ps

# Restart specific service
docker-compose -f docker-compose.test.yml restart api

# View real-time logs
docker-compose -f docker-compose.test.yml logs -f worker

# Enter container for debugging
docker-compose -f docker-compose.test.yml exec api bash
```

## 📊 Monitoring URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| API Health | http://localhost:8001/health | - |
| API Docs | http://localhost:8001/docs | - |
| Gmail OAuth | http://localhost:8001/api/v1/gmail/auth | - |
| Gmail Status | http://localhost:8001/api/v1/gmail/watch/status | - |
| Frontend | http://localhost:3001 | - |
| MinIO Console | http://localhost:9005 | minioadmin/minioadmin123 |

## 🎯 Success Criteria

✅ **Setup Complete** when:
- All services start without errors
- API health endpoint returns 200
- Gmail OAuth authorization flow works
- Test invoice is generated successfully

✅ **Testing Complete** when:
- Gmail watch is active
- Email with PDF attachment triggers processing
- Invoice appears in dashboard
- Slack notifications are sent (if configured)

## 📚 Additional Resources

- **Gmail OAuth Guide**: `GMAIL_OAUTH_TESTING_GUIDE.md`
- **Production Setup**: `GMAIL_OAUTH_SETUP.md`
- **API Documentation**: http://localhost:8001/docs
- **Docker Compose Reference**: `docker-compose.test.yml`

## 🆘 Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review container logs: `docker-compose -f docker-compose.test.yml logs`
3. Verify environment variables in `.env.local`
4. Ensure Gmail OAuth credentials are correctly configured
5. Check that redirect URI matches Google Cloud Console settings

## 🔄 Cleanup

To clean up test environment:
```bash
# Stop and remove containers
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.simple.yml down

# Remove test environment file
rm .env.local

# Remove test invoices
rm -rf test_invoices/
```

---

**Ready to test Gmail OAuth integration!** 🎉

Start with: `./test-gmail-setup.sh`