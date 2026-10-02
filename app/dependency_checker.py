"""
Comprehensive Dependency Checker for PowerTrader
Scans all modules and reports availability status.
"""

import importlib
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class DependencyInfo:
    """Information about a dependency."""

    name: str
    module: str
    required: bool
    available: bool
    version: Optional[str] = None
    error: Optional[str] = None
    description: str = ""
    install_command: str = ""


class DependencyChecker:
    """Comprehensive dependency checker for PowerTrader."""

    def __init__(self):
        self.dependencies = self._define_dependencies()
        self.results = {}

    def _define_dependencies(self) -> List[DependencyInfo]:
        """Define all PowerTrader dependencies."""
        return [
            # Core GUI dependencies
            DependencyInfo(
                name="Tkinter",
                module="tkinter",
                required=True,
                available=False,
                description="Core GUI framework (should be built into Python)",
                install_command="Built into Python - reinstall Python if missing",
            ),
            DependencyInfo(
                name="TTK Themes",
                module="tkinter.ttk",
                required=True,
                available=False,
                description="Enhanced GUI widgets",
                install_command="Built into Python",
            ),
            # Data visualization
            DependencyInfo(
                name="Matplotlib",
                module="matplotlib",
                required=True,
                available=False,
                description="Chart plotting and data visualization",
                install_command="pip install matplotlib",
            ),
            DependencyInfo(
                name="NumPy",
                module="numpy",
                required=True,
                available=False,
                description="Numerical computing (required by matplotlib)",
                install_command="pip install numpy",
            ),
            # Database and ORM
            DependencyInfo(
                name="SQLAlchemy",
                module="sqlalchemy",
                required=False,
                available=False,
                description="Database ORM for order management",
                install_command="pip install sqlalchemy",
            ),
            # HTTP requests
            DependencyInfo(
                name="Requests",
                module="requests",
                required=False,
                available=False,
                description="HTTP library for API calls",
                install_command="pip install requests",
            ),
            # Async support
            DependencyInfo(
                name="AsyncIO",
                module="asyncio",
                required=False,
                available=False,
                description="Asynchronous programming support",
                install_command="Built into Python 3.7+",
            ),
            # JSON handling (should be built-in)
            DependencyInfo(
                name="JSON",
                module="json",
                required=True,
                available=False,
                description="JSON data handling",
                install_command="Built into Python",
            ),
            # Threading
            DependencyInfo(
                name="Threading",
                module="threading",
                required=True,
                available=False,
                description="Multi-threading support",
                install_command="Built into Python",
            ),
            # Date/Time
            DependencyInfo(
                name="DateTime",
                module="datetime",
                required=True,
                available=False,
                description="Date and time handling",
                install_command="Built into Python",
            ),
            # LLM Dependencies
            DependencyInfo(
                name="OpenAI",
                module="openai",
                required=False,
                available=False,
                description="OpenAI API for LLM research engine",
                install_command="pip install openai",
            ),
            # Data science (optional)
            DependencyInfo(
                name="Pandas",
                module="pandas",
                required=False,
                available=False,
                description="Data analysis and manipulation",
                install_command="pip install pandas",
            ),
            # Scientific computing (optional)
            DependencyInfo(
                name="SciPy",
                module="scipy",
                required=False,
                available=False,
                description="Scientific computing library",
                install_command="pip install scipy",
            ),
            # Web scraping (optional)
            DependencyInfo(
                name="BeautifulSoup",
                module="bs4",
                required=False,
                available=False,
                description="Web scraping and HTML parsing",
                install_command="pip install beautifulsoup4",
            ),
            # Cryptocurrency libraries (optional)
            DependencyInfo(
                name="CCXT",
                module="ccxt",
                required=False,
                available=False,
                description="Cryptocurrency exchange library",
                install_command="pip install ccxt",
            ),
            # Configuration files
            DependencyInfo(
                name="YAML",
                module="yaml",
                required=False,
                available=False,
                description="YAML configuration file support",
                install_command="pip install pyyaml",
            ),
            # Logging (built-in)
            DependencyInfo(
                name="Logging",
                module="logging",
                required=True,
                available=False,
                description="Application logging",
                install_command="Built into Python",
            ),
            # File operations
            DependencyInfo(
                name="OS",
                module="os",
                required=True,
                available=False,
                description="Operating system interface",
                install_command="Built into Python",
            ),
            DependencyInfo(
                name="Pathlib",
                module="pathlib",
                required=False,
                available=False,
                description="Modern path handling",
                install_command="Built into Python 3.4+",
            ),
            # Regular expressions
            DependencyInfo(
                name="RegEx",
                module="re",
                required=True,
                available=False,
                description="Regular expression support",
                install_command="Built into Python",
            ),
            # Subprocess
            DependencyInfo(
                name="Subprocess",
                module="subprocess",
                required=True,
                available=False,
                description="Process management",
                install_command="Built into Python",
            ),
            # UUID
            DependencyInfo(
                name="UUID",
                module="uuid",
                required=False,
                available=False,
                description="Unique identifier generation",
                install_command="Built into Python",
            ),
            # Hashlib
            DependencyInfo(
                name="Hashlib",
                module="hashlib",
                required=False,
                available=False,
                description="Cryptographic hashing",
                install_command="Built into Python",
            ),
            # Collections
            DependencyInfo(
                name="Collections",
                module="collections",
                required=True,
                available=False,
                description="Specialized container datatypes",
                install_command="Built into Python",
            ),
        ]

    def check_all_dependencies(self) -> Dict[str, DependencyInfo]:
        """Check all dependencies and return results."""
        print("Checking PowerTrader dependencies...")
        print("=" * 50)

        for dep in self.dependencies:
            self.results[dep.name] = self._check_dependency(dep)

        self._print_summary()
        return self.results

    def _check_dependency(self, dep: DependencyInfo) -> DependencyInfo:
        """Check a single dependency."""
        try:
            module = importlib.import_module(dep.module)
            dep.available = True

            # Try to get version
            if hasattr(module, "__version__"):
                dep.version = module.__version__
            elif hasattr(module, "version"):
                dep.version = module.version
            elif hasattr(module, "VERSION"):
                dep.version = str(module.VERSION)
            elif dep.module == "tkinter":
                dep.version = "Built-in"

            print(
                f"✓ {dep.name:15} - Available {f'(v{dep.version})' if dep.version else ''}"
            )

        except ImportError as e:
            dep.available = False
            dep.error = str(e)
            status = "REQUIRED" if dep.required else "Optional"
            print(f"✗ {dep.name:15} - Missing ({status}) - {dep.install_command}")

        except Exception as e:
            dep.available = False
            dep.error = f"Unexpected error: {str(e)}"
            print(f"? {dep.name:15} - Error: {str(e)}")

        return dep

    def _print_summary(self):
        """Print a summary of dependency check results."""
        print("\n" + "=" * 50)
        print("DEPENDENCY CHECK SUMMARY")
        print("=" * 50)

        available = sum(1 for dep in self.results.values() if dep.available)
        total = len(self.results)
        required_missing = [
            dep for dep in self.results.values() if dep.required and not dep.available
        ]
        optional_missing = [
            dep
            for dep in self.results.values()
            if not dep.required and not dep.available
        ]

        print(f"Total Dependencies: {total}")
        print(f"Available: {available}")
        print(f"Missing: {total - available}")

        if required_missing:
            print(
                f"\n⚠️  CRITICAL: {len(required_missing)} required dependencies missing!"
            )
            for dep in required_missing:
                print(f"   - {dep.name}: {dep.install_command}")

        if optional_missing:
            print(
                f"\n💡 OPTIONAL: {len(optional_missing)} optional dependencies missing"
            )
            print("   (These provide enhanced functionality)")
            for dep in optional_missing:
                print(f"   - {dep.name}: {dep.install_command}")

        print(f"\n🎯 PowerTrader Status:")
        if not required_missing:
            print("   ✅ Core functionality available")
        else:
            print("   ❌ Core functionality limited - install required dependencies")

        functionality_status = self._get_functionality_status()
        for feature, status in functionality_status.items():
            print(f"   {status['icon']} {feature}: {status['status']}")

    def _get_functionality_status(self) -> Dict[str, Dict[str, str]]:
        """Get status of different PowerTrader functionality areas."""
        status = {}

        # Core GUI
        tkinter_available = self.results.get(
            "Tkinter", DependencyInfo("", "", True, False)
        ).available
        matplotlib_available = self.results.get(
            "Matplotlib", DependencyInfo("", "", True, False)
        ).available

        if tkinter_available and matplotlib_available:
            status["Core GUI"] = {"icon": "✅", "status": "Fully Available"}
        elif tkinter_available:
            status["Core GUI"] = {"icon": "⚠️", "status": "Basic GUI only (no charts)"}
        else:
            status["Core GUI"] = {"icon": "❌", "status": "Not Available"}

        # Order Management
        sqlalchemy_available = self.results.get(
            "SQLAlchemy", DependencyInfo("", "", False, False)
        ).available

        if sqlalchemy_available:
            status["Order Management"] = {"icon": "✅", "status": "Fully Available"}
        else:
            status["Order Management"] = {
                "icon": "⚠️",
                "status": "Limited (no database persistence)",
            }

        # LLM Research Engine
        openai_available = self.results.get(
            "OpenAI", DependencyInfo("", "", False, False)
        ).available
        requests_available = self.results.get(
            "Requests", DependencyInfo("", "", False, False)
        ).available

        if openai_available and requests_available:
            status["LLM Research"] = {"icon": "✅", "status": "Fully Available"}
        elif requests_available:
            status["LLM Research"] = {
                "icon": "⚠️",
                "status": "Limited (no LLM integration)",
            }
        else:
            status["LLM Research"] = {"icon": "❌", "status": "Not Available"}

        # Exchange Integration
        ccxt_available = self.results.get(
            "CCXT", DependencyInfo("", "", False, False)
        ).available

        if ccxt_available:
            status["Exchange APIs"] = {"icon": "✅", "status": "Available"}
        else:
            status["Exchange APIs"] = {
                "icon": "⚠️",
                "status": "Limited (manual trading only)",
            }

        # Data Analysis
        pandas_available = self.results.get(
            "Pandas", DependencyInfo("", "", False, False)
        ).available
        numpy_available = self.results.get(
            "NumPy", DependencyInfo("", "", True, False)
        ).available

        if pandas_available and numpy_available:
            status["Data Analysis"] = {"icon": "✅", "status": "Advanced Available"}
        elif numpy_available:
            status["Data Analysis"] = {"icon": "⚠️", "status": "Basic Available"}
        else:
            status["Data Analysis"] = {"icon": "❌", "status": "Not Available"}

        return status

    def get_missing_required(self) -> List[DependencyInfo]:
        """Get list of missing required dependencies."""
        return [
            dep for dep in self.results.values() if dep.required and not dep.available
        ]

    def get_missing_optional(self) -> List[DependencyInfo]:
        """Get list of missing optional dependencies."""
        return [
            dep
            for dep in self.results.values()
            if not dep.required and not dep.available
        ]

    def generate_install_script(self) -> str:
        """Generate pip install script for missing dependencies."""
        missing_optional = self.get_missing_optional()
        missing_required = self.get_missing_required()

        script = "# PowerTrader Dependency Installation Script\n"
        script += f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if missing_required:
            script += "# REQUIRED dependencies (install these first)\n"
            for dep in missing_required:
                if dep.install_command.startswith("pip install"):
                    script += f"{dep.install_command}  # {dep.description}\n"
            script += "\n"

        if missing_optional:
            script += "# OPTIONAL dependencies (for enhanced functionality)\n"
            for dep in missing_optional:
                if dep.install_command.startswith("pip install"):
                    script += f"{dep.install_command}  # {dep.description}\n"

        if missing_required or missing_optional:
            script += "\n# Install all at once:\n"
            all_packages = []
            for dep in missing_required + missing_optional:
                if dep.install_command.startswith("pip install"):
                    package = dep.install_command.replace("pip install ", "")
                    all_packages.append(package)

            if all_packages:
                script += f"pip install {' '.join(all_packages)}\n"

        return script

    def save_report(self, filename: str = None):
        """Save dependency report to file (default: the PowerTraderAI log folder)."""
        if filename is None:
            import pt_paths

            filename = pt_paths.log_file("dependency_report.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"PowerTrader Dependency Report\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")

                # Available dependencies
                f.write("AVAILABLE DEPENDENCIES:\n")
                for name, dep in self.results.items():
                    if dep.available:
                        version_str = f" (v{dep.version})" if dep.version else ""
                        f.write(f"✓ {name}{version_str} - {dep.description}\n")

                # Missing dependencies
                f.write("\nMISSING DEPENDENCIES:\n")
                for name, dep in self.results.items():
                    if not dep.available:
                        status = "REQUIRED" if dep.required else "Optional"
                        f.write(f"✗ {name} ({status}) - {dep.description}\n")
                        f.write(f"  Install: {dep.install_command}\n")

                # Install script
                f.write("\n" + "=" * 50 + "\n")
                f.write("INSTALLATION SCRIPT:\n")
                f.write("=" * 50 + "\n")
                f.write(self.generate_install_script())

            print(f"\nDependency report saved to: {filename}")
            return True

        except Exception as e:
            print(f"Error saving report: {e}")
            return False


# Global instance
_checker = None


def get_dependency_checker() -> DependencyChecker:
    """Get global dependency checker instance."""
    global _checker
    if _checker is None:
        _checker = DependencyChecker()
    return _checker


def quick_check() -> Dict[str, bool]:
    """Quick check of critical dependencies."""
    critical_modules = {
        "tkinter": "Core GUI",
        "matplotlib": "Charts",
        "sqlalchemy": "Order Management",
        "openai": "LLM Research",
        "requests": "API Calls",
    }

    results = {}
    for module, description in critical_modules.items():
        try:
            importlib.import_module(module)
            results[description] = True
        except ImportError:
            results[description] = False

    return results


if __name__ == "__main__":
    # Run dependency check
    checker = get_dependency_checker()
    results = checker.check_all_dependencies()

    # Save report
    checker.save_report()

    # Generate install script
    install_script = checker.generate_install_script()
    if install_script.strip():
        with open("install_dependencies.sh", "w") as f:
            f.write("#!/bin/bash\n")
            f.write(install_script)
        print("\nInstall script saved to: install_dependencies.sh")

    print("\nDependency check complete!")
