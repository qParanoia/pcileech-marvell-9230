# SPDX-License-Identifier: MIT
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$build = Join-Path $repo 'build'
$archive = Join-Path $build 'arm-gnu-toolchain-15.2.rel1.zip'
$toolchain = Join-Path $build 'toolchain'
$compiler = Join-Path $toolchain 'bin\arm-none-eabi-gcc.exe'
$url = 'https://armkeil.blob.core.windows.net/developer/files/downloads/gnu/15.2.rel1/binrel/arm-gnu-toolchain-15.2.rel1-mingw-w64-x86_64-arm-none-eabi.zip'
$expectedSha256 = '7936CAC895611023FFB22A64B8E426098C7104CB689778C1894572CA840B9ECE'

New-Item -ItemType Directory -Force -Path $build | Out-Null
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri $url -OutFile $archive
}
$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($actualSha256 -ne $expectedSha256) {
    throw "Toolchain archive SHA-256 mismatch: $actualSha256"
}
if (-not (Test-Path -LiteralPath $compiler)) {
    Expand-Archive -LiteralPath $archive -DestinationPath $toolchain -Force
}
& $compiler --version | Select-Object -First 1
