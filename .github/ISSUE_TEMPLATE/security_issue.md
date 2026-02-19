---
name: 🚨 Security Issue
about: Report a security vulnerability (Use responsibly - see security policy)
title: '[SECURITY] '
labels: ['security', 'critical']
assignees: ''
---

## ⚠️ Security Issue Notice

**IMPORTANT: Please follow responsible disclosure practices**

If this is a critical security vulnerability that could affect live trading or user funds, please:
1. **DO NOT** post details publicly in this issue
2. Contact the maintainers privately first
3. Allow time for a fix before public disclosure

## Security Issue Type
**What type of security issue is this?**
- [ ] API Key/Credential exposure
- [ ] Authentication bypass
- [ ] Trading logic manipulation
- [ ] File system access vulnerability
- [ ] Network security issue
- [ ] Dependency vulnerability
- [ ] Configuration security flaw
- [ ] Other: ___________

## Issue Severity
**How would you rate the severity?**
- [ ] Critical - Immediate threat to user funds or data
- [ ] High - Significant security risk
- [ ] Medium - Moderate security concern
- [ ] Low - Minor security improvement

## Affected Components
**Which components are affected?**
- [ ] Trading engine (pt_trader.py)
- [ ] Neural network trainer (pt_trainer.py)
- [ ] Price analyzer (pt_thinker.py)
- [ ] GUI interface (pt_hub.py)
- [ ] Credential management
- [ ] File operations
- [ ] Configuration files
- [ ] Dependencies
- [ ] Other: ___________

## Impact Assessment
**Potential impact:**
- [ ] Could affect live trading decisions
- [ ] Could expose API credentials
- [ ] Could lead to unauthorized access
- [ ] Could cause financial loss
- [ ] Information disclosure only
- [ ] Limited to local system

## Basic Description
**General description (avoid sensitive details):**
<!-- Provide a general description without revealing exploit details -->

## Environment
**Environment where discovered:**
- OS: [e.g. Windows 11, Ubuntu 22.04]
- Python Version: [e.g. 3.11.5]
- PowerTrader AI Version: [e.g. v1.2.3 or commit hash]

## Reproduction (General Steps)
**General reproduction steps (without exploit details):**
<!-- Provide enough information to understand the issue without enabling exploitation -->

## Suggested Remediation
**Suggested fix (if known):**
<!-- Any suggestions for how this could be addressed -->

## Additional Context
**Additional context:**
<!-- Any other relevant information that doesn't reveal sensitive details -->

## Checklist
- [ ] I have followed responsible disclosure practices
- [ ] I have avoided posting sensitive exploit details
- [ ] I understand the potential impact of this issue
- [ ] I am willing to work with maintainers on a fix