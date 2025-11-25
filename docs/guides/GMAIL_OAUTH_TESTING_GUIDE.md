# Gmail OAuth Testing Guide for AP Intake System

## 🎯 Overview

This guide helps you set up Gmail OAuth authentication for testing the AP Intake & Validation System's email processing capabilities.

## 📋 Prerequisites

### 1. Google Cloud Project Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the following APIs:
   - **Gmail API**
   - **Google Cloud Pub/Sub API**
   - **Cloud Storage API** (for attachments)

### 2. Create OAuth Credentials
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Select **Web application**
4. Configure:
   - **Name**: AP Intake Test
   - **Authorized redirect URIs**: 
     - `http://localhost:8001/api/v1/gmail/oauth/callback`
     - `http://localhost:8001/api/v1/gmail/oauth/callback`
5. Save the **Client ID** and **Client Secret**

### 3. Create Pub/Sub Topic
1. Go to **Pub/Sub → Topics**
2. Create topic: `gmail-invoice-notifications`
3. Note the **Topic Name**

## 🔧 Configuration Setup

### 1. Update Environment File
Copy `.env.test` to `.env.local` and update:

```bash
# Gmail OAuth Configuration
GMAIL_CLIENT_ID=your-actual-client-id-here
GMAIL_CLIENT_SECRET=your-actual-client-secret-here
GCP_PROJECT_ID=your-gcp-project-id-here

# Webhook Configuration
GMAIL_WEBHOOK_URL=http://localhost:8001/api/v1/gmail/gmail-webhook
GMAIL_PUBSUB_TOPIC_NAME=gmail-invoice-notifications
GMAIL_PUBSUB_SUBSCRIPTION_NAME=gmail-invoice-subscription
```

### 2. Test Environment Variables
```bash
# Load test environment
export $(cat .env.local | grep -v '^#' | xargs)
```

## 🚀 Gmail OAuth Setup Process

### Step 1: Initialize Gmail Watch
```bash
# Start the system with test environment
docker-compose -f docker-compose.test.yml up -d

# Initialize Gmail watch
curl -X POST "http://localhost:8001/api/v1/gmail/watch" \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "gmail-invoice-notifications"
  }'
```

### Step 2: OAuth Authorization
1. Open browser to: `http://localhost:8001/api/v1/gmail/auth`
2. Click "Authorize with Gmail"
3. Sign in with your Gmail account
4. Grant permissions for:
   - Read Gmail messages
   - Manage Gmail labels
5. You'll be redirected back to the application

### Step 3: Verify Setup
```bash
# Check Gmail watch status
curl "http://localhost:8001/api/v1/gmail/watch/status"

# Test webhook endpoint
curl "http://localhost:8001/api/v1/gmail/webhook/status"
```

## 📧 Testing Email Processing

### 1. Send Test Email
Send an email with the following characteristics to your Gmail account:

**To**: Your Gmail address (the one you authorized)
**Subject**: Invoice Payment Due - Test
**Body**: Please find attached invoice for processing
**Attachment**: PDF invoice (use generated test invoice)

### 2. Monitor Processing
```bash
# Check processing logs
docker-compose -f docker-compose.test.yml logs api | grep gmail

# Monitor Redis for jobs
docker exec -it ap_intake_redis_1 redis-cli monitor

# Check database for new invoices
docker exec -it ap_intake_postgres_1 psql -U postgres -d ap_intake -c "
SELECT id, filename, status, created_at 
FROM invoices 
ORDER BY created_at DESC 
LIMIT 5;"
```

### 3. Verify Frontend
1. Access: `http://localhost:3001`
2. Navigate to: `http://localhost:3001/invoices`
3. Look for your processed invoice

## 🔍 Troubleshooting

### Common Issues

#### 1. OAuth Authorization Fails
**Problem**: Redirect URI mismatch
**Solution**: 
- Ensure redirect URI in Google Console matches: `http://localhost:8001/api/v1/gmail/oauth/callback`
- Check for trailing slashes

#### 2. Gmail Watch Not Working
**Problem**: Pub/Sub permissions
**Solution**:
- Verify Pub/Sub API is enabled
- Check service account permissions
- Ensure topic name matches

#### 3. Webhook Not Receiving Notifications
**Problem**: Firewall or network issues
**Solution**:
- Check if port 8001 is accessible
- Use ngrok for testing: `ngrok http 8001`
- Update webhook URL in Google Console

#### 4. Email Processing Fails
**Problem**: Missing permissions or configuration
**Solution**:
- Verify Gmail API scopes
- Check environment variables
- Review API logs for specific errors

### Debug Commands
```bash
# Check Gmail API credentials
curl "http://localhost:8001/api/v1/gmail/credentials/status"

# Test Pub/Sub connection
curl "http://localhost:8001/api/v1/gmail/pubsub/status"

# View detailed logs
docker-compose -f docker-compose.test.yml logs api --tail 50

# Check email processing status
curl "http://localhost:8001/api/v1/ingestion/status"
```

## 📊 Expected Behavior

### Successful Setup
1. ✅ **OAuth Flow**: Browser authorization works smoothly
2. ✅ **Gmail Watch**: Real-time notifications enabled
3. ✅ **Email Detection**: New emails trigger processing
4. ✅ **PDF Extraction**: Invoice data extracted correctly
5. ✅ **Database Storage**: Invoice records created
6. ✅ **Frontend Display**: Processed invoices appear in dashboard

### Test Scenarios

#### Scenario A: Perfect Invoice
- **Send**: Well-formatted PDF invoice
- **Expected**: High confidence (>95%), auto-approval
- **Result**: Appears in dashboard as "Approved"

#### Scenario B: Invoice with Issues
- **Send**: Invoice with missing PO number
- **Expected**: Medium confidence, manual review required
- **Result**: Appears in dashboard as "Needs Review"

#### Scenario C: Multiple Attachments
- **Send**: Email with multiple PDFs
- **Expected**: Each attachment processed separately
- **Result**: Multiple invoice records created

## 🔐 Security Considerations

### Production Deployment
1. **Environment Variables**: Never commit real credentials to git
2. **Redirect URIs**: Use HTTPS in production
3. **Scopes**: Request minimum necessary permissions
4. **Token Storage**: Store tokens securely
5. **Rate Limits**: Monitor Gmail API usage

### Test Environment
1. **Test Accounts**: Use dedicated test Gmail accounts
2. **Token Expiration**: OAuth tokens expire periodically
3. **Cleanup**: Regularly clean test data
4. **Isolation**: Keep test and production separate

## 📞 Support Resources

### Documentation
- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Cloud Pub/Sub](https://cloud.google.com/pubsub)
- [OAuth 2.0 Flow](https://developers.google.com/identity/protocols/oauth2)

### Common Error Codes
- `401`: Invalid credentials
- `403`: Insufficient permissions
- `429`: Rate limit exceeded
- `500`: Server error (retry with backoff)

## 🎯 Success Criteria

Your Gmail OAuth setup is successful when:

- [ ] OAuth authorization flow completes without errors
- [ ] Gmail watch is established and active
- [ ] Webhook receives real-time notifications
- [ ] Email attachments are processed automatically
- [ ] Invoice data appears in frontend dashboard
- [ ] No authentication errors in logs
- [ ] Processing completes within expected timeframes

Once all criteria are met, your Gmail integration is ready for production testing!