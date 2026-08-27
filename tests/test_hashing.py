"""Tests for content hashing."""

from __future__ import annotations

from pathlib import Path

from frp.hashing import hash_bytes, hash_file, hash_json


def test_same_bytes_same_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"hello world")
    b.write_bytes(b"hello world")
    assert hash_file(a) == hash_file(b)


def test_changed_bytes_different_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"hello world")
    b.write_bytes(b"hello world!")
    assert hash_file(a) != hash_file(b)


def test_known_sha256_vector() -> None:
    # SHA-256("abc")
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hash_bytes(b"abc") == expected


def test_hash_json_is_order_independent() -> None:
    assert hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})