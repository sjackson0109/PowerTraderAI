#!/usr/bin/env python3
"""
PowerTrader AI - Pre-commit Setup Script
Install and configure pre-commit hooks for local development
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"📋 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {e.stderr}")
        return False

def main():
    """Set up pre-commit hooks"""
    print("🔧 PowerTrader AI - Pre-commit Setup")
    print("=" * 50)
    
    # Check if we're in git repository
    if not os.path.exists('.git'):
        print("❌ Not in a git repository. Please run from project root.")
        sys.exit(1)
    
    # Install pre-commit if not available
    print("📦 Installing pre-commit...")
    if not run_command("pip install pre-commit", "Installing pre-commit"):
        print("❌ Failed to install pre-commit")
        sys.exit(1)
    
    # Install the hooks
    if not run_command("pre-commit install", "Installing git hooks"):
        print("❌ Failed to install git hooks")
        sys.exit(1)
    
    # Run against all files initially
    print("🧹 Running pre-commit on all files...")
    run_command("pre-commit run --all-files", "Initial pre-commit run")
    
    print("\n🎉 Pre-commit setup complete!")
    print("\nNow your commits will automatically run:")
    print("  • Code formatting (Black, isort)")
    print("  • Linting (flake8)")
    print("  • Security scanning (Bandit)")
    print("  • Basic file checks")
    print("  • Tests (pytest)")
    print("\nTo bypass hooks temporarily: git commit --no-verify")

if __name__ == "__main__":
    main()