$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $ProjectRoot "apps\web")

npm.cmd run dev -- --host 127.0.0.1 --port 5173
