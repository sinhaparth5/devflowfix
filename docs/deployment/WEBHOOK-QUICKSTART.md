# GitHub Webhook Setup - Quick Reference

## 🚀 Quick Start (3 Steps)

### Step 1: Generate Webhook Secret
```powershell
# Run the setup script
.\scripts\setup-webhook.ps1

# Or manually generate
python scripts/generate_webhook_secret.py
```

Add the secret to `.env`:
```bash
GITHUB_WEBHOOK_SECRET=your_generated_secret_here
```

### Step 2: Start Application & Tunnel

**Terminal 1 - Application:**
```powershell
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - ngrok (for local dev):**
```powershell
ngrok http 8000
```

Copy the ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`)

### Step 3: Configure GitHub Webhook

1. **Go to:** `https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks`

2. **Click:** "Add webhook"

3. **Configure:**
   - **Payload URL:** `https://YOUR_NGROK_URL/webhooks/github`
   - **Content type:** `application/json`
   - **Secret:** [Your GITHUB_WEBHOOK_SECRET from .env]
   - **SSL verification:** Enabled ✅

4. **Select Events:**
   - ✅ Workflow runs
   - ✅ Pushes
   - ✅ Check runs (optional)
   - ✅ Pull requests (optional)

5. **Click:** "Add webhook"

---

## ✅ Verify Setup

```powershell
# Run verification script
python scripts/verify_webhook_setup.py

# Or manually test
curl http://localhost:8000/health
```

**Check in GitHub:**
- Settings → Webhooks → Your webhook → Recent Deliveries
- Should see a green checkmark for the ping event

---

## 🧪 Test Webhook

Trigger a workflow to test:

```powershell
git commit --allow-empty -m "Test webhook trigger"
git push
```

Check logs for:
```
INFO: Received GitHub webhook event: workflow_run
INFO: Webhook signature verified successfully
```

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `docs/deployment/github-webhook-setup.md` | Comprehensive setup guide |
| `scripts/setup-webhook.ps1` | Automated setup script |
| `scripts/generate_webhook_secret.py` | Generate webhook secrets |
| `scripts/verify_webhook_setup.py` | Verify configuration |
| `examples/webhook_payloads/workflow_failure.json` | Example payload |
| `examples/webhook_payloads/push.json` | Example payload |

---

## 🔧 Webhook Client Features

The webhook client (`app/adapters/external/github/webhooks.py`) includes:

✅ **HMAC-SHA256 signature verification** using `GITHUB_WEBHOOK_SECRET`  
✅ **Automatic payload validation and parsing**  
✅ **Event type detection** (workflow_run, push, check_run)  
✅ **Failure detection** and details extraction  
✅ **Security best practices** (constant-time comparison)  
✅ **Comprehensive error handling**  

---

## 🌐 Production Deployment

For production, use your actual domain instead of ngrok:

```
Payload URL: https://api.your-domain.com/webhooks/github
```

Store `GITHUB_WEBHOOK_SECRET` in:
- AWS Secrets Manager
- HashiCorp Vault
- Environment variables (Docker/K8s)

---

## 🔐 Security Notes

- ✅ Never commit `.env` to version control
- ✅ Use strong, random webhook secrets (32+ chars)
- ✅ Enable SSL verification
- ✅ Rotate secrets periodically
- ✅ Monitor webhook deliveries for suspicious activity
- ✅ Use HTTPS endpoints only

---

## 📚 Additional Resources

- [GitHub Webhooks Documentation](https://docs.github.com/en/webhooks)
- [Webhook Events Reference](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [Securing Webhooks](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Verify webhook secret matches in .env and GitHub |
| Connection Refused | Ensure application is running on port 8000 |
| SSL Error | Use HTTPS ngrok URL, not HTTP |
| No events received | Check event selection in GitHub webhook settings |

For detailed troubleshooting, see `docs/deployment/github-webhook-setup.md`

---

**Ready to go!** 🎉 Run `.\scripts\setup-webhook.ps1` to get started.
