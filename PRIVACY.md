# DASPull Privacy Policy

Effective date: July 27, 2026

DASPull is an open-source, local command-line tool for downloading DAS
datasets. There is no DASPull-hosted service.

- **No collection.** The maintainers do not receive telemetry, analytics,
  crash reports, OAuth tokens, or download activity from DASPull.
- **Local data only.** Globus OAuth tokens, remote file lists, and download
  state are processed and stored only on your machine: by default at
  `~/.config/daspull/tokens.json` (override with `DASPULL_TOKEN_FILE`).
  `daspull logout --globus` deletes the local token file but does not revoke
  your consent at Globus.
- **Third parties.** DASPull communicates directly with Globus and each
  dataset's host (PubDAS, S3, Hugging Face, Dataverse, Zenodo, Dropbox,
  Pando). Their own policies apply, e.g. the
  [Globus Privacy Policy](https://www.globus.org/legal/privacy).
- **Security.** Downloads use HTTPS. No guarantee is made about the security
  of third-party services or your local environment.
- **Changes.** This policy may be updated in this repository, with the
  effective date revised accordingly.

Contact: Sebastian Konietzny · <koniet.se@gmail.com>
