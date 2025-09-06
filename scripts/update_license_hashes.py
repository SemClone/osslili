#!/usr/bin/env python3
"""
Script to compute and add SHA-256 and MD5 hashes to the bundled SPDX license data.
"""

import json
import hashlib
import re
from pathlib import Path


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.
    Removes whitespace variations, punctuation, and case differences.
    """
    if not text:
        return ""
    
    # Remove extra whitespace first
    text = ' '.join(text.split())
    
    # Convert to lowercase
    normalized = text.lower()
    
    # Remove URLs
    normalized = re.sub(r'https?://[^\s]+', '', normalized)
    
    # Remove email addresses
    normalized = re.sub(r'\S+@\S+', '', normalized)
    
    # Remove common variable placeholders
    normalized = re.sub(r'\[year\]|\[yyyy\]|\[name of copyright owner\]|\[fullname\]', '', normalized)
    normalized = re.sub(r'<year>|<name of author>|<organization>', '', normalized)
    normalized = re.sub(r'\{year\}|\{fullname\}|\{email\}', '', normalized)
    
    # Remove punctuation except for essential ones
    normalized = re.sub(r'[^\w\s\-]', ' ', normalized)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove common copyright lines that vary
    normalized = re.sub(r'copyright.*?\d{4}.*?(?:\n|$)', '', normalized, flags=re.IGNORECASE)
    
    # Remove leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def compute_text_hash(text: str, algorithm: str = 'sha256') -> str:
    """
    Compute hash of license text for comparison.
    
    Args:
        text: License text
        algorithm: Hash algorithm to use
        
    Returns:
        Hex digest of hash
    """
    # Normalize text for hashing
    normalized = normalize_text(text)
    
    if algorithm == 'sha256':
        hasher = hashlib.sha256()
    elif algorithm == 'md5':
        hasher = hashlib.md5()
    else:
        hasher = hashlib.sha256()
    
    hasher.update(normalized.encode('utf-8'))
    return hasher.hexdigest()


def main():
    """Main function to update license hashes."""
    # Path to the bundled data file
    data_file = Path(__file__).parent.parent / "semantic_copycat_oslili" / "data" / "spdx_licenses.json"
    
    if not data_file.exists():
        print(f"Error: Data file not found at {data_file}")
        return 1
    
    # Load existing data
    print(f"Loading data from {data_file}")
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Check if license texts are available
    if 'license_texts' not in data:
        print("Error: No license_texts found in data file")
        print("Please run download_spdx_licenses.py first to fetch license texts")
        return 1
    
    license_texts = data['license_texts']
    print(f"Found {len(license_texts)} license texts")
    
    # Compute hashes for all licenses
    license_hashes = {}
    
    for license_id, text in license_texts.items():
        if text:
            # Compute both SHA-256 and MD5 for compatibility
            license_hashes[license_id] = {
                'sha256': compute_text_hash(text, 'sha256'),
                'md5': compute_text_hash(text, 'md5'),
                'text_length': len(text),
                'normalized_length': len(normalize_text(text))
            }
            print(f"Computed hashes for {license_id}")
    
    print(f"\nComputed hashes for {len(license_hashes)} licenses")
    
    # Add hashes to data
    data['license_hashes'] = license_hashes
    
    # Save updated data
    print(f"\nSaving updated data to {data_file}")
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Successfully updated license hashes!")
    
    # Print some statistics
    print("\nHash statistics:")
    print(f"Total licenses with hashes: {len(license_hashes)}")
    
    # Check for any hash collisions
    sha256_hashes = {}
    md5_hashes = {}
    
    for license_id, hashes in license_hashes.items():
        sha256 = hashes['sha256']
        md5 = hashes['md5']
        
        if sha256 in sha256_hashes:
            print(f"SHA-256 collision: {license_id} and {sha256_hashes[sha256]}")
        else:
            sha256_hashes[sha256] = license_id
        
        if md5 in md5_hashes:
            print(f"MD5 collision: {license_id} and {md5_hashes[md5]}")
        else:
            md5_hashes[md5] = license_id
    
    if len(sha256_hashes) == len(license_hashes) and len(md5_hashes) == len(license_hashes):
        print("No hash collisions detected!")
    
    return 0


if __name__ == "__main__":
    exit(main())