"""
CycloneDX SBOM formatter for standard software bill of materials output.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import uuid


def _as_written(license_info) -> str:
    """The licence as the file granted it, exception and all.

    `GPL-2.0-only WITH Classpath-exception-2.0` is one grant. The record
    keeps the two apart because a record is one licence, and the exception is
    a condition on it; an SBOM wants them back together (issue #24).
    """
    exception = getattr(license_info, "exception", None)
    if exception:
        return f"{license_info.spdx_id} WITH {exception}"
    return license_info.spdx_id


from .. import __version__
from ..core.models import DetectionResult


class CycloneDXFormatter:
    """Format detection results as CycloneDX SBOM."""
    
    def format(self, results: List[DetectionResult], format_type: str = "json") -> str:
        """
        Format results as CycloneDX SBOM.
        
        Args:
            results: List of detection results
            format_type: Output format ("json" or "xml")
            
        Returns:
            CycloneDX SBOM as string
        """
        if format_type == "json":
            return self._format_json(results)
        elif format_type == "xml":
            return self._format_xml(results)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def _format_json(self, results: List[DetectionResult]) -> str:
        """Format as CycloneDX JSON."""
        components = []
        
        for result in results:
            # Build component
            component = {
                "type": "library",
                "bom-ref": str(uuid.uuid4()),
                "name": result.package_name or Path(result.path).name,
                "version": result.package_version or "unknown"
            }
            
            # Add the project's own licenses. Bundled third-party notice
            # licenses are not listed as the component's license; they are
            # emitted as properties so they remain visible but filterable
            # (issue #78).
            # One entry per licence, not per detection. The same licence
            # reached by the keyword and the regex tier is one grant noticed
            # twice, and a consumer counting entries was reading the
            # detection count. Sorted so two runs render alike.
            # A licence granted with an exception is written as an
            # expression, which is the slot CycloneDX has for exactly this.
            # An exception makes a licence less restrictive, so naming the
            # licence alone tells a consumer the work is more encumbered
            # than it is (issue #24).
            licenses = [
                ({"expression": spdx_id} if " WITH " in spdx_id
                 else {"license": {"id": spdx_id}})
                for spdx_id in sorted({
                    _as_written(license_info)
                    for license_info in result.get_own_licenses()
                    if license_info.spdx_id and license_info.spdx_id != "NO-ASSERTION"
                })
            ]

            if licenses:
                component["licenses"] = licenses

            third_party_ids = sorted(set(
                l.spdx_id for l in result.get_third_party_licenses()
                if l.spdx_id and l.spdx_id != "NO-ASSERTION"
            ))
            if third_party_ids:
                component["properties"] = [
                    {"name": "osslili:third-party-license", "value": spdx_id}
                    for spdx_id in third_party_ids
                ]

            # Add copyright
            if result.copyrights:
                copyright_text = "\n".join(c.statement for c in result.copyrights)
                component["copyright"] = copyright_text
            
            # Add evidence
            evidence = {
                "identity": {
                    "field": "purl",
                    "confidence": max((l.confidence for l in result.licenses), default=0.0),
                    "methods": list(set(l.detection_method for l in result.licenses))
                }
            }
            component["evidence"] = evidence
            
            components.append(component)
        
        # Build SBOM
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "tools": [
                    {
                        "vendor": "osslili",
                        "name": "osslili",
                        "version": __version__
                    }
                ]
            },
            "components": components
        }
        
        return json.dumps(sbom, indent=2, ensure_ascii=False)
    
    def _format_xml(self, results: List[DetectionResult]) -> str:
        """Format as CycloneDX XML."""
        # Create root element
        root = ET.Element("bom", {
            "xmlns": "http://cyclonedx.org/schema/bom/1.4",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": "1"
        })
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        timestamp = ET.SubElement(metadata, "timestamp")
        timestamp.text = datetime.utcnow().isoformat() + "Z"
        
        tools = ET.SubElement(metadata, "tools")
        tool = ET.SubElement(tools, "tool")
        vendor = ET.SubElement(tool, "vendor")
        vendor.text = "osslili"
        name = ET.SubElement(tool, "name")
        name.text = "osslili"
        version = ET.SubElement(tool, "version")
        version.text = __version__
        
        # Add components
        components = ET.SubElement(root, "components")
        
        for result in results:
            component = ET.SubElement(components, "component", {
                "type": "library",
                "bom-ref": str(uuid.uuid4())
            })
            
            name = ET.SubElement(component, "name")
            name.text = result.package_name or Path(result.path).name
            
            version = ET.SubElement(component, "version")
            version.text = result.package_version or "unknown"
            
            # Add the project's own licenses (issue #78: bundled third-party
            # notice licenses are emitted as properties, not component licenses).
            own_ids = sorted({
                license_info.spdx_id
                for license_info in result.get_own_licenses()
                if license_info.spdx_id and license_info.spdx_id != "NO-ASSERTION"
            })
            if own_ids:
                licenses_elem = ET.SubElement(component, "licenses")
                for spdx_id in own_ids:
                    license_elem = ET.SubElement(licenses_elem, "license")
                    id_elem = ET.SubElement(license_elem, "id")
                    id_elem.text = spdx_id

            # Add copyright (must precede <properties> in the CycloneDX 1.4
            # XML component sequence).
            if result.copyrights:
                copyright_elem = ET.SubElement(component, "copyright")
                copyright_elem.text = "\n".join(c.statement for c in result.copyrights)

            third_party_ids = sorted(set(
                l.spdx_id for l in result.get_third_party_licenses()
                if l.spdx_id and l.spdx_id != "NO-ASSERTION"
            ))
            if third_party_ids:
                properties_elem = ET.SubElement(component, "properties")
                for spdx_id in third_party_ids:
                    prop_elem = ET.SubElement(
                        properties_elem, "property",
                        {"name": "osslili:third-party-license"}
                    )
                    prop_elem.text = spdx_id
        
        # Convert to string
        return ET.tostring(root, encoding="unicode", method="xml")