<p align="center">
  <img src="https://raw.githubusercontent.com/konietse/daspull/main/docs/logo.png" alt="DASPull logo" width="200">
</p>

<h1 align="center">DASPull</h1>

<p align="center">
  A lightweight downloader for open-access <strong>Distributed Acoustic Sensing (DAS)</strong> data.
No provider-specific tooling required, just Python and HTTP.
</p>

<p align="center">
  <a href="https://pypi.org/project/daspull/"><img alt="PyPI" src="https://img.shields.io/pypi/v/daspull?logo=pypi&logoColor=white&color=3775A9&cacheSeconds=300"></a>
  <a href="https://pypi.org/project/daspull/"><img alt="Python 3.9+" src="https://img.shields.io/pypi/pyversions/daspull?logo=python&logoColor=white&color=3776AB&cacheSeconds=300"></a>
  <a href="https://github.com/konietse/daspull/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/konietse/daspull/ci.yml?branch=main&label=tests&logo=githubactions&logoColor=white"></a>
  <img alt="Linux, macOS, Windows" src="https://img.shields.io/badge/OS-Linux%20%7C%20macOS%20%7C%20Windows-4c566a">
  <a href="https://doi.org/10.5281/zenodo.21789169"><img alt="DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.21789169.svg?v=1"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-2ea44f"></a>
  <a href="PRIVACY.md"><img alt="Privacy Policy" src="https://img.shields.io/badge/Privacy-Policy-6c5ce7"></a>
  <a href="TERMS.md"><img alt="Terms of Use" src="https://img.shields.io/badge/Terms-of%20Use-6c5ce7"></a>
</p>


Designed for researchers and engineers who need to download complete files or selected
parts of DAS datasets directly to your system. The datasets are spread across **Globus**,
**S3**, **Hugging Face**, **Dataverse**, **Zenodo**, **Dropbox**, and **Pando**, normally
one client per provider (Globus Connect Personal, AWS CLI, `git-lfs`, etc.). DASPull
replaces all of them, so it works on HPC login nodes, in containers, and anywhere else you
can't (or don't want to) install extra software.

## Installation

Requires Python 3.9+.

As a command-line tool, isolated from your other environments:

```bash
uv tool install daspull    # or: pipx install daspull
```

As a library, into an existing project or environment:

```bash
uv add daspull             # or: pip install daspull
```

## Usage

```bash
daspull ID --list                             # browse the remote catalog
daspull ID --list-intervals                   # list continuous UTC coverage blocks
daspull ID --date 2016-03-11 --dry-run        # preview a selection and its total size
daspull ID --date 2016-03-11 -o DIR           # download it
daspull ID --all -o DIR                       # download the whole catalog
daspull https://example.org/file.h5 -o DIR    # or any direct URL, no dataset ID needed
```

IDs come from the table below. `daspull ID --help` shows a dataset's options and defaults.
Output goes to a directory named after the ID unless `-o DIR` says otherwise, remote paths are preserved below it, and interrupted downloads resume via HTTP range requests.
Globus-hosted datasets need a one-time `daspull login --globus` (add `--no-browser` with no local
browser to open; `daspull logout --globus` to remove the cached tokens), everything else
works immediately.

## Supported datasets
| Dataset | ID | Description | Gauge (m) | Channel spacing (m) | Sampling rate (Hz) | Size (TB) | Format | Access | 
|---|---|---|---|---|---|---|---|---|
| [DAS4Microseism](https://doi.org/10.18710/VPRD2H) [[18](#ref18)] | das4microseism | Ocean-bottom fiber-optic array, Isfjorden, Svalbard, Norway | 8.16 | 4.08 | 50 | 0.20 | MAT | Dataverse |
| [DAS4Whale](https://doi.org/10.5281/zenodo.5823343) [[3](#ref3)] | das4whale | Baleen whale monitoring array excerpts, Isfjorden, Svalbard, Norway | 8.16 | 4 | 645.16 | 0.04 | MAT | Zenodo |
| [Fairbanks](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FFairbanks%2F&two_pane=true) [[4](#ref4), [15](#ref15)] | fairbanks | Permafrost monitoring array, Fairbanks, Alaska | 10 | 1 | 1000 | 5.47 | TDMS | Globus | 
| [FORESEE](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FFORESEE%2F&two_pane=true) [[20](#ref20), [15](#ref15)] | foresee | Urban monitoring array, Pennsylvania State University campus | 10 | 2 | 125 | 15.02 | HDF5 | Globus |
| [FORGE Phase 2C](https://doi.org/10.15121/1603679) [[6](#ref6)] | forge_2c | Vertical monitoring-well fiber-optic array, Utah FORGE geothermal field, Milford, Utah | 10 | 1 | 2000 | 13.00 | SEG-Y | Pando |
| [FOSSA](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FFOSSA%2F&two_pane=true) [[2](#ref2), [15](#ref15)] | fossa | Near-surface seismic array, Sacramento River, California | 10 | 2 | 500 | 6.12 | TDMS | Globus |
| [GorDAS-1](https://huggingface.co/datasets/AI4EPS/quakeflow_das/tree/main/eureka) [[1](#ref1), [11](#ref11), [13](#ref13)] | gordas_1 | Telecom-fiber array between Arcata and Eureka, California | 8.168 | 2.04 | 250 | 0.024 | HDF5 | Hugging Face |
| [GorDAS-2](https://huggingface.co/datasets/AI4EPS/quakeflow_das/tree/main/arcata) [[1](#ref1), [12](#ref12), [13](#ref13)] | gordas_2 | Telecom-fiber array at Arcata, California (2022 M6.4 Ferndale aftershocks) | 8.1676 | 2.042 / 5.105 | 125 / 100 | 0.51 | HDF5 | Hugging Face |
| [LaFarge](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FLaFargeConcoMine%2F&two_pane=true) [[15](#ref15), [19](#ref19)] | lafarge | Underground mine array, North Aurora, Illinois | 10 | 1 | 1000 | 0.02 | SEG-Y | Globus |
| [MARS](https://huggingface.co/datasets/AI4EPS/quakeflow_das/tree/main/monterey_bay) [[1](#ref1), [14](#ref14)] | mars | Submarine MARS cable array (SeaFOAM), Monterey Bay, California | 20.4 | 5.2 | 200 | 0.0045 | HDF5 | Hugging Face |
| [PoroTomo DASH](https://doi.org/10.15121/1778858) [[5](#ref5)] | porotomo_h | Horizontal trenched DAS array, Brady Hot Springs geothermal field, Nevada | 10 | 1.021 | 1000 | 42.75 | HDF5 | S3 |
| [PoroTomo DASV](https://doi.org/10.15121/1778858) [[5](#ref5)] | porotomo_v | Vertical borehole DAS array, Brady Hot Springs geothermal field, Nevada | 10 | 1.021 | 1000 | 1.06 | HDF5 | S3 |
| [Ridgecrest North](https://scedc.caltech.edu/data/cloud.html) [[8](#ref8)] | ridgecrest_north | Telecom-fiber array, Ridgecrest to Inyokern airport, California | 16.34 | 8 | 250 | 4.09 | SEG-Y | S3 |
| [SAFOD](https://www.dropbox.com/scl/fo/fiwbxwfpz65qbx2bu441b/AKY86kM-Zbbie7_v8v62iKI?rlkey=plqbl8wfb5n90ycpgc7vhms7a) [[7](#ref7)] | safod | Downhole fiber-optic array, SAFOD, Parkfield, California | 10 | 1 | 250 | 0.0015 | NPY | Dropbox |
| [Stanford-1](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FStanford-1-Campus%2F&two_pane=true) [[10](#ref10), [15](#ref15)] | stanford_1 | Urban campus array, Stanford, California | 7.14 | 8.16 | 50 | 9.91 | SEG-Y | Globus |
| [Stanford-2](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FStanford-2-Sandhill-Road%2F&two_pane=true) [[9](#ref9), [15](#ref15)] | stanford_2 | City-scale urban array, Palo Alto, California | 20 | 8.16 | 250 | 1.51 | SEG-Y | Globus |
| [Stanford-3](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FStanford-3-ODH4%2F&two_pane=true) [[15](#ref15), [17](#ref17)] | stanford_3 | Dual-interrogator comparison array, Stanford, California | 7.14 / 2 / 4 | 8.16 | 50 / 100 | 0.05 | SEG-Y | Globus |
| [Valencia](https://app.globus.org/file-manager?origin_id=706e304c-5def-11ec-9b5c-f9dfb1abb183&origin_path=%2FValencia%2F&two_pane=true) [[15](#ref15), [16](#ref16)] | valencia | Submarine telecom cable array, Valencia–Mallorca, Spain | 30.4 | 16.8 | 250 | 1.68 | HDF5 | Globus |


## Python

```python
import daspull

daspull.download("fairbanks", date="2016-08-12")
```

`daspull.download`/`list_files`/`list_intervals`/`open_dataset` mirror the CLI options above,
and Globus login is available as `daspull.login(provider="globus")`. Full walkthrough, including
opening a dataset once and customising a provider client, is in
[`docs/python-api.md`](docs/python-api.md).


## Citation

If you use DASPull in your research, please cite it as below:

```
@software{Konietzny_DASPull_2026,
  author    = {Konietzny, Sebastian},
  title     = {DASPull},
  version   = {0.1.0},
  date      = {2026-08-04},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21789169},
  url       = {https://doi.org/10.5281/zenodo.21789169}
}
```

## References
<a id="ref1"></a>**[1]**
AI4EPS. (2023). quakeflow_das (Revision 91b72d3) [Data set]. Hugging Face. https://doi.org/10.57967/hf/0962
<br>
<a id="ref2"></a>**[2]**
Ajo-Franklin, J. B., Dou, S., Lindsey, N. J., et al. (2019). Distributed Acoustic Sensing Using Dark Fiber for Near-Surface Characterization and Broadband Seismic Event Detection. Scientific Reports, 9 (1), 1328. https://doi.org/10.1038/s41598-018-36675-8
<br>
<a id="ref3"></a>**[3]**
Bouffaut, L., Taweesintananon, K. (2022). DAS4Whale: Svalbard distributed acoustic sensing dataset for baleen whale monitoring (Version 1.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.5823343
<br>
<a id="ref4"></a>**[4]**
Cheng, F., Lindsey, N., Sobolevskaia, V., et al. (2022). Watching the Cryosphere Thaw: Seismic Monitoring of Permafrost Degradation Using Distributed Acoustic Sensing During a Controlled Heating Experiment. Geophysical Research Letters, 49 (10), e2021GL097195. https://doi.org/10.1029/2021GL097195
<br>
<a id="ref5"></a>**[5]**
Feigl, K., Reinisch, E., Patterson, J., et al. (2016). PoroTomo Natural Laboratory Horizontal and Vertical Distributed Acoustic Sensing Data. [Data set]. Geothermal Data Repository. University of Wisconsin. https://doi.org/10.15121/1778858
<br>
<a id="ref6"></a>**[6]**
Martin, T., Nash, G. (2019). Utah FORGE: High-Resolution DAS Microseismic Data from Well 78-32. [Data set]. Geothermal Data Repository. Energy and Geoscience Institute at the University of Utah. https://doi.org/10.15121/1603679
<br>
<a id="ref7"></a>**[7]**
Lellouch, A., Yuan, S., Spica, Z., et al. (2019). Seismic velocity estimation using passive downhole distributed acoustic sensing records: Examples from the San Andreas Fault Observatory at Depth. Journal of Geophysical Research: Solid Earth, 124, 6931–6948. https://doi.org/10.1029/2019JB017533
<br>
<a id="ref8"></a>**[8]**
Li, Z., Shen, Z., Yang, Y., et al. (2021). Rapid response to the 2019 Ridgecrest earthquake with distributed acoustic sensing. AGU Advances, 2, e2021AV000395. https://doi.org/10.1029/2021AV000395
<br>
<a id="ref9"></a>**[9]**
Lindsey, N. J., Yuan, S., Lellouch, A., et al. (2020). City-Scale Dark Fiber DAS Measurements of Infrastructure Use During the COVID-19 Pandemic. Geophysical Research Letters, 47, e2020GL089931. https://doi.org/10.1029/2020GL089931
<br>
<a id="ref10"></a>**[10]**
Martin, E. R., Castillo, C. M., Cole, S., et al. (2017). Seismic monitoring leveraging existing telecom infrastructure at the SDASA: Active, passive, and ambient-noise analysis. The Leading Edge, 36, 1025–1031. https://doi.org/10.1190/tle36121025.1
<br>
<a id="ref11"></a>**[11]**
McGuire, J.J., Barbour, A.J., Karrenbach, M., et al. (2022). Spring 2022 Arcata to Eureka California, Distributed Acoustic Sensing (DAS) experiment. U.S. Geological Survey data release. https://doi.org/10.5066/P9NYAT5Z
<br>
<a id="ref12"></a>**[12]**
McGuire, J. J., Barbour, A. J., Stewart, C., et al. (2024). Arcata, California, Distributed Acoustic Sensing (DAS) experiment: 2022 M6.4 Ferndale Aftershock Sequence (ver. 3.0, February 2026). U.S. Geological Survey data release. https://doi.org/10.5066/P1V7CKGA
<br>
<a id="ref13"></a>**[13]**
McGuire, J. J., Barbour, A. J., Stewart, C., et al. (2025). The GorDAS Distributed Acoustic Sensing Experiment Above the Cascadia Locked Zone and Subducted Gorda Slab. Seismological Research Letters, 96 (4): 2489–2503. https://doi.org/10.1785/0220240415
<br>
<a id="ref14"></a>**[14]**
Romanowicz, B., Allen, R., Brekke, K., et al. (2023). SeaFOAM: A Year‐Long DAS Deployment in Monterey Bay, California. Seismological Research Letters, 94 (5): 2348–2359. https://doi.org/10.1785/0220230047
<br>
<a id="ref15"></a>**[15]**
Spica, Z. J., Ajo-Franklin, J., Beroza, G. C., et al. (2023). PubDAS: A PUBlic Distributed Acoustic Sensing Datasets Repository for Geosciences, Seismological Research Letters, 94 (2A), 983–998. https://doi.org/10.1785/0220220279
<br>
<a id="ref16"></a>**[16]**
Spica, Z. J., Gaite, B., Barajas, S. B. (2020). The Valencia-Islalink Distributed Acoustic Sensing Experiment [Data set]. PubDAS. https://doi.org/10.7914/SN/ZH_2020
<br>
<a id="ref17"></a>**[17]**
Spica, Z. J., Perton, M., Martin, E. R., et al. (2020). Urban Seismic Site Characterization by Fiber-Optic Seismology. Journal of Geophysical Research: Solid Earth, 125, e2019JB018656. https://doi.org/10.1029/2019JB018656
<br>
<a id="ref18"></a>**[18]**
Taweesintananon, K., Landrø, M. (2022). Replication data for DAS4Microseism - Svalbard distributed acoustic sensing (DAS) strain data for oceanographic study. DataverseNO, V1. https://doi.org/10.18710/VPRD2H
<br>
<a id="ref19"></a>**[19]**
Wang, H., Zeng, X. Lord, N., et al. (2017). Lafarge-Conco Mine Distributed Acoustic Sensing Experiment (N Aurora, Illinois) [Data set]. International Federation of Digital Seismograph Networks. https://doi.org/10.7914/SN/5S_2017
<br>
<a id="ref20"></a>**[20]**
Zhu, T., Shen, J., Martin, E. R. (2021). Sensing Earth and environment dynamics by telecommunication fiber-optic sensors: an urban experiment in Pennsylvania, USA. Solid Earth. Copernicus GmbH. https://doi.org/10.5194/se-12-219-2021
<br>