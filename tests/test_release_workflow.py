import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
PR_VALIDATION_WORKFLOW = WORKFLOWS / "pr-validation.yml"
RELEASE_CONFIG = ROOT / "release-please-config.json"
RELEASE_MANIFEST = ROOT / ".release-please-manifest.json"
AGENT_POLICY = ROOT / "AGENTS.md"
VERSION_MODULE = ROOT / "src" / "fl_midi_batch_exporter" / "__init__.py"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def test_release_please_owns_pre_1_0_versioning_and_changelog():
    config = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))

    assert config["release-type"] == "python"
    assert config["bump-minor-pre-major"] is True
    assert config["bump-patch-for-minor-pre-major"] is True
    assert config["include-v-in-tag"] is True
    assert config["include-component-in-tag"] is False
    assert config["draft"] is True
    assert config["force-tag-creation"] is True
    assert config["packages"]["."]["extra-files"] == [
        "src/fl_midi_batch_exporter/__init__.py"
    ]
    assert set(manifest) == {"."}
    assert re.fullmatch(r"0\.\d+\.\d+", manifest["."])

    visible_types = {
        section["type"]
        for section in config["changelog-sections"]
        if not section.get("hidden", False)
    }
    assert {"feat", "fix", "perf", "refactor", "docs", "build", "ci", "chore"} <= visible_types


def test_release_workflow_uses_one_serial_release_please_pipeline():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "branches:\n      - master" in workflow
    assert "workflow_dispatch:" in workflow
    assert "group: release-master" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "googleapis/release-please-action@" in workflow
    assert "config-file: release-please-config.json" in workflow
    assert "manifest-file: .release-please-manifest.json" in workflow
    assert "release_created: ${{ steps.release.outputs.release_created }}" in workflow
    assert "tag_name: ${{ steps.release.outputs.tag_name }}" in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "git push origin" not in workflow


def test_release_build_is_gated_and_publishes_only_after_assets_exist():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    build = workflow.index("python -m pytest")
    package = workflow.index(r".\build.ps1")
    upload = workflow.index("gh release upload")
    publish = workflow.index("gh release edit")

    assert "if: needs.release.outputs.release_created == 'true'" in workflow
    assert "python -m ruff check ." in workflow
    assert "Verify release version metadata" in workflow
    assert "importlib.metadata.version('pattern-atlas')" in workflow
    assert "fl_midi_batch_exporter.__version__" in workflow
    assert build < package < upload < publish
    assert "--clobber" in workflow
    assert "for ($attempt = 1; $attempt -le 3; $attempt++)" in workflow
    assert "Start-Sleep -Seconds (5 * $attempt)" in workflow
    assert "--draft=false" in workflow
    assert "isDraft" in workflow
    assert ".sha256" in workflow


def test_pull_requests_require_conventional_titles_and_a_description():
    workflow = PR_VALIDATION_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "PR_TITLE: ${{ github.event.pull_request.title }}" in workflow
    assert "PR_BODY: ${{ github.event.pull_request.body }}" in workflow
    assert "feat|fix|perf|refactor|docs|build|ci|chore|test|style|revert" in workflow
    assert "$env:PR_TITLE -cnotmatch $titlePattern" in workflow
    assert "Pull request description is required" in workflow


def test_release_policy_prevents_manual_versions_tags_releases_and_changelog_edits():
    policy = AGENT_POLICY.read_text(encoding="utf-8").lower()

    assert "release please" in policy
    assert "do not manually change" in policy
    assert "do not create or move git tags" in policy
    assert "do not create or publish github releases" in policy
    assert "do not edit `changelog.md`" in policy
    assert "conventional commit" in policy


def test_python_version_module_is_managed_as_an_extra_release_file():
    version_module = VERSION_MODULE.read_text(encoding="utf-8")

    assert "x-release-please-version" in version_module


def test_download_documentation_matches_versioned_release_assets():
    readme = README.read_text(encoding="utf-8")
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "Pattern-Atlas-X.Y.Z-Windows-x64.exe" in readme
    assert '$assetName = "Pattern-Atlas-$env:RELEASE_VERSION-Windows-x64.exe"' in workflow
    assert "name: Pattern-Atlas-${{ needs.release.outputs.version }}-Windows-x64" in workflow


def test_changelog_documents_its_release_please_source():
    changelog = CHANGELOG.read_text(encoding="utf-8")

    assert "Release Please" in changelog
    assert "signed commits" not in changelog


def test_all_reusable_actions_are_pinned_to_full_commit_shas():
    action_reference = re.compile(r"^[ \t]*-[ \t]+uses:[ \t]+[^@\s]+@([^\s#]+)", re.MULTILINE)

    for workflow_path in WORKFLOWS.glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        references = action_reference.findall(workflow)
        assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in references), workflow_path
