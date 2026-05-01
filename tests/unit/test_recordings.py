import os


def test_path_sanitization_traversal():
    safe = os.path.basename("../../etc/passwd")
    assert safe == "passwd"


def test_path_sanitization_normal():
    safe = os.path.basename("/recordings/sector-test_1234567890.mp4")
    assert safe == "sector-test_1234567890.mp4"


def test_path_sanitization_nested():
    safe = os.path.basename("/recordings/subdir/file.mp4")
    assert safe == "file.mp4"
