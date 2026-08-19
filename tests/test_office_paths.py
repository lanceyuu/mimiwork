"""Root-aware path resolution shared by every Office tool.

Office tools take a model-supplied path, so they are a workspace-escape surface. The rule
must be identical across docx/xlsx/pptx, which is why it lives in one resolver.
"""

import pytest

from coworker.roots import RootDir
from coworker.tools.office.paths import PathError, resolve_read, resolve_write


@pytest.fixture
def roots(tmp_path):
    primary = tmp_path / "scratch"
    primary.mkdir()
    reference = tmp_path / "reference"
    reference.mkdir()
    return [
        RootDir(path=primary, writable=True),
        RootDir(path=reference, writable=False),
    ]


def test_relative_path_resolves_against_primary_root(roots):
    assert resolve_write("out.docx", roots) == roots[0].path / "out.docx"


def test_relative_path_with_subdir_stays_under_primary(roots):
    assert resolve_write("sub/out.docx", roots) == roots[0].path / "sub" / "out.docx"


def test_absolute_path_inside_a_root_is_allowed(roots):
    target = roots[1].path / "source.xlsx"
    target.write_text("x")
    assert resolve_read(str(target), roots) == target


def test_absolute_path_outside_every_root_is_rejected(roots, tmp_path):
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("secret")
    with pytest.raises(PathError):
        resolve_read(str(outside), roots)


def test_traversal_escape_is_rejected(roots):
    with pytest.raises(PathError):
        resolve_read("../../etc/passwd", roots)


def test_write_into_readonly_root_is_rejected(roots):
    target = roots[1].path / "out.docx"
    with pytest.raises(PathError) as exc:
        resolve_write(str(target), roots)
    assert "read-only" in str(exc.value)


def test_read_from_readonly_root_is_allowed(roots):
    target = roots[1].path / "source.docx"
    target.write_text("x")
    assert resolve_read(str(target), roots) == target


def test_symlink_out_of_the_workspace_is_rejected(roots, tmp_path):
    """resolve() before containment, so a symlink can't be used as a side door."""
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = roots[0].path / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(PathError):
        resolve_read("link.txt", roots)


def test_empty_path_is_rejected(roots):
    with pytest.raises(PathError):
        resolve_read("   ", roots)


def test_no_roots_configured_is_rejected(roots):
    with pytest.raises(PathError):
        resolve_read("out.docx", [])


def test_single_root_fallback_accepts_a_bare_path(tmp_path):
    """A plain workspace (no multi-root session) still resolves."""
    ws = tmp_path / "ws"
    ws.mkdir()
    roots = [RootDir(path=ws, writable=True)]
    assert resolve_write("deck.pptx", roots) == ws / "deck.pptx"


def test_write_creates_no_directories_implicitly(roots):
    """Resolution is pure: it must not touch the filesystem."""
    resolved = resolve_write("nested/deep/out.docx", roots)
    assert not resolved.parent.exists()
