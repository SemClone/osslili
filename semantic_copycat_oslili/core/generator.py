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
from .package_acquisition import PackageAcquisition

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
        self.package_acquisition = PackageAcquisition(self.config)
        
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
    
    def process_purl(self, purl_string: str, use_external_sources: bool = False) -> AttributionResult:
        """
        Process a single package URL.
        
        Args:
            purl_string: Package URL string
            
        Returns:
            AttributionResult object
        """
        start_time = time.time()
        
        # Parse purl
        purl = self.input_processor.parse_purl(purl_string)
        if not purl:
            result = AttributionResult(purl=purl_string)
            result.errors.append(f"Invalid purl: {purl_string}")
            return result
        
        # Get package info
        package_info = self.input_processor.get_package_info(purl)
        
        # Create result object
        result = AttributionResult(
            purl=purl_string,
            package_name=package_info['display_name'],
            package_version=purl.version
        )
        
        try:
            # ALWAYS try local package analysis first
            logger.info(f"Processing {package_info['display_name_with_version']} (offline mode)")
            extracted_path = self.package_acquisition.acquire_and_extract_package(purl)
            
            if extracted_path:
                # Process the extracted package locally
                self._process_extracted_package(extracted_path, result)
            else:
                result.errors.append("Failed to download or extract package")
            
            # Only use external sources if explicitly enabled AND we need more data
            if use_external_sources:
                # Only fetch external data if local analysis is incomplete
                if not result.licenses or not result.copyrights:
                    logger.info(f"Supplementing with external sources for {package_info['display_name_with_version']}")
                    from ..data.external_sources import ExternalDataSources
                    external = ExternalDataSources(self.config)
                    external_data = external.fetch_all_sources(purl)
                    
                    # Add external licenses only if we don't have any
                    if not result.licenses:
                        for license in external_data.get('licenses', []):
                            result.licenses.append(license)
                    
                    # Add external copyrights only if we don't have any
                    if not result.copyrights:
                        for copyright in external_data.get('copyrights', []):
                            result.copyrights.append(copyright)
            
            if not extracted_path and not result.licenses and not result.copyrights:
                result.errors.append("No package data available (use --online for external sources)")
                return result
            
            # Clean up
            self.package_acquisition.cleanup_temp_directory(extracted_path.parent)
        
        except Exception as e:
            logger.error(f"Error processing {purl_string}: {e}")
            result.errors.append(str(e))
        
        finally:
            result.processing_time = time.time() - start_time
        
        return result
    
    def process_purl_list(self, purls: List[str]) -> List[AttributionResult]:
        """
        Process multiple package URLs.
        
        Args:
            purls: List of purl strings
            
        Returns:
            List of AttributionResult objects
        """
        results = []
        
        if self.config.thread_count > 1:
            # Multi-threaded processing
            with ThreadPoolExecutor(max_workers=self.config.thread_count) as executor:
                futures = {executor.submit(self.process_purl, purl): purl for purl in purls}
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        purl = futures[future]
                        logger.error(f"Failed to process {purl}: {e}")
                        result = AttributionResult(purl=purl)
                        result.errors.append(str(e))
                        results.append(result)
        else:
            # Single-threaded processing
            for purl in purls:
                results.append(self.process_purl(purl))
        
        return results
    
    def process_purl_file(self, file_path: str) -> List[AttributionResult]:
        """
        Process package URLs from a file.
        
        Args:
            file_path: Path to file containing purls
            
        Returns:
            List of AttributionResult objects
        """
        purls = self.input_processor.read_purl_file(file_path)
        
        if not purls:
            logger.warning(f"No valid purls found in {file_path}")
            return []
        
        logger.info(f"Processing {len(purls)} package(s) from {file_path}")
        return self.process_purl_list(purls)
    
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
            purl=f"file://{path}",
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
    
    def generate_kissbom(self, results: List[AttributionResult]) -> Dict[str, Any]:
        """
        Generate enriched KissBOM format output.
        
        Args:
            results: List of attribution results
            
        Returns:
            Dictionary in KissBOM format
        """
        from ..formatters.kissbom_formatter import KissBOMFormatter
        formatter = KissBOMFormatter()
        return formatter.format(results)
    
    def generate_cyclonedx(self, results: List[AttributionResult], format: str = 'json') -> str:
        """
        Generate CycloneDX SBOM.
        
        Args:
            results: List of attribution results
            format: Output format ('json' or 'xml')
            
        Returns:
            CycloneDX SBOM as string
        """
        from ..formatters.cyclonedx_formatter import CycloneDXFormatter
        formatter = CycloneDXFormatter()
        return formatter.format(results, format)
    
    def generate_notices(self, results: List[AttributionResult]) -> str:
        """
        Generate human-readable legal notices.
        
        Args:
            results: List of attribution results
            
        Returns:
            Legal notices as string
        """
        from ..formatters.notices_formatter import NoticesFormatter
        formatter = NoticesFormatter(self.config)
        return formatter.format(results)