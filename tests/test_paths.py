from digest.paths import DATA_DIR, ROOT, data_dir


def test_world_name_or_path():
    assert data_dir("dev") == DATA_DIR / "dev"
    assert data_dir("tests/fixtures/mini") == ROOT / "tests" / "fixtures" / "mini"
    assert data_dir(str(ROOT / "data" / "x")) == ROOT / "data" / "x"
