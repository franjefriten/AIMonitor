from exporters.kafka import _encode_partition_key


def test_partition_key_is_stable_and_bytes():
    first = _encode_partition_key("sample_tool")
    second = _encode_partition_key("sample_tool")

    assert first == second
    assert isinstance(first, bytes)
    assert first
