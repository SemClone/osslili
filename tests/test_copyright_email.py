"""Tests for copyright extraction with email addresses."""

import pytest
import tempfile
from pathlib import Path

from osslili.core.models import Config
from osslili.extractors.copyright_extractor import CopyrightExtractor


class TestCopyrightWithEmail:
    """Test copyright extraction when holder has email address."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.extractor = CopyrightExtractor(self.config)
        self.test_dir = Path(tempfile.mkdtemp())

    def test_copyright_with_email_standard_format(self):
        """Test 'Copyright (c) YYYY Name <email>' format."""
        test_file = self.test_dir / "test1.c"
        test_file.write_text("""
/*
 * Copyright (c) 2003 Michael Niedermayer <michaelni@gmx.at>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract at least one copyright"

        # Find the copyright for Michael Niedermayer
        michael = next((c for c in copyrights if "Michael Niedermayer" in c.holder), None)
        assert michael is not None, "Should extract Michael Niedermayer"
        assert michael.holder == "Michael Niedermayer"
        assert 2003 in michael.years
        assert "Copyright 2003 Michael Niedermayer" in michael.statement

    def test_copyright_with_email_no_year(self):
        """Test 'Copyright Name <email>' format without year."""
        test_file = self.test_dir / "test2.c"
        test_file.write_text("""
/*
 * Copyright John Doe <john@example.com>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract at least one copyright"

        john = next((c for c in copyrights if "John Doe" in c.holder), None)
        assert john is not None, "Should extract John Doe"
        assert john.holder == "John Doe"

    def test_copyright_with_email_c_symbol(self):
        """Test '(C) YYYY Name <email>' format."""
        test_file = self.test_dir / "test3.c"
        test_file.write_text("""
/*
 * (C) 2020 Jane Smith <jane@example.org>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract at least one copyright"

        jane = next((c for c in copyrights if "Jane Smith" in c.holder), None)
        assert jane is not None, "Should extract Jane Smith"
        assert jane.holder == "Jane Smith"
        assert 2020 in jane.years

    def test_copyright_with_email_copyright_symbol(self):
        """Test '© YYYY Name <email>' format."""
        test_file = self.test_dir / "test4.c"
        test_file.write_text("""
/*
 * © 2021 Bob Johnson <bob@example.net>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract at least one copyright"

        bob = next((c for c in copyrights if "Bob Johnson" in c.holder), None)
        assert bob is not None, "Should extract Bob Johnson"
        assert bob.holder == "Bob Johnson"
        assert 2021 in bob.years

    def test_ffmpeg_actual_header(self):
        """Test with actual FFmpeg-style header."""
        test_file = self.test_dir / "h264_cavlc.c"
        test_file.write_text("""/*
 * H.26L/H.264/AVC/JVT/14496-10/... cavlc bitstream decoding
 * Copyright (c) 2003 Michael Niedermayer <michaelni@gmx.at>
 *
 * This file is part of FFmpeg.
 *
 * FFmpeg is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract copyright from FFmpeg header"

        michael = next((c for c in copyrights if "Michael Niedermayer" in c.holder), None)
        assert michael is not None, "Should extract Michael Niedermayer from FFmpeg header"
        assert michael.holder == "Michael Niedermayer"
        assert 2003 in michael.years

    def test_multiple_copyrights_with_emails(self):
        """Test multiple copyright holders with email addresses."""
        test_file = self.test_dir / "test5.c"
        test_file.write_text("""
/*
 * Copyright (c) 2003 Michael Niedermayer <michaelni@gmx.at>
 * Copyright (c) 2004 John Smith <john@example.com>
 * Copyright (c) 2005 Jane Doe <jane@example.org>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) >= 3, "Should extract all three copyrights"

        holders = [c.holder for c in copyrights]
        assert "Michael Niedermayer" in holders
        assert "John Smith" in holders
        assert "Jane Doe" in holders

    def test_copyright_with_email_year_range(self):
        """Test 'Copyright (c) YYYY-YYYY Name <email>' format."""
        test_file = self.test_dir / "test6.c"
        test_file.write_text("""
/*
 * Copyright (c) 2020-2023 Alice Cooper <alice@example.com>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract copyright with year range"

        alice = next((c for c in copyrights if "Alice Cooper" in c.holder), None)
        assert alice is not None, "Should extract Alice Cooper"
        assert alice.holder == "Alice Cooper"
        assert 2020 in alice.years
        assert 2023 in alice.years

    def test_copyright_without_email_still_works(self):
        """Test that extraction without email addresses still works."""
        test_file = self.test_dir / "test7.c"
        test_file.write_text("""
/*
 * Copyright (c) 2023 Test Corporation
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0, "Should extract copyright without email"

        test_corp = next((c for c in copyrights if "Test Corporation" in c.holder), None)
        assert test_corp is not None, "Should extract Test Corporation"
        assert test_corp.holder == "Test Corporation"

    def test_copyright_mixed_formats(self):
        """Test file with both email and non-email copyright formats."""
        test_file = self.test_dir / "test8.c"
        test_file.write_text("""
/*
 * Copyright (c) 2020 Individual Developer <dev@example.com>
 * Copyright (c) 2021 Big Corporation
 * Copyright (c) 2022 Another Dev <another@example.org>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) >= 3, "Should extract all copyrights"

        holders = [c.holder for c in copyrights]
        assert "Individual Developer" in holders
        assert "Big Corporation" in holders
        assert "Another Dev" in holders

    def test_author_format_with_email(self):
        """Test 'Author: Name <email>' format."""
        test_file = self.test_dir / "test9.py"
        test_file.write_text("""
# Author: Python Developer <pydev@example.com>
# Created: 2023-01-15

def main():
    pass
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        # Author format might be extracted as copyright
        if len(copyrights) > 0:
            holders = [c.holder for c in copyrights]
            # Should extract name without email
            assert any("Python Developer" in h for h in holders), "Should extract Python Developer"

    def test_email_in_brackets_cleaned(self):
        """Test that email addresses are properly stripped from holder names."""
        test_file = self.test_dir / "test10.c"
        test_file.write_text("""
/*
 * Copyright (c) 2023 Developer Name <dev@example.com>
 */
""")

        copyrights = self.extractor.extract_copyrights(test_file)

        assert len(copyrights) > 0

        # Verify no email addresses in the cleaned holder name
        for copyright_info in copyrights:
            assert "<" not in copyright_info.holder, f"Holder should not contain '<': {copyright_info.holder}"
            assert ">" not in copyright_info.holder, f"Holder should not contain '>': {copyright_info.holder}"
            assert "@" not in copyright_info.holder, f"Holder should not contain '@': {copyright_info.holder}"
