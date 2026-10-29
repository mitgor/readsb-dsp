# Frozen inference models

These are the existing companion cascade (original first) and pulse templates
from the ADS-B neural-rescue project. SHA-256 provenance is recorded in
`docs/INTEGRATION_PROVENANCE.json`; the three production ONNX hashes are also
checked at worker initialization. Model selection never changes with CPU load.
No RF captures, supervised labels, candidate training archives or aircraft tracks
are distributed. Unverified DSP/neural predictions must not become training labels.
