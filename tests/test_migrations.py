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


def _migration_modules() -> list[tuple[Path, ast.Module]]:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    return [
        (migration_path, ast.parse(migration_path.read_text(encoding="utf-8")))
        for migration_path in sorted(versions_dir.glob("*.py"))
    ]


def test_alembic_revision_ids_fit_default_version_table() -> None:
    revision_ids: list[str] = []

    for migration_path, module in _migration_modules():
        revision = _literal_assignment(module, "revision")
        down_revision = _literal_assignment(module, "down_revision")
        assert revision, f"{migration_path.name} must define a literal revision id"
        revision_ids.append(revision)
        assert len(revision) <= MAX_ALEMBIC_VERSION_NUM_LENGTH, (
            f"{migration_path.name} revision id {revision!r} is {len(revision)} characters; "
            f"Alembic's default version_num column is {MAX_ALEMBIC_VERSION_NUM_LENGTH} characters."
        )
        filename_revision_prefix = migration_path.stem.split("_", 1)[0]
        revision_prefix = revision.split("_", 1)[0]
        assert filename_revision_prefix == revision_prefix, (
            f"{migration_path.name} numeric prefix {filename_revision_prefix!r} must match "
            f"revision id prefix {revision_prefix!r}."
        )
        if down_revision is not None:
            assert len(down_revision) <= MAX_ALEMBIC_VERSION_NUM_LENGTH, (
                f"{migration_path.name} down_revision {down_revision!r} is {len(down_revision)} characters; "
                f"Alembic's default version_num column is {MAX_ALEMBIC_VERSION_NUM_LENGTH} characters."
            )

    assert len(revision_ids) == len(set(revision_ids))


def test_alembic_revisions_form_single_linear_chain() -> None:
    revisions: dict[str, str | None] = {}

    for migration_path, module in _migration_modules():
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


def test_alembic_migrations_do_not_import_application_services() -> None:
    for migration_path, module in _migration_modules():
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                raise AssertionError(
                    f"{migration_path.name} imports {node.module!r}; migrations must freeze helper logic "
                    "instead of depending on mutable app modules."
                )
            if isinstance(node, ast.Import):
                imported_names = [alias.name for alias in node.names]
                app_imports = [name for name in imported_names if name == "app" or name.startswith("app.")]
                assert not app_imports, (
                    f"{migration_path.name} imports {app_imports!r}; migrations must not depend on app modules."
                )
