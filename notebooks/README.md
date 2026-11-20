# Research notebooks

Notebooks 01–05 cover retrospective QC forecasting. Notebook
[06_weekly_barangay_reconstruction.ipynb](06_weekly_barangay_reconstruction.ipynb)
audits UPRI annual and city weekly cases, the supplied GIS settlement master and
Tracker-backcast scenario, and the existing synthetic weekly trial. It explains
median recovery, performs masked-value experiments, and generates separate
source-preserving and median-imputed weekly allocation artifacts.

Start the kernel from this repository or `notebooks/`. Install optional execution
tools with `.venv/bin/python -m pip install -r notebooks/requirements.txt` (or
`uv pip install --python .venv/bin/python -r notebooks/requirements.txt`). Select
the project `.venv` Python kernel and **Run All**. Outputs are saved in the notebook.
The final cell writes only to `data/processed/weekly_barangay_reconstruction/`;
set `EXPORT = False` in the first code cell for an analysis-only rerun.

Headless execution, with the project kernel explicitly selected:

```bash
.venv/bin/python - <<'PY'
import nbformat
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager
from pathlib import Path
import json, sys, tempfile
path = Path('notebooks/06_weekly_barangay_reconstruction.ipynb')
with tempfile.TemporaryDirectory() as tmp:
    kernel = Path(tmp) / 'surgewise'
    kernel.mkdir()
    (kernel / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'SurgeWise project Python', 'language': 'python'}))
    nb = nbformat.read(path, as_version=4)
    from jupyter_client import KernelManager
    km = KernelManager(kernel_name='surgewise', transport='ipc',
                       kernel_spec_manager=KernelSpecManager(kernel_dirs=[tmp]))
    NotebookClient(nb, timeout=600, km=km,
                   resources={'metadata': {'path': str(Path.cwd())}}).execute()
    nbformat.write(nb, path)
PY
```

The pure generation functions are also usable without Jupyter:

```bash
.venv/bin/python scripts/generate_weekly_barangay.py --help
.venv/bin/python scripts/generate_weekly_barangay.py --recovery none --output /tmp/qc-weekly-check
.venv/bin/python -m pytest -q services/engine/tests/test_weekly_barangay_reconstruction.py
```

Selected original Drive files are preserved under `data/raw/gis_settlements/`,
`data/raw/weekly_barangay_synthetic/`, `data/raw/drive_qc_prepared/`, and
`data/raw/drive_dengue/`. Their IDs, dates, hashes and permissions caveats are in
`data/reference/weekly_barangay_reconstruction/drive-sources.json`. Existing
`data/raw/upri_noah/` inputs remain unchanged. This is a selected input snapshot,
not a mirror of every linked folder or an independent satellite extraction.

The 39 missing annual cells are unknown observations. Median estimates are
assumptions. QC weekly observations and annual barangay sums disagree, so the
annual-preserving trial uses **scaled weekly targets**. Generated weekly counts,
including the original Drive trial, are modeled allocations. No production
forecast or simulation source is replaced by this notebook.
