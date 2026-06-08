# FLAME Body Part Regression Analysis Tutorial

This guide provides a concise walkthrough of a body-part regression inference workflow in FLAME. It explains how analyzer and aggregator components work together in the STAR pattern to process distributed medical image input and return structured JSON inference results.

## 1. Overview

This analysis is a practical baseline for body-part regression inference in FLAME.
It accepts NIfTI/NRRD input directly for inference.

At runtime, the pipeline performs these steps:

1. Receives input bytes from FLAME (`data_type="s3"`)
2. Selects S3 object keys via query input (`--query_keys`, fallback: `image_data`)
3. Extracts archive content into a temporary working directory
4. Detects supported image files (`.nii`, `.nii.gz`, `.nrrd`)
5. Runs body-part regression inference for all prepared image paths
6. Returns one result object per processed image

## 2. Code Walkthrough

### 2.1. STAR components

The workflow uses the standard STAR pattern:

- `MyAnalyzer` for local analysis logic
- `MyAggregator` for aggregation (pass-through)
- `StarModel` for orchestration

```python
StarModel(
    analyzer=MyAnalyzer,
    aggregator=MyAggregator,
    data_type="s3",
    query=query,
    simple_analysis=True,
    output_type="pickle"
)
```

### 2.2. Analyzer (`MyAnalyzer`)

#### Input handling

Input payloads are extracted from an archive into a temporary folder.
The analyzer scans recursively and collects inference-ready files
(`.nii`, `.nii.gz`, `.nrrd`, depending on configuration).

The workflow supports explicit query keys for S3-style input selection.
If `--query_keys` is provided, those keys are used as `query`.
Otherwise, the workflow falls back to the configured image archive key.

#### Inference

All prepared image paths are processed by the inference model using `nifti2json(...)`.
For each file, the workflow stores either:

- `json` for successful inference
- `basic_error` if inference fails

### 2.3. Aggregator (`MyAggregator`)

`MyAggregator` is pass-through and returns analysis results unchanged:

```python
def aggregation_method(self, analysis_results):
    return analysis_results
```

The convergence method always returns `True`, because this workflow is configured as single-round (`simple_analysis=True`).

## 3. Output

The analysis returns one dictionary entry per input image, for example:

```json
{
  "case1.nii.gz": {
    "json": {
      "cleaned slice-scores": [0.5, 1.3, 2.1, 3.0],
      "body part examined": {
        "pelvis": [0, 1],
        "abdomen": [2, 3]
      },
      "body part examined tag": "ABDOMEN-PELVIS",
      "valid z-spacing": 1
    }
  },
  "case2.nii.gz": {
    "basic_error": "<error message>"
  }
}
```
