"""
CycloneDX SBOM formatter for standard software bill of materials output.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import uuid

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
            
            # Add licenses
            licenses = []
            for license_info in result.licenses:
                if license_info.spdx_id and license_info.spdx_id != "NO-ASSERTION":
                    licenses.append({
                        "license": {
                            "id": license_info.spdx_id
                        }
                    })
            
            if licenses:
                component["licenses"] = licenses
            
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
                        "vendor": "semantic-copycat-oslili",
                        "name": "oslili",
                        "version": "1.2.9"
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
        vendor.text = "semantic-copycat-oslili"
        name = ET.SubElement(tool, "name")
        name.text = "oslili"
        version = ET.SubElement(tool, "version")
        version.text = "1.2.9"
        
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
            
            # Add licenses
            if result.licenses:
                licenses_elem = ET.SubElement(component, "licenses")
                for license_info in result.licenses:
                    if license_info.spdx_id and license_info.spdx_id != "NO-ASSERTION":
                        license_elem = ET.SubElement(licenses_elem, "license")
                        id_elem = ET.SubElement(license_elem, "id")
                        id_elem.text = license_info.spdx_id
            
            # Add copyright
            if result.copyrights:
                copyright_elem = ET.SubElement(component, "copyright")
                copyright_elem.text = "\n".join(c.statement for c in result.copyrights)
        
        # Convert to string
        return ET.tostring(root, encoding="unicode", method="xml")