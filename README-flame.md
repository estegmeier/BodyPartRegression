# Body Part Regression 

This Docker image runs the **StarModel pipeline** for the body part regression tool. The Body Part Regression (BPR) model maps CT slices to continuous slice scores that increase monotonically from pelvis (0) to head (100), enabling a machine-interpretable representation of anatomy. Trained in a fully self-supervised manner, it supports tasks such as sorting, labeling, and cropping of radiologic images. Pretrained models are available for direct inference on NIfTI and NRRD images.

---

## 📂 Input Data

The pipeline expects the input data to be provided as `.tar` archives.  
This archive will be automatically extracted during runtime.

- `--image_data`: Path to a tar archive containing the input images (default: `images.tar`)

Example structure:
```
images.tar
├── case1.nii.gz
├── case2.nrrd
└── case3.nrrd
```

**Note:** The pipeline only supports these medical image formats (`.nii`, `.nii.gz`, `.nrrd`) and CT images.

---

## ⚙️ Parameters

The following console arguments are supported:

| Argument               | Type   | Default                  | Description |
|------------------------|--------|--------------------------|-------------|
| `--image_data`         | str    | `images.tar`             | Name of the tar archive with input images |
| `--file_endings`       | list   | `.dcm .nii .nii.gz .nrrd`| File types to process |

### Usage
 ```
 --image_data test.tar --file_endings .nrrd
 ``` 
---

## 📦 Output
The json-file contains all the metadata regarding the examined body part of the image-file. It includes the following  tags: 
- `cleaned slice-scores`: Cleanup of the outcome from the BPR model (smoothing, filtering out outliers). 
- `unprocessed slice-scores`: Plain outcome of the BPR model. 
- `body part examined`: Dictionary with the tags: "legs", "pelvis", "abdomen", "chest", "shoulder-neck" and "head". For each body-part, the slice indices are listed, where the body part is visible. 
- `body part examined tag`: updated tag for BodyPartExamined. Possible values: PELVIS, ABDOMEN, CHEST, NECK, HEAD, HEAD-NECK-CHEST-ABDOMEN-PELVIS, HEAD-NECK-CHEST-ABDOMEN, ... 
- `look-up table`: reference table to be able to map slice scores to landmarks and vise versa. 
- `reverse z-ordering`: (0/1) equal to one if patient height decreases with slice index. 
- `valid z-spacing`: (0/1) equal to one if z-spacing seems to be plausible. The data sanity check is based on the slope of the curve from the cleaned slice-scores.

The information from the meta-data file can be traced back to the `unprocessed slice-scores` and the `look-up table`. 

## License
Copyright © German Cancer Research Center (DKFZ), Division of Medical Image Computing (MIC). Please make sure that your usage of this code is in compliance with the code license:
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/MIC-DKFZ/basic_unet_example/blob/master/LICENSE)

### Cite Software 
Sarah Schuhegger. (2021). MIC-DKFZ/BodyPartRegression: (v1.0). Zenodo. https://doi.org/10.5281/zenodo.5195341