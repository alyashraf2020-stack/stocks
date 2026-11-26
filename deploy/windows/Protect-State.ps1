param([Parameter(Mandatory)][string]$Path)
$ErrorActionPreference = "Stop"
$item = Get-Item -LiteralPath $Path -Force
if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "EGX storage must be a normal directory on a private local NTFS volume."
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
$desktop = $PSVersionTable.PSEdition -eq "Desktop"
$acl = if ($desktop) { $item.GetAccessControl() } else { [IO.FileSystemAclExtensions]::GetAccessControl($item) }
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in $acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier])) {
    $acl.RemoveAccessRuleSpecific($rule)
}
foreach ($sid in @($identity, $system)) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $sid, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"
    ))
}
if ($desktop) { $item.SetAccessControl($acl) } else { [IO.FileSystemAclExtensions]::SetAccessControl($item, $acl) }
