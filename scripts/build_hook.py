#!/usr/bin/env python
"""
Build hook to update SPDX licenses before packaging.
This can be called from setup.py or as part of CI/CD.
"""

import os
import sys
from pathlib import Path

def update_spdx_licenses():
    """Update SPDX licenses if needed."""
    script_dir = Path(__file__).parent
    data_file = script_dir.parent / "osslili" / "data" / "spdx_licenses.json"
    
    # Check if file exists and is recent (less than 30 days old)
    if data_file.exists():
        import time
        age_days = (time.time() - data_file.stat().st_mtime) / (24 * 3600)
        if age_days < 30:
            print(f"SPDX licenses are up to date ({age_days:.1f} days old)")
            return True
    
    # Run the download script
    download_script = script_dir / "download_spdx_licenses.py"
    if download_script.exists():
        print("Updating SPDX license data...")
        import subprocess
        result = subprocess.run([sys.executable, str(download_script)], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ SPDX licenses updated successfully")
            return True
        else:
            print(f"Warning: Failed to update SPDX licenses: {result.stderr}")
            # Continue anyway if we have existing data
            return data_file.exists()
    
    return data_file.exists()

if __name__ == "__main__":
    success = update_spdx_licenses()
    sys.exit(0 if success else 1)