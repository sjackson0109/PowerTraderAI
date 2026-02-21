# Artifact Repository Configuration

This document explains how to configure PowerTrader AI's release pipeline to publish artifacts to various artifact repositories.

## Overview

The release pipeline automatically publishes artifacts to multiple distribution channels:

### Automatic Distribution
- **GitHub Releases** - ZIP downloads for manual installation
- **GitHub Actions Artifacts** - Build artifacts (90-day retention)

### Configurable Repositories
- **PyPI** - Python Package Index (`pip install powertrader-ai`)
- **GitHub Packages** - GitHub's package registry
- **JFrog Artifactory** - Enterprise artifact repository
- **AWS CodeArtifact** - AWS managed package repository

## Repository Configuration

### 1. PyPI Publication

**Required Secrets:**
```yaml
PYPI_API_TOKEN: your-pypi-api-token
```

**Setup Instructions:**
1. Create PyPI account at https://pypi.org
2. Generate API token in PyPI account settings
3. Add token to GitHub repository secrets
4. Tagged releases automatically publish to PyPI

**Installation:**
```bash
pip install powertrader-ai
```

### 2. GitHub Packages

**Required Secrets:**
```yaml
GITHUB_TOKEN: auto-generated (no setup needed)
```

**Setup Instructions:**
1. Automatically configured for GitHub repositories
2. Uses repository's GITHUB_TOKEN
3. Publishes on tagged releases and main branch pushes

**Installation:**
```bash
pip install --index-url https://ghcr.io/owner/repo powertrader-ai
```

### 3. JFrog Artifactory

**Required Secrets:**
```yaml
ARTIFACTORY_URL: https://your-company.jfrog.io/artifactory
ARTIFACTORY_USERNAME: your-username
ARTIFACTORY_PASSWORD: your-password-or-token
```

**Repository Structure:**
- `/powertrader-releases/` - ZIP artifacts
- `/python-packages/` - Python wheels

**Setup Instructions:**
1. Contact your DevOps team for Artifactory credentials
2. Add secrets to GitHub repository settings
3. Pipeline automatically uploads on tagged releases

### 4. AWS CodeArtifact

**Required Secrets:**
```yaml
AWS_ACCESS_KEY_ID: your-aws-access-key
AWS_SECRET_ACCESS_KEY: your-aws-secret-key
AWS_DEFAULT_REGION: us-west-2
CODEARTIFACT_DOMAIN: your-domain
CODEARTIFACT_REPOSITORY: your-repository
```

**Setup Instructions:**
1. Create CodeArtifact domain and repository in AWS
2. Create IAM user with CodeArtifact permissions
3. Add AWS credentials to GitHub secrets
4. Pipeline automatically uploads on tagged releases

**Installation:**
```bash
aws codeartifact login --tool pip --domain your-domain --repository your-repository
pip install powertrader-ai
```

## Artifact Types

### 1. ZIP Distribution
```
PowerTrader_AI_Desktop_v1.0.0.zip
├── Complete application
├── Documentation
├── Installation scripts
├── Quick start guide
└── SHA256 checksum
```

### 2. Python Package
```
powertrader-ai-1.0.0.tar.gz    # Source distribution
powertrader_ai-1.0.0-py3-none-any.whl  # Wheel distribution
```

### 3. Checksums and Metadata
```
PowerTrader_AI_Desktop_v1.0.0.zip.sha256
```

## Distribution Workflow

### On PR Merge/Main Push:
1. Build ZIP artifact
2. Upload to GitHub Actions artifacts
3. Publish to GitHub Packages (if configured)

### On Git Tag (Release):
1. Build all artifact types
2. Create GitHub release with ZIP
3. Publish to PyPI
4. Publish to configured enterprise repositories
5. Generate comprehensive release notes

## Security Considerations

### Secret Management
- Use repository secrets for credentials
- Rotate tokens regularly
- Use least-privilege access tokens
- Monitor artifact download metrics

### Access Control
- Configure repository permissions appropriately
- Use organization-level secrets for enterprise repos
- Implement approval workflows for sensitive releases

## Monitoring and Maintenance

### Health Checks
```yaml
# Add to workflow for monitoring
- name: Verify artifact availability
  run: |
    # Check PyPI
    pip index versions powertrader-ai
    
    # Check artifact repositories
    curl -f "$ARTIFACTORY_URL/powertrader-releases/"
```

### Metrics
- Track download counts
- Monitor build success rates
- Alert on publication failures
- Verify artifact integrity

## Troubleshooting

### Common Issues

**PyPI Upload Fails:**
- Verify API token permissions
- Check package name conflicts
- Ensure version numbers are unique

**Artifactory Upload Fails:**
- Verify network connectivity
- Check authentication credentials
- Confirm repository permissions

**AWS CodeArtifact Issues:**
- Verify IAM permissions
- Check region configuration
- Ensure domain/repository exists

### Debug Commands
```bash
# Test PyPI token
twine upload --repository testpypi dist/*

# Test Artifactory connection
curl -u username:password "$ARTIFACTORY_URL/api/system/ping"

# Test AWS CodeArtifact
aws codeartifact list-repositories --domain your-domain
```

## Integration Examples

### Enterprise CI/CD Integration
```yaml
# Download from Artifactory in downstream pipelines
- name: Download PowerTrader AI
  run: |
    curl -u $ARTIFACTORY_USER:$ARTIFACTORY_PASS \
         -o powertrader-ai.zip \
         "$ARTIFACTORY_URL/powertrader-releases/PowerTrader_AI_Desktop_latest.zip"
```

### Docker Integration
```dockerfile
# Install from PyPI in containers
FROM python:3.11
RUN pip install powertrader-ai
CMD ["powertrader"]
```

---

**Configuration Team:**  
*Simon Jackson (@sjackson0109) - PowerTrader AI Development Team*

**Last Updated:** February 20, 2026