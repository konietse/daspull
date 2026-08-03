__version__ = "0.1.0"

from .api import (
    Dataset,
    describe_datasets,
    download,
    download_url,
    list_datasets,
    list_files,
    list_intervals,
    login,
    logout,
    open_dataset,
)
from .catalog import RemoteFile
from .datasets import DATASETS, DatasetSpec
from .providers import build_client
from .providers.dataverse import DataverseClient
from .providers.dropbox import DropboxClient
from .providers.globus_auth import GLOBUS_CLIENT_ID, TokenStore
from .providers.huggingface import HuggingFaceClient
from .providers.pando import PandoClient
from .providers.pubdas import PubDASClient
from .providers.s3 import S3Client
from .providers.zenodo import ZenodoClient

__all__ = [
    "DATASETS",
    "GLOBUS_CLIENT_ID",
    "Dataset",
    "DatasetSpec",
    "DataverseClient",
    "DropboxClient",
    "HuggingFaceClient",
    "PandoClient",
    "PubDASClient",
    "RemoteFile",
    "S3Client",
    "TokenStore",
    "ZenodoClient",
    "build_client",
    "describe_datasets",
    "download",
    "download_url",
    "list_datasets",
    "list_files",
    "list_intervals",
    "login",
    "logout",
    "open_dataset",
]
