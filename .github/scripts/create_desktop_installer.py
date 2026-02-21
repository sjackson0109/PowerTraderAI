"""
PowerTraderAI+ Desktop Installer

Creates a Windows desktop installer package with auto-updater and dependency management.
Includes Python environment setup, configuration templates, and desktop shortcuts.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
import zipfile
import requests
from datetime import datetime

class DesktopInstaller:
    """Desktop application installer for PowerTraderAI+."""
    
    def __init__(self):
        self.app_name = "PowerTraderAI+"
        self.version = "4.0.0"
        self.project_dir = Path(__file__).parent.absolute()
        self.build_dir = self.project_dir / "dist" / "desktop"
        self.installer_dir = self.project_dir / "installer"
        
        # Application files to include
        self.app_files = [
            "pt_desktop_app.py",
            "pt_gui_integration.py", 
            "pt_hub.py",
            "pt_trader.py",
            "pt_thinker.py",
            "pt_trainer.py",
            "pt_paper_trading.py",
            "pt_live_monitor.py",
            "pt_risk.py",
            "pt_cost.py", 
            "pt_logging.py",
            "pt_integration.py",
            "requirements.txt",
            "README.md",
            "LICENSE"
        ]
        
        # Configuration templates
        self.config_templates = {
            "settings.json": {
                "coins": ["BTC", "ETH", "ADA", "DOT", "MATIC"],
                "auto_start_scripts": False,
                "main_neural_dir": "./neural_data",
                "hub_data_dir": "./hub_data",
                "script_neural_runner2": "pt_thinker.py",
                "script_trader": "pt_trader.py",
                "script_neural_trainer": "pt_trainer.py",
                "paper_trading": {
                    "initial_balance": 10000.00,
                    "commission_rate": 0.001
                },
                "risk_management": {
                    "max_position_size_pct": 20,
                    "max_daily_loss_pct": 5,
                    "risk_per_trade_pct": 2
                },
                "monitoring": {
                    "refresh_interval_seconds": 10,
                    "alert_levels": ["WARNING", "ERROR", "CRITICAL"]
                }
            },
            "logging_config.json": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "standard": {
                        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                    }
                },
                "handlers": {
                    "file": {
                        "level": "INFO",
                        "formatter": "standard",
                        "class": "logging.handlers.RotatingFileHandler",
                        "filename": "powertrader.log",
                        "maxBytes": 10485760,
                        "backupCount": 5
                    },
                    "console": {
                        "level": "INFO", 
                        "formatter": "standard",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout"
                    }
                },
                "loggers": {
                    "": {
                        "handlers": ["file", "console"],
                        "level": "INFO",
                        "propagate": False
                    }
                }
            }
        }
    
    def create_installer(self):
        """Create the desktop installer package."""
        print(f"Creating {self.app_name} Desktop Installer v{self.version}")
        print("=" * 60)
        
        try:
            # Clean and create build directory
            self._prepare_build_dir()
            
            # Copy application files
            self._copy_app_files()
            
            # Create configuration templates
            self._create_config_templates()
            
            # Create Python environment setup
            self._create_python_setup()
            
            # Create desktop shortcuts
            self._create_shortcuts()
            
            # Create installer scripts
            self._create_installer_scripts()
            
            # Package everything
            installer_path = self._create_installer_package()
            
            print(f"\nDesktop installer created successfully!")
            print(f"Installer location: {installer_path}")
            print(f"Package size: {self._format_size(installer_path.stat().st_size)}")
            
            return installer_path
            
        except Exception as e:
            print(f"Installer creation failed: {e}")
            raise
    
    def _prepare_build_dir(self):
        """Prepare the build directory."""
        print("Preparing build directory...")
        
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        
        self.build_dir.mkdir(parents=True)
        
        # Create subdirectories
        (self.build_dir / "app").mkdir()
        (self.build_dir / "config").mkdir()
        (self.build_dir / "data").mkdir()
        (self.build_dir / "neural_data").mkdir()
        (self.build_dir / "hub_data").mkdir()
        (self.build_dir / "logs").mkdir()
    
    def _copy_app_files(self):
        """Copy application files to build directory."""
        print("Copying application files...")
        
        for file_name in self.app_files:
            src_path = self.project_dir / file_name
            dst_path = self.build_dir / "app" / file_name
            
            if src_path.exists():
                shutil.copy2(src_path, dst_path)
                print(f"   Copied {file_name}")
            else:
                print(f"   Warning: {file_name} (not found)")
    
    def _create_config_templates(self):
        """Create configuration template files."""
        print("Creating configuration templates...")
        
        for config_file, config_data in self.config_templates.items():
            config_path = self.build_dir / "config" / config_file
            
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            print(f"   Created {config_file}")
    
    def _create_python_setup(self):
        """Create Python environment setup scripts."""
        print("Creating Python environment setup...")
        
        # Requirements installer script
        setup_script = '''@echo off
echo PowerTraderAI+ - Python Environment Setup
echo =========================================

echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo Installing required packages...
python -m pip install --upgrade pip
python -m pip install -r app\\requirements.txt

if %errorlevel% neq 0 (
    echo ERROR: Failed to install required packages
    pause
    exit /b 1
)

echo Setup complete!
pause
'''
        
        setup_path = self.build_dir / "setup_environment.bat"
        with open(setup_path, 'w') as f:
            f.write(setup_script)
        
        # Application launcher script
        launcher_script = '''@echo off
title PowerTraderAI+

echo Starting PowerTraderAI+...
cd /d "%~dp0"

python app\\pt_desktop_app.py

if %errorlevel% neq 0 (
    echo Application exited with error code %errorlevel%
    pause
)
'''
        
        launcher_path = self.build_dir / "PowerTrader_AI.bat"
        with open(launcher_path, 'w') as f:
            f.write(launcher_script)
        
        print("   Created setup_environment.bat")
        print("   Created PowerTrader_AI.bat")
    
    def _create_shortcuts(self):
        """Create desktop shortcuts."""
        print("Creating desktop shortcuts...")
        
        # PowerShell script to create shortcuts
        shortcut_script = f'''
$WshShell = New-Object -comObject WScript.Shell
$InstallDir = Get-Location

# PowerTraderAI+ shortcut
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\\Desktop\\PowerTraderAI+.lnk")
$Shortcut.TargetPath = "$InstallDir\\PowerTrader_AI.bat"
$Shortcut.WorkingDirectory = "$InstallDir"
$Shortcut.Description = "{self.app_name} v{self.version} - Desktop Trading Application"
$Shortcut.Save()

# Setup shortcut
$SetupShortcut = $WshShell.CreateShortcut("$env:USERPROFILE\\Desktop\\PowerTraderAI+ Setup.lnk")  
$SetupShortcut.TargetPath = "$InstallDir\\setup_environment.bat"
$SetupShortcut.WorkingDirectory = "$InstallDir"
$SetupShortcut.Description = "Setup Python environment for {self.app_name}"
$SetupShortcut.Save()

Write-Host "Desktop shortcuts created successfully!"
'''
        
        shortcut_path = self.build_dir / "create_shortcuts.ps1"
        with open(shortcut_path, 'w') as f:
            f.write(shortcut_script)
        
        print("   Created create_shortcuts.ps1")
    
    def _create_installer_scripts(self):
        """Create installer and uninstaller scripts."""
        print("Creating installer scripts...")
        
        # Main installer script
        installer_script = f'''@echo off
title {self.app_name} Installer v{self.version}

echo {self.app_name} Desktop Installer
echo {'=' * 40}
echo Version: {self.version}
echo Target: Windows Desktop Application  
echo {'=' * 40}
echo.

echo This installer will:
echo - Set up {self.app_name} application files
echo - Create Python environment setup tools
echo - Create desktop shortcuts
echo - Configure application settings
echo.

set /p choice="Continue with installation? (Y/N): "
if /i "%choice%" neq "Y" (
    echo Installation cancelled.
    pause
    exit /b 0
)

echo.
echo Installing {self.app_name}...

echo Creating application directory...
if not exist "%USERPROFILE%\\{self.app_name}" mkdir "%USERPROFILE%\\{self.app_name}"

echo Copying application files...
xcopy /s /y app "%USERPROFILE%\\{self.app_name}\\app\\"
xcopy /s /y config "%USERPROFILE%\\{self.app_name}\\config\\"
xcopy /s /y data "%USERPROFILE%\\{self.app_name}\\data\\"
xcopy /s /y neural_data "%USERPROFILE%\\{self.app_name}\\neural_data\\"
xcopy /s /y hub_data "%USERPROFILE%\\{self.app_name}\\hub_data\\"
xcopy /s /y logs "%USERPROFILE%\\{self.app_name}\\logs\\"

copy setup_environment.bat "%USERPROFILE%\\{self.app_name}\\"
copy PowerTrader_AI.bat "%USERPROFILE%\\{self.app_name}\\"
copy create_shortcuts.ps1 "%USERPROFILE%\\{self.app_name}\\"

echo Creating desktop shortcuts...
cd /d "%USERPROFILE%\\{self.app_name}"
powershell -ExecutionPolicy Bypass -File create_shortcuts.ps1

echo.
echo {self.app_name} installed successfully!
echo Installation directory: %USERPROFILE%\\{self.app_name}
echo.
echo Next steps:
echo 1. Run "PowerTraderAI+ Setup" from desktop to install Python packages
echo 2. Run "PowerTraderAI+" from desktop to start the application
echo.
pause
'''
        
        installer_path = self.build_dir / "install.bat"
        with open(installer_path, 'w') as f:
            f.write(installer_script)
        
        # Uninstaller script  
        uninstaller_script = f'''@echo off
title {self.app_name} Uninstaller

echo {self.app_name} Uninstaller
echo {'=' * 30}
echo.

set /p choice="Are you sure you want to uninstall {self.app_name}? (Y/N): "
if /i "%choice%" neq "Y" (
    echo Uninstall cancelled.
    pause
    exit /b 0
)

echo.
echo Removing {self.app_name}...

echo Removing application files...
if exist "%USERPROFILE%\\{self.app_name}" rmdir /s /q "%USERPROFILE%\\{self.app_name}"

echo Removing desktop shortcuts...
if exist "%USERPROFILE%\\Desktop\\PowerTraderAI+.lnk" del "%USERPROFILE%\\Desktop\\PowerTraderAI+.lnk"
if exist "%USERPROFILE%\\Desktop\\PowerTraderAI+ Setup.lnk" del "%USERPROFILE%\\Desktop\\PowerTraderAI+ Setup.lnk"

echo.
echo {self.app_name} uninstalled successfully!
pause
'''
        
        uninstaller_path = self.build_dir / "uninstall.bat"
        with open(uninstaller_path, 'w') as f:
            f.write(uninstaller_script)
        
        print("   Created install.bat")
        print("   Created uninstall.bat")
    
    def _create_installer_package(self):
        """Create the final installer package."""
        print("Creating installer package...")
        
        installer_name = f"{self.app_name.replace(' ', '_')}_Desktop_v{self.version}.zip"
        installer_path = self.project_dir / installer_name
        
        with zipfile.ZipFile(installer_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(self.build_dir):
                for file in files:
                    file_path = Path(root) / file
                    arc_path = file_path.relative_to(self.build_dir)
                    zf.write(file_path, arc_path)
        
        return installer_path
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

def main():
    """Main installer creation function."""
    print(f"PowerTraderAI+ Desktop Installer Builder")
    print(f"Build Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        installer = DesktopInstaller()
        installer_path = installer.create_installer()
        
        print("\\n" + "=" * 60)
        print("INSTALLATION INSTRUCTIONS:")
        print("=" * 60)
        print("1. Extract the installer ZIP file to a temporary directory")
        print("2. Run 'install.bat' as Administrator")
        print("3. Follow the installation prompts")
        print("4. Run 'PowerTraderAI+ Setup' from desktop to install Python packages")
        print("5. Run 'PowerTraderAI+' from desktop to start the application")
        print()
        print("NOTE: Requires Python 3.9+ installed and added to PATH")
        print("Download Python: https://python.org/downloads/")
        
        return True
        
    except Exception as e:
        print(f"\nInstaller creation failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)