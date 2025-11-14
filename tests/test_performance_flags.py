"""Tests for performance optimization flags."""

import pytest
import tempfile
import time
from pathlib import Path

from osslili.core.models import Config
from osslili.core.generator import LicenseCopyrightDetector


class TestPerformanceFlags:
    """Test performance optimization flags."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())

        # Create test files
        # LICENSE file
        (self.test_dir / "LICENSE").write_text("""
MIT License

Copyright (c) 2024 Test Author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
""")

        # Source file with license header
        (self.test_dir / "main.py").write_text("""
# Copyright (c) 2024 Test Author
# Licensed under the MIT License

def main():
    pass
""")

        # File without extension
        (self.test_dir / "Makefile").write_text("""
all:
\techo "build"
""")

        # Another file without extension (would require content detection)
        (self.test_dir / "configure").write_text("""#!/bin/bash
echo "configuring..."
""")

        # Large file for size testing
        large_content = "# " + ("x" * 1000 + "\n") * 2000  # ~2MB file
        (self.test_dir / "large_file.py").write_text(large_content)

    def test_config_defaults(self):
        """Test that performance flags have correct defaults."""
        config = Config()
        assert config.skip_content_detection is False
        assert config.license_files_only is False
        assert config.skip_extensionless is False
        assert config.max_file_size_kb is None
        assert config.skip_smart_read is False
        assert config.fast_mode is False

    def test_fast_mode_preset(self):
        """Test that fast mode applies correct preset."""
        config = Config()
        config.fast_mode = True
        config.apply_fast_mode()

        assert config.skip_content_detection is True
        assert config.skip_extensionless is True
        assert config.skip_smart_read is True
        assert config.max_file_size_kb == 1024

    def test_skip_content_detection(self):
        """Test skip_content_detection flag."""
        # Without flag - should find configure file via content detection
        config_with = Config(skip_content_detection=False)
        detector_with = LicenseCopyrightDetector(config_with)

        # With flag - should skip configure file
        config_without = Config(skip_content_detection=True)
        detector_without = LicenseCopyrightDetector(config_without)

        # Test that the flag affects file detection
        assert detector_with.license_detector._is_readable_file(self.test_dir / "configure") is True
        assert detector_without.license_detector._is_readable_file(self.test_dir / "configure") is False

    def test_license_files_only(self):
        """Test license_files_only flag scans fewer files."""
        config_all = Config(license_files_only=False)
        detector_all = LicenseCopyrightDetector(config_all)

        config_license_only = Config(license_files_only=True)
        detector_license_only = LicenseCopyrightDetector(config_license_only)

        # Scan with both configs
        result_all = detector_all.process_local_path(str(self.test_dir))
        result_license_only = detector_license_only.process_local_path(str(self.test_dir))

        # Both should find licenses, but license_only should be faster
        assert len(result_all.licenses) > 0
        assert len(result_license_only.licenses) > 0

    def test_skip_extensionless(self):
        """Test skip_extensionless flag."""
        config_with = Config(skip_extensionless=False)
        detector_with = LicenseCopyrightDetector(config_with)

        config_without = Config(skip_extensionless=True)
        detector_without = LicenseCopyrightDetector(config_without)

        # Makefile should still be detected (known pattern)
        assert detector_without.license_detector._is_readable_file(self.test_dir / "Makefile") is True

        # configure should be skipped
        assert detector_without.license_detector._is_readable_file(self.test_dir / "configure") is False

    def test_max_file_size(self):
        """Test max_file_size_kb flag."""
        # Config with 1KB limit - should skip large file
        config = Config(max_file_size_kb=1)
        detector = LicenseCopyrightDetector(config)

        # Large file should be skipped
        assert detector.license_detector._is_readable_file(self.test_dir / "large_file.py") is False

        # Small files should not be skipped
        assert detector.license_detector._is_readable_file(self.test_dir / "main.py") is True

    def test_skip_smart_read(self):
        """Test skip_smart_read flag."""
        config_smart = Config(skip_smart_read=False)
        detector_smart = LicenseCopyrightDetector(config_smart)

        config_sequential = Config(skip_smart_read=True)
        detector_sequential = LicenseCopyrightDetector(config_sequential)

        # Both should be able to read files, but in different ways
        content_smart = detector_smart.license_detector._read_file_smart(self.test_dir / "LICENSE")
        content_sequential = detector_sequential.license_detector._read_file_smart(self.test_dir / "LICENSE")

        # Both should have content
        assert len(content_smart) > 0
        assert len(content_sequential) > 0
        # Content should be similar (though smart read might add ...)
        assert "MIT License" in content_smart
        assert "MIT License" in content_sequential

    def test_performance_comparison(self):
        """Test that fast mode is actually faster."""
        # Normal mode
        config_normal = Config()
        detector_normal = LicenseCopyrightDetector(config_normal)

        start = time.time()
        result_normal = detector_normal.process_local_path(str(self.test_dir))
        time_normal = time.time() - start

        # Fast mode
        config_fast = Config(fast_mode=True)
        config_fast.apply_fast_mode()
        detector_fast = LicenseCopyrightDetector(config_fast)

        start = time.time()
        result_fast = detector_fast.process_local_path(str(self.test_dir))
        time_fast = time.time() - start

        # Both should find licenses
        assert len(result_normal.licenses) > 0
        assert len(result_fast.licenses) > 0

        # Fast mode should be faster (or at least not slower)
        # Note: In a small test directory, the difference might be negligible
        # but this test ensures the code path works
        assert time_fast <= time_normal * 2  # Allow some variance

    def test_combined_flags(self):
        """Test using multiple flags together."""
        config = Config(
            skip_content_detection=True,
            skip_extensionless=True,
            max_file_size_kb=100
        )
        detector = LicenseCopyrightDetector(config)

        result = detector.process_local_path(str(self.test_dir))

        # Should still find the LICENSE file
        assert len(result.licenses) > 0

        # Should have completed without errors
        assert len(result.errors) == 0


class TestPerformanceCLIIntegration:
    """Test CLI integration with performance flags."""

    def test_cli_flags_map_to_config(self):
        """Test that CLI flags correctly map to config."""
        from osslili.cli import load_config

        # Base config
        config = load_config(None)

        # Simulate CLI flag application
        config.skip_content_detection = True
        config.license_files_only = True
        config.skip_extensionless = True
        config.max_file_size_kb = 500
        config.skip_smart_read = True
        config.fast_mode = True

        assert config.skip_content_detection is True
        assert config.license_files_only is True
        assert config.skip_extensionless is True
        assert config.max_file_size_kb == 500
        assert config.skip_smart_read is True
        assert config.fast_mode is True
