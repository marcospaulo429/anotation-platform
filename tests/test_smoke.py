"""Smoke test: package is importable after install."""


def test_package_importable() -> None:
    import annotation_platform

    assert annotation_platform.__version__ == "0.1.0"


def test_subpackages_importable() -> None:
    import annotation_platform.api  # noqa: F401
    import annotation_platform.contracts  # noqa: F401
    import annotation_platform.engine  # noqa: F401
