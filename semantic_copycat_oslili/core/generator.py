"""
Main generator class for legal attribution processing.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import Config, AttributionResult, DetectedLicense, CopyrightInfo
from .input_processor import InputProcessor

logger = logging.getLogger(__name__)


class LegalAttributionGenerator:
    """
    Main class for generating legal attribution notices.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the attribution generator.
        
        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.input_processor = InputProcessor()
        
        # Lazy load components as needed
        self._license_detector = None
        self._copyright_extractor = None
        self._spdx_data = None
    
    @property
    def license_detector(self):
        """Lazy load license detector."""
        if self._license_detector is None:
            from ..detectors.license_detector import LicenseDetector
            self._license_detector = LicenseDetector(self.config)
        return self._license_detector
    
    @property
    def copyright_extractor(self):
        """Lazy load copyright extractor."""
        if self._copyright_extractor is None:
            from ..extractors.copyright_extractor import CopyrightExtractor
            self._copyright_extractor = CopyrightExtractor(self.config)
        return self._copyright_extractor
    
    
    
    
    def process_local_path(self, path: str) -> AttributionResult:
        """
        Process a local source code directory or file.
        
        Args:
            path: Path to local directory or file
            
        Returns:
            AttributionResult object
        """
        start_time = time.time()
        
        # Validate path
        is_valid, path_obj, error = self.input_processor.validate_local_path(path)
        
        result = AttributionResult(
            path=str(path),
            package_name=Path(path).name
        )
        
        if not is_valid:
            result.errors.append(error)
            return result
        
        try:
            logger.info(f"Processing local path: {path}")
            self._process_extracted_package(path_obj, result)
        
        except Exception as e:
            logger.error(f"Error processing {path}: {e}")
            result.errors.append(str(e))
        
        finally:
            result.processing_time = time.time() - start_time
        
        return result
    
    def _process_extracted_package(self, path: Path, result: AttributionResult):
        """
        Process an extracted package directory.
        
        Args:
            path: Path to extracted package
            result: AttributionResult to populate
        """
        # Detect licenses
        licenses = self.license_detector.detect_licenses(path)
        result.licenses.extend(licenses)
        
        # Extract copyright information
        copyrights = self.copyright_extractor.extract_copyrights(path)
        result.copyrights.extend(copyrights)
        
        # Calculate confidence scores
        if result.licenses:
            result.confidence_scores['license'] = max(l.confidence for l in result.licenses)
        else:
            result.confidence_scores['license'] = 0.0
        
        if result.copyrights:
            result.confidence_scores['copyright'] = max(c.confidence for c in result.copyrights)
        else:
            result.confidence_scores['copyright'] = 0.0
        
        logger.debug(f"Found {len(result.licenses)} license(s) and {len(result.copyrights)} copyright(s)")
    
    def generate_evidence(self, results: List[AttributionResult]) -> str:
        """
        Generate evidence showing file-to-license mappings.
        
        Args:
            results: List of attribution results
            
        Returns:
            Evidence as JSON string
        """
        from ..formatters.evidence_formatter import EvidenceFormatter
        formatter = EvidenceFormatter()
        return formatter.format(results)