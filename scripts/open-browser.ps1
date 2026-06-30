$Url = "http://127.0.0.1:8000/login"
$TimeoutSeconds = 60
$StartedAt = Get-Date

while (((Get-Date) - $StartedAt).TotalSeconds -lt $TimeoutSeconds) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            Start-Process $Url
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

Start-Process $Url
