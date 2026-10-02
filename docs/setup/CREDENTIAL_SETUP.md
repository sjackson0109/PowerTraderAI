# Credential Setup Guide

## 🔐 Robinhood API Credentials Configuration

PowerTraderAI+ now supports **dual credential modes** for different use cases:

### 🖥️ **Desktop Use (Option 2): OS credential store**

**Recommended for local development and personal trading**

1. **Run the GUI Setup Wizard:**
   ```bash
   cd app
   python pt_hub.py
   ```

2. **Navigate:** Settings → Robinhood API → Setup/Update

3. **The wizard will:**
   - Generate a public/private keypair
   - Guide you through Robinhood API setup
   - Store both values in the operating system's credential store (Windows Credential
     Manager, macOS Keychain or the Linux Secret Service) as `robinhood:api_key` and
     `robinhood:private_key`. No file is written.

### 🚀 **CI/CD Use (Option 3): Environment Variables**

**For GitHub Actions and automated pipelines**

#### **Set GitHub Repository Secrets:**

1. Go to your repository: Settings → Secrets and variables → Actions

2. **Add these secrets:**
   ```
   ROBINHOOD_API_KEY=rh_crypto_your_api_key_here
   ROBINHOOD_PRIVATE_KEY=LS0tLS1CRUdJTi...your_base64_private_key
   ```

#### **How to Get the Values:**

1. **Generate credentials via Robinhood:**
   - Visit [Robinhood API Console](https://robinhood.com/crypto/trading/api)
   - Go to Settings → Crypto → API Trading
   - Generate keypair and upload public key
   - Copy the API key (starts with `rh_crypto_`)
   - Save your private key in Base64 format

2. **Or use the GUI wizard first:** the wizard shows the public key; the private key is
   only kept in the credential store, so keep your own copy if you need it for CI

## ⚙️ **How It Works**

**Credential Loading Priority** (defined once, in `app/pt_secrets.py`):
1. **Environment variables** (CI/CD): `POWERTRADER_ROBINHOOD_API_KEY`, `POWERTRADER_ROBINHOOD_PRIVATE_KEY`
2. **OS credential store** (desktop): entries `robinhood:api_key`, `robinhood:private_key`
   under the service `SJackson.PowerTraderAI`

There is no plaintext fallback: if the system has no credential store, nothing is saved,
PowerTrader names the environment variables to set, and keeps running in paper mode.

**Upgrading:** older versions kept these keys in `app/r_key.enc`/`r_secret.enc` (encrypted
with a machine-derived key) or `app/r_key.txt`/`r_secret.txt` (plain text). On first start
the migration (`app/pt_migrate.py`) moves them into the credential store and lists them in
`migration-report.md`; the old files stay until you press **Remove old files**.

## ✅ **Verification**

**Desktop:** Credentials work when the PowerTrader GUI shows "✓ Robinhood API Connected"

**CI/CD:** GitHub Actions will pass without credential errors

## 🔒 **Security Notes**

- **Desktop:** Credentials are protected by the operating system's credential store
- **CI/CD:** Secrets are encrypted by GitHub and only available during workflow execution
- **Never commit** old `r_key*` / `r_secret*` files from earlier versions to git
- **Keep private keys secure** - they provide full trading access

## 🆘 **Troubleshooting**

**"Robinhood API credentials not found" error:**
- Desktop: Run the GUI wizard (Settings → Robinhood API) or check the migration report
- CI/CD: Verify GitHub secrets are set correctly

**Import errors in CI/CD:**
- Ensure both `ROBINHOOD_API_KEY` and `ROBINHOOD_PRIVATE_KEY` secrets are set
- Check secret names match exactly (case-sensitive)

---

*Updated: February 21, 2026*
