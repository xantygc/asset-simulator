"""Test version information."""

from asset_simulator import __version__


def test_version() -> None:
    """Test that version is set correctly."""
    assert __version__ == "0.1.0"
