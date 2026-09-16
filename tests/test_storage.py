import hashlib
from pathlib import Path
import pytest
from backend.services.storage import LocalStorageProvider, compute_sha256, get_storage_provider


def test_compute_sha256():
    data = b"hello world dynamic pricing engine"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(data) == expected


def test_local_storage_save_and_load(tmp_path: Path):
    provider = LocalStorageProvider(base_dir=tmp_path)
    content = b"date,sku,price,units_sold\n2025-01-01,SKU-A,15.99,10"
    destination = "retailer-123/dataset-abc.csv"

    saved_path = provider.save(content, destination)
    assert Path(saved_path).exists()
    assert Path(saved_path).read_bytes() == content

    # Load via relative path
    loaded = provider.load(destination)
    assert loaded == content

    # Load via absolute path
    loaded_abs = provider.load(saved_path)
    assert loaded_abs == content


def test_get_storage_provider_default():
    provider = get_storage_provider()
    assert isinstance(provider, LocalStorageProvider)
