"""
KissBOM format generator.
"""

import logging
from typing import List, Dict, Any

from ..core.models import AttributionResult

logger = logging.getLogger(__name__)


class KissBOMFormatter:
    """Generate KissBOM format output."""
    
    def format(self, results: List[AttributionResult]) -> Dict[str, Any]:
        """
        Format results as KissBOM.
        
        Args:
            results: List of attribution results
            
        Returns:
            KissBOM dictionary
        """
        packages = []
        
        for result in results:
            # Get primary license
            primary_license = result.get_primary_license()
            license_id = primary_license.spdx_id if primary_license else "NO-ASSERTION"
            
            # Collect unique copyright holders, prioritizing those with years
            copyright_holders = {}
            for copyright_info in result.copyrights:
                holder = copyright_info.holder
                if holder not in copyright_holders or (
                    copyright_info.years and not copyright_holders.get(holder, {}).get('years')
                ):
                    copyright_holders[holder] = {
                        'years': copyright_info.years,
                        'confidence': copyright_info.confidence
                    }
            
            # Format copyright string
            copyright_strings = []
            for holder, info in sorted(copyright_holders.items(), 
                                      key=lambda x: x[1]['confidence'], 
                                      reverse=True)[:3]:  # Limit to top 3
                if info['years']:
                    year_str = self._format_years(info['years'])
                    copyright_strings.append(f"{year_str} {holder}")
                else:
                    copyright_strings.append(holder)
            
            package_entry = {
                "path": result.path,
                "license": license_id,
                "copyright": ", ".join(copyright_strings) if copyright_strings else None
            }
            
            # Add notes if there were errors
            if result.errors:
                package_entry["notes"] = f"Errors: {'; '.join(result.errors)}"
            
            packages.append(package_entry)
        
        return {
            "packages": packages
        }
    
    def _format_years(self, years: List[int]) -> str:
        """Format list of years for display."""
        if not years:
            return ""
        
        if len(years) == 1:
            return str(years[0])
        
        # Check if consecutive range
        if years == list(range(years[0], years[-1] + 1)):
            return f"{years[0]}-{years[-1]}"
        
        # Otherwise use first and last year
        return f"{years[0]}-{years[-1]}"