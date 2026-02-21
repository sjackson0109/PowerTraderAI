# Credential Setup Guide

## 🔐 Robinhood API Credentials Configuration

PowerTrader AI now supports **dual credential modes** for different use cases:

### 🖥️ **Desktop Use (Option 2): Encrypted Credentials**

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
   - Store encrypted credentials automatically
   - Create secure files: `r_key.enc`, `r_secret.enc`, `.pt_salt`

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

2. **Or use the GUI wizard first:** Run the desktop setup, then copy values from generated files

## ⚙️ **How It Works**

**Credential Loading Priority:**
1. **Encrypted files** (desktop): `r_key.enc`, `r_secret.enc`
2. **Environment variables** (CI/CD): `POWERTRADER_ROBINHOOD_API_KEY`, `POWERTRADER_ROBINHOOD_PRIVATE_KEY`
3. **Plaintext files** (legacy): `r_key.txt`, `r_secret.txt`

## ✅ **Verification**

**Desktop:** Credentials work when the PowerTrader GUI shows "✓ Robinhood API Connected"

**CI/CD:** GitHub Actions will pass without credential errors

## 🔒 **Security Notes**

- **Desktop:** Credentials are encrypted with machine-specific keys
- **CI/CD:** Secrets are encrypted by GitHub and only available during workflow execution
- **Never commit** `.txt`, `.enc` credential files to git
- **Keep private keys secure** - they provide full trading access

## 🆘 **Troubleshooting**

**"Robinhood API credentials not found" error:**
- Desktop: Run GUI wizard or check encrypted files exist
- CI/CD: Verify GitHub secrets are set correctly

**Import errors in CI/CD:**
- Ensure both `ROBINHOOD_API_KEY` and `ROBINHOOD_PRIVATE_KEY` secrets are set
- Check secret names match exactly (case-sensitive)

---

*Updated: February 21, 2026*
