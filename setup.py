import os
import subprocess
from datetime import datetime

from setuptools import find_packages, setup


# Read requirements
def read_requirements():
    req_path = os.path.join("app", "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path, "r") as f:
            return [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
    return []


# Read README
def read_readme():
    if os.path.exists("README.md"):
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    return ""


# Generate PEP 440 compliant version
def get_version():
    try:
        # Try to get commit hash
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        # Generate date-based version
        date_version = datetime.now().strftime("%Y.%-m.%-d")
        return f"{date_version}.dev0+{commit}"
    except:
        # Fallback version if git is not available
        return "2026.2.21.dev0"


setup(
    name="powertrader-ai",
    version=get_version(),
    author="Simon Jackson",
    author_email="simon@powertrader.ai",
    description="PowerTraderAI+ - Advanced Cryptocurrency Trading Bot",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/sjackson0109/PowerTraderAI",
    packages=find_packages(),
    package_dir={"powertrader": "app"},
    package_data={"powertrader": ["config/*", "*.py", "requirements.txt"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "powertrader=powertrader.pt_desktop_app:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
