#!/usr/bin/env python
"""
Download SPDX license data and bundle it with the package.
This script should be run during package build time.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
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

    for license_info in licenses_data.get("licenses", []):
        license_id = license_info.get("licenseId")
        if not license_id:
            continue

        bundled_data["licenses"][license_id] = {
            "name": license_info.get("name", license_id),
            "reference": license_info.get("reference", ""),
            "isDeprecatedLicenseId": license_info.get("isDeprecatedLicenseId", False),
            "isOsiApproved": license_info.get("isOsiApproved", False),
            "isFsfLibre": license_info.get("isFsfLibre", False),
            "seeAlso": license_info.get("seeAlso", [])
        }

    # The text of every licence, not a chosen few. The tiers that compare text
    # can only recognise a licence whose text is here, and for the rest the
    # regex tier answered instead: a Sleepycat licence file was reported as
    # BSD-3-Clause, copyleft as permissive, and BSD-4-Clause lost the
    # advertising clause that distinguishes it (issue #126).
    #
    # `standardLicenseTemplate` is not stored. Nothing in osslili reads it and
    # it is roughly the size of the text again.
    def fetch_text(license_id):
        try:
            response = requests.get(f"{DETAILS_URL}{license_id}.json", timeout=30)
            if response.status_code == 200:
                return license_id, response.json().get("licenseText", "")
        except Exception as exc:
            print(f"    Warning: could not download text for {license_id}: {exc}")
        return license_id, None

    print(f"Fetching licence texts for {total_licenses} licenses...")
    done = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        for license_id, text in pool.map(fetch_text, list(bundled_data["licenses"])):
            done += 1
            if done % 100 == 0:
                print(f"  Fetched {done}/{total_licenses} texts...")
            if text:
                bundled_data["licenses"][license_id]["text"] = text

    with_text = sum(1 for v in bundled_data["licenses"].values() if v.get("text"))
    print(f"  {with_text} of {total_licenses} licenses have text")
    if with_text < total_licenses:
        missing = [k for k, v in bundled_data["licenses"].items() if not v.get("text")]
        print(f"  Without text: {', '.join(missing[:20])}")
    
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
# COMMON_LICENSES is gone: every licence on the list is bundled with its text
# now, so there is no chosen few to keep in step with anything (issue #126).

def main():
    """Main entry point."""
    
    # Determine output path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "osslili" / "data"
    
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