import pytest

from app.services.storage import LocalStorage


@pytest.fixture()
def storage(tmp_path):
    return LocalStorage(root=tmp_path)


def test_save_load_delete_roundtrip(storage):
    storage.save("abc123/data.csv", b"a,b\n1,2\n")
    assert storage.load("abc123/data.csv") == b"a,b\n1,2\n"

    storage.delete("abc123/data.csv")
    with pytest.raises(FileNotFoundError):
        storage.load("abc123/data.csv")


def test_delete_removes_empty_folder(storage, tmp_path):
    storage.save("ds1/f.csv", b"x")
    storage.delete("ds1/f.csv")
    assert not (tmp_path / "ds1").exists()


def test_path_traversal_rejected(storage):
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"nope")


def test_overwrite(storage):
    storage.save("k/f", b"one")
    storage.save("k/f", b"two")
    assert storage.load("k/f") == b"two"
