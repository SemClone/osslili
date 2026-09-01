"""
KissBOM formatter for simple JSON output with packages and licenses.
"""

import json
from typing import List, Dict, Any
from pathlib import Path

from ..core.models import DetectionResult


class KissBOMFormatter:
    """Format detection results as KissBOM (Keep It Simple Software Bill of Materials)."""
    
    def format(self, results: List[DetectionResult]) -> str:
        """
        Format results as KissBOM JSON.
        
        Args:
            results: List of detection results
            
        Returns:
            KissBOM as JSON string
        """
        packages = []
        
        for result in results:
            # Get primary license
            primary_license = result.get_primary_license()
            # Written with the exception it was granted with, where there was
            # one. An exception makes a licence less restrictive, so naming
            # the licence alone says the work is more encumbered than it is
            # (issue #24).
            license_id = "NO-ASSERTION"
            if primary_license:
                license_id = primary_license.spdx_id
                granted_with = getattr(primary_license, "exception", None)
                if granted_with:
                    license_id = f"{license_id} WITH {granted_with}"
            
            # Collect unique copyright holders
            copyright_holders = []
            seen_holders = set()
            for copyright_info in result.copyrights:
                if copyright_info.holder not in seen_holders:
                    copyright_holders.append(copyright_info.holder)
                    seen_holders.add(copyright_info.holder)
            
            # Build package entry
            package = {
                "path": result.path,
                "license": license_id,
                "copyright": ", ".join(copyright_holders) if copyright_holders else None
            }
            
            # Add optional fields
            if result.package_name:
                package["name"] = result.package_name
            if result.package_version:
                package["version"] = result.package_version

            # Add all of the project's own detected licenses if multiple.
            # Bundled third-party notice licenses are reported separately so
            # they are not conflated with the project's own license (issue #78).
            own_licenses = result.get_own_licenses()
            if len(own_licenses) > 1:
                package["all_licenses"] = sorted(set(l.spdx_id for l in own_licenses))

            third_party_ids = sorted(set(
                l.spdx_id for l in result.get_third_party_licenses()
            ))
            if third_party_ids:
                package["third_party_licenses"] = third_party_ids

            packages.append(package)
        
        kissbom = {
            "packages": packages
        }
        
        return json.dumps(kissbom, indent=2, ensure_ascii=False)