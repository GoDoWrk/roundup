from __future__ import annotations

import ast
from pathlib import Path


MAX_ALEMBIC_VERSION_NUM_LENGTH = 32


def _literal_assignment(module: ast.Module, name: str) -> str | None:
    for node in module.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


def test_alembic_revision_ids_fit_default_version_table() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    revision_ids: list[str] = []

    for migration_path in sorted(versions_dir.glob("*.py")):
        module = ast.parse(migration_path.read_text(encoding="utf-8"))
        revision = _literal_assignment(module, "revision")
        assert revision, f"{migration_path.name} must define a literal revision id"
        revision_ids.append(revision)
        assert len(revision) <= MAX_ALEMBIC_VERSION_NUM_LENGTH, (
            f"{migration_path.name} revision id {revision!r} is {len(revision)} characters; "
            f"Alembic's default version_num column is {MAX_ALEMBIC_VERSION_NUM_LENGTH} characters."
        )

    assert len(revision_ids) == len(set(revision_ids))


def test_alembic_revisions_form_single_linear_chain() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    revisions: dict[str, str | None] = {}

    for migration_path in sorted(versions_dir.glob("*.py")):
        module = ast.parse(migration_path.read_text(encoding="utf-8"))
        revision = _literal_assignment(module, "revision")
        down_revision = _literal_assignment(module, "down_revision")
        assert revision, f"{migration_path.name} must define a literal revision id"
        revisions[revision] = down_revision

    roots = [revision for revision, parent in revisions.items() if parent is None]
    heads = set(revisions)
    for parent in revisions.values():
        if parent is not None:
            assert parent in revisions, f"down_revision {parent!r} does not match a migration revision"
            heads.discard(parent)

    assert roots == ["0001_initial"]
    assert len(heads) == 1, f"expected a single Alembic head, found {sorted(heads)}"
