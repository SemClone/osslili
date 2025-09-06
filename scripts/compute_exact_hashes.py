#!/usr/bin/env python3
"""
Script to compute SHA-256 and MD5 hashes for all SPDX licenses and save them.
Uses the existing license text retrieval mechanism from SPDXLicenseData.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_copycat_oslili.data.spdx_licenses import SPDXLicenseData


class Config:
    """Minimal config for SPDXLicenseData."""
    def __init__(self):
        self.cache_dir = None
        self.spdx_data_url = "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"
        self.network_timeout = 30


def main():
    """Compute SHA-256 and MD5 hashes for all licenses."""
    # Initialize SPDX data
    config = Config()
    spdx_data = SPDXLicenseData(config)
    
    # Output file for exact hashes
    output_file = Path(__file__).parent.parent / "semantic_copycat_oslili" / "data" / "exact_hashes.json"
    
    print(f"Computing exact hashes for SPDX licenses...")
    
    # Get all license IDs
    license_ids = spdx_data.get_all_license_ids()
    print(f"Found {len(license_ids)} licenses")
    
    # Compute hashes
    exact_hashes = {}
    processed = 0
    skipped = 0
    
    for license_id in license_ids:
        # Get license text
        license_text = spdx_data.get_license_text(license_id)
        
        if license_text:
            # Compute both SHA-256 and MD5
            sha256_hash = spdx_data.compute_text_hash(license_text, 'sha256')
            md5_hash = spdx_data.compute_text_hash(license_text, 'md5')
            
            # Get license info
            license_info = spdx_data.get_license_info(license_id)
            
            exact_hashes[license_id] = {
                'sha256': sha256_hash,
                'md5': md5_hash,
                'name': license_info.get('name', license_id) if license_info else license_id,
                'text_length': len(license_text),
                'normalized_length': len(spdx_data._normalize_text(license_text))
            }
            
            processed += 1
            if processed % 10 == 0:
                print(f"  Processed {processed} licenses...")
        else:
            skipped += 1
    
    print(f"\nProcessed {processed} licenses, skipped {skipped} (no text available)")
    
    # Check for collisions
    sha256_map = {}
    md5_map = {}
    collisions = []
    
    for license_id, hashes in exact_hashes.items():
        sha256 = hashes['sha256']
        md5 = hashes['md5']
        
        if sha256 in sha256_map:
            collisions.append(f"SHA-256: {license_id} == {sha256_map[sha256]}")
        else:
            sha256_map[sha256] = license_id
        
        if md5 in md5_map:
            collisions.append(f"MD5: {license_id} == {md5_map[md5]}")
        else:
            md5_map[md5] = license_id
    
    if collisions:
        print("\nWarning: Hash collisions detected!")
        for collision in collisions:
            print(f"  {collision}")
    else:
        print("\nNo hash collisions detected!")
    
    # Save to file
    print(f"\nSaving hashes to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(exact_hashes, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully saved {len(exact_hashes)} license hashes!")
    
    # Print some statistics
    print("\nStatistics:")
    print(f"  Total licenses: {len(license_ids)}")
    print(f"  Licenses with text: {processed}")
    print(f"  Unique SHA-256 hashes: {len(sha256_map)}")
    print(f"  Unique MD5 hashes: {len(md5_map)}")
    
    # Show a few examples
    print("\nExample hashes (first 3):")
    for i, (license_id, hashes) in enumerate(exact_hashes.items()):
        if i >= 3:
            break
        print(f"  {license_id}:")
        print(f"    SHA-256: {hashes['sha256'][:32]}...")
        print(f"    MD5: {hashes['md5'][:16]}...")
    
    return 0


if __name__ == "__main__":
    exit(main())