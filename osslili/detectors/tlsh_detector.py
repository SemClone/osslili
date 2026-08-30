"""
TLSH (Trend Micro Locality Sensitive Hash) detector for license matching.
"""

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any

from ..core.models import DetectedLicense, DetectionMethod, LicenseCategory
from ..utils.text_similarity import create_bigrams, dice_coefficient

logger = logging.getLogger(__name__)

# TLSH distance under which two texts count as near neighbours. TLSH is a
# locality-sensitive hash over the whole document, so it measures bulk
# similarity: excellent at finding which licenses a text resembles, useless at
# telling those licenses apart. Canonical MIT text, for instance, sits closer
# to the JSON license (distance 17) than to MIT itself (29), because JSON is
# MIT plus one sentence and that sentence offsets the length difference of a
# package's own copyright line. See issue #90.
# Measured over 675 bundled licences, taking the canonical text with a project's
# own copyright line on top, which is what a real licence file looks like: at 30
# the licence itself was among the candidates only 76% of the time. The Pallets
# BSD-3-Clause file sits at distance 35 from BSD-3-Clause and 29 from
# BSD-4-Clause, so the tier proposed only the neighbour a clause away and
# corroborated it, having nothing better to compare against.
#
# Widening cannot cost precision: corroboration keeps the candidate whose real
# licence text scores highest, so an extra candidate can only win by being a
# better match or lose. It costs candidates to compare, and few: at 60 the
# median licence file has 2 and the worst has 23, out of 737.
#
#   cutoff 30 -> the true licence is a candidate for 76% of licence files
#   cutoff 45 -> 84%
#   cutoff 60 -> 91%
#   cutoff 80 -> 95%, median 6 candidates
NEAR_NEIGHBOUR_DISTANCE = 60

# Minimum Dice-Sørensen agreement between the scanned text and a candidate's
# actual license text before that candidate may be asserted. Matches the bar
# the Dice-Sørensen tier applies to its own matches.
CORROBORATION_THRESHOLD = 0.9

# How far the runner-up must sit behind the best candidate for that candidate to
# count as unambiguous. TLSH's weakness is discriminating between licenses that
# differ by a clause; when nothing else is anywhere near, that weakness does not
# apply and the match can be trusted without a text to check it against.
#
# Measured, not guessed. Across the near-neighbour confusions from issue #90 the
# wrong answer never led by more than 13 (MIT->JSON 12, ->JSON 13,
# BSD-3->BSD-4 3 and 2, BSD-3->BSD-3-Clause-HP 1). Across licenses TLSH gets
# right but cannot corroborate, the correct answer leads by 20 or more
# (Sleepycat 43, Python-2.0 39, Apache-1.1 26, CECILL-2.1 20). Nothing falls
# between, so 20 separates them cleanly.
UNAMBIGUOUS_MARGIN = 20

# Confidence band for an unambiguous but uncorroborated match, interpolated over
# the distance threshold. Deliberately below the exact-hash and Dice-Sørensen
# tiers: this is a whole-document resemblance, not a text identification.
_UNCORROBORATED_CONFIDENCE_MAX = 0.95
_UNCORROBORATED_CONFIDENCE_MIN = 0.75

# Try to import tlsh, make it optional
try:
    import tlsh
    TLSH_AVAILABLE = True
except ImportError:
    TLSH_AVAILABLE = False
    logger.warning("TLSH library not available. Install with: pip install python-tlsh")


class TLSHDetector:
    """Detect licenses using TLSH fuzzy hashing."""
    
    def __init__(self, config, spdx_data):
        """
        Initialize TLSH detector.
        
        Args:
            config: Configuration object
            spdx_data: SPDXLicenseData instance
        """
        self.config = config
        self.spdx_data = spdx_data
        self.license_hashes = {}
        self._initialized = False
        
        if TLSH_AVAILABLE:
            self._initialize_hashes()
    
    
    def _initialize_hashes(self):
        """Initialize TLSH hashes for known licenses."""
        try:
            # Load pre-computed hashes if available
            hash_file = Path(__file__).parent.parent / 'data' / 'license_hashes.json'
            if hash_file.exists():
                with open(hash_file, 'r') as f:
                    self.license_hashes = json.load(f)
                logger.debug(f"Loaded {len(self.license_hashes)} pre-computed license hashes")
            else:
                # Compute hashes for available licenses
                self._compute_license_hashes()
            
            self._initialized = True
        except Exception as e:
            logger.error(f"Error initializing TLSH hashes: {e}")
    
    def _compute_license_hashes(self):
        """Compute TLSH hashes for all available SPDX licenses."""
        if not TLSH_AVAILABLE:
            return
        
        logger.info("Computing TLSH hashes for SPDX licenses...")
        
        for license_id in self.spdx_data.get_all_license_ids():
            try:
                # Get license text
                license_text = self.spdx_data.get_license_text(license_id)
                if not license_text:
                    continue
                
                # Preprocess text for TLSH
                processed_text = self._preprocess_for_tlsh(license_text)
                
                # Compute hash
                hash_value = tlsh.hash(processed_text.encode('utf-8'))
                
                if hash_value and hash_value != 'TNULL':
                    self.license_hashes[license_id] = {
                        'hash': hash_value,
                        'name': self.spdx_data.get_license_info(license_id).get('name', license_id)
                    }
            
            except Exception as e:
                logger.debug(f"Error computing TLSH for {license_id}: {e}")
        
        logger.debug(f"Computed {len(self.license_hashes)} TLSH hashes")
        
        # Save computed hashes for future use
        self._save_hashes()
    
    def _save_hashes(self):
        """Save computed hashes to file."""
        try:
            hash_file = Path(__file__).parent.parent / 'data' / 'license_hashes.json'
            hash_file.parent.mkdir(exist_ok=True)
            
            with open(hash_file, 'w') as f:
                json.dump(self.license_hashes, f, indent=2)
            
            logger.debug(f"Saved license hashes to {hash_file}")
        except Exception as e:
            logger.warning(f"Could not save license hashes: {e}")
    
    def _preprocess_for_tlsh(self, text: str) -> str:
        """
        Preprocess text for TLSH hashing.
        
        Args:
            text: Original text
            
        Returns:
            Preprocessed text
        """
        import re
        
        # Convert to lowercase
        text = text.lower()
        
        # Extract only alphanumeric and basic punctuation
        text = re.sub(r'[^a-z0-9\s\.\,\;\:\!\?\-]', ' ', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove common variable placeholders
        text = re.sub(r'\[year\]|\[yyyy\]|\[name of copyright owner\]|\[fullname\]', '', text)
        text = re.sub(r'<year>|<name of author>|<organization>', '', text)
        text = re.sub(r'\{year\}|\{fullname\}|\{email\}', '', text)
        
        return text
    
    def _find_near_neighbours(self, input_hash: str) -> list:
        """
        Find every known license whose TLSH hash is a near neighbour of the input.

        Args:
            input_hash: TLSH hash of the preprocessed scanned text

        Returns:
            List of (distance, license_id) tuples, closest first
        """
        neighbours = []

        for license_id, hash_data in self.license_hashes.items():
            try:
                distance = tlsh.diff(input_hash, hash_data['hash'])
            except Exception as e:
                logger.debug(f"Error comparing TLSH hashes for {license_id}: {e}")
                continue

            if distance <= NEAR_NEIGHBOUR_DISTANCE:
                neighbours.append((distance, license_id))

        neighbours.sort()
        return neighbours

    def _corroborate(self, text: str, candidates: list) -> Optional[tuple]:
        """
        Pick the candidate whose real license text best agrees with the scanned text.

        TLSH proximity alone cannot separate licenses that differ by a single
        clause, and those clauses carry the obligations that matter (the JSON
        license is MIT plus "Good, not Evil"; BSD-4-Clause is BSD-3-Clause plus
        the advertising clause). So a candidate is only accepted once the
        license's own text confirms it.

        Args:
            text: The scanned text
            candidates: (distance, license_id) tuples from _find_near_neighbours

        Returns:
            (license_id, similarity) for the best corroborated candidate, or
            None when no candidate's text can substantiate the match
        """
        input_bigrams = create_bigrams(self.spdx_data._normalize_text(text))
        if not input_bigrams:
            return None

        best = None

        for _distance, license_id in candidates:
            license_text = self.spdx_data.get_license_text(license_id)
            if not license_text:
                # No text bundled or cached for this id, so the proposal cannot
                # be checked. Silence beats an unverifiable license assertion.
                logger.debug(f"No license text available to corroborate {license_id}")
                continue

            license_bigrams = create_bigrams(self.spdx_data._normalize_text(license_text))
            similarity = dice_coefficient(input_bigrams, license_bigrams)

            if similarity >= CORROBORATION_THRESHOLD and (best is None or similarity > best[1]):
                best = (license_id, similarity)

        return best

    def _unambiguous_match(self, input_hash: str, candidates: list) -> Optional[tuple]:
        """
        Accept the best candidate only when nothing else is close to it.

        The confusions TLSH is prone to all look the same: a cluster of licenses
        that differ by a clause, sitting within a few points of each other. A
        best candidate that leads the whole license list by a wide margin is not
        that situation, and is reliable even with no text to check it against.

        The runner-up is taken from the entire hash table, not just the near
        neighbour list, so a second candidate sitting just outside the near
        neighbour threshold still counts against the match.

        Args:
            input_hash: TLSH hash of the preprocessed scanned text
            candidates: (distance, license_id) tuples, closest first

        Returns:
            (license_id, confidence) when unambiguous, otherwise None
        """
        best_distance, best_match = candidates[0]

        runner_up = None
        for license_id, hash_data in self.license_hashes.items():
            if license_id == best_match:
                continue
            try:
                distance = tlsh.diff(input_hash, hash_data['hash'])
            except Exception:
                continue
            if runner_up is None or distance < runner_up:
                runner_up = distance

        if runner_up is not None and runner_up - best_distance < UNAMBIGUOUS_MARGIN:
            return None

        # Closer match, higher confidence, held below the text-matching tiers.
        span = _UNCORROBORATED_CONFIDENCE_MAX - _UNCORROBORATED_CONFIDENCE_MIN
        confidence = _UNCORROBORATED_CONFIDENCE_MAX - (
            best_distance / NEAR_NEIGHBOUR_DISTANCE
        ) * span
        return best_match, round(confidence, 3)

    def detect_license_tlsh(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Detect license using TLSH fuzzy hashing.

        TLSH is used as a candidate generator, not as the verdict: the near
        neighbours it proposes are re-checked against their actual license
        texts, and only a corroborated candidate is reported. The reported
        confidence is that text agreement, so a fuzzy match no longer outranks
        an exact or keyword identification of the same file.

        Args:
            text: License text to analyze
            file_path: Source file path

        Returns:
            DetectedLicense or None
        """
        if not TLSH_AVAILABLE:
            logger.debug("TLSH not available, skipping")
            return None

        if not self._initialized:
            logger.debug("TLSH detector not initialized")
            return None

        try:
            # Preprocess input text
            processed_text = self._preprocess_for_tlsh(text)

            # Compute hash for input
            input_hash = tlsh.hash(processed_text.encode('utf-8'))

            if not input_hash or input_hash == 'TNULL':
                logger.debug("Could not compute TLSH hash for input text")
                return None

            candidates = self._find_near_neighbours(input_hash)
            if not candidates:
                return None

            # Preferred: the candidate's own license text confirms the match.
            corroborated = self._corroborate(text, candidates)
            if corroborated:
                best_match, confidence = corroborated
            else:
                # The fallback exists for candidates that cannot be checked at
                # all. It was written when only a minority of SPDX entries
                # shipped their text, so most proposals were uncheckable and
                # falling silent for all of them lost licences TLSH identifies
                # perfectly well — see UNAMBIGUOUS_MARGIN.
                #
                # Every licence on the list carries its text now (#126), so a
                # failed corroboration usually means something different and
                # much more important: the text was read and it disagreed.
                # Asserting over that would be the fallback overruling the
                # evidence, and widening the candidate distance would have made
                # it reachable for candidates that are simply wrong.
                # Only the candidate that would be asserted gets to veto the
                # fallback. Asking whether *any* candidate had text refused the
                # fallback whenever a checkable neighbour sat beside an
                # uncheckable best candidate, which is the very case the
                # fallback is kept for.
                proposed = candidates[0][1]
                if self.spdx_data.get_license_text(proposed):
                    logger.debug(
                        f"TLSH proposed {proposed} for {file_path} "
                        f"(distance {candidates[0][0]}) and its licence text does "
                        f"not agree; not asserting a license"
                    )
                    return None

                unambiguous = self._unambiguous_match(input_hash, candidates)
                if not unambiguous:
                    logger.debug(
                        f"TLSH proposed {candidates[0][1]} for {file_path} "
                        f"(distance {candidates[0][0]}) but it is neither corroborated "
                        f"by a license text nor unambiguous; not asserting a license"
                    )
                    return None
                best_match, confidence = unambiguous
            license_info = self.spdx_data.get_license_info(best_match)

            # Determine category based on filename
            name_lower = file_path.name.lower()
            is_license_file = any(pattern in name_lower for pattern in
                                 ['license', 'licence', 'copying', 'copyright', 'notice'])
            category = LicenseCategory.DECLARED.value if is_license_file else LicenseCategory.DETECTED.value

            return DetectedLicense(
                spdx_id=best_match,
                name=license_info.get('name', best_match) if license_info else best_match,
                confidence=confidence,
                detection_method=DetectionMethod.TLSH.value,
                source_file=str(file_path),
                category=category,
                match_type="text_similarity"
            )

        except Exception as e:
            logger.error(f"Error in TLSH detection: {e}")
            return None

    @property
    def can_confirm(self) -> bool:
        """Whether corroboration is actually available.

        ``python-tlsh`` is an optional dependency that needs a C toolchain to
        build, so a plain ``pip install osslili`` commonly has no TLSH at all.
        Callers that treat corroboration as a safety requirement must check
        this: ``confirm_license_match`` answers True when it cannot check, so a
        caller that only looks at its return value gets a rubber stamp rather
        than a confirmation.
        """
        return TLSH_AVAILABLE and self._initialized

    def confirm_license_match(self, text: str, license_id: str, threshold: int = 100) -> bool:
        """
        Confirm a license match using TLSH.

        Returns True when it cannot check — an unavailable confirmer must not
        veto an otherwise good match. Check :attr:`can_confirm` first if a real
        confirmation is required.

        Args:
            text: Text to check
            license_id: SPDX license ID to confirm
            threshold: Maximum TLSH distance for confirmation (default 100)

        Returns:
            True if confirmed or unable to check, False if refuted
        """
        if not self.can_confirm:
            return True  # Can't confirm, assume valid
        
        try:
            # Preprocess input text
            processed_text = self._preprocess_for_tlsh(text)
            
            # Compute hash for input
            input_hash = tlsh.hash(processed_text.encode('utf-8'))
            
            if not input_hash or input_hash == 'TNULL':
                return True  # Can't compute hash, assume valid
            
            # Check against specific license
            if license_id in self.license_hashes:
                license_hash = self.license_hashes[license_id]['hash']
                
                try:
                    distance = tlsh.diff(input_hash, license_hash)
                    # Confirm if distance is within threshold
                    return distance <= threshold
                except Exception:
                    return True  # Error comparing, assume valid
            
            return True  # License not in database, assume valid
        
        except Exception as e:
            logger.debug(f"Error confirming license match: {e}")
            return True  # Error, assume valid
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute similarity between two texts using TLSH.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not TLSH_AVAILABLE:
            return 0.0
        
        try:
            # Preprocess texts
            processed1 = self._preprocess_for_tlsh(text1)
            processed2 = self._preprocess_for_tlsh(text2)
            
            # Compute hashes
            hash1 = tlsh.hash(processed1.encode('utf-8'))
            hash2 = tlsh.hash(processed2.encode('utf-8'))
            
            if not hash1 or not hash2 or hash1 == 'TNULL' or hash2 == 'TNULL':
                return 0.0
            
            # Calculate distance
            distance = tlsh.diff(hash1, hash2)
            
            # Convert distance to similarity
            # Distance 0 = 100% similar
            # Distance 100+ = 0% similar
            similarity = max(0.0, 1.0 - (distance / 100))
            
            return similarity
        
        except Exception as e:
            logger.debug(f"Error computing TLSH similarity: {e}")
            return 0.0