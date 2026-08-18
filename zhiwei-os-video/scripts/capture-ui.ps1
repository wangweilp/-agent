param(
    [string]$Session = "zhiwei-record",
    [string]$BaseUrl = "http://127.0.0.1:3000"
)

$ErrorActionPreference = "Stop"

$frontendRoot = "D:\dma\day2\frontend"
$outputRoot = "D:\dma\day2\zhiwei-os-video\public\ui"
$playwright = @(
    "--yes",
    "--package",
    "@playwright/cli",
    "playwright-cli",
    "-s=$Session"
)

$routes = [ordered]@{
    "home" = "/home"
    "memory-console" = "/memory-console"
    "memory" = "/memory"
    "reflection" = "/reflection"
    "graph" = "/graph"
    "causal-kernel" = "/causal-kernel"
    "causal-graph" = "/causal-graph"
    "timeline" = "/timeline"
    "observability" = "/dashboard-v2"
    "runtime-control" = "/runtime"
    "runtime-admin" = "/admin/runtime"
    "enterprise-dashboard" = "/admin"
    "organization" = "/admin/organization"
    "users" = "/admin/users"
    "audit" = "/admin/audit"
    "policy" = "/admin/policy"
    "deployment" = "/admin/deployment"
    "developer-docs" = "/docs"
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

Push-Location $frontendRoot
try {
    foreach ($entry in $routes.GetEnumerator()) {
        & npx @playwright goto "$BaseUrl$($entry.Value)" | Out-Null
        & npx @playwright snapshot | Out-Null
        & npx @playwright run-code "await page.addStyleTag({content:'nextjs-portal{display:none!important}'})" | Out-Null

        $result = (& npx @playwright screenshot | Out-String)
        $match = [regex]::Match(
            $result,
            '\[Screenshot of viewport\]\(([^)]+)\)'
        )
        if (-not $match.Success) {
            throw "Could not determine screenshot path for $($entry.Key)."
        }

        $source = Join-Path $frontendRoot $match.Groups[1].Value
        $destination = Join-Path $outputRoot "$($entry.Key).png"
        Copy-Item -LiteralPath $source -Destination $destination -Force
        Write-Output "Captured $($entry.Key) -> $destination"
    }
}
finally {
    Pop-Location
}
