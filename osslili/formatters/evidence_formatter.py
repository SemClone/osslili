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
                - 'detailed': All individual detections without aggregation
                - 'full': Same as detailed (for backwards compatibility)

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

        files_seen = set()

        for result in results:
            scan_result = {
                "path": result.path,
                "license_evidence": [],
                "copyright_evidence": []
            }

            # For detailed mode, don't aggregate - show every individual detection
            if detail_level in ['detailed', 'full']:
                # Add each license detection as a separate evidence entry
                for license in result.licenses:
                    source = license.source_file or "unknown"
                    files_seen.add(source)
                    evidence_entry = {
                        "file": source,
                        "detected_license": license.spdx_id,
                        "confidence": round(license.confidence, 3),
                        "detection_method": license.detection_method,
                        "category": getattr(license, 'category', 'detected')
                    }

                    # Use the match_type from the license if available
                    match_type = getattr(license, 'match_type', None)
                    if match_type:
                        evidence_entry["match_type"] = match_type
                    else:
                        # Fallback to determining match type from method
                        if license.detection_method == "filename":
                            evidence_entry["match_type"] = "license_text"
                        elif license.detection_method == "tag":
                            evidence_entry["match_type"] = "spdx_identifier"
                        elif license.detection_method == "regex":
                            evidence_entry["match_type"] = "license_reference"
                        elif license.detection_method in ["dice-sorensen", "tlsh", "hash"]:
                            evidence_entry["match_type"] = "text_similarity"
                        elif license.detection_method == "keyword":
                            evidence_entry["match_type"] = "keyword"
                        else:
                            evidence_entry["match_type"] = "pattern_match"

                    # Generate description based on match type
                    match_type = evidence_entry.get("match_type", "pattern_match")
                    if match_type == "license_file":
                        evidence_entry["description"] = f"License file contains {license.spdx_id} license"
                    elif match_type == "spdx_identifier":
                        evidence_entry["description"] = f"SPDX-License-Identifier: {license.spdx_id} found"
                    elif match_type == "package_metadata":
                        evidence_entry["description"] = f"Package metadata declares {license.spdx_id} license"
                    elif match_type == "license_reference":
                        evidence_entry["description"] = f"License reference '{license.spdx_id}' detected"
                    elif match_type == "text_similarity":
                        evidence_entry["description"] = f"Text matches {license.spdx_id} license ({license.confidence*100:.1f}% similarity)"
                    elif match_type == "exact_hash":
                        evidence_entry["description"] = f"Pattern match for {license.spdx_id}"
                    else:
                        evidence_entry["description"] = f"Pattern match for {license.spdx_id}"

                    # Add line/offset information if available
                    if hasattr(license, 'line_number'):
                        evidence_entry["line_number"] = license.line_number
                    if hasattr(license, 'byte_offset'):
                        evidence_entry["byte_offset"] = license.byte_offset

                    scan_result["license_evidence"].append(evidence_entry)

                    # Update summary based on category
                    category = evidence_entry["category"]
                    spdx_id = license.spdx_id

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

                # Add copyrights without aggregation in detailed mode
                for copyright in result.copyrights:
                    source = copyright.source_file or "unknown"
                    files_seen.add(source)
                    scan_result["copyright_evidence"].append({
                        "file": source,
                        "holder": copyright.holder,
                        "years": copyright.years,
                        "statement": copyright.statement
                    })
                    evidence["summary"]["copyrights_found"] += 1

                    # Add unique copyright holders to summary
                    if copyright.holder and copyright.holder not in evidence["summary"]["copyright_holders"]:
                        evidence["summary"]["copyright_holders"].append(copyright.holder)

            else:
                # For minimal/summary modes, aggregate as before
                # Group licenses by source file
                license_by_file = {}
                for license in result.licenses:
                    source = license.source_file or "unknown"
                    files_seen.add(source)
                    if source not in license_by_file:
                        license_by_file[source] = []
                    license_by_file[source].append({
                        "spdx_id": license.spdx_id,
                        "confidence": round(license.confidence, 3),
                        "method": license.detection_method,
                        "category": getattr(license, 'category', 'detected'),
                        "match_type": getattr(license, 'match_type', None)
                    })

                # Format license evidence (aggregated)
                for file_path, licenses in license_by_file.items():
                    # Create one evidence entry per unique license per file
                    seen_licenses = set()
                    for lic in licenses:
                        # Only add if we haven't seen this license for this file yet
                        if lic["spdx_id"] not in seen_licenses:
                            seen_licenses.add(lic["spdx_id"])
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
                                elif lic["method"] in ["dice-sorensen", "tlsh", "hash"]:
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

                        # Always update summary counts (even for duplicates in aggregated mode)
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
                    files_seen.add(source)
                    if source not in copyright_by_file:
                        copyright_by_file[source] = []
                    copyright_by_file[source].append({
                        "holder": copyright.holder,
                        "years": copyright.years,
                        "statement": copyright.statement
                    })

                # Format copyright evidence (aggregated)
                for file_path, copyrights in copyright_by_file.items():
                    seen_copyrights = set()
                    for cp in copyrights:
                        # Create unique key for copyright
                        cp_key = f"{cp['holder']}_{cp['years']}"
                        if cp_key not in seen_copyrights:
                            seen_copyrights.add(cp_key)
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

        # Update file count based on actual files seen
        evidence["summary"]["total_files_scanned"] = len(files_seen)

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
                    "files_with_licenses": len(set(e["file"] for r in evidence["scan_results"] for e in r["license_evidence"])),
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
                    "files_with_licenses": len(set(e["file"] for r in evidence["scan_results"] for e in r["license_evidence"])),
                    "license_breakdown": evidence["summary"]["all_licenses"],
                    "total_license_detections": sum(len(r["license_evidence"]) for r in evidence["scan_results"]),
                    "detection_methods": method_counts,
                    "copyrights_found": evidence["summary"]["copyrights_found"],
                    "unique_copyright_holders": len(evidence["summary"]["copyright_holders"])
                }
            }
            return filtered

        elif detail_level in ['detailed', 'full']:
            # Return everything without filtering for detailed mode
            return evidence

        else:
            # Default to detailed
            return evidence