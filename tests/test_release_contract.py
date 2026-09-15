import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_0_2_1_and_lock_matches():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["version"] == "0.2.1"

    lock = (ROOT / "uv.lock").read_text()
    assert 'name = "rapid7-insightconnect-mcp"\nversion = "0.2.1"' in lock


def test_release_declares_and_packages_mit_license():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["license"] == "MIT"
    assert "LICENSE.md" in project["project"]["license-files"]
    assert "/LICENSE.md" in project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert (ROOT / "LICENSE.md").read_text().startswith("MIT License\n")


def test_readme_primary_install_is_uvx_and_harness_owned():
    readme = (ROOT / "README.md").read_text()
    assert "uvx rapid7-insightconnect-mcp" in readme
    assert "claude mcp add" in readme
    assert "codex mcp add" in readme
    assert "Connect my Rapid7 InsightConnect account" in readme
    assert "rapid7-insightconnect-mcp doctor" in readme
    assert "Do not run `uvx rapid7-insightconnect-mcp` directly in a terminal" in readme
    assert "uvx rapid7-insightconnect-mcp --version" in readme
    assert "package is not currently published on PyPI" not in readme
    assert "prints a configuration example" not in readme
    assert "does **not** save the credential" not in readme


def test_dev_setup_installs_the_dev_extra_everywhere_it_is_required():
    expected = "uv sync --frozen --extra dev"
    assert expected in (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert expected in (ROOT / "README.md").read_text()
    assert expected in (ROOT / "CONTRIBUTING.md").read_text()
    assert expected in (ROOT / "RELEASING.md").read_text()


def test_release_workflow_uses_oidc_and_pinned_pypi_action():
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    assert "release:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "id-token: write" in workflow
    assert "uv build" in workflow
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    assert "password:" not in workflow


def test_release_orchestrator_waits_for_successful_main_ci():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" in workflow
    assert "workflows: [checks]" in workflow
    assert "types: [completed]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.head_sha" in workflow
    assert "push:" not in workflow
    assert "contents: write" in workflow
    assert "actions: write" in workflow
    assert "gh release create" in workflow
    assert "gh workflow run publish.yml" in workflow
    assert '--ref "${TAG}"' in workflow
    assert "v${VERSION}" in workflow
    assert "already released" in workflow
