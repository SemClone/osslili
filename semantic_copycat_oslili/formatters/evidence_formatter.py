"""
Evidence formatter for showing license detection results with file mappings.
"""

import json
from typing import List
from pathlib import Path

from ..core.models import DetectionResult


class EvidenceFormatter:
    """Format attribution results as evidence showing file-to-license mappings."""
    
    def format(self, results: List[DetectionResult], detail_level: str = 'detailed') -> str:
        """
        Format results as evidence showing what was detected where.

        Args:
            results: List of attribution results
            detail_level: Evidence detail level:
                - 'minimal': Only license summary counts
                - 'summary': Summary plus detection method counts
                - 'detailed': Summary, method counts, and sample detections (default)
                - 'full': All detection evidence included

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

        # Apply detail level filtering
        evidence = self._apply_detail_filtering(evidence, detail_level)

        return json.dumps(evidence, indent=2)

    def _apply_detail_filtering(self, evidence: dict, detail_level: str) -> dict:
        """Apply detail level filtering to evidence data."""
        if detail_level == 'minimal':
            # Only keep summary license and copyright counts
            filtered = {
                "summary": {
                    "total_files_scanned": evidence["summary"]["total_files_scanned"],
                    "files_with_licenses": len([r for r in evidence["scan_results"] if r["license_evidence"]]),
                    "license_breakdown": evidence["summary"]["all_licenses"],
                    "total_license_detections": sum(len(r["license_evidence"]) for r in evidence["scan_results"]),
                    "copyrights_found": evidence["summary"]["copyrights_found"],
                    "unique_copyright_holders": len(evidence["summary"]["copyright_holders"])
                }
            }
            return filtered

        elif detail_level == 'summary':
            # Add detection method counts
            method_counts = {}
            for result in evidence["scan_results"]:
                for lic_evidence in result["license_evidence"]:
                    method = lic_evidence["detection_method"]
                    method_counts[method] = method_counts.get(method, 0) + 1

            filtered = {
                "summary": {
                    "total_files_scanned": evidence["summary"]["total_files_scanned"],
                    "files_with_licenses": len([r for r in evidence["scan_results"] if r["license_evidence"]]),
                    "license_breakdown": evidence["summary"]["all_licenses"],
                    "total_license_detections": sum(len(r["license_evidence"]) for r in evidence["scan_results"]),
                    "detection_methods": method_counts,
                    "copyrights_found": evidence["summary"]["copyrights_found"],
                    "unique_copyright_holders": len(evidence["summary"]["copyright_holders"])
                }
            }
            return filtered

        elif detail_level == 'detailed':
            # Include sample detections (limit to 10 per license type)
            license_samples = {}
            filtered_results = []

            for result in evidence["scan_results"]:
                filtered_result = {
                    "path": result["path"],
                    "license_evidence": [],
                    "copyright_evidence": result["copyright_evidence"][:5] if result["copyright_evidence"] else []  # Limit copyrights
                }

                for lic_evidence in result["license_evidence"]:
                    license_id = lic_evidence["detected_license"]
                    if license_id not in license_samples:
                        license_samples[license_id] = 0

                    # Include first 10 samples per license type
                    if license_samples[license_id] < 10:
                        filtered_result["license_evidence"].append(lic_evidence)
                        license_samples[license_id] += 1

                if filtered_result["license_evidence"] or filtered_result["copyright_evidence"]:
                    filtered_results.append(filtered_result)

            evidence["scan_results"] = filtered_results[:100]  # Limit to first 100 scan results
            return evidence

        else:  # 'full' or any other value
            # Return complete evidence
            return evidence