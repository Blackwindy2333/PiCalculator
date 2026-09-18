import pytest

from pi_tool.common.constants import PI_HEX_FIRST_64
from pi_tool.engine.chudnovsky import SeriesState, terms_for_digits
from pi_tool.engine.decimal import NotEnoughTerms
from pi_tool.engine.verify import bbp_crosscheck, prefix_matches, sha256_file

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_matches_known_value(tmp_path):
    path = tmp_path / "abc.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == ABC_SHA256


def test_sha256_streams_large_file(tmp_path):
    import hashlib

    path = tmp_path / "big.bin"
    payload = bytes(range(256)) * 8192
    path.write_bytes(payload)
    assert sha256_file(path, chunk_size=1024) == hashlib.sha256(payload).hexdigest()


def test_prefix_matches():
    assert prefix_matches("3141592653", "31415")
    assert not prefix_matches("3141592653", "31416")


def test_bbp_crosscheck_ok():
    state = SeriesState()
    state.extend(terms_for_digits(5000))
    expected, got, ok = bbp_crosscheck(state, 0, 64)
    assert ok
    assert expected == got == PI_HEX_FIRST_64


def test_bbp_crosscheck_raises_when_behind():
    state = SeriesState()
    state.extend(10)
    with pytest.raises(NotEnoughTerms):
        bbp_crosscheck(state, 1000, 16)
