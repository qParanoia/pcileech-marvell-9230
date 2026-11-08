param(
    [string]$ToolchainRoot = "",
    [string]$CygwinBin = ""
)

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Workspace = (Resolve-Path (Join-Path $Project "..\..")).Path

if (-not $ToolchainRoot) {
    $ToolchainRoot = Join-Path $Workspace "work\ch568_archive\toolchain_media\nds_toolchain\files\nds32le-elf-mculib-v3m"
}
if (-not $CygwinBin) {
    $CygwinBin = Join-Path $Workspace "work\ch568_archive\toolchain_media\resource_extract\cygwin\cygwin\bin"
}

$ToolchainRoot = (Resolve-Path $ToolchainRoot).Path
$CygwinBin = (Resolve-Path $CygwinBin).Path
$ToolBin = Join-Path $ToolchainRoot "bin"
$TargetBin = Join-Path $ToolchainRoot "nds32le-elf\bin"
$Gcc = Join-Path $ToolBin "nds32le-elf-gcc.exe"

# The vendor package stores these as Cygwin symlinks.  A normal Windows unzip
# often materializes them as zero-byte files; replace only those placeholders.
$ToolAliases = @{
    "as.exe" = "nds32le-elf-as.exe"
    "ar.exe" = "nds32le-elf-ar.exe"
    "ld.exe" = "nds32le-elf-ld.bfd.exe"
    "ld.bfd.exe" = "nds32le-elf-ld.bfd.exe"
    "nm.exe" = "nds32le-elf-nm.exe"
    "objcopy.exe" = "nds32le-elf-objcopy.exe"
    "objdump.exe" = "nds32le-elf-objdump.exe"
    "ranlib.exe" = "nds32le-elf-ranlib.exe"
    "strip.exe" = "nds32le-elf-strip.exe"
}
foreach ($Alias in $ToolAliases.Keys) {
    $Destination = Join-Path $TargetBin $Alias
    if ((Get-Item -LiteralPath $Destination).Length -eq 0) {
        Remove-Item -LiteralPath $Destination
        Copy-Item -LiteralPath (Join-Path $ToolBin $ToolAliases[$Alias]) -Destination $Destination
    }
}

$GccVersionRoot = Join-Path $ToolchainRoot "lib\gcc\nds32le-elf"
$GccVersion = Get-ChildItem -LiteralPath $GccVersionRoot -Directory |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $GccVersion) { throw "GCC runtime libraries were not found under $GccVersionRoot" }
$GccLib = $GccVersion.FullName
$LargeMvhGcc = Join-Path $GccLib "mcmodel-large\mvh"
foreach ($Pair in @(
    @("mcmodel-large\libgcc.a", "mcmodel-large\mvh\libgcc.a"),
    @("libnds32_isr.a", "mcmodel-large\mvh\libnds32_isr.a")
)) {
    $Destination = Join-Path $GccLib $Pair[1]
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -eq 0) {
        Remove-Item -LiteralPath $Destination
        Copy-Item -LiteralPath (Join-Path $GccLib $Pair[0]) -Destination $Destination
    }
}

$TargetLib = Join-Path $ToolchainRoot "nds32le-elf\lib\mcmodel-large"
$TargetMvh = Join-Path $TargetLib "mvh"
foreach ($Name in @("libdsp.a", "libm.a", "libnosys.a", "libssp_nonshared.a", "libssp.a", "libstdc++.a", "libsupc++.a")) {
    $Destination = Join-Path $TargetMvh $Name
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -eq 0) {
        Remove-Item -LiteralPath $Destination
        Copy-Item -LiteralPath (Join-Path $TargetLib $Name) -Destination $Destination
    }
}
$DebugLibrary = Join-Path $TargetMvh "libg.a"
if ((Test-Path -LiteralPath $DebugLibrary) -and (Get-Item -LiteralPath $DebugLibrary).Length -eq 0) {
    Remove-Item -LiteralPath $DebugLibrary
    Copy-Item -LiteralPath (Join-Path $TargetMvh "libc.a") -Destination $DebugLibrary
}

$env:PATH = "$CygwinBin;$ToolBin;$env:PATH"
$Build = Join-Path $Project "build"
New-Item -ItemType Directory -Force $Build | Out-Null
Get-ChildItem -LiteralPath $Build -Filter "*.o" -File | Remove-Item

$Includes = @(
    "-I$(Join-Path $Project 'src\sys')",
    "-I$(Join-Path $Project 'src\driver')",
    "-I$(Join-Path $Project 'src\main')"
)
$Objects = @()
foreach ($Source in Get-ChildItem -Recurse -File (Join-Path $Project "src") -Filter "*.c") {
    $Object = Join-Path $Build ($Source.BaseName + ".o")
    & $Gcc -Os1 -mcmodel=large -mcpu=n801 -Wall -fno-strict-aliasing @Includes -c $Source.FullName -o $Object
    if ($LASTEXITCODE -ne 0) { throw "compile failed: $($Source.FullName)" }
    $Objects += $Object
}

$Adx = Join-Path $Build "ch568_sata_mailbox.adx"
$Binary = Join-Path $Build "ch568_sata_mailbox.bin"
$Map = Join-Path $Build "ch568_sata_mailbox.map"
$Disassembly = Join-Path $Build "ch568_sata_mailbox.disasm.txt"
$MapArg = "-Wl,-Map,$Map"
& $Gcc -Os1 -nostartfiles -static -mcmodel=large -T (Join-Path $Project "CH56x.ld") -mvh $MapArg -o $Adx @Objects -lnds32_isr
if ($LASTEXITCODE -ne 0) { throw "link failed" }

& (Join-Path $ToolBin "nds32le-elf-objcopy.exe") -O binary $Adx $Binary
& (Join-Path $ToolBin "nds32le-elf-objdump.exe") -d -S $Adx | Set-Content -Encoding ascii $Disassembly
& (Join-Path $ToolBin "nds32le-elf-size.exe") $Adx
Get-FileHash -Algorithm SHA256 $Binary
