# rgeo PyTorch Installation Check

Date checked: 2026-06-08  
Environment: `/members/dhnyu/.conda/envs/rgeo`  
Working directory: `/members/dhnyu/fuse`

No packages were installed. Only environment inspection, `conda --dry-run`, and `pip --dry-run` commands were run.

## Summary

PyTorch should **not** be installed into `rgeo` with conda against the current Python 3.14 environment. Conda cannot solve PyTorch while keeping Python 3.14.

The safest currently identified route is a **pip CPU-wheel install of PyTorch 2.12.0 for Python 3.14**, because the dry-run shows it does not require downgrading Python or rebuilding the R/spatial stack.

Recommended command:

```bash
conda activate rgeo
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

This is CPU-only. It is enough to run the small GeoNeuralRepresentation import and 100-building smoke tests, but it may be slow for larger embedding experiments.

## Current Python Version

Command:

```bash
conda run -n rgeo python --version
```

Result:

```text
Python 3.14.0
```

## Current R Version

Command:

```bash
conda run -n rgeo Rscript -e 'cat(R.version.string, "\n")'
```

Result:

```text
R version 4.5.3 (2026-03-11)
```

## Installed R Packages

Checked with `requireNamespace()` in `rgeo`.

| Package | Status |
|---|---:|
| `sf` | `1.1.0` |
| `terra` | `1.9.11` |
| `arrow` | `22.0.0` |
| `data.table` | `1.17.8` |
| `tidyverse` | `2.0.0` |
| `future.mirai` | `0.10.1` |
| `future_mirai` | not installed under this name |
| `collapse` | `2.1.4` |

Spatial library check:

```text
GEOS 3.14.1
GDAL 3.12.2
PROJ 9.7.1
terra 1.9.11
```

`sf::sf_use_s2(FALSE)` works.

## Installed Python Packages Relevant to Geo2Vec

Checked with `python -m pip show`.

| Package | Status |
|---|---:|
| `torch` | not installed |
| `geopandas` | `1.1.3` |
| `shapely` | `2.1.2` |
| `numpy` | `2.4.6` |
| `pandas` | `2.3.3` |
| `pyarrow` | `22.0.0` |
| `tqdm` | `4.67.1` |
| `scikit-learn` | `1.8.0` |
| `matplotlib` | `3.10.9` |
| `scipy` | `1.17.1` |
| `pyogrio` | `0.12.1` |
| `fiona` | not installed |
| `osmnx` | not installed |

The external GeoNeuralRepresentation `requirements.txt` is UTF-16 encoded and lists:

```text
geopandas==0.14.4
osmnx==1.9.4
shapely==2.0.6
torch==2.7.1+cu128
tqdm
multiprocessing
```

For current FUSE tests, `osmnx` is not needed by `runners/list2embedding.py`; PyTorch is the missing blocker.

## Conda PyTorch Solve With Current Python 3.14

Command:

```bash
conda install -n rgeo --dry-run --override-channels -c pytorch -c conda-forge pytorch cpuonly
```

Result: **failed**.

Key solver message:

```text
The following packages are incompatible
├─ pin-1 is installable and it requires
│  └─ python 3.14.* , which can be installed;
└─ pytorch is not installable
```

The solver lists PyTorch builds for Python 3.12 and older, but not a viable conda PyTorch build for the current Python 3.14 environment.

CUDA conda dry-run also failed for the same root reason:

```bash
conda install -n rgeo --dry-run -c pytorch -c nvidia -c conda-forge pytorch pytorch-cuda=12.4
```

Key result:

```text
pin-1 ... requires python 3.14.*
pytorch is not installable
```

## Python Downgrade Solve

Command:

```bash
conda install -n rgeo --dry-run -c conda-forge 'python=3.12' 'pytorch'
```

Result: **solves**, but it is invasive.

The dry-run proposed:

- Python downgrade from `3.14.0` to `3.12.13`.
- PyTorch `2.11.0` CUDA build from conda-forge.
- Download size around `2.84 GB`.
- Many CUDA packages, including `libtorch`, `triton`, CUDA runtime libraries, cuDNN, cuBLAS, cuSPARSE, NCCL, MAGMA.
- Rebuild/downgrade of Python geospatial packages:
  - `gdal` from Python 3.14 build to Python 3.12 build.
  - `pyarrow`, `numpy`, `pandas`, `shapely`, `pyogrio`, `pyproj`, `scipy`, `scikit-learn`.
- Shared-library updates that may affect both R and Python stacks:
  - `libgdal` `3.12.2` to `3.12.3`
  - `libarrow` build revision changes
  - `hdf5` major package change in the plan
  - `libnetcdf` update
  - `openblas` threading variant changes
  - `r-s2` build change
- Removal of some pip-installed packages:
  - `py360convert`
  - `streetview`
  - several Jupyter-related pip packages

This is technically solvable but not a safe first action for an environment whose priority is R spatial analysis.

## pip PyTorch Dry Run

Command:

```bash
conda run -n rgeo python -m pip install --dry-run torch --index-url https://download.pytorch.org/whl/cpu
```

Result: **succeeds as a dry-run**.

Planned install:

```text
torch-2.12.0+cpu
filelock-3.29.0
fsspec-2026.4.0
mpmath-1.3.0
setuptools-70.2.0
sympy-1.14.0
```

Important observations:

- A Python 3.14 wheel exists: `torch-2.12.0+cpu-cp314-cp314-manylinux_2_28_x86_64.whl`.
- No Python downgrade is required.
- No conda package rebuild is proposed.
- No R packages or compiled R spatial dependencies are touched by the dry-run.

I also attempted a CUDA pip dry-run:

```bash
conda run -n rgeo python -m pip install --dry-run torch --index-url https://download.pytorch.org/whl/cu128
```

That command stalled without output and was terminated. It did not install anything. Because the CPU wheel is sufficient for import and small integration tests, the CUDA pip route should be treated as unverified.

## GPU Context

`nvidia-smi` reports:

- Driver: `595.45.04`
- CUDA runtime capability shown by driver: `13.2`
- GPUs: two NVIDIA RTX A6000 GPUs

One GPU was occupied during inspection. GPU availability at the system level is not the blocker. The blocker is package compatibility inside the Python 3.14 `rgeo` environment.

## Does Python Need to be Downgraded?

For **conda PyTorch**: yes, Python must be downgraded to Python 3.12 or possibly 3.11.

For **pip CPU PyTorch**: no. PyTorch 2.12.0 has a CPU wheel for Python 3.14.

Given the user requirement to preserve the existing R spatial workflow, Python should **not** be downgraded as the first step.

## Risk of Downgrading Python Inside rgeo

Risk level: **High**.

Reasons:

- The current environment is a mixed R/Python geospatial stack.
- The conda Python 3.12 + PyTorch solve updates or rebuilds Python GDAL, libGDAL, Arrow, HDF5, NetCDF, BLAS/OpenMP, and `r-s2`.
- Those shared libraries are exactly the libraries that `sf`, `terra`, `arrow`, and related R spatial workflows depend on.
- Even if conda solves, runtime regressions are possible: CRS transforms, GDAL drivers, Parquet/Arrow behavior, raster IO, and parallel numerical behavior can change.
- The solve also removes some pip packages used elsewhere in FUSE/streetview workflows.

Downgrading Python inside `rgeo` should only be considered after exporting a full environment specification and accepting a broader validation pass for R and Python workflows.

## Safest Install Command

Recommended first install command:

```bash
conda activate rgeo
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Why this command:

- Does not create a new conda environment.
- Does not downgrade Python.
- Does not ask conda to rebuild GDAL, Arrow, HDF5, NetCDF, BLAS, or R package dependencies.
- Installs a PyTorch wheel that explicitly supports Python 3.14.
- Is sufficient for `tests/test_geo2vec_import.py` and the 100-building Geo2Vec smoke test.

Suggested immediate verification after install:

```bash
python tests/test_geo2vec_import.py
python tests/test_geo2vec_gwanak_100.py
Rscript -e 'library(sf); library(terra); library(arrow); library(data.table); library(future.mirai); sf::sf_use_s2(FALSE); print(sf::sf_extSoftVersion()); print(packageVersion("terra")); print(packageVersion("arrow"))'
```

## Recommendation

Use the pip CPU PyTorch wheel first. Do not downgrade Python inside `rgeo` for the initial GeoNeuralRepresentation tests.

Final answers:

- Can torch be installed directly? **Yes, via pip CPU wheel for Python 3.14. Not via conda PyTorch against current Python 3.14.**
- Is Python downgrade required? **No for pip CPU torch; yes for conda PyTorch.**
- Exact recommended command:

```bash
conda activate rgeo
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

- Risk level for existing R spatial packages: **Low for pip CPU torch; high for conda Python downgrade + PyTorch.**
