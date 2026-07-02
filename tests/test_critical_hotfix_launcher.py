from pathlib import Path


def test_run_oko_skips_pip_install_when_hash_unchanged():
    source = Path("run_oko.sh").read_text(encoding="utf-8")
    assert ".oko_requirements_sha256" in source
    assert "Зависимости уже установлены, пропускаю pip install." in source
    assert "pip install --upgrade pip" not in source
    assert "--repair" in source and "--install-deps" in source
