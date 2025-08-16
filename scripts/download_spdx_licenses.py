#!/usr/bin/env python
"""
Download SPDX license data and bundle it with the package.
This script should be run during package build time.
"""

import json
import os
import sys
from pathlib import Path
import requests
from datetime import datetime

def download_spdx_licenses():
    """Download and process SPDX license data."""
    
    print("Downloading SPDX license data...")
    
    # SPDX API endpoints
    SPDX_API_BASE = "https://raw.githubusercontent.com/spdx/license-list-data/main/json"
    LICENSES_URL = f"{SPDX_API_BASE}/licenses.json"
    DETAILS_URL = f"{SPDX_API_BASE}/details/"
    
    # Download main license list
    print(f"Fetching license list from {LICENSES_URL}")
    response = requests.get(LICENSES_URL, timeout=30)
    response.raise_for_status()
    licenses_data = response.json()
    
    # Create bundled data structure
    bundled_data = {
        "version": licenses_data.get("licenseListVersion", "unknown"),
        "release_date": licenses_data.get("releaseDate", datetime.now().isoformat()),
        "download_date": datetime.now().isoformat(),
        "licenses": {}
    }
    
    # Process each license
    total_licenses = len(licenses_data.get("licenses", []))
    print(f"Processing {total_licenses} licenses...")
    
    for i, license_info in enumerate(licenses_data.get("licenses", []), 1):
        license_id = license_info.get("licenseId")
        if not license_id:
            continue
        
        if i % 10 == 0:
            print(f"  Processed {i}/{total_licenses} licenses...")
        
        # Store basic info
        bundled_data["licenses"][license_id] = {
            "name": license_info.get("name", license_id),
            "reference": license_info.get("reference", ""),
            "isDeprecatedLicenseId": license_info.get("isDeprecatedLicenseId", False),
            "isOsiApproved": license_info.get("isOsiApproved", False),
            "isFsfLibre": license_info.get("isFsfLibre", False),
            "seeAlso": license_info.get("seeAlso", [])
        }
        
        # Try to download full license text for common licenses
        if license_id in COMMON_LICENSES:
            try:
                details_url = f"{DETAILS_URL}{license_id}.json"
                detail_response = requests.get(details_url, timeout=10)
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    bundled_data["licenses"][license_id]["text"] = detail_data.get("licenseText", "")
                    bundled_data["licenses"][license_id]["standardLicenseTemplate"] = detail_data.get("standardLicenseTemplate", "")
            except Exception as e:
                print(f"    Warning: Could not download text for {license_id}: {e}")
    
    # Create license name mappings and aliases
    bundled_data["name_mappings"] = create_name_mappings(bundled_data["licenses"])
    bundled_data["aliases"] = create_common_aliases()
    
    print(f"Successfully processed {len(bundled_data['licenses'])} licenses")
    
    return bundled_data

def create_name_mappings(licenses):
    """Create mappings from license names to IDs."""
    mappings = {}
    
    for license_id, info in licenses.items():
        name = info.get("name", "")
        if name and name != license_id:
            # Store both exact and lowercase versions
            mappings[name] = license_id
            mappings[name.lower()] = license_id
            
            # Also store without "License" suffix
            if name.endswith(" License"):
                short_name = name[:-8].strip()
                mappings[short_name] = license_id
                mappings[short_name.lower()] = license_id
    
    return mappings

def create_common_aliases():
    """Create common license aliases and variations."""
    return {
        # Apache variants
        "Apache 2.0": "Apache-2.0",
        "Apache 2": "Apache-2.0",
        "Apache License 2.0": "Apache-2.0",
        "Apache License Version 2.0": "Apache-2.0",
        "Apache Software License 2.0": "Apache-2.0",
        "ASL 2.0": "Apache-2.0",
        "Apache-2": "Apache-2.0",
        
        # MIT variants
        "MIT License": "MIT",
        "The MIT License": "MIT",
        "Expat": "MIT",
        
        # BSD variants
        "BSD": "BSD-3-Clause",
        "BSD License": "BSD-3-Clause",
        "BSD 3-Clause": "BSD-3-Clause",
        "BSD-3": "BSD-3-Clause",
        "New BSD": "BSD-3-Clause",
        "Modified BSD": "BSD-3-Clause",
        "BSD 2-Clause": "BSD-2-Clause",
        "Simplified BSD": "BSD-2-Clause",
        "FreeBSD": "BSD-2-Clause",
        
        # GPL variants
        "GPL": "GPL-3.0-only",
        "GPLv2": "GPL-2.0-only",
        "GPL v2": "GPL-2.0-only",
        "GPL-2": "GPL-2.0-only",
        "GPLv3": "GPL-3.0-only",
        "GPL v3": "GPL-3.0-only",
        "GPL-3": "GPL-3.0-only",
        "GPL version 2": "GPL-2.0-only",
        "GPL version 3": "GPL-3.0-only",
        
        # LGPL variants
        "LGPL": "LGPL-3.0-only",
        "LGPLv2": "LGPL-2.0-only",
        "LGPLv2.1": "LGPL-2.1-only",
        "LGPLv3": "LGPL-3.0-only",
        "Lesser GPL": "LGPL-3.0-only",
        
        # Other common variants
        "ISC License": "ISC",
        "Mozilla Public License 2.0": "MPL-2.0",
        "MPL 2.0": "MPL-2.0",
        "MPL": "MPL-2.0",
        "Artistic License 2.0": "Artistic-2.0",
        "Artistic 2.0": "Artistic-2.0",
        "CC0": "CC0-1.0",
        "Public Domain": "CC0-1.0",
        "Unlicense": "Unlicense",
        "WTFPL": "WTFPL",
        "PostgreSQL": "PostgreSQL",
        "Python Software Foundation License": "PSF-2.0",
        "PSF": "PSF-2.0",
        "Zlib": "Zlib",
        "Boost": "BSL-1.0",
        "Boost Software License": "BSL-1.0",
    }

# Common licenses to download full text for
COMMON_LICENSES = {
    "MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC",
    "GPL-2.0-only", "GPL-3.0-only", "LGPL-2.1-only", "LGPL-3.0-only",
    "MPL-2.0", "CC0-1.0", "Unlicense", "BSL-1.0", "AFL-3.0",
    "Artistic-2.0", "EPL-1.0", "EPL-2.0", "EUPL-1.2", "AGPL-3.0-only",
    "GPL-2.0-or-later", "GPL-3.0-or-later", "LGPL-2.1-or-later",
    "LGPL-3.0-or-later", "AGPL-3.0-or-later", "CC-BY-4.0",
    "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
    "CDDL-1.0", "CPL-1.0", "ECL-2.0", "MIT-0", "MS-PL", "MS-RL",
    "NCSA", "OpenSSL", "PHP-3.01", "PostgreSQL", "PSF-2.0",
    "Ruby", "Vim", "W3C", "WTFPL", "X11", "Zlib", "ZPL-2.1"
}

def main():
    """Main entry point."""
    
    # Determine output path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "semantic_copycat_oslili" / "data"
    
    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "spdx_licenses.json"
    
    try:
        # Download and process licenses
        bundled_data = download_spdx_licenses()
        
        # Save to file
        print(f"\nSaving bundled license data to {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(bundled_data, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print(f"\nSuccess! Bundled {len(bundled_data['licenses'])} licenses")
        print(f"  - Version: {bundled_data['version']}")
        print(f"  - Full text available for {sum(1 for l in bundled_data['licenses'].values() if 'text' in l)} licenses")
        print(f"  - Name mappings: {len(bundled_data['name_mappings'])}")
        print(f"  - Aliases: {len(bundled_data['aliases'])}")
        print(f"  - File size: {output_file.stat().st_size / 1024:.1f} KB")
        
        return 0
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())