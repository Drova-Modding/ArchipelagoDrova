@echo off
REM Wrapper so the Rider run configuration can start the server with one click.
REM -ExecutionPolicy Bypass avoids the machine's PowerShell script policy blocking host_server.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0host_server.ps1" %*
