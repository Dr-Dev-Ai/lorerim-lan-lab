param([Parameter(Mandatory=$true)][string]$Peer, [int]$Samples=100, [string]$Output='lan-rtt.csv')
$ErrorActionPreference = 'Stop'
if ($Samples -lt 1 -or $Samples -gt 10000) { throw 'Samples must be 1..10000' }
$ping = [System.Net.NetworkInformation.Ping]::new()
$rows = for($i=0; $i -lt $Samples; $i++) {
    $stamp = (Get-Date).ToUniversalTime().ToString('o')
    try {
        $reply = $ping.Send($Peer,1000)
        if ($reply.Status -eq 'Success') {
            [pscustomobject]@{timestamp=$stamp;metric='icmp_rtt';unit='ms';value=$reply.RoundtripTime;status='Success'}
        } else {
            [pscustomobject]@{timestamp=$stamp;metric='icmp_timeout';unit='count';value=1;status=$reply.Status}
        }
    } catch {
        [pscustomobject]@{timestamp=$stamp;metric='icmp_error';unit='count';value=1;status=$_.Exception.Message}
    }
    Start-Sleep -Milliseconds 200
}
$ping.Dispose()
$rows | Export-Csv -LiteralPath $Output -NoTypeInformation
Write-Output "Saved ICMP measurements to $Output. These are not game latency, frame time, or synchronization measurements."
