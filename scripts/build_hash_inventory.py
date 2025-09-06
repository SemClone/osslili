#!/usr/bin/env python3
"""
Build a comprehensive hash inventory for license matching.
Includes:
- Standard SPDX license hashes
- Common variants and aliases
- Known real-world variations (like gradle's Apache-2.0)
"""

import json
import hashlib
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_copycat_oslili.data.spdx_licenses import SPDXLicenseData


class Config:
    """Minimal config for SPDXLicenseData."""
    def __init__(self):
        self.cache_dir = None


def add_variant_hash(inventory, text, canonical_id, variant_name, spdx_data):
    """Add a hash for a license variant."""
    sha256_hash = spdx_data.compute_text_hash(text, 'sha256')
    md5_hash = spdx_data.compute_text_hash(text, 'md5')
    
    # Add to variants section
    if 'variants' not in inventory:
        inventory['variants'] = {}
    
    variant_key = f"{canonical_id}:{variant_name}"
    inventory['variants'][variant_key] = {
        'canonical_id': canonical_id,
        'variant_name': variant_name,
        'sha256': sha256_hash,
        'md5': md5_hash,
        'text_length': len(text),
        'normalized_length': len(spdx_data._normalize_text(text))
    }
    
    # Add to hash lookup tables
    if 'sha256_lookup' not in inventory:
        inventory['sha256_lookup'] = {}
    if 'md5_lookup' not in inventory:
        inventory['md5_lookup'] = {}
    
    inventory['sha256_lookup'][sha256_hash] = canonical_id
    inventory['md5_lookup'][md5_hash] = canonical_id
    
    return variant_key


def main():
    """Build comprehensive hash inventory."""
    # Initialize SPDX data
    config = Config()
    spdx_data = SPDXLicenseData(config)
    
    # Output file
    output_file = Path(__file__).parent.parent / "semantic_copycat_oslili" / "data" / "hash_inventory.json"
    
    print("Building comprehensive hash inventory...")
    
    # Initialize inventory structure
    inventory = {
        'version': '1.0.0',
        'standard_licenses': {},
        'variants': {},
        'sha256_lookup': {},
        'md5_lookup': {},
        'aliases': {}
    }
    
    # Process standard SPDX licenses
    license_ids = spdx_data.get_all_license_ids()
    print(f"Processing {len(license_ids)} standard licenses...")
    
    for license_id in license_ids:
        license_text = spdx_data.get_license_text(license_id)
        if license_text:
            sha256_hash = spdx_data.compute_text_hash(license_text, 'sha256')
            md5_hash = spdx_data.compute_text_hash(license_text, 'md5')
            
            license_info = spdx_data.get_license_info(license_id)
            
            inventory['standard_licenses'][license_id] = {
                'sha256': sha256_hash,
                'md5': md5_hash,
                'name': license_info.get('name', license_id) if license_info else license_id,
                'text_length': len(license_text),
                'normalized_length': len(spdx_data._normalize_text(license_text))
            }
            
            # Add to lookup tables
            inventory['sha256_lookup'][sha256_hash] = license_id
            inventory['md5_lookup'][md5_hash] = license_id
    
    print(f"Added {len(inventory['standard_licenses'])} standard licenses")
    
    # Add known variants and aliases
    print("\nAdding known variants...")
    
    # Example: Gradle Apache-2.0 variant (from real-world testing)
    gradle_apache_path = Path('/tmp/apache-license.txt')
    if gradle_apache_path.exists():
        with open(gradle_apache_path, 'r') as f:
            gradle_apache = f.read()
        variant = add_variant_hash(inventory, gradle_apache, 'Apache-2.0', 'gradle-wrapper', spdx_data)
        print(f"  Added variant: {variant}")
    
    # Add common aliases from bundled data
    if hasattr(spdx_data, 'aliases') and spdx_data.aliases:
        inventory['aliases'] = spdx_data.aliases
        print(f"  Added {len(spdx_data.aliases)} aliases")
    
    # Process license name mappings
    if hasattr(spdx_data, 'name_mappings') and spdx_data.name_mappings:
        print(f"  Processing {len(spdx_data.name_mappings)} name mappings...")
        # These can help identify aliases but don't have separate text
    
    # Check for hash collisions
    print("\nChecking for hash collisions...")
    sha256_collisions = {}
    md5_collisions = {}
    
    # Check standard licenses
    for license_id, data in inventory['standard_licenses'].items():
        sha256 = data['sha256']
        md5 = data['md5']
        
        # Check if hash already exists for different license
        existing_sha256 = inventory['sha256_lookup'].get(sha256)
        if existing_sha256 and existing_sha256 != license_id:
            if sha256 not in sha256_collisions:
                sha256_collisions[sha256] = []
            sha256_collisions[sha256].append(license_id)
            sha256_collisions[sha256].append(existing_sha256)
        
        existing_md5 = inventory['md5_lookup'].get(md5)
        if existing_md5 and existing_md5 != license_id:
            if md5 not in md5_collisions:
                md5_collisions[md5] = []
            md5_collisions[md5].append(license_id)
            md5_collisions[md5].append(existing_md5)
    
    if sha256_collisions:
        print(f"  Found {len(sha256_collisions)} SHA-256 collisions:")
        for hash_val, licenses in sha256_collisions.items():
            print(f"    {', '.join(set(licenses))}")
    
    if md5_collisions:
        print(f"  Found {len(md5_collisions)} MD5 collisions:")
        for hash_val, licenses in md5_collisions.items():
            print(f"    {', '.join(set(licenses))}")
    
    if not sha256_collisions and not md5_collisions:
        print("  No hash collisions detected!")
    
    # Add metadata
    inventory['metadata'] = {
        'total_standard_licenses': len(inventory['standard_licenses']),
        'total_variants': len(inventory['variants']),
        'total_aliases': len(inventory['aliases']),
        'unique_sha256_hashes': len(set(inventory['sha256_lookup'].keys())),
        'unique_md5_hashes': len(set(inventory['md5_lookup'].keys()))
    }
    
    # Save inventory
    print(f"\nSaving inventory to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)
    
    print("\nInventory summary:")
    for key, value in inventory['metadata'].items():
        print(f"  {key}: {value}")
    
    print("\nHash inventory built successfully!")
    
    # Special note about Pixar vs Apache-2.0
    if 'Pixar' in inventory['standard_licenses'] and 'Apache-2.0' in inventory['standard_licenses']:
        pixar_len = inventory['standard_licenses']['Pixar']['normalized_length']
        apache_len = inventory['standard_licenses']['Apache-2.0']['normalized_length']
        print(f"\nNote: Pixar is a 'Modified Apache 2.0 License'")
        print(f"  Pixar normalized length: {pixar_len}")
        print(f"  Apache-2.0 normalized length: {apache_len}")
        print(f"  Difference: {abs(apache_len - pixar_len)} characters")
    
    return 0


if __name__ == "__main__":
    exit(main())