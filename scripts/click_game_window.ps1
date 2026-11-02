param([Parameter(Mandatory)][int]$X,[Parameter(Mandatory)][int]$Y)
if (-not ('TMClick' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TMClick {
 [DllImport("user32.dll")]public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
}
'@
}
$proc=Get-Process Trackmania -ErrorAction Stop|Where-Object {$_.MainWindowHandle -ne 0}|Select-Object -First 1
if(-not $proc){throw 'Trackmania GUI not found'}
if($X -lt 0 -or $X -ge 1920 -or $Y -lt 0 -or $Y -ge 1080){throw 'Out of window coords'}
$coord=[IntPtr](($Y -shl 16) -bor ($X -band 65535))
[TMClick]::PostMessage($proc.MainWindowHandle,0x0200,[IntPtr]0,$coord)|Out-Null
[TMClick]::PostMessage($proc.MainWindowHandle,0x0201,[IntPtr]1,$coord)|Out-Null
Start-Sleep -Milliseconds 110
[TMClick]::PostMessage($proc.MainWindowHandle,0x0202,[IntPtr]0,$coord)|Out-Null
"Clicked Trackmania GUI at $X,$Y"