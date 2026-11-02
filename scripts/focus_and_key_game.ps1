param([ValidateSet('Space','Enter','Escape','Back')][string]$Key='Space')
if (-not ('TMFocusKeys' -as [type])){
Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
public static class TMFocusKeys {
 [DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")]public static extern bool BringWindowToTop(IntPtr h);
 [DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int cmd);
 [DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("kernel32.dll")]public static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")]public static extern bool AttachThreadInput(uint a,uint b,bool yes);
 [DllImport("user32.dll")]public static extern void keybd_event(byte code,byte scan,uint flags,IntPtr extra);
}
'@
}
$keys=@{Space=0x20;Enter=0x0d;Escape=0x1b;Back=0x08}
$game=(Get-Process Trackmania|Where-Object {$_.MainWindowHandle -ne 0}|Select-Object -First 1)
if(-not $game){throw 'No Trackmania window'}
$h=$game.MainWindowHandle;$f=[TMFocusKeys]::GetForegroundWindow()
$pidTemp=[uint32]0
$fg=[TMFocusKeys]::GetWindowThreadProcessId($f,[ref]$pidTemp)
$gt=[TMFocusKeys]::GetWindowThreadProcessId($h,[ref]$pidTemp)
$self=[TMFocusKeys]::GetCurrentThreadId()
$attachedFg=$false;$attachedGame=$false
try{
 if($fg -ne $self){$attachedFg=[TMFocusKeys]::AttachThreadInput($self,$fg,$true)}
 if($gt -ne $self -and $gt -ne $fg){$attachedGame=[TMFocusKeys]::AttachThreadInput($self,$gt,$true)}
 [TMFocusKeys]::ShowWindow($h,9)|Out-Null
 [TMFocusKeys]::BringWindowToTop($h)|Out-Null
 [TMFocusKeys]::SetForegroundWindow($h)|Out-Null
 if([TMFocusKeys]::GetForegroundWindow() -ne $h){throw 'Could not focus Trackmania'}
 $vk=[byte]$keys[$Key]
 [TMFocusKeys]::keybd_event($vk,0,0,[IntPtr]::Zero)
 Start-Sleep -Milliseconds 120
 [TMFocusKeys]::keybd_event($vk,0,2,[IntPtr]::Zero)
 'SENT_REAL_INPUT_TO_LOCAL_TRACKMANIA '+$Key
}finally{
 if($attachedGame){[TMFocusKeys]::AttachThreadInput($self,$gt,$false)|Out-Null}
 if($attachedFg){[TMFocusKeys]::AttachThreadInput($self,$fg,$false)|Out-Null}
}