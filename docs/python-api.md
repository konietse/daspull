# Python API

```python
import daspull

daspull.list_datasets()
# ['das4microseism', 'das4whale', 'fairbanks', 'foresee', 'forge_2c', ...]

daspull.download("das4microseism", "data", date="2020-07-05")
daspull.download(
    "foresee", date="2019-04-05 08:00:00", buffer=30
)  # dir defaults to the ID
daspull.download("valencia", include="*2020-09-01*")
daspull.download("das4whale", all_files=True)  # whole primary catalog
daspull.download("https://example.org/file.h5", "data")

files = daspull.list_files("porotomo_h", date="2016-03-11")  # browse, no download
daspull.list_intervals("safod")  # continuous UTC coverage
```

`date=` also takes `"2016"` or `"2016-08"` for a whole UTC year or month, and `datetime` objects;
`start=`/`end=` give an explicit `[start, end)`. `include=`/`exclude=` take one glob or a list.
The acquisition selector is `sampling_rate=` / `channel_spacing=` / `gauge_length=`, required
wherever the table lists several values and validated against the one value everywhere else.
Downloading a whole catalog needs `all_files=True`, so an unfiltered call cannot start a
multi-terabyte transfer by accident.

## Logging in to Globus

Eight of the eighteen datasets are hosted on a Globus collection and need a one-time login before
they can be browsed or downloaded. Every other provider is anonymous. 

```python
import daspull

daspull.login(provider="globus", no_browser=True)  # prompts once for the resulting code
daspull.download("fairbanks", date="2016-08-12")

daspull.logout(provider="globus")  # removes the locally cached tokens
```

## Opening a dataset once

Open a dataset once when a script lists before it downloads::

```python
ds = daspull.open_dataset(
    "fairbanks"
)  # Globus: call daspull.login(provider="globus") first
ds.summary, ds.data_format, ds.provider, ds.metadata["provenance"]["doi"]

selected = ds.list_files(date="2016-08-05", limit=10)
ds.download("data/fairbanks", files=selected)
```