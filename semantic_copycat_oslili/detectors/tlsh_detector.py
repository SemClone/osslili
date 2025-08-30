"""
TLSH (Trend Micro Locality Sensitive Hash) detector for license matching.
"""

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any

from ..core.models import DetectedLicense, DetectionMethod, LicenseCategory

logger = logging.getLogger(__name__)

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
    
    def detect_license_tlsh(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Detect license using TLSH fuzzy hashing.
        
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
            
            # Find best match
            best_match = None
            best_score = float('inf')
            
            for license_id, hash_data in self.license_hashes.items():
                license_hash = hash_data['hash']
                
                # Calculate TLSH distance (lower is better)
                try:
                    distance = tlsh.diff(input_hash, license_hash)
                    
                    # TLSH distance of 0-30 is very similar
                    # 30-100 is similar
                    # 100+ is different
                    if distance < best_score:
                        best_score = distance
                        best_match = license_id
                
                except Exception as e:
                    logger.debug(f"Error comparing TLSH hashes: {e}")
            
            if best_match and best_score <= 30:  # Very similar threshold
                # Convert TLSH distance to confidence score
                # Distance 0 = 100% confidence
                # Distance 30 = 97% confidence (our threshold)
                confidence = max(0.97, 1.0 - (best_score / 1000))
                
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
            
            return None
        
        except Exception as e:
            logger.error(f"Error in TLSH detection: {e}")
            return None
    
    def confirm_license_match(self, text: str, license_id: str, threshold: int = 100) -> bool:
        """
        Confirm a license match using TLSH.
        
        Args:
            text: Text to check
            license_id: SPDX license ID to confirm
            threshold: Maximum TLSH distance for confirmation (default 100)
            
        Returns:
            True if confirmed, False otherwise
        """
        if not TLSH_AVAILABLE or not self._initialized:
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