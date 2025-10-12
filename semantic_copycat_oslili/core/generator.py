"""
Main detector class for license and copyright detection.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

from .models import Config, DetectionResult
from .input_processor import InputProcessor

logger = logging.getLogger(__name__)


class LicenseCopyrightDetector:
    """
    Main class for detecting licenses and copyright information in source code.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the license and copyright detector.
        
        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.input_processor = InputProcessor()
        
        # Lazy load components as needed
        self._license_detector = None
        self._copyright_extractor = None
        self._spdx_data = None
        
        # Initialize cache if cache_dir is configured
        self._cache = None
        if self.config.cache_dir:
            from ..utils.cache_manager import CacheManager
            self._cache = CacheManager(cache_dir=self.config.cache_dir)
    
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
    
    def process_local_path(self, path: str, extract_archives: bool = True) -> DetectionResult:
        """
        Process a local source code directory or file.
        
        Args:
            path: Path to local directory or file
            extract_archives: Whether to extract and scan archives
            
        Returns:
            DetectionResult object
        """
        # Check cache first
        if self._cache:
            cached_data = self._cache.get(path)
            if cached_data:
                logger.info(f"Using cached result for {path}")
                # Reconstruct DetectionResult from cached data
                result = DetectionResult(path=path)
                result.__dict__.update(cached_data)
                return result
        
        start_time = time.time()
        
        # Validate path
        is_valid, path_obj, error = self.input_processor.validate_local_path(path)
        logger.debug(f"Path validation: is_valid={is_valid}, path_obj={path_obj}, error={error}")
        
        result = DetectionResult(
            path=str(path),
            package_name=Path(path).name
        )
        
        if not is_valid:
            result.errors.append(error)
            logger.warning(f"Path validation failed: {error}")
            return result
        
        try:
            logger.info(f"Processing local path: {path}")
            logger.debug(f"Path object: {path_obj}, is_file: {path_obj.is_file()}, extract_archives: {extract_archives}")
            
            # Check if it's an archive and extract if needed
            if extract_archives and path_obj.is_file():
                from ..utils.archive_extractor import ArchiveExtractor
                extractor = ArchiveExtractor(max_depth=self.config.max_extraction_depth)
                
                if extractor.is_archive(path_obj):
                    logger.info(f"Detected archive file: {path_obj}")
                    with extractor:
                        extracted_dir = extractor.extract_archive(path_obj)
                        if extracted_dir:
                            logger.info(f"Extracted archive to: {extracted_dir}")
                            self._process_local_path(extracted_dir, result)
                        else:
                            logger.warning(f"Failed to extract archive: {path_obj}")
                            self._process_local_path(path_obj, result)
                else:
                    logger.debug(f"Not an archive, processing as regular file: {path_obj}")
                    self._process_local_path(path_obj, result)
            else:
                self._process_local_path(path_obj, result)
        
        except Exception as e:
            logger.error(f"Error processing {path}: {e}")
            result.errors.append(str(e))
        
        finally:
            result.processing_time = time.time() - start_time
        
        # Store in cache if enabled
        if self._cache and not result.errors:
            self._cache.set(path, result.to_dict())
        
        return result
    
    def extract_package_metadata(self, path: str) -> DetectionResult:
        """
        Fast-path API for extracting license information from package metadata files only.
        This method skips full text analysis and only extracts from structured metadata.

        Supports:
        - package.json (Node.js)
        - pyproject.toml, setup.py, setup.cfg (Python)
        - pom.xml (Maven/Java)
        - Cargo.toml (Rust)
        - *.gemspec (Ruby)
        - *.nuspec (NuGet/.NET)
        - composer.json (PHP)
        - build.gradle (Gradle/Java)

        Args:
            path: Path to package metadata file or directory containing metadata files

        Returns:
            DetectionResult with licenses extracted from metadata only
        """
        start_time = time.time()

        # Validate path
        is_valid, path_obj, error = self.input_processor.validate_local_path(path)

        result = DetectionResult(
            path=str(path),
            package_name=Path(path).name
        )

        if not is_valid:
            result.errors.append(error)
            return result

        try:
            from ..detectors.license_detector import LicenseDetector
            detector = LicenseDetector(self.config)

            # List of package metadata filenames to look for
            metadata_files = [
                'package.json', 'pyproject.toml', 'setup.py', 'setup.cfg',
                'pom.xml', 'Cargo.toml', 'composer.json', 'build.gradle'
            ]

            files_to_scan = []

            if path_obj.is_file():
                # Single file mode
                files_to_scan = [path_obj]
            else:
                # Directory mode - find metadata files
                for metadata_file in metadata_files:
                    candidate = path_obj / metadata_file
                    if candidate.exists() and candidate.is_file():
                        files_to_scan.append(candidate)

                # Also check for .gemspec and .nuspec files
                for pattern in ['*.gemspec', '*.nuspec']:
                    files_to_scan.extend(path_obj.glob(pattern))

            # Extract metadata from each file
            for file_path in files_to_scan:
                try:
                    content = self.input_processor.read_text_file(file_path)
                    if content:
                        metadata_licenses = detector._extract_package_metadata(content, file_path)
                        result.licenses.extend(metadata_licenses)
                except Exception as e:
                    logger.debug(f"Error reading {file_path}: {e}")

            # Calculate confidence scores
            if result.licenses:
                result.confidence_scores['license'] = max(l.confidence for l in result.licenses)
            else:
                result.confidence_scores['license'] = 0.0

        except Exception as e:
            logger.error(f"Error extracting metadata from {path}: {e}")
            result.errors.append(str(e))
        finally:
            result.processing_time = time.time() - start_time

        return result

    def _process_local_path(self, path: Path, result: DetectionResult):
        """
        Process a local directory or file.

        Args:
            path: Path to local directory or file
            result: DetectionResult to populate
        """
        # Detect licenses
        logger.debug(f"_process_local_path called with: {path} (is_file: {path.is_file()}, exists: {path.exists()})")
        licenses = self.license_detector.detect_licenses(path)
        logger.debug(f"License detector returned {len(licenses)} licenses")
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
    
    def generate_evidence(self, results: List[DetectionResult]) -> str:
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
    
    def generate_kissbom(self, results: List[DetectionResult]) -> str:
        """
        Generate KissBOM (Keep It Simple Software Bill of Materials) output.
        
        Args:
            results: List of detection results
            
        Returns:
            KissBOM as JSON string
        """
        from ..formatters.kissbom_formatter import KissBOMFormatter
        formatter = KissBOMFormatter()
        return formatter.format(results)
    
    def generate_cyclonedx(self, results: List[DetectionResult], format_type: str = "json") -> str:
        """
        Generate CycloneDX SBOM output.
        
        Args:
            results: List of detection results
            format_type: Output format ("json" or "xml")
            
        Returns:
            CycloneDX SBOM as string
        """
        from ..formatters.cyclonedx_formatter import CycloneDXFormatter
        formatter = CycloneDXFormatter()
        return formatter.format(results, format_type)