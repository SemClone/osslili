# Add Machine Learning-based License Detection (Tier 3 Enhancement)

## Description
Implement machine learning models for advanced license detection as part of the Tier 3 detection system. This will improve detection of non-standard, modified, or custom license texts that don't match predefined patterns.

## Current Behavior
- Tier 3 currently uses only regex pattern matching
- Cannot detect heavily modified licenses
- Misses custom licenses that don't match patterns

## Proposed Solution
Implement ML-based classification using transformer models or similar approaches:

### Technical Requirements
- [ ] Add optional ML dependencies (transformers, torch/tensorflow)
- [ ] Implement model loading and inference pipeline
- [ ] Create confidence scoring for ML predictions
- [ ] Add fallback when ML dependencies not available

### Implementation Details
```python
# Example in license_detector.py
def _tier3_ml_detection(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
    """Use ML model for license detection."""
    if not self.ml_model_available:
        return None
    
    # Preprocess text
    processed_text = self._preprocess_for_ml(text)
    
    # Get predictions
    predictions = self.ml_model.predict(processed_text)
    
    # Filter by confidence threshold
    if predictions.confidence > self.config.ml_confidence_threshold:
        return DetectedLicense(...)
```

### Models to Consider
- Pre-trained BERT fine-tuned on license texts
- DistilBERT for faster inference
- Custom trained model on SPDX license corpus

## Benefits
- Detect custom and modified licenses
- Handle non-English licenses better
- Improve overall detection accuracy
- Reduce false negatives

## Acceptance Criteria
- [ ] ML model can be optionally enabled
- [ ] Detects at least 90% of modified standard licenses
- [ ] Performance impact < 2 seconds per file
- [ ] Works offline with bundled model
- [ ] Graceful fallback when ML not available

## Priority
Medium-High

## Labels
`enhancement`, `tier-3`, `machine-learning`, `license-detection`