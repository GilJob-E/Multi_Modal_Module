# pyright: reportMissingImports=false
import base64
from pathlib import Path

import pytest

from local_infer.native_media_store import NativeMediaStore


def mp4_b64(label: str, size: int | None = None) -> str:
    payload = f"mp4-{label}".encode()
    if size is not None:
        payload = payload.ljust(size, b"x")
    return base64.b64encode(payload).decode()


def test_native_media_store_keeps_only_max_windows_and_deletes_evicted_file(tmp_path: Path):
    store = NativeMediaStore(
        runtime_dir=tmp_path,
        url_prefix="file:///native-media",
        max_windows_per_session=2,
        max_total_bytes=1000,
    )

    first = store.add_window("s1", 0, 1000, mp4_b64("one"))
    second = store.add_window("s1", 1000, 2000, mp4_b64("two"))
    third = store.add_window("s1", 2000, 3000, mp4_b64("three"))

    recent = store.get_recent_windows("s1")

    assert [window.start_ms for window in recent] == [1000, 2000]
    assert Path(first.host_path).exists() is False
    assert Path(second.host_path).exists() is True
    assert Path(third.host_path).exists() is True
    assert third.file_url == f"file:///native-media/s1/{Path(third.host_path).name}"


def test_native_media_store_total_bytes_eviction_removes_oldest_across_sessions(tmp_path: Path):
    store = NativeMediaStore(
        runtime_dir=tmp_path,
        url_prefix="file:///media",
        max_windows_per_session=10,
        max_total_bytes=20,
        max_window_bytes=20,
    )

    old = store.add_window("s1", 0, 1000, mp4_b64("old", size=9))
    middle = store.add_window("s2", 1000, 2000, mp4_b64("middle", size=9))
    newest = store.add_window("s1", 2000, 3000, mp4_b64("new", size=9))

    assert Path(old.host_path).exists() is False
    assert Path(middle.host_path).exists() is True
    assert Path(newest.host_path).exists() is True
    assert store.get_recent_windows("s1") == [newest]
    assert store.get_recent_windows("s2") == [middle]
    assert store.total_bytes() == middle.size_bytes + newest.size_bytes


def test_native_media_store_duplicate_same_session_eviction_keeps_retained_file(tmp_path: Path):
    store = NativeMediaStore(
        runtime_dir=tmp_path,
        url_prefix="file:///media",
        max_windows_per_session=1,
        max_total_bytes=1000,
    )
    payload = mp4_b64("duplicate")

    evicted = store.add_window("s1", 0, 1000, payload)
    retained = store.add_window("s1", 0, 1000, payload)

    assert evicted.sha256 == retained.sha256
    assert evicted.host_path != retained.host_path
    assert Path(evicted.host_path).exists() is False
    assert Path(retained.host_path).exists() is True
    assert store.get_recent_windows("s1") == [retained]
    assert store.total_bytes() == retained.size_bytes


def test_native_media_store_clear_one_session_keeps_identical_cross_session_file(tmp_path: Path):
    store = NativeMediaStore(
        runtime_dir=tmp_path,
        url_prefix="file:///media",
        max_windows_per_session=3,
        max_total_bytes=1000,
    )
    payload = mp4_b64("duplicate-cross-session")

    cleared = store.add_window("s1", 0, 1000, payload)
    retained = store.add_window("s2", 0, 1000, payload)

    store.clear("s1")

    assert cleared.sha256 == retained.sha256
    assert cleared.host_path != retained.host_path
    assert Path(cleared.host_path).exists() is False
    assert Path(retained.host_path).exists() is True
    assert store.get_recent_windows("s1") == []
    assert store.get_recent_windows("s2") == [retained]
    assert store.total_bytes() == retained.size_bytes


def test_native_media_store_sessions_are_isolated(tmp_path: Path):
    store = NativeMediaStore(tmp_path, "file:///media", max_windows_per_session=1)

    s1 = store.add_window("s1", 0, 1000, mp4_b64("s1"))
    s2 = store.add_window("s2", 0, 1000, mp4_b64("s2"))

    assert store.get_recent_windows("s1") == [s1]
    assert store.get_recent_windows("s2") == [s2]
    assert Path(s1.host_path).parent == tmp_path / "s1"
    assert Path(s2.host_path).parent == tmp_path / "s2"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"video_mp4_base64": "not-base64"}, "valid base64"),
        ({"video_mp4_base64": base64.b64encode(b"").decode()}, "decoded video bytes"),
        ({"mime_type": "video/webm"}, "video/mp4"),
        ({"end_ms": 0}, "greater than start_ms"),
        ({"end_ms": 30001}, "<= 30000"),
        ({"session_id": "../bad"}, "letters, numbers"),
    ],
)
def test_native_media_store_rejects_invalid_inputs(tmp_path: Path, kwargs: dict[str, object], message: str):
    store = NativeMediaStore(tmp_path, "file:///media")
    params = {
        "session_id": "safe-session_1",
        "start_ms": 0,
        "end_ms": 1000,
        "video_mp4_base64": mp4_b64("ok"),
        "mime_type": "video/mp4",
    }
    params.update(kwargs)

    with pytest.raises(ValueError, match=message):
        store.add_window(**params)

    assert list(tmp_path.rglob("*.mp4")) == []


def test_native_media_store_rejects_oversized_decoded_bytes_before_write(tmp_path: Path):
    store = NativeMediaStore(
        runtime_dir=tmp_path,
        url_prefix="file:///media",
        max_window_bytes=4,
        max_total_bytes=100,
    )

    with pytest.raises(ValueError, match="max_window_bytes"):
        store.add_window("s1", 0, 1000, mp4_b64("too-large"))

    assert list(tmp_path.rglob("*")) == []


def test_native_media_store_clear_deletes_files_for_one_session_only(tmp_path: Path):
    store = NativeMediaStore(tmp_path, "file:///media", max_windows_per_session=3)
    s1_first = store.add_window("s1", 0, 1000, mp4_b64("s1-a"))
    s1_second = store.add_window("s1", 1000, 2000, mp4_b64("s1-b"))
    s2 = store.add_window("s2", 0, 1000, mp4_b64("s2"))

    store.clear("s1")

    assert store.get_recent_windows("s1") == []
    assert store.get_recent_windows("s2") == [s2]
    assert Path(s1_first.host_path).exists() is False
    assert Path(s1_second.host_path).exists() is False
    assert Path(s2.host_path).exists() is True
    assert store.total_bytes() == s2.size_bytes


def test_native_media_store_runtime_dir_is_constructor_configured_tmp_path(tmp_path: Path):
    store = NativeMediaStore(tmp_path, "file:///media")

    window = store.add_window("s1", 0, 1000, mp4_b64("ok"))

    assert Path(window.host_path).is_relative_to(tmp_path)
    assert "src" not in Path(window.host_path).parts
    assert "tests" not in Path(window.host_path).parts
    assert "docs" not in Path(window.host_path).parts


def test_native_media_window_is_immutable(tmp_path: Path):
    store = NativeMediaStore(tmp_path, "file:///media")
    window = store.add_window("s1", 0, 1000, mp4_b64("ok"))

    with pytest.raises(Exception):
        window.session_id = "changed"
