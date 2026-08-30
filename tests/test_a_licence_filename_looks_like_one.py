"""A licence filename is recognised by its shape, not by a word inside it.

`_is_license_file` matched on substring, so any name containing "license",
"legal", "gpl", "bundle", "commercial" or "agreement" anywhere in it held the
project's licence. `bundle.js` was the most surprising: every minified
JavaScript bundle was a licence file, because "bundle" was in the list.

That matters wherever the answer changes how content is read. Evidence found
in a licence file is categorised `declared` with match type `license_file`,
so a page *about* licensing had its examples read as declarations, and a
`bundle.js` carrying a vendored header was read as the project's own licence
rather than as code.

Issue #116. The same substring test existed twice — in the detector and in
`models.names_a_licence_file`, which decides scan-target categories — so the
two could drift. There is one shape rule now and both ask it.

The shape: the stem is a licence noun on its own, or a licence noun joined to
the licence being named. `LICENSE-MIT`, `COPYING.LESSER`,
`THIRD_PARTY_NOTICES`. Every part has to belong, and at least one has to name
a licence rather than merely describe one.
"""

from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector
from osslili.core.models import looks_like_a_licence_filename, the_category_of


# Names that really do hold a licence. A regression here loses detection.
HOLDS_A_LICENCE = [
    "LICENSE", "LICENSE.txt", "LICENSE.md", "license", "license.rst",
    "LICENCE", "LICENCE.txt",
    "COPYING", "COPYING.txt", "COPYING.LESSER", "COPYING.LIB",
    "NOTICE", "NOTICE.txt", "COPYRIGHT", "COPYRIGHT.txt", "UNLICENSE",
    "LICENSE-MIT", "LICENSE-APACHE", "LICENSE-MIT.txt", "LICENSE.GPL",
    "MIT-LICENSE", "MIT-LICENSE.txt", "BSD-LICENSE", "LICENSE.APACHE2",
    "APACHE-LICENSE-2.0", "GPL-3.0.txt",
    "EULA.txt", "LEGAL", "LEGAL.txt", "COPYLEFT.txt",
    "3rdpartylicenses.txt", "THIRD_PARTY_NOTICES.txt", "THIRD-PARTY-NOTICES",
    "LICENSE-3RD-PARTY.txt",
]

# Names that merely contain a licence word. Each was a licence file before.
DOES_NOT = [
    # the surprising one: "bundle" was in the word list
    "bundle.js", "app.bundle.js", "vendor.bundle.css", "bundler.rb",
    # pages *about* licensing
    "docs/licenses.md", "docs/license-policy.md", "licensing-faq.md",
    "CONTRIBUTING-legal.md", "copyrights-faq.md", "legalese.md",
    # code that implements licensing
    "license_manager.py", "LicenseValidator.java", "test_license_detection.py",
    # words that were reaching for a different question entirely
    "commercial-terms.md", "vendor-agreement.pdf", "agreement.html",
    # a word that merely starts the same way
    "noticeboard.txt", "gplus.py",
    # ordinary files
    "main.go", "README.md", "index.html", "setup.py", "package.json",
    # an unknown suffix is part of the name, not an inert extension: reading
    # only the stem let anything hide after the dot
    "LICENSE.POLICY", "GPL.README", "COPYING.FAQ", "LICENSE-MIT.POLICY",
    "NOTICE.BOARD",
]


@pytest.fixture
def is_a_licence_file():
    detector = LicenseCopyrightDetector().license_detector
    return lambda name: detector._is_license_file(Path(name))


class TestWhatHoldsALicence:
    @pytest.mark.parametrize("name", HOLDS_A_LICENCE)
    def test_it_is_recognised(self, is_a_licence_file, name):
        assert is_a_licence_file(name)

    @pytest.mark.parametrize("name", DOES_NOT)
    def test_a_name_that_merely_says_the_word_is_not(self, is_a_licence_file, name):
        assert not is_a_licence_file(name)


class TestTheSurprisingOne:
    def test_a_javascript_bundle_is_not_a_licence_file(self, is_a_licence_file):
        """"bundle" was in the word list, so every bundle was one."""
        assert not is_a_licence_file("bundle.js")

    def test_a_page_about_licensing_is_not_a_declaration(self, is_a_licence_file):
        """Its examples were read as the project's own licence."""
        assert not is_a_licence_file("docs/license-policy.md")


class TestOneAnswer:
    """The detector and the scan-target reader ask the same question.

    They each had their own substring list. Two answers to one question is
    what the issue asked to be fixed here rather than at one caller.
    """

    @pytest.mark.parametrize("name", HOLDS_A_LICENCE + DOES_NOT)
    def test_both_readers_agree(self, is_a_licence_file, name):
        assert is_a_licence_file(name) == looks_like_a_licence_filename(name)


class TestTheScanTargetFollows:
    @pytest.mark.parametrize(
        "name,category",
        [
            ("LICENSE", "license_files"),
            ("COPYING.LESSER", "license_files"),
            ("THIRD_PARTY_NOTICES.txt", "notice_files"),
            ("pyproject.toml", "package_metadata"),
            ("README.md", "documentation"),
            # was license_files, which is the fault
            ("bundle.js", "source_files"),
            ("license_manager.py", "source_files"),
            ("main.go", "source_files"),
        ],
    )
    def test_the_category(self, name, category):
        assert the_category_of(Path(name)) == category


class TestTheShapeItself:
    def test_every_part_has_to_belong(self):
        """"policy" is not a licence word, so the name is not a licence."""
        assert looks_like_a_licence_filename("LICENSE-MIT")
        assert not looks_like_a_licence_filename("LICENSE-POLICY")

    def test_a_part_matches_whole_or_not_at_all(self):
        """Substring matching is what made "gplus" a licence file."""
        assert looks_like_a_licence_filename("GPL-3.0")
        assert not looks_like_a_licence_filename("gplus.py")

    def test_something_has_to_name_a_licence(self):
        """Qualifiers describe a licence; they do not name one."""
        assert looks_like_a_licence_filename("THIRD_PARTY_NOTICES")
        assert not looks_like_a_licence_filename("THIRD-PARTY")

    def test_an_unknown_suffix_is_part_of_the_name(self):
        """Projects write the licence into the suffix: COPYING.LESSER.

        Treating every suffix as an inert extension meant only the stem was
        examined, so anything could hide after the dot.
        """
        assert looks_like_a_licence_filename("COPYING.LESSER")
        assert looks_like_a_licence_filename("LICENSE.APACHE2")
        assert not looks_like_a_licence_filename("LICENSE.POLICY")
        assert not looks_like_a_licence_filename("GPL.README")

    def test_a_prose_suffix_is_dropped(self):
        assert looks_like_a_licence_filename("LICENSE.txt")
        assert looks_like_a_licence_filename("LICENSE.md")
        assert looks_like_a_licence_filename("license.rst")

    def test_a_family_may_carry_its_version(self):
        """"apache2" is the Apache licence, not an unknown word."""
        assert looks_like_a_licence_filename("LICENSE.APACHE2")
        assert looks_like_a_licence_filename("LICENSE-BSD3")

    def test_a_code_suffix_says_it_is_not_the_licence(self):
        assert looks_like_a_licence_filename("LICENSE.txt")
        assert not looks_like_a_licence_filename("license.py")

    def test_a_configured_pattern_is_still_honoured(self):
        """An explicit instruction about one project is not a guess."""
        from osslili.core.models import Config

        config = Config()
        config.license_filename_patterns = config.license_filename_patterns + [
            "OUR-TERMS*"
        ]
        detector = LicenseCopyrightDetector(config).license_detector

        assert detector._is_license_file(Path("OUR-TERMS.md"))
