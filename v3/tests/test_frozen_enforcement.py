import sys
from pathlib import Path
from unittest.mock import patch

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
BIN_DIR = V3_DIR / "bin"
sys.path.insert(0, str(BIN_DIR))

import frozen_manifest  # noqa: E402
import rehash_frozen_manifest  # noqa: E402


def _ok_result() -> frozen_manifest.VerifyResult:
    return frozen_manifest.VerifyResult(ok=True)


def _write_fixture_tree(tmp_path: Path, files: dict[str, bytes]) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return tmp_path


def _manifest_for(repo_root: Path) -> str:
    return frozen_manifest.generate_manifest_content(repo_root)


def test_verify_passes_clean_fixture(tmp_path):
    files = {
        "v3/frozen/foo.py": b"print('ok')\n",
        "init.state": b"state-bytes",
    }
    _write_fixture_tree(tmp_path, files)
    (tmp_path / frozen_manifest.MANIFEST_REL).write_text(_manifest_for(tmp_path))

    result = frozen_manifest.verify(tmp_path)
    assert result.ok
    assert not result.hash_mismatches
    assert not result.missing_on_disk
    assert not result.extra_on_disk


def test_verify_tampered_file(tmp_path):
    files = {
        "v3/frozen/foo.py": b"original\n",
        "init.state": b"state-bytes",
    }
    _write_fixture_tree(tmp_path, files)
    (tmp_path / frozen_manifest.MANIFEST_REL).write_text(_manifest_for(tmp_path))

    (tmp_path / "v3/frozen/foo.py").write_bytes(b"tampered\n")
    result = frozen_manifest.verify(tmp_path)

    assert not result.ok
    assert result.hash_mismatches == ["v3/frozen/foo.py"]


def test_verify_listed_but_missing(tmp_path):
    files = {
        "v3/frozen/foo.py": b"original\n",
        "init.state": b"state-bytes",
    }
    _write_fixture_tree(tmp_path, files)
    manifest = _manifest_for(tmp_path)
    (tmp_path / frozen_manifest.MANIFEST_REL).write_text(manifest)
    (tmp_path / "v3/frozen/foo.py").unlink()

    result = frozen_manifest.verify(tmp_path)

    assert not result.ok
    assert result.missing_on_disk == ["v3/frozen/foo.py"]


def test_verify_extra_unlisted_frozen_file(tmp_path):
    files = {
        "v3/frozen/foo.py": b"original\n",
        "init.state": b"state-bytes",
    }
    _write_fixture_tree(tmp_path, files)
    (tmp_path / frozen_manifest.MANIFEST_REL).write_text(_manifest_for(tmp_path))

    (tmp_path / "v3/frozen/extra.py").write_bytes(b"new file\n")
    result = frozen_manifest.verify(tmp_path)

    assert not result.ok
    assert result.extra_on_disk == ["v3/frozen/extra.py"]


def test_protected_paths_excludes_pycache(tmp_path):
    files = {
        "v3/frozen/a.py": b"a\n",
        "v3/frozen/__pycache__/a.cpython-311.pyc": b"pyc\n",
        "v3/frozen/pkg/__pycache__/b.pyc": b"pyc\n",
        "v3/frozen/pkg/b.py": b"b\n",
    }
    _write_fixture_tree(tmp_path, files)

    paths = frozen_manifest.protected_paths(tmp_path)
    assert paths == ["v3/frozen/a.py", "v3/frozen/pkg/b.py"]


def test_rehash_refuses_dirty_protected(tmp_path):
    with patch.object(rehash_frozen_manifest, "dirty_protected_paths", return_value=["v3/frozen/foo.py"]):
        rc = rehash_frozen_manifest.main(["--repo-root", str(tmp_path)])
    assert rc == 1


def test_offending_staged_only_editable():
    assert frozen_manifest.offending_staged_paths(["v3/train.py"]) == []


def test_offending_staged_frozen_modify():
    assert frozen_manifest.offending_staged_paths(["v3/frozen/ram_map.py"]) == [
        "v3/frozen/ram_map.py"
    ]


def test_offending_staged_manifest():
    assert frozen_manifest.offending_staged_paths(["v3/frozen_manifest.sha256"]) == [
        "v3/frozen_manifest.sha256"
    ]


def test_offending_staged_frozen_delete():
    assert frozen_manifest.offending_staged_paths(["v3/frozen/scorer/core.py"]) == [
        "v3/frozen/scorer/core.py"
    ]


def test_manifest_line_format(tmp_path):
    files = {"v3/frozen/z.py": b"z\n", "v3/frozen/a.py": b"a\n"}
    _write_fixture_tree(tmp_path, files)
    content = frozen_manifest.generate_manifest_content(tmp_path)
    lines = content.strip().splitlines()
    assert lines == sorted(lines, key=lambda line: line.split("  ", 1)[1])
    for line in lines:
        digest, rel = line.split("  ", 1)
        assert len(digest) == 64
        assert rel.startswith("v3/frozen/")


def test_parse_manifest_rejects_bad_lines():
    with pytest.raises(ValueError, match="malformed"):
        frozen_manifest.parse_manifest("not-a-valid-line\n")


def test_manifest_diff_reports_changes():
    old = {"a": "1", "b": "2"}
    new = {"a": "1", "b": "3", "c": "4"}
    added, removed, changed = frozen_manifest.manifest_diff(old, new)
    assert added == ["c"]
    assert removed == []
    assert changed == ["b"]


def test_staged_paths_passes_no_renames(tmp_path):
    with patch.object(frozen_manifest.subprocess, "check_output", return_value="") as mock_co:
        frozen_manifest.staged_paths(tmp_path)
    cmd = mock_co.call_args[0][0]
    assert "--no-renames" in cmd


def test_run_pre_commit_blocks_frozen(tmp_path):
    with patch.object(frozen_manifest, "staged_paths", return_value=["v3/frozen/ram_map.py"]):
        rc = frozen_manifest.run_pre_commit(tmp_path)
    assert rc == 1


def test_run_pre_commit_allows_editable(tmp_path):
    with patch.object(frozen_manifest, "staged_paths", return_value=["v3/train.py"]):
        rc = frozen_manifest.run_pre_commit(tmp_path)
    assert rc == 0


def test_rehash_writes_manifest_on_clean_tree(tmp_path):
    files = {
        "v3/frozen/foo.py": b"content\n",
        "init.state": b"state\n",
    }
    _write_fixture_tree(tmp_path, files)
    with patch.object(rehash_frozen_manifest, "dirty_protected_paths", return_value=[]):
        rc = rehash_frozen_manifest.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    manifest_path = tmp_path / frozen_manifest.MANIFEST_REL
    assert manifest_path.is_file()
    result = frozen_manifest.verify(tmp_path)
    assert result.ok
