# Commercial Submission AI - Command Line Tester
# Simple PowerShell script to test API endpoints

$BaseUrl = "http://localhost:8000"

function Test-APIHealth {
    Write-Host "`n=== Testing Health Endpoint ===" -ForegroundColor Cyan
    $response = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    Write-Host "Status: " -NoNewline
    Write-Host "OK" -ForegroundColor Green
    Write-Host "Version: $($response.data.version)"
    Write-Host "Database: $($response.data.database)"
    Write-Host "LLM Model: $($response.data.llm_model)"
    Write-Host "LLM Configured: $($response.data.llm_configured)"
}

function Get-APIEndpoints {
    Write-Host "`n=== Available API Endpoints ===" -ForegroundColor Cyan
    $schema = Invoke-RestMethod -Uri "$BaseUrl/openapi.json" -Method Get
    Write-Host "API Title: $($schema.info.title)"
    Write-Host "Version: $($schema.info.version)"
    Write-Host "`nEndpoints ($($schema.paths.Count) total):"
    $schema.paths.PSObject.Properties.Name | Sort-Object | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Yellow
    }
}

function Show-Menu {
    Write-Host "`n╔═══════════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "║  Commercial Submission AI - API Tester       ║" -ForegroundColor Magenta
    Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Magenta
    Write-Host "`n1. Test Health Endpoint"
    Write-Host "2. List All Endpoints"
    Write-Host "3. View OpenAPI Schema"
    Write-Host "4. Open Swagger UI in Browser"
    Write-Host "5. Open ReDoc in Browser"
    Write-Host "6. Open Custom API Explorer"
    Write-Host "Q. Quit"
    Write-Host ""
}

# Main loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Select an option"
    
    switch ($choice) {
        "1" { Test-APIHealth }
        "2" { Get-APIEndpoints }
        "3" { 
            $schema = Invoke-RestMethod -Uri "$BaseUrl/openapi.json"
            $schema | ConvertTo-Json -Depth 10 | Out-File -FilePath "openapi_schema.json"
            Write-Host "`nSchema saved to: openapi_schema.json" -ForegroundColor Green
            code openapi_schema.json
        }
        "4" { Start-Process "http://localhost:8000/docs" }
        "5" { Start-Process "http://localhost:8000/redoc" }
        "6" { Start-Process "scripts\api_explorer.html" }
        "Q" { Write-Host "`nGoodbye!" -ForegroundColor Cyan; exit }
        default { Write-Host "`nInvalid option. Please try again." -ForegroundColor Red }
    }
    
    Write-Host "`nPress any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    Clear-Host
}
