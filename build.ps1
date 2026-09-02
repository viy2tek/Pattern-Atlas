$ErrorActionPreference = "Stop"

$env:PYTHONPATH = (Join-Path (Get-Location) "src")

python -m nuitka `
    launcher.py `
    --follow-imports `
    --enable-plugin=pyside6 `
    --onefile `
    --windows-console-mode=disable `
    --assume-yes-for-downloads `
    --noinclude-qt-translations `
    --include-qt-plugins=platforminputcontexts `
    --output-dir=dist/nuitka-build `
    --output-filename="Pattern Atlas.exe"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Copy-Item `
    -LiteralPath "dist\nuitka-build\Pattern Atlas.exe" `
    -Destination "dist\Pattern Atlas.exe" `
    -Force
