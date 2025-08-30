#!/usr/bin/env python3
"""
Example demonstrating how to use semantic-copycat-oslili as a library.
"""

import json
from semantic_copycat_oslili import LicenseCopyrightDetector
from semantic_copycat_oslili.formatters.evidence_formatter import EvidenceFormatter

def example_single_file():
    """Example: Scan a single file."""
    print("=" * 60)
    print("EXAMPLE 1: Scanning a single file")
    print("=" * 60)
    
    # Create detector instance
    detector = LicenseCopyrightDetector()
    
    # Scan a single file
    result = detector.process_local_path("LICENSE")
    
    # Access detected licenses
    if result.licenses:
        print("\nDetected Licenses:")
        for license in result.licenses:
            print(f"  • {license.spdx_id}")
            print(f"    Category: {license.category}")
            print(f"    Match Type: {license.match_type}")
            print(f"    Confidence: {license.confidence:.2%}")
            print(f"    Source: {license.source_file}")
    
    # Access copyright information
    if result.copyrights:
        print("\nCopyright Information:")
        for copyright in result.copyrights:
            print(f"  • {copyright.statement}")
            print(f"    Holder: {copyright.holder}")
            if copyright.years:
                print(f"    Years: {copyright.years}")

def example_directory():
    """Example: Scan a directory."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Scanning a directory")
    print("=" * 60)
    
    # Create detector instance
    detector = LicenseCopyrightDetector()
    
    # Scan current directory
    result = detector.process_local_path(".")
    
    # Organize licenses by category
    declared_licenses = {}
    detected_licenses = {}
    referenced_licenses = {}
    
    for license in result.licenses:
        category_map = {
            'declared': declared_licenses,
            'detected': detected_licenses,
            'referenced': referenced_licenses
        }
        
        target_dict = category_map.get(license.category, detected_licenses)
        if license.spdx_id not in target_dict:
            target_dict[license.spdx_id] = 0
        target_dict[license.spdx_id] += 1
    
    print("\nLicense Hierarchy:")
    print(f"  Declared (explicitly stated):")
    for spdx_id, count in declared_licenses.items():
        print(f"    • {spdx_id} ({count} occurrences)")
    
    if detected_licenses:
        print(f"  Detected (inferred from content):")
        for spdx_id, count in detected_licenses.items():
            print(f"    • {spdx_id} ({count} occurrences)")
    
    if referenced_licenses:
        print(f"  Referenced (mentioned in code):")
        for spdx_id, count in referenced_licenses.items():
            print(f"    • {spdx_id} ({count} occurrences)")
    
    # Get unique copyright holders
    unique_holders = set(c.holder for c in result.copyrights)
    if unique_holders:
        print(f"\nCopyright Holders ({len(unique_holders)}):")
        for holder in sorted(unique_holders):
            print(f"  • {holder}")
    
    # Get primary license
    primary = result.get_primary_license()
    if primary:
        print(f"\nPrimary License: {primary.spdx_id} (confidence: {primary.confidence:.2%})")

def example_json_output():
    """Example: Generate formatted JSON output."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Generating JSON output")
    print("=" * 60)
    
    # Create detector and scan
    detector = LicenseCopyrightDetector()
    result = detector.process_local_path(".")
    
    # Format as evidence JSON
    formatter = EvidenceFormatter()
    json_output = formatter.format([result])
    
    # Parse and display summary
    data = json.loads(json_output)
    summary = data['summary']
    
    print("\nJSON Summary:")
    print(f"  Files Scanned: {summary['total_files_scanned']}")
    print(f"  Declared Licenses: {list(summary['declared_licenses'].keys())}")
    print(f"  Detected Licenses: {list(summary['detected_licenses'].keys())}")
    print(f"  Referenced Licenses: {list(summary['referenced_licenses'].keys())}")
    print(f"  Copyright Holders: {summary['copyright_holders']}")
    print(f"  Total Copyrights: {summary['copyrights_found']}")

def example_filtering():
    """Example: Working with specific license categories."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Filtering by license category")
    print("=" * 60)
    
    detector = LicenseCopyrightDetector()
    result = detector.process_local_path(".")
    
    # Filter only declared licenses
    declared_only = [l for l in result.licenses if l.category == 'declared']
    
    print("\nDeclared Licenses Only:")
    for license in declared_only:
        print(f"  • {license.spdx_id} in {license.source_file}")
        print(f"    Match type: {license.match_type}")
    
    # Find high-confidence licenses
    high_confidence = [l for l in result.licenses if l.confidence >= 0.95]
    
    print(f"\nHigh Confidence Licenses (≥95%):")
    for license in high_confidence:
        print(f"  • {license.spdx_id}: {license.confidence:.2%}")

def example_custom_config():
    """Example: Using custom configuration."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Custom configuration")
    print("=" * 60)
    
    from semantic_copycat_oslili.core.models import Config
    
    # Create custom config
    config = Config(
        thread_count=8,  # Use 8 threads
        similarity_threshold=0.95,  # Higher similarity threshold
        verbose=False,  # Disable verbose output
        debug=False  # Disable debug logging
    )
    
    # Create detector with custom config
    detector = LicenseCopyrightDetector(config=config)
    
    # Process with custom settings
    result = detector.process_local_path(".")
    
    print(f"\nProcessed with custom config:")
    print(f"  Thread count: {config.thread_count}")
    print(f"  Similarity threshold: {config.similarity_threshold}")
    print(f"  Licenses found: {len(result.licenses)}")
    print(f"  Copyrights found: {len(result.copyrights)}")

if __name__ == "__main__":
    print("Semantic Copycat OSLILI - Library Usage Examples\n")
    
    example_single_file()
    example_directory()
    example_json_output()
    example_filtering()
    example_custom_config()
    
    print("\n" + "=" * 60)
    print("Examples completed successfully!")
    print("=" * 60)