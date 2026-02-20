# PowerTrader AI - Developer Setup Guide

## Pre-commit Hooks Setup

Pre-commit hooks ensure code quality by running checks before each commit. This prevents broken or poorly formatted code from entering the repository.

### Quick Setup

Run the automated setup script:

```bash
python .github/scripts/setup-precommit.py
```

This will automatically install all required dependencies and configure the hooks.

### Manual Setup (if needed)

If the automated script fails, follow these manual steps:

#### 1. Install Pre-commit Dependencies

```bash
# Core testing framework
pip install pytest pytest-cov pytest-mock pytest-benchmark

# Performance monitoring
pip install psutil memory-profiler

# Security and cryptography
pip install pynacl pbr cryptography bandit safety

# Code quality tools
pip install flake8 black isort

# Testing utilities
pip install responses requests-mock

# Pre-commit framework
pip install pre-commit
```

#### 2. Install Project Dependencies

```bash
# Install PowerTrader AI dependencies
pip install -r app/requirements.txt
```

#### 3. Install Git Hooks

```bash
python -m pre_commit install
```

#### 4. Test Installation (optional)

```bash
# Run hooks on all files to test
python -m pre_commit run --all-files
```

### What the Hooks Do

The pre-commit system runs these checks before each commit:

- **Formatting**: Black (code formatting) and isort (import sorting)
- **Linting**: flake8 (code quality and style)
- **Security**: Bandit (security vulnerability scanning)
- **File Checks**: Trailing whitespace, large files, merge conflicts
- **Tests**: pytest (unit and integration tests)

### Dependencies Explained

| Package | Purpose | Required For |
|---------|---------|--------------|
| `pytest` | Testing framework | Running test suite |
| `pytest-cov` | Coverage reporting | Test coverage analysis |
| `pytest-mock` | Mocking utilities | Unit test mocking |
| `pytest-benchmark` | Performance testing | Benchmark tests |
| `psutil` | System monitoring | Performance tests |
| `memory-profiler` | Memory analysis | Memory usage tests |
| `pynacl` | Cryptography | Encryption/security features |
| `pbr` | Build utilities | Package building |
| `cryptography` | Cryptographic operations | Security features |
| `bandit` | Security scanner | Security vulnerability detection |
| `safety` | Dependency security | Package vulnerability scanning |
| `flake8` | Code linter | Code quality checks |
| `black` | Code formatter | Automatic code formatting |
| `isort` | Import sorter | Import organization |
| `responses` | HTTP mocking | API testing |
| `requests-mock` | Request mocking | HTTP request testing |

### Troubleshooting

#### Hook Failures
If commits are blocked by hook failures:

1. **Review the errors** - The hooks show exactly what needs to be fixed
2. **Fix formatting issues** - Many are auto-fixable by re-running the commit
3. **Install missing dependencies** - Run the setup script again
4. **Bypass temporarily** - Use `git commit --no-verify` (not recommended)

#### Dependency Issues
If you get import errors during commit:

```bash
# Reinstall all dependencies
python .github/scripts/setup-precommit.py

# Or install manually
pip install pytest pytest-cov pytest-mock pytest-benchmark psutil memory-profiler pynacl pbr cryptography bandit safety flake8 black isort responses requests-mock
```

#### Permission Issues
On Windows, if you get permission errors:

1. Run terminal as Administrator
2. Or install to user directory: `pip install --user [package]`
3. Or use virtual environment (recommended)

### Virtual Environment (Recommended)

For isolated dependency management:

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
python .github/scripts/setup-precommit.py
```

### CI/CD Integration

Pre-commit hooks complement the CI/CD pipeline:

1. **Local (Pre-commit)**: Catches issues before commit
2. **Remote (GitHub Actions)**: Validates on push/PR
3. **Release (Automation)**: Final validation before release

This three-tier system ensures maximum code quality and reliability.