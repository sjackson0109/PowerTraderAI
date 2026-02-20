"""
Dependency security checker for PowerTrader AI.
Validates and monitors dependencies for known vulnerabilities.
"""
import os
import re
import sys
import json
import subprocess
from typing import Dict, List, Tuple, Optional
from pkg_resources import parse_version


class DependencySecurityChecker:
    """Security checker for Python dependencies."""
    
    # Known secure versions (minimum versions with security fixes)
    SECURE_VERSIONS = {
        'requests': '2.31.0',       # CVE fixes
        'cryptography': '41.0.0',   # Multiple CVE fixes
        'PyNaCl': '1.5.0',         # Security improvements
        'matplotlib': '3.7.0',     # Security fixes
        'psutil': '5.9.5',         # Security improvements
        'colorama': '0.4.6',       # Latest stable
    }
    
    # Packages with known vulnerabilities (to avoid)
    VULNERABLE_PACKAGES = {
        'pycrypto',     # Use cryptography instead
        'pycryptodome', # Potential issues, prefer cryptography
        'PyYAML',       # Unless pinned to safe version
    }
    
    # Required packages for functionality
    REQUIRED_PACKAGES = {
        'requests', 'cryptography', 'PyNaCl', 'matplotlib', 'psutil', 'colorama'
    }
    
    def __init__(self, requirements_file: str = 'requirements.txt'):
        self.requirements_file = requirements_file
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.requirements_path = os.path.join(self.base_dir, requirements_file)
    
    def parse_requirements(self) -> List[Tuple[str, Optional[str]]]:
        """Parse requirements.txt and return list of (package, version) tuples."""
        requirements = []
        
        if not os.path.exists(self.requirements_path):
            return requirements
        
        try:
            with open(self.requirements_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Parse package name and version
                        match = re.match(r'^([a-zA-Z0-9_-]+)\s*([><=!]*)\s*([0-9.]+.*)?', line)
                        if match:
                            package = match.group(1).lower()
                            version = match.group(3) if match.group(3) else None
                            requirements.append((package, version))
                        else:
                            # Simple package name without version
                            package = re.sub(r'[^a-zA-Z0-9_-]', '', line).lower()
                            if package:
                                requirements.append((package, None))
        except Exception:
            pass
        
        return requirements
    
    def check_vulnerable_packages(self, requirements: List[Tuple[str, Optional[str]]]) -> List[str]:
        """Check for known vulnerable packages."""
        issues = []
        
        for package, version in requirements:
            if package.lower() in self.VULNERABLE_PACKAGES:
                issues.append(f"VULNERABLE: {package} - Known security issues, consider alternatives")
        
        return issues
    
    def check_version_security(self, requirements: List[Tuple[str, Optional[str]]]) -> List[str]:
        """Check if package versions meet security requirements."""
        issues = []
        
        for package, version in requirements:
            if package.lower() in self.SECURE_VERSIONS:
                required_version = self.SECURE_VERSIONS[package.lower()]
                
                if version is None:
                    issues.append(f"UNPINNED: {package} - No version specified, should be >= {required_version}")
                else:
                    try:
                        if parse_version(version) < parse_version(required_version):
                            issues.append(f"OUTDATED: {package} {version} - Should be >= {required_version} for security")
                    except Exception:
                        issues.append(f"INVALID: {package} {version} - Cannot parse version")
        
        return issues
    
    def check_missing_packages(self, requirements: List[Tuple[str, Optional[str]]]) -> List[str]:
        """Check for missing required packages."""
        issues = []
        present_packages = {pkg.lower() for pkg, _ in requirements}
        
        for required_pkg in self.REQUIRED_PACKAGES:
            if required_pkg.lower() not in present_packages:
                issues.append(f"MISSING: {required_pkg} - Required for PowerTrader functionality")
        
        return issues
    
    def generate_secure_requirements(self) -> str:
        """Generate secure requirements.txt content with pinned versions."""
        lines = []
        lines.append("# PowerTrader AI Dependencies - Security Hardened")
        lines.append("# Generated with version pinning for security")
        lines.append("")
        
        # Add required packages with secure versions
        for package in sorted(self.REQUIRED_PACKAGES):
            if package.lower() in self.SECURE_VERSIONS:
                version = self.SECURE_VERSIONS[package.lower()]
                lines.append(f"{package}>={version}")
            else:
                lines.append(f"{package}")
        
        # Add KuCoin package
        lines.append("kucoin-python>=2.1.0")
        
        return '\n'.join(lines) + '\n'
    
    def run_security_audit(self) -> Dict[str, List[str]]:
        """Run comprehensive security audit on dependencies."""
        audit_results = {
            'vulnerable_packages': [],
            'version_issues': [],
            'missing_packages': [],
            'recommendations': []
        }
        
        requirements = self.parse_requirements()
        
        audit_results['vulnerable_packages'] = self.check_vulnerable_packages(requirements)
        audit_results['version_issues'] = self.check_version_security(requirements)
        audit_results['missing_packages'] = self.check_missing_packages(requirements)
        
        # Generate recommendations
        if audit_results['vulnerable_packages']:
            audit_results['recommendations'].append("Remove or replace vulnerable packages")
        
        if audit_results['version_issues']:
            audit_results['recommendations'].append("Update packages to secure versions")
        
        if audit_results['missing_packages']:
            audit_results['recommendations'].append("Install missing required packages")
        
        if not any(audit_results[key] for key in ['vulnerable_packages', 'version_issues', 'missing_packages']):
            audit_results['recommendations'].append("Dependencies appear secure")
        
        return audit_results
    
    def update_requirements_file(self) -> bool:
        """Update requirements.txt with secure versions."""
        try:
            # Backup existing file
            if os.path.exists(self.requirements_path):
                backup_path = self.requirements_path + '.backup'
                with open(self.requirements_path, 'r') as src, open(backup_path, 'w') as dst:
                    dst.write(src.read())
            
            # Write secure requirements
            secure_content = self.generate_secure_requirements()
            with open(self.requirements_path, 'w', encoding='utf-8') as f:
                f.write(secure_content)
            
            return True
        except Exception:
            return False
    
    def check_installed_packages(self) -> Dict[str, str]:
        """Check currently installed package versions."""
        installed = {}
        
        try:
            # Use pip list to get installed packages
            result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=json'], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                packages_data = json.loads(result.stdout)
                for pkg_info in packages_data:
                    name = pkg_info.get('name', '').lower()
                    version = pkg_info.get('version', '')
                    if name and version:
                        installed[name] = version
        except Exception:
            pass
        
        return installed


def run_dependency_audit():
    """Run dependency security audit and print results."""
    checker = DependencySecurityChecker()
    results = checker.run_security_audit()
    
    print("=== PowerTrader Dependency Security Audit ===")
    print()
    
    if results['vulnerable_packages']:
        print("🚨 VULNERABLE PACKAGES:")
        for issue in results['vulnerable_packages']:
            print(f"  - {issue}")
        print()
    
    if results['version_issues']:
        print("⚠️  VERSION SECURITY ISSUES:")
        for issue in results['version_issues']:
            print(f"  - {issue}")
        print()
    
    if results['missing_packages']:
        print("❌ MISSING REQUIRED PACKAGES:")
        for issue in results['missing_packages']:
            print(f"  - {issue}")
        print()
    
    if results['recommendations']:
        print("💡 RECOMMENDATIONS:")
        for rec in results['recommendations']:
            print(f"  - {rec}")
        print()
    
    # Show installed vs. required
    installed = checker.check_installed_packages()
    if installed:
        print("📦 INSTALLED PACKAGE STATUS:")
        for pkg in checker.REQUIRED_PACKAGES:
            pkg_lower = pkg.lower()
            if pkg_lower in installed:
                version = installed[pkg_lower]
                required_version = checker.SECURE_VERSIONS.get(pkg_lower, "any")
                status = "✅" if required_version == "any" or parse_version(version) >= parse_version(required_version) else "⚠️"
                print(f"  {status} {pkg}: {version} (required: {required_version})")
            else:
                print(f"  ❌ {pkg}: NOT INSTALLED")
    
    return results


if __name__ == "__main__":
    run_dependency_audit()