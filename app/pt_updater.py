"""
PowerTraderAI+ Auto-Updater

Handles automatic updates for the desktop application, including version checking,
download management, and seamless update installation.
"""

import os
import sys
import json
import requests
import zipfile
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess

class UpdateManager:
    """Manages application updates and version checking."""
    
    def __init__(self, app_dir: str = None):
        self.app_dir = Path(app_dir or os.path.dirname(os.path.abspath(__file__)))
        self.current_version = self._get_current_version()
        self.update_url = "https://api.github.com/repos/powertrader/releases/latest"
        self.backup_dir = self.app_dir / "backup"
        self.temp_dir = self.app_dir / "temp"
        
        # Update settings
        self.settings_file = self.app_dir / "config" / "update_settings.json"
        self.settings = self._load_settings()
    
    def _get_current_version(self) -> str:
        """Get the current application version."""
        try:
            version_file = self.app_dir / "version.json"
            if version_file.exists():
                with open(version_file, 'r') as f:
                    data = json.load(f)
                    return data.get("version", "4.0.0")
        except Exception:
            pass
        return "4.0.0"
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load update settings."""
        default_settings = {
            "auto_check": True,
            "check_interval_hours": 24,
            "auto_download": True,
            "auto_install": False,  # Always ask user for install
            "last_check": None,
            "update_channel": "stable",  # stable, beta, alpha
            "backup_count": 3
        }
        
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    # Merge with defaults
                    default_settings.update(settings)
        except Exception as e:
            print(f"Warning: Could not load update settings: {e}")
        
        return default_settings
    
    def _save_settings(self):
        """Save update settings."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save update settings: {e}")
    
    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """Check for available updates."""
        try:
            print("🔍 Checking for updates...")
            
            # Mock update check for demo (replace with actual API)
            latest_version = "4.1.0"
            release_notes = """
🚀 PowerTraderAI+ v4.1.0 - Enhanced Trading Features

✨ New Features:
• Advanced risk management with portfolio heat maps
• Real-time P&L alerts and notifications
• Enhanced paper trading with realistic slippage simulation
• Multi-timeframe strategy backtesting
• Custom indicator builder

🔧 Improvements:
• 40% faster chart rendering
• Improved order execution speed
• Better memory usage optimization
• Enhanced error handling and logging

🐛 Bug Fixes:
• Fixed occasional GUI freeze during high-volume periods
• Resolved paper trading balance calculation issues
• Fixed risk management alert timing
• Improved connection stability
            """
            
            if self._is_newer_version(latest_version, self.current_version):
                update_info = {
                    "version": latest_version,
                    "current_version": self.current_version,
                    "release_notes": release_notes,
                    "download_url": f"https://github.com/powertrader/releases/download/v{latest_version}/PowerTrader_AI_Desktop_v{latest_version}.zip",
                    "size": 15728640,  # ~15 MB
                    "release_date": datetime.now().isoformat(),
                    "critical": False
                }
                
                self.settings["last_check"] = datetime.now().isoformat()
                self._save_settings()
                
                return update_info
            else:
                print(f"✓ Application is up to date (v{self.current_version})")
                return None
                
        except Exception as e:
            print(f"Error checking for updates: {e}")
            return None
    
    def _is_newer_version(self, version1: str, version2: str) -> bool:
        """Compare version strings."""
        try:
            def version_tuple(v):
                return tuple(map(int, (v.split("."))))
            return version_tuple(version1) > version_tuple(version2)
        except:
            return False
    
    def download_update(self, update_info: Dict[str, Any], progress_callback=None) -> Optional[str]:
        """Download update package."""
        try:
            download_url = update_info["download_url"]
            version = update_info["version"]
            
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            
            download_path = self.temp_dir / f"PowerTrader_AI_v{version}.zip"
            
            print(f"📥 Downloading update v{version}...")
            
            # Mock download for demo (replace with actual download)
            # In real implementation, use requests to download with progress
            import time
            for i in range(101):
                if progress_callback:
                    progress_callback(i, f"Downloading... {i}%")
                time.sleep(0.02)  # Simulate download time
            
            # Create a mock update file
            with open(download_path, 'w') as f:
                f.write("Mock update package")
            
            print(f"✓ Download completed: {download_path}")
            return str(download_path)
            
        except Exception as e:
            print(f"Error downloading update: {e}")
            return None
    
    def create_backup(self) -> bool:
        """Create backup of current installation."""
        try:
            print("💾 Creating backup...")
            
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_name = f"backup_v{self.current_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.backup_dir / backup_name
            
            # Copy current app files
            app_source = self.app_dir / "app"
            if app_source.exists():
                shutil.copytree(app_source, backup_path / "app")
            
            # Copy config files
            config_source = self.app_dir / "config"
            if config_source.exists():
                shutil.copytree(config_source, backup_path / "config")
            
            # Clean old backups (keep only last N)
            self._clean_old_backups()
            
            print(f"✓ Backup created: {backup_name}")
            return True
            
        except Exception as e:
            print(f"Error creating backup: {e}")
            return False
    
    def install_update(self, update_package_path: str) -> bool:
        """Install downloaded update."""
        try:
            print("🚀 Installing update...")
            
            # Create backup first
            if not self.create_backup():
                print("Warning: Backup creation failed, but continuing with update...")
            
            # Extract update package
            with zipfile.ZipFile(update_package_path, 'r') as zf:
                extract_path = self.temp_dir / "update_extract"
                if extract_path.exists():
                    shutil.rmtree(extract_path)
                
                zf.extractall(extract_path)
            
            # Replace app files
            new_app_dir = extract_path / "app"
            current_app_dir = self.app_dir / "app"
            
            if new_app_dir.exists():
                if current_app_dir.exists():
                    shutil.rmtree(current_app_dir)
                shutil.copytree(new_app_dir, current_app_dir)
            
            # Update version file
            version_data = {
                "version": "4.1.0",  # Mock version
                "updated": datetime.now().isoformat(),
                "previous_version": self.current_version
            }
            
            with open(self.app_dir / "version.json", 'w') as f:
                json.dump(version_data, f, indent=2)
            
            # Clean up temp files
            shutil.rmtree(self.temp_dir)
            
            print("✓ Update installed successfully!")
            return True
            
        except Exception as e:
            print(f"Error installing update: {e}")
            return False
    
    def _clean_old_backups(self):
        """Remove old backup files, keeping only the latest N."""
        try:
            if not self.backup_dir.exists():
                return
            
            backups = [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")]
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            max_backups = self.settings.get("backup_count", 3)
            for old_backup in backups[max_backups:]:
                shutil.rmtree(old_backup)
                print(f"Removed old backup: {old_backup.name}")
                
        except Exception as e:
            print(f"Warning: Could not clean old backups: {e}")
    
    def should_check_for_updates(self) -> bool:
        """Check if it's time to check for updates."""
        if not self.settings.get("auto_check", True):
            return False
        
        last_check = self.settings.get("last_check")
        if not last_check:
            return True
        
        try:
            last_check_time = datetime.fromisoformat(last_check)
            check_interval = timedelta(hours=self.settings.get("check_interval_hours", 24))
            return datetime.now() - last_check_time >= check_interval
        except:
            return True

class UpdateDialog(tk.Toplevel):
    """GUI dialog for update management."""
    
    def __init__(self, parent, update_info: Dict[str, Any]):
        super().__init__(parent)
        self.update_info = update_info
        self.result = False
        
        self.title(f"PowerTraderAI+ Update Available")
        self.geometry("600x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 50,
            parent.winfo_rooty() + 50
        ))
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the update dialog UI."""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="🚀 Update Available!", 
                              font=("Arial", 16, "bold"))
        title_label.pack()
        
        version_label = ttk.Label(header_frame, 
                                 text=f"Version {self.update_info['version']} is ready to install")
        version_label.pack()
        
        # Current vs New version
        version_frame = ttk.LabelFrame(main_frame, text="Version Information", padding="10")
        version_frame.pack(fill="x", pady=(0, 20))
        
        ttk.Label(version_frame, text=f"Current Version: {self.update_info['current_version']}").pack(anchor="w")
        ttk.Label(version_frame, text=f"New Version: {self.update_info['version']}").pack(anchor="w")
        
        size_mb = self.update_info.get('size', 0) / 1024 / 1024
        ttk.Label(version_frame, text=f"Download Size: {size_mb:.1f} MB").pack(anchor="w")
        
        # Release notes
        notes_frame = ttk.LabelFrame(main_frame, text="What's New", padding="10")
        notes_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        notes_text = tk.Text(notes_frame, height=12, wrap="word", 
                           background="#0E1626", foreground="#C7D1DB")
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=notes_text.yview)
        notes_text.configure(yscrollcommand=notes_scroll.set)
        
        notes_text.pack(side="left", fill="both", expand=True)
        notes_scroll.pack(side="right", fill="y")
        
        # Insert release notes
        notes_text.insert("1.0", self.update_info.get('release_notes', 'No release notes available.'))
        notes_text.configure(state="disabled")
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="Cancel", command=self._cancel).pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Update Now", command=self._accept).pack(side="right")
        ttk.Button(button_frame, text="Remind Me Later", command=self._remind_later).pack(side="right", padx=(0, 10))
    
    def _accept(self):
        """Accept the update."""
        self.result = True
        self.destroy()
    
    def _cancel(self):
        """Cancel the update."""
        self.result = False
        self.destroy()
    
    def _remind_later(self):
        """Remind later (cancel for now)."""
        self.result = False
        self.destroy()

class UpdateProgressDialog(tk.Toplevel):
    """Progress dialog for update download and installation."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Updating PowerTraderAI+")
        self.geometry("400x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 100,
            parent.winfo_rooty() + 100
        ))
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up progress UI."""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Preparing update...")
        self.status_label.pack(pady=(0, 20))
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        
        # Progress text
        self.progress_label = ttk.Label(main_frame, text="0%")
        self.progress_label.pack()
        
        # Cancel button (initially disabled)
        self.cancel_btn = ttk.Button(main_frame, text="Cancel", state="disabled")
        self.cancel_btn.pack(pady=(20, 0))
    
    def update_progress(self, percent: int, status: str = ""):
        """Update progress display."""
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent}%")
        if status:
            self.status_label.config(text=status)
        self.update()

def check_and_apply_updates(parent_window=None) -> bool:
    """Check for updates and apply if available and user consents."""
    try:
        update_manager = UpdateManager()
        
        # Check if we should check for updates
        if not update_manager.should_check_for_updates():
            return False
        
        # Check for updates
        update_info = update_manager.check_for_updates()
        if not update_info:
            return False
        
        # Show update dialog
        if parent_window:
            dialog = UpdateDialog(parent_window, update_info)
            parent_window.wait_window(dialog)
            
            if not dialog.result:
                return False
        
        # Show progress dialog
        if parent_window:
            progress_dialog = UpdateProgressDialog(parent_window)
        
        try:
            # Download update
            def progress_callback(percent, status):
                if parent_window:
                    progress_dialog.update_progress(percent, status)
            
            progress_callback(0, "Downloading update...")
            download_path = update_manager.download_update(update_info, progress_callback)
            
            if not download_path:
                if parent_window:
                    progress_dialog.destroy()
                messagebox.showerror("Error", "Failed to download update")
                return False
            
            # Install update
            progress_callback(100, "Installing update...")
            success = update_manager.install_update(download_path)
            
            if parent_window:
                progress_dialog.destroy()
            
            if success:
                messagebox.showinfo("Update Complete", 
                                  "Update installed successfully!\\nPlease restart PowerTraderAI+ to use the new version.")
                return True
            else:
                messagebox.showerror("Error", "Failed to install update")
                return False
                
        except Exception as e:
            if parent_window:
                progress_dialog.destroy()
            messagebox.showerror("Error", f"Update failed: {e}")
            return False
            
    except Exception as e:
        print(f"Error in update process: {e}")
        return False

if __name__ == "__main__":
    # Test the update system
    root = tk.Tk()
    root.title("Update Test")
    root.geometry("300x200")
    
    ttk.Button(root, text="Check for Updates", 
               command=lambda: check_and_apply_updates(root)).pack(pady=50)
    
    root.mainloop()