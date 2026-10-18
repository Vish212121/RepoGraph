"""Deterministic, conservative Python import extraction for graph enrichment."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class DependencyCandidate:
    source_path: str
    target_path: str
    import_name: str
    edge_type: str = "python_import"
    confidence: float = 1.0


@dataclass(frozen=True)
class DependencyExtraction:
    dependencies: tuple[DependencyCandidate, ...]
    warnings: tuple[str, ...] = ()


def _module_candidates(module: str, file_paths: set[str]) -> list[str]:
    if not module:
        return []
    base = module.replace(".", "/").strip("/")
    candidates = [f"{base}.py", f"{base}/__init__.py"]
    return [path for path in candidates if path in file_paths]


def _relative_module(source_path: str, module: str, level: int, file_paths: set[str]) -> list[str]:
    source = PurePosixPath(source_path)
    package_parts = list(source.parent.parts)
    if level > 1:
        package_parts = package_parts[: max(0, len(package_parts) - (level - 1))]
    qualified = ".".join([*package_parts, module] if module else package_parts)
    return _module_candidates(qualified, file_paths)


def extract_python_dependencies(source_path: str, source: str, file_paths: set[str]) -> DependencyExtraction:
    """Extract only imports that resolve to files in the same repository snapshot."""

    try:
        tree = ast.parse(source, filename=source_path)
    except SyntaxError as exc:
        return DependencyExtraction((), (f"Could not parse {source_path}: {exc.msg}",))

    dependencies: dict[tuple[str, str], DependencyCandidate] = {}

    def add(module: str, targets: list[str]) -> None:
        for target in targets:
            dependencies.setdefault(
                (source_path, target),
                DependencyCandidate(source_path, target, module),
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, _module_candidates(alias.name, file_paths))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                targets = _relative_module(source_path, module, node.level, file_paths)
            else:
                targets = _module_candidates(module, file_paths)
            if node.level and not module:
                package = ".".join(
                    [*PurePosixPath(source_path).parent.parts[: max(0, len(PurePosixPath(source_path).parent.parts) - (node.level - 1))]]
                )
                for alias in node.names:
                    add(("." * node.level) + alias.name, _module_candidates(f"{package}.{alias.name}", file_paths))
                continue
            if not targets and module:
                source = PurePosixPath(source_path)
                package_parts = list(source.parent.parts)
                if node.level > 1:
                    package_parts = package_parts[: max(0, len(package_parts) - (node.level - 1))]
                relative_prefix = [*package_parts, *module.split(".")]
                for alias in node.names:
                    qualified = ".".join([*relative_prefix, alias.name])
                    candidates = _module_candidates(qualified, file_paths)
                    if candidates:
                        add(qualified, candidates)
            else:
                add(("." * node.level) + module, targets)

    return DependencyExtraction(tuple(dependencies.values()))
