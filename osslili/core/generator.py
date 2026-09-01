"""
Main detector class for license and copyright detection.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

from .models import Config, CopyrightInfo, DetectedLicense, DetectionResult
from .input_processor import InputProcessor
# At the top, not where it is first needed. Built lazily, a detector that
# could not be imported was caught by the guard around reading one path and
# reported as a path with no licence in it, and the scan finished at exit 0
# saying the file carries nothing. A tool for reading licences must not
# answer that when the truth is that it could not look.
from ..detectors.license_detector import LicenseDetector

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

                cached_data["licenses"] = [
                    DetectedLicense(**license) for license in cached_data["licenses"]
                ]

                cached_data["copyrights"] = [
                    CopyrightInfo(**copyright) for copyright in cached_data["copyrights"]
                ]

                result.__dict__.update(cached_data)
                return result

        start_time = time.time()

        # Validate path
        is_valid, path_obj, error = self.input_processor.validate_local_path(path)
        logger.debug(f"Path validation: is_valid={is_valid}, path_obj={path_obj}, error={error}")

        result = DetectionResult(path=str(path), package_name=Path(path).name)

        if not is_valid:
            result.errors.append(error)
            logger.warning(f"Path validation failed: {error}")
            return result

        try:
            logger.info(f"Processing local path: {path}")
            logger.debug(
                f"Path object: {path_obj}, is_file: {path_obj.is_file()}, extract_archives: {extract_archives}"
            )

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
                            self._name_evidence_by_its_path_inside(
                                result, extracted_dir
                            )
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

        result = DetectionResult(path=str(path), package_name=Path(path).name)

        if not is_valid:
            result.errors.append(error)
            return result

        try:

            detector = LicenseDetector(self.config)

            # List of package metadata filenames to look for
            metadata_files = [
                "package.json",
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "pom.xml",
                "Cargo.toml",
                "composer.json",
                "build.gradle",
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
                for pattern in ["*.gemspec", "*.nuspec"]:
                    files_to_scan.extend(path_obj.glob(pattern))

            # Extract metadata from each file
            for file_path in files_to_scan:
                try:
                    content = self.input_processor.read_text_file(file_path)
                    if content:
                        # `_extract_package_metadata` modernises what it
                        # produces, so this path answers the same identifier a
                        # scan of the same manifest answers. It used to reach
                        # the reader with the deprecated form (issue #112).
                        metadata_licenses = detector._extract_package_metadata(content, file_path)
                        result.licenses.extend(metadata_licenses)
                except Exception as e:
                    logger.debug(f"Error reading {file_path}: {e}")

            # Calculate confidence scores
            if result.licenses:
                result.confidence_scores["license"] = max(l.confidence for l in result.licenses)
            else:
                result.confidence_scores["license"] = 0.0

        except Exception as e:
            logger.error(f"Error extracting metadata from {path}: {e}")
            result.errors.append(str(e))
        finally:
            result.processing_time = time.time() - start_time

        return result

    def _name_evidence_by_its_path_inside(
        self, result: DetectionResult, extracted_dir: Path
    ) -> None:
        """Name each piece of evidence by its path inside the archive.

        Extraction picks a fresh temporary directory every run, so reporting
        where a file was extracted to gave the same file a different name each
        time — two scans of one archive could not be compared — and named a
        directory that no longer exists by the time anyone reads the report.

        The path inside the archive is stable across runs and is what a reader
        recognises: ``gin-1.10.0/auth.go`` rather than
        ``/var/folders/.../oslili_extract_x3wmyiba/extract_0_gin/gin-1.10.0/auth.go``.

        Both sides are resolved before they are compared. ``mkdtemp`` answers
        with ``/var/...`` on macOS while the scan walks its way to
        ``/private/var/...``, and the two spell the same directory; comparing
        them as written finds no common prefix and would leave every path
        untouched.

        A path that is not under the extraction directory is left as it is: it
        did not come out of the archive, and there is nothing to make it
        relative to.

        The name is spelled with forward slashes on every platform, because
        that is how tar and zip spell the entries themselves. Letting the
        local separator through would report ``proj-2.0\\LICENSE`` on Windows
        for an archive that stores ``proj-2.0/LICENSE``, which is a different
        name for the same member and puts the report back to answering
        differently depending on where it ran.
        """
        extracted_root = Path(extracted_dir).resolve()

        def named_inside(path: str):
            try:
                return Path(path).resolve().relative_to(extracted_root).as_posix()
            except (ValueError, OSError):
                # Deliberately left as it is rather than raised. A nested
                # archive extracts to a sibling of this directory rather than
                # into it, and nothing walks those today, so nothing reaches
                # here; were that gap closed, such a path would keep its
                # extracted name rather than stop the scan.
                return None

        for evidence in (*result.licenses, *result.copyrights):
            if not evidence.source_file:
                continue
            inside = named_inside(evidence.source_file)
            if inside is not None:
                evidence.source_file = inside

            # A licence settled by a notice names the file the notice was
            # read in, which is a second path into the archive and needs the
            # same treatment (issue #144). Without it a record read
            # `pkg/LICENSE` and pointed at a temporary directory that is gone
            # by the time anyone opens the report.
            resolved_by = getattr(evidence, "resolved_by", None)
            if resolved_by and resolved_by.get("file"):
                named = named_inside(resolved_by["file"])
                if named is not None:
                    evidence.resolved_by = {**resolved_by, "file": named}

    def _process_local_path(self, path: Path, result: DetectionResult):
        """
        Process a local directory or file.

        Args:
            path: Path to local directory or file
            result: DetectionResult to populate
        """
        # Detect licenses
        logger.debug(
            f"_process_local_path called with: {path} (is_file: {path.is_file()}, exists: {path.exists()})"
        )
        licenses = self.license_detector.detect_licenses(path)
        logger.debug(f"License detector returned {len(licenses)} licenses")
        result.licenses.extend(licenses)

        # Extract copyright information
        copyrights = self.copyright_extractor.extract_copyrights(path)
        result.copyrights.extend(copyrights)

        # Calculate confidence scores
        if result.licenses:
            result.confidence_scores["license"] = max(l.confidence for l in result.licenses)
        else:
            result.confidence_scores["license"] = 0.0

        if result.copyrights:
            result.confidence_scores["copyright"] = max(c.confidence for c in result.copyrights)
        else:
            result.confidence_scores["copyright"] = 0.0

        logger.debug(
            f"Found {len(result.licenses)} license(s) and {len(result.copyrights)} copyright(s)"
        )

    def generate_evidence(
        self, results: List[DetectionResult], detail_level: str = "detailed"
    ) -> str:
        """
        Generate evidence showing file-to-license mappings.

        Args:
            results: List of attribution results
            detail_level: Evidence detail level ('minimal', 'summary', 'detailed', 'full')

        Returns:
            Evidence as JSON string
        """
        from ..formatters.evidence_formatter import EvidenceFormatter

        formatter = EvidenceFormatter()
        return formatter.format(results, detail_level=detail_level)

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
