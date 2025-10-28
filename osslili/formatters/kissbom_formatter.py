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
            license_id = primary_license.spdx_id if primary_license else "NO-ASSERTION"
            
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
                
            # Add all detected licenses if multiple
            if len(result.licenses) > 1:
                package["all_licenses"] = list(set(l.spdx_id for l in result.licenses))
            
            packages.append(package)
        
        kissbom = {
            "packages": packages
        }
        
        return json.dumps(kissbom, indent=2, ensure_ascii=False)