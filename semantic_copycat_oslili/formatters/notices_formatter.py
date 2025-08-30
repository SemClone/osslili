"""
Human-readable notices formatter for legal attribution.
"""

from typing import List, Dict, Set
from pathlib import Path

from ..core.models import DetectionResult
from ..data.spdx_licenses import SPDXLicenseData


class NoticesFormatter:
    """Format detection results as human-readable legal notices."""
    
    def __init__(self):
        """Initialize the notices formatter."""
        from ..core.models import Config
        self.spdx_data = SPDXLicenseData(Config())
    
    def format(self, results: List[DetectionResult]) -> str:
        """
        Format results as human-readable notices with license texts.
        
        Args:
            results: List of detection results
            
        Returns:
            Formatted notices as string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
        lines.append("=" * 80)
        lines.append("")
        lines.append("This project incorporates components from the projects listed below.")
        lines.append("")
        
        # Track which licenses we need to include full text for
        licenses_to_include: Set[str] = set()
        
        # Process each result
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. {Path(result.path).name}")
            lines.append("-" * 40)
            
            # Add package info if available
            if result.package_name:
                lines.append(f"   Package: {result.package_name}")
                if result.package_version:
                    lines.append(f"   Version: {result.package_version}")
            
            lines.append(f"   Path: {result.path}")
            
            # Add licenses
            if result.licenses:
                # Group licenses by category
                declared = [l for l in result.licenses if l.category == "declared"]
                detected = [l for l in result.licenses if l.category == "detected"]
                referenced = [l for l in result.licenses if l.category == "referenced"]
                
                if declared:
                    primary = declared[0]
                    lines.append(f"   License: {primary.spdx_id or primary.name}")
                    licenses_to_include.add(primary.spdx_id)
                elif detected:
                    primary = detected[0]
                    lines.append(f"   License (detected): {primary.spdx_id or primary.name}")
                    licenses_to_include.add(primary.spdx_id)
                
                # List all licenses if multiple
                all_licenses = list(set(l.spdx_id for l in result.licenses if l.spdx_id))
                if len(all_licenses) > 1:
                    lines.append(f"   All licenses found: {', '.join(all_licenses)}")
                    licenses_to_include.update(all_licenses)
            else:
                lines.append("   License: NO-ASSERTION")
            
            # Add copyright information
            if result.copyrights:
                lines.append("   Copyright notices:")
                for copyright_info in result.copyrights:
                    lines.append(f"      {copyright_info.statement}")
            
            lines.append("")
        
        # Add separator before license texts
        lines.append("")
        lines.append("=" * 80)
        lines.append("LICENSE TEXTS")
        lines.append("=" * 80)
        lines.append("")
        
        # Add full license texts
        added_licenses = set()
        for spdx_id in sorted(licenses_to_include):
            if spdx_id and spdx_id != "NO-ASSERTION" and spdx_id not in added_licenses:
                lines.append(f"## {spdx_id}")
                lines.append("-" * 40)
                
                # Try to get license text
                license_text = self._get_license_text(spdx_id)
                if license_text:
                    lines.append(license_text)
                else:
                    lines.append(f"License text for {spdx_id} not available.")
                    lines.append("Please refer to: https://spdx.org/licenses/" + spdx_id + ".html")
                
                lines.append("")
                lines.append("")
                added_licenses.add(spdx_id)
        
        return "\n".join(lines)
    
    def _get_license_text(self, spdx_id: str) -> str:
        """
        Get the full text of a license.
        
        Args:
            spdx_id: SPDX license identifier
            
        Returns:
            License text or empty string if not found
        """
        # Try to get from SPDX data
        license_text = self.spdx_data.get_license_text(spdx_id)
        if license_text:
            return license_text
        
        # Try common licenses with bundled text
        common_licenses = {
            "MIT": """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
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
            
            "Apache-2.0": """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.""",
            
            "BSD-3-Clause": """BSD 3-Clause License

Redistribution and use in source and binary forms, with or without
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
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.""",
            
            "ISC": """ISC License

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE."""
        }
        
        return common_licenses.get(spdx_id, "")