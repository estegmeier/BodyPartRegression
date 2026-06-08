# FLAME Integration

This folder contains the files used to run the Body Part Regression analysis on
the FLAME platform. The integration is split into two parts because the platform
master image and the analysis payload are handled separately.

## Structure

- `main/`: FLAME analysis code and analysis-specific documentation.
- `master-images/`: Docker image definition and Python requirements for the
  master image. These files belong in the platform
  [`master-images`](https://github.com/PrivateAIM/master-images) repository.

`TUTORIAL.md` gives a short walkthrough of the Body Part Regression STAR
analysis and can be used as a starting point for FLAME homepage or analysis
documentation.

## Workflow

1. Create or update the master image using the files in `master-images/`.
2. Select that master image on the platform when configuring the analysis run.
3. When starting an analysis, upload `main/analysis.py` as the analysis payload.

The analysis entrypoint runs Body Part Regression inference for supported CT
image files and returns one result object per processed image.