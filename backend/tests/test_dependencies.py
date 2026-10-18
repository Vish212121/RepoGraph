from app.ingestion.dependencies import extract_python_dependencies


def test_extracts_absolute_and_relative_imports_that_resolve_inside_snapshot():
    paths = {
        "src/pkg/__init__.py",
        "src/pkg/app.py",
        "src/pkg/sansio/app.py",
        "src/pkg/utils.py",
        "tests/test_app.py",
    }
    source = "from .sansio import app\nfrom . import utils\nimport external_package\n"

    result = extract_python_dependencies("src/pkg/app.py", source, paths)

    assert {item.target_path for item in result.dependencies} == {
        "src/pkg/sansio/app.py",
        "src/pkg/utils.py",
    }
    assert all(item.confidence == 1.0 for item in result.dependencies)


def test_syntax_errors_are_reported_without_failing_enrichment():
    result = extract_python_dependencies("src/pkg/app.py", "def broken(:", {"src/pkg/app.py"})

    assert result.dependencies == ()
    assert result.warnings
