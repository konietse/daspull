from __future__ import annotations

import os

import requests

from ..client import DatasetClient
from ..datasets import DatasetSpec
from .dataverse import DataverseClient
from .dropbox import DropboxClient
from .globus_auth import PUBDAS_HTTPS_SCOPE, TokenStore
from .huggingface import DEFAULT_REVISION, HuggingFaceClient
from .pando import PandoClient
from .pubdas import PubDASClient
from .s3 import S3Client
from .zenodo import ZenodoClient

#: Access types that require an OAuth login before anything can be read.
LOGIN_REQUIRED_TYPES = frozenset({"globus_https"})


def provider_type(dataset: DatasetSpec) -> str:
    """Return the dataset's ``access.type`` (e.g. ``"zenodo_https"``)."""
    return str(dataset.metadata["access"]["type"])


def requires_login(dataset: DatasetSpec) -> bool:
    """Return whether reading this dataset needs a `daspull login` first."""
    return provider_type(dataset) in LOGIN_REQUIRED_TYPES


def build_client(
    dataset: DatasetSpec,
    *,
    catalog_only: bool = False,
    https_base_url: str | None = None,
    session: requests.Session | None = None,
) -> DatasetClient:
    """Construct the client for *dataset*'s access provider.

    A Dataverse deposit, a Zenodo record, a public S3 bucket, a Pando
    manifest, a Dropbox folder, or a Hugging Face repo is public and needs no
    login; a Globus collection needs a cached or freshly obtained OAuth token.
    """
    access = dataset.metadata["access"]
    kind = access["type"]
    shared = {"session": session} if session is not None else {}

    if kind == "dataverse_https":
        return DataverseClient(
            access["base_url"],
            access["persistent_id"],
            dataset.dataset_root,
            **shared,
        )
    if kind == "zenodo_https":
        return ZenodoClient(
            access["base_url"],
            access["record_id"],
            dataset.dataset_root,
            **shared,
        )
    if kind == "s3_https":
        return S3Client(
            access["base_url"],
            access["prefix"],
            dataset.dataset_root,
            **shared,
        )
    if kind == "huggingface_https":
        return HuggingFaceClient(
            access["base_url"],
            access["repo_id"],
            access["prefix"],
            dataset.dataset_root,
            revision=access.get("revision", DEFAULT_REVISION),
            **shared,
        )
    if kind == "pando_https":
        return PandoClient(
            access["base_url"],
            access["manifest_url"],
            dataset.dataset_root,
            **shared,
        )
    if kind == "dropbox_https":
        return DropboxClient(access["share_url"], dataset.dataset_root, **shared)
    if kind != "globus_https":
        raise ValueError(f"Unsupported access type for dataset {dataset.name}: {kind}")

    store = TokenStore()
    transfer_token = (
        os.environ.get("DASPULL_GLOBUS_TRANSFER_TOKEN") or store.access_token()
    )
    https_token = os.environ.get("DASPULL_GLOBUS_HTTPS_TOKEN")
    if not catalog_only and not https_token:
        https_token = store.access_token_for_scope(PUBDAS_HTTPS_SCOPE)

    return PubDASClient(
        transfer_token,
        https_token=https_token,
        collection_id=access["collection_id"],
        https_base_url=https_base_url or os.environ.get("DASPULL_PUBDAS_HTTPS_URL"),
        **shared,
    )
