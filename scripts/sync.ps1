# Windows version of scripts/sync.sh: share $LEXHACK_DATA through Cloudflare R2 (rclone). Copies only; never deletes.
#
#   .\scripts\sync.ps1 pull
#   .\scripts\sync.ps1 push
#   .\scripts\sync.ps1 push --dry-run
#
# Safe both ways (caches are named by content hash). Don't sync while a pipeline job is running.
# raw/frontier.db is never synced from here: only the person who crawls pushes it (sync.sh --with-frontier).
param([Parameter(Mandatory=$true)][ValidateSet("push","pull")][string]$Direction, [Parameter(ValueFromRemainingArguments=$true)]$Extra)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not $env:LEXHACK_DATA -and (Test-Path .env)) {
  $line = Select-String -Path .env -Pattern '^LEXHACK_DATA=' | Select-Object -First 1
  if ($line) { $env:LEXHACK_DATA = $line.Line.Split("=", 2)[1].Trim('"') }
}
if (-not $env:LEXHACK_DATA) { throw "LEXHACK_DATA not set (in .env or the environment)" }
$remote = if ($env:LEXHACK_R2) { $env:LEXHACK_R2 } else { "lexhack-data:lexhack-data" }
$flags = @("--checksum","--transfers","16","--checkers","32","--fast-list","--progress",
           "--exclude","raw/frontier.db*","--exclude","*.pid","--exclude","raw/STOPPED.txt",
           "--exclude","raw/*.out","--exclude","raw/*.log","--exclude",".DS_Store") + $Extra
if ($Direction -eq "push") { rclone copy $env:LEXHACK_DATA $remote @flags }
else { rclone copy $remote $env:LEXHACK_DATA @flags }
