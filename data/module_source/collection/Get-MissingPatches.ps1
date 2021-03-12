#Additional priv esc patches should be added to these gloabl arrays.
$server2008Patches = @("KB3161949", "KB3139914", "KB3175024", "KB3139914", "KB3121212", "KB3124280", "KB3159398", "KB3088195")
$server2008r2Patches = @("KB3161949", "KB3139914", "KB3175024", "KB3139852", "KB3121212", "KB3124280", "KB3159398", "KB3088195")
$server2012Patches = @("KB3161949", "KB3139914", "KB3175024", "KB3139914", "KB3121212", "KB3124280", "KB3159398", "KB3088195")
$server2012r2Patches = @("KB3161949", "KB3139914", "KB3175024", "KB3139914", "KB3121212", "KB3124280", "KB3159398", "KB3088195")

function Get-MissingPatches
{
<#
.SYNOPSIS
This script is used to check for missing priv esc patches.
Function: Get-MissingPatches
Author: hackern0v1c3
Required Dependencies: None
Optional Dependencies: None
Version: 1.0

.DESCRIPTION
This script is used to check for missing priv esc patches. It does so by enumerating installed patches, 
detecting the operating system version, then comparing the installed patch list to a static list of priv esc patches 
for the current operating system version.

.EXAMPLE
Get-MissingPatches
Gets known missing priv esc patches and outputs as a string.

.NOTES
This script only checks for specific patches on particular Windows versions.  Additional patches can be easily added for each operating system.
Installed patches enumerated using this method https://gallery.technet.microsoft.com/scriptcenter/PowerShell-script-to-list-0955fe87
#>

    Set-StrictMode -Version 2

    Function Get-Patchlist
    {
        $os = Get-WmiObject Win32_OperatingSystem
    
        switch ($os.Version) 
        { 
            "6.0.6001" {$server2008Patches}
            "6.1.7601" {$server2008r2Patches} 
            "6.2.9200" {$server2012Patches}
            "6.3.9600" {$server2012r2Patches} 
            default {"OS Version "+$os.Version+" not supported by this module."}
        }
    }

    Function Get-MSHotfix 
    { 
        $outputs = Invoke-Expression "wmic qfe list" 
        $outputs = $outputs[1..($outputs.length)] 
        $return = @()
     
        foreach ($output in $Outputs) { 
            if ($output) { 
                $output = $output -replace 'y U','y-U' 
                $output = $output -replace 'NT A','NT-A' 
                $output = $output -replace '\s+',' ' 
                $parts = $output -split ' ' 

                $return += [string]$parts[3]
            } 
        }
        return $return 
    }

    $patchList = Get-Patchlist
    $installedPatches = Get-MSHotfix 

    $missing = Compare-Object $patchList $installedPatches | 
        Where-Object { $_.SideIndicator -eq '<=' } | 
        Foreach-Object { $_.InputObject }

    "Missing Patches: " + $missing
}
