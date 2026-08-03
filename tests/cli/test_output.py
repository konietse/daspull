from daspull.cli.output import _format_size


def test_format_size_uses_decimal_units_below_a_terabyte():
    assert _format_size(500) == "500 B"
    assert _format_size(1_500) == "1.5 KB"
    assert _format_size(2_500_000) == "2.5 MB"
    assert _format_size(42_750_000_000) == "42.75 GB"


def test_format_size_shows_gb_alongside_once_it_reaches_a_terabyte():
    # Most datasets here are TB-scale; a bare TB figure used to always show
    # as base-1024 TiB, which this asserts against by checking for decimal GB.
    assert _format_size(5_470_000_000_000) == "5.47 TB (5,470.0 GB)"
