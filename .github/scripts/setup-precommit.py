#!/usr/bin/env python3
"""
PowerTraderAI+ - Pre-commit Setup Script
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
    print("🔧 PowerTraderAI+ - Pre-commit Setup")
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
    
    # Install required dependencies for pre-commit hooks
    print("📦 Installing pre-commit dependencies...")
    dependencies = [
        "pytest pytest-cov pytest-mock pytest-benchmark",
        "psutil memory-profiler",
        "pynacl pbr cryptography",
        "bandit safety flake8 black isort",
        "responses requests-mock"
    ]
    
    for dep_group in dependencies:
        if not run_command(f"pip install {dep_group}", f"Installing {dep_group}"):
            print(f"⚠️ Warning: Failed to install {dep_group}")
    
    # Install project dependencies
    print("📦 Installing project dependencies...")
    if os.path.exists('app/requirements.txt'):
        run_command("pip install -r app/requirements.txt", "Installing app requirements")
    elif os.path.exists('requirements.txt'):
        run_command("pip install -r requirements.txt", "Installing requirements")
    
    # Install the hooks
    if not run_command("python -m pre_commit install", "Installing git hooks"):
        print("❌ Failed to install git hooks")
        sys.exit(1)
    
    # Run against all files initially
    print("🧹 Running pre-commit on all files...")
    run_command("python -m pre_commit run --all-files", "Initial pre-commit run")
    
    print("\n🎉 Pre-commit setup complete!")
    print("\nInstalled dependencies:")
    print("  • Testing: pytest, pytest-cov, pytest-mock, pytest-benchmark")
    print("  • Performance: psutil, memory-profiler")
    print("  • Security: pynacl, pbr, cryptography, bandit, safety")
    print("  • Code Quality: flake8, black, isort")
    print("  • Mocking: responses, requests-mock")
    print("\nNow your commits will automatically run:")
    print("  • Code formatting (Black, isort)")
    print("  • Linting (flake8)")
    print("  • Security scanning (Bandit)")
    print("  • Basic file checks")
    print("  • Tests (pytest)")
    print("\nTo bypass hooks temporarily: git commit --no-verify")
    print("\n📋 Manual installation command if needed:")
    print("pip install pytest pytest-cov pytest-mock pytest-benchmark psutil memory-profiler pynacl pbr cryptography bandit safety flake8 black isort responses requests-mock")

if __name__ == "__main__":
    main()