"""
Human-readable legal notices formatter.
"""

import logging
from typing import List, Dict, Optional
from collections import defaultdict

from ..core.models import AttributionResult, Config
from ..data.spdx_licenses import SPDXLicenseData

logger = logging.getLogger(__name__)


class NoticesFormatter:
    """Generate human-readable legal notices."""
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the notices formatter.
        
        Args:
            config: Configuration object (optional)
        """
        self.config = config or Config()
        self.spdx_licenses = SPDXLicenseData(self.config)
    
    def format(self, results: List[AttributionResult]) -> str:
        """
        Format results as human-readable notices.
        
        Args:
            results: List of attribution results
            
        Returns:
            Legal notices as string
        """
        # Group packages by license
        license_groups = defaultdict(list)
        license_texts_needed = set()
        
        for result in results:
            primary_license = result.get_primary_license()
            license_id = primary_license.spdx_id if primary_license else "NO-ASSERTION"
            license_groups[license_id].append(result)
            if license_id != "NO-ASSERTION":
                license_texts_needed.add(license_id)
        
        # Pre-fetch all needed license texts
        license_texts = {}
        for license_id in license_texts_needed:
            text = self._get_license_text(license_id)
            if text:
                license_texts[license_id] = text
        
        # Build output
        output_lines = []
        output_lines.append("=" * 70)
        output_lines.append("LEGAL NOTICES AND ATTRIBUTION")
        output_lines.append("=" * 70)
        output_lines.append("")
        
        # First, list all packages with their copyrights
        output_lines.append("PACKAGE INFORMATION:")
        output_lines.append("-" * 70)
        output_lines.append("")
        
        for license_id in sorted(license_groups.keys()):
            packages = license_groups[license_id]
            
            output_lines.append(f"Packages under {license_id}:")
            output_lines.append("")
            
            for result in packages:
                # Package header
                output_lines.append(f"  • {result.purl}")
                
                # Add copyright statements
                if result.copyrights:
                    output_lines.append("    Copyright:")
                    # Deduplicate and format copyright statements
                    seen_holders = {}  # Track both exact and normalized forms
                    
                    for copyright_info in result.copyrights:
                        holder = copyright_info.holder
                        holder_key = self._normalize_holder_for_dedup(holder)
                        
                        # Skip if we've seen this holder or a variant
                        if holder_key in seen_holders:
                            # If this one has years and previous didn't, update
                            if copyright_info.years and not seen_holders[holder_key].get('years'):
                                seen_holders[holder_key] = {
                                    'holder': holder,
                                    'years': copyright_info.years
                                }
                            continue
                        
                        seen_holders[holder_key] = {
                            'holder': holder,
                            'years': copyright_info.years
                        }
                    
                    # Output unique holders (limit to 5)
                    count = 0
                    for holder_info in seen_holders.values():
                        if count >= 5:
                            break
                        if holder_info['years']:
                            year_str = self._format_years(holder_info['years'])
                            output_lines.append(f"      © {year_str} {holder_info['holder']}")
                        else:
                            output_lines.append(f"      © {holder_info['holder']}")
                        count += 1
                else:
                    output_lines.append("    No copyright information found")
                
                output_lines.append("")
        
        # Then add license texts
        output_lines.append("")
        output_lines.append("=" * 70)
        output_lines.append("LICENSE TEXTS")
        output_lines.append("=" * 70)
        
        for license_id in sorted(license_texts_needed):
            output_lines.append("")
            output_lines.append(f"License: {license_id}")
            output_lines.append("-" * 70)
            output_lines.append("")
            
            if license_id in license_texts:
                # Add the actual license text
                output_lines.append(license_texts[license_id])
            else:
                # Fallback if we couldn't get the text
                output_lines.append(f"[License text for {license_id} not available]")
                output_lines.append("")
                output_lines.append("Please refer to: https://spdx.org/licenses/" + license_id + ".html")
            
            output_lines.append("")
            output_lines.append("#" * 70)
        
        return "\n".join(output_lines)
    
    def _get_license_text(self, license_id: str) -> Optional[str]:
        """
        Get the full text of a license.
        
        Args:
            license_id: SPDX license identifier
            
        Returns:
            License text or None
        """
        try:
            # First try to get from SPDX
            text = self.spdx_licenses.get_license_text(license_id)
            if text:
                return text
            
            # For common licenses, provide inline text if SPDX fails
            return self._get_common_license_text(license_id)
        except Exception as e:
            logger.debug(f"Failed to get license text for {license_id}: {e}")
            return None
    
    def _get_common_license_text(self, license_id: str) -> Optional[str]:
        """
        Get text for common licenses as fallback.
        
        Args:
            license_id: SPDX license identifier
            
        Returns:
            License text or None
        """
        # Provide abbreviated text for very common licenses
        common_licenses = {
            "MIT": """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.""",
            
            "Apache-2.0": """Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

[Full Apache 2.0 license text available at: http://www.apache.org/licenses/LICENSE-2.0]""",
            
            "BSD-3-Clause": """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""
        }
        
        return common_licenses.get(license_id)
    
    def _normalize_holder_for_dedup(self, holder: str) -> str:
        """
        Normalize holder name for deduplication.
        
        Args:
            holder: Copyright holder name
            
        Returns:
            Normalized key for deduplication
        """
        import re
        
        # Convert to lowercase
        normalized = holder.lower()
        
        # Remove common variations
        normalized = re.sub(r'\s*<[^>]+>$', '', normalized)  # Remove emails
        normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
        normalized = normalized.strip()
        
        # Remove "by" prefix if present
        if normalized.startswith('by '):
            normalized = normalized[3:]
        
        # Remove punctuation at end
        normalized = re.sub(r'[.,;:]+$', '', normalized)
        
        return normalized
    
    def _format_years(self, years: List[int]) -> str:
        """Format list of years for display."""
        if not years:
            return ""
        
        if len(years) == 1:
            return str(years[0])
        
        # Check if consecutive range
        if years == list(range(years[0], years[-1] + 1)):
            return f"{years[0]}-{years[-1]}"
        
        # Otherwise use first and last
        return f"{years[0]}-{years[-1]}"