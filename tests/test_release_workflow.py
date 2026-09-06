import re
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "build-release.yml"
).read_text(encoding="utf-8")

SEMVER = re.compile(
    r"^\d+\.\d+\.\d+(-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def test_release_tag_policy_accepts_stable_and_prerelease_tags_only():
    assert SEMVER.fullmatch("0.3.2")
    assert SEMVER.fullmatch("0.3.2-beta.1")
    assert SEMVER.fullmatch("0.3.2-sigma.0000067")
    assert not SEMVER.fullmatch("v0.3.2")
    assert not SEMVER.fullmatch("Pattern-Atlas 0.3.2")
    assert not SEMVER.fullmatch("0.3")


def test_workflow_uses_tag_trigger_and_classifies_prereleases():
    assert "tags:" in WORKFLOW
    assert "'[0-9]*.[0-9]*.[0-9]*'" in WORKFLOW
    assert "prerelease: ${{ needs.validate.outputs.is_prerelease }}" in WORKFLOW
    assert "make_latest: ${{ needs.validate.outputs.is_stable }}" in WORKFLOW
    assert "workflow_dispatch:" not in WORKFLOW


def test_workflow_uses_required_gemini_model_and_retry_policy():
    assert "gemini-3.5-flash-lite:generateContent" in WORKFLOW
    assert "for ($attempt = 0; $attempt -le 5; $attempt++)" in WORKFLOW
    assert "Start-Sleep -Seconds 10" in WORKFLOW
    assert "$status -in @(429, 500, 503)" in WORKFLOW
    assert "git diff --binary \"$previousTag...$tag\"" in WORKFLOW


def test_workflow_generates_sha256_checksum_without_code_signing_secrets():
    assert "Generate SHA-256 checksum" in WORKFLOW
    assert "Get-FileHash -LiteralPath $assetPath -Algorithm SHA256" in WORKFLOW
    assert ".sha256" in WORKFLOW
    assert "WINDOWS_SIGNING_CERTIFICATE_BASE64" not in WORKFLOW
    assert "WINDOWS_SIGNING_CERTIFICATE_PASSWORD" not in WORKFLOW


def test_workflow_updates_supported_version_metadata():
    assert "pyproject.toml" in WORKFLOW
    assert "__version__" in WORKFLOW
    assert "package.json" in WORKFLOW
    assert "package-lock.json" in WORKFLOW
    assert "README*.md" in WORKFLOW
    assert "sync version metadata" in WORKFLOW


def test_workflow_archives_ai_notes_in_changelog():
    assert "Archive generated changelog" in WORKFLOW
    assert "docs: archive release notes" in WORKFLOW
    assert "CHANGELOG.md" in WORKFLOW
