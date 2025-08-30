"""
Evidence formatter for showing license detection results with file mappings.
"""

import json
from typing import List, Dict, Any
from pathlib import Path

from ..core.models import DetectionResult


class EvidenceFormatter:
    """Format attribution results as evidence showing file-to-license mappings."""
    
    def format(self, results: List[DetectionResult]) -> str:
        """
        Format results as evidence showing what was detected where.
        
        Args:
            results: List of attribution results
            
        Returns:
            Evidence as JSON string
        """
        evidence = {
            "scan_results": [],
            "summary": {
                "total_files_scanned": 0,
                "declared_licenses": {},
                "detected_licenses": {},
                "referenced_licenses": {},
                "all_licenses": {},
                "copyright_holders": [],
                "copyrights_found": 0
            }
        }
        
        for result in results:
            scan_result = {
                "path": result.path,
                "license_evidence": [],
                "copyright_evidence": []
            }
            
            # Group licenses by source file
            license_by_file = {}
            for license in result.licenses:
                source = license.source_file or "unknown"
                if source not in license_by_file:
                    license_by_file[source] = []
                license_by_file[source].append({
                    "spdx_id": license.spdx_id,
                    "confidence": round(license.confidence, 3),
                    "method": license.detection_method,
                    "category": getattr(license, 'category', 'detected'),
                    "match_type": getattr(license, 'match_type', None)
                })
            
            # Format license evidence
            for file_path, licenses in license_by_file.items():
                for lic in licenses:
                    evidence_entry = {
                        "file": file_path,
                        "detected_license": lic["spdx_id"],
                        "confidence": lic["confidence"],
                        "detection_method": lic["method"],
                        "category": lic["category"]
                    }
                    
                    # Use the match_type from the license if available
                    if lic.get("match_type"):
                        evidence_entry["match_type"] = lic["match_type"]
                    else:
                        # Fallback to determining match type from method
                        file_name = Path(file_path).name.lower() if file_path != "unknown" else "unknown"
                        if lic["method"] == "filename":
                            evidence_entry["match_type"] = "license_text"
                        elif lic["method"] == "tag":
                            evidence_entry["match_type"] = "spdx_identifier"
                        elif lic["method"] == "regex":
                            evidence_entry["match_type"] = "license_reference"
                        elif lic["method"] in ["dice-sorensen", "tlsh"]:
                            evidence_entry["match_type"] = "text_similarity"
                        else:
                            evidence_entry["match_type"] = "pattern_match"
                    
                    # Generate description based on match type
                    match_type = evidence_entry["match_type"]
                    if match_type == "license_file":
                        evidence_entry["description"] = f"License file contains {lic['spdx_id']} license"
                    elif match_type == "spdx_identifier":
                        evidence_entry["description"] = f"SPDX-License-Identifier: {lic['spdx_id']} found"
                    elif match_type == "package_metadata":
                        evidence_entry["description"] = f"Package metadata declares {lic['spdx_id']} license"
                    elif match_type == "license_reference":
                        evidence_entry["description"] = f"License reference '{lic['spdx_id']}' detected"
                    elif match_type == "text_similarity":
                        evidence_entry["description"] = f"Text matches {lic['spdx_id']} license ({lic['confidence']*100:.1f}% similarity)"
                    else:
                        evidence_entry["description"] = f"Pattern match for {lic['spdx_id']}"
                    
                    scan_result["license_evidence"].append(evidence_entry)
                    
                    # Update summary based on category
                    category = lic["category"]
                    spdx_id = lic["spdx_id"]
                    
                    # Add to category-specific counts
                    if category == "declared":
                        if spdx_id not in evidence["summary"]["declared_licenses"]:
                            evidence["summary"]["declared_licenses"][spdx_id] = 0
                        evidence["summary"]["declared_licenses"][spdx_id] += 1
                    elif category == "detected":
                        if spdx_id not in evidence["summary"]["detected_licenses"]:
                            evidence["summary"]["detected_licenses"][spdx_id] = 0
                        evidence["summary"]["detected_licenses"][spdx_id] += 1
                    elif category == "referenced":
                        if spdx_id not in evidence["summary"]["referenced_licenses"]:
                            evidence["summary"]["referenced_licenses"][spdx_id] = 0
                        evidence["summary"]["referenced_licenses"][spdx_id] += 1
                    
                    # Add to overall count
                    if spdx_id not in evidence["summary"]["all_licenses"]:
                        evidence["summary"]["all_licenses"][spdx_id] = 0
                    evidence["summary"]["all_licenses"][spdx_id] += 1
            
            # Group copyrights by source file
            copyright_by_file = {}
            for copyright in result.copyrights:
                source = copyright.source_file or "unknown"
                if source not in copyright_by_file:
                    copyright_by_file[source] = []
                copyright_by_file[source].append({
                    "holder": copyright.holder,
                    "years": copyright.years,
                    "statement": copyright.statement
                })
            
            # Format copyright evidence
            for file_path, copyrights in copyright_by_file.items():
                for cp in copyrights:
                    scan_result["copyright_evidence"].append({
                        "file": file_path,
                        "holder": cp["holder"],
                        "years": cp["years"],
                        "statement": cp["statement"]
                    })
                    evidence["summary"]["copyrights_found"] += 1
                    
                    # Add unique copyright holders to summary
                    if cp["holder"] and cp["holder"] not in evidence["summary"]["copyright_holders"]:
                        evidence["summary"]["copyright_holders"].append(cp["holder"])
            
            # Add errors if any
            if result.errors:
                scan_result["errors"] = result.errors
            
            evidence["scan_results"].append(scan_result)
            
            # Update file count
            evidence["summary"]["total_files_scanned"] += len(license_by_file) + len(copyright_by_file)
        
        return json.dumps(evidence, indent=2)