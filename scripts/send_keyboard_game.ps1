param([ValidateSet('Space','Enter','Up')][string]$Key='Space')
if(-not('TMSendScan' -as [type])){
Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential)]public struct NativeInput{public uint type;public NativeInputUnion u;}
[StructLayout(LayoutKind.Explicit)]public struct NativeInputUnion{[FieldOffset(0)]public NativeKeyboard keyboard;[FieldOffset(0)]public NativeMouse mouse;}
[StructLayout(LayoutKind.Sequential)]public struct NativeKeyboard{public ushort vk;public ushort scan;public uint flags;public uint time;public IntPtr extra;}
[StructLayout(LayoutKind.Sequential)]public struct NativeMouse{public int dx,dy;public uint data,flags,time;public IntPtr extra;}
public static class TMSendScan{
 [DllImport("user32.dll",SetLastError=true)]public static extern uint SendInput(uint n,[In]NativeInput[] inputs,int cb);
 [DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")]public static extern bool BringWindowToTop(IntPtr h);
 [DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("kernel32.dll")]public static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")]public static extern bool AttachThreadInput(uint a,uint b,bool yes);
}
'@
}
$g=(Get-Process Trackmania -ErrorAction Stop|Select -First 1).MainWindowHandle
$f=[TMSendScan]::GetForegroundWindow()
$x=[uint32]0;$ft=[TMSendScan]::GetWindowThreadProcessId($f,[ref]$x)
$gt=[TMSendScan]::GetWindowThreadProcessId($g,[ref]$x)
$me=[TMSendScan]::GetCurrentThreadId()
$a=[TMSendScan]::AttachThreadInput($me,$ft,$true)
$b=[TMSendScan]::AttachThreadInput($me,$gt,$true)
try{
 [TMSendScan]::BringWindowToTop($g)|Out-Null
 if(-not [TMSendScan]::SetForegroundWindow($g)){throw 'Trackmania foreground activation failed'}
 $scan=if($Key -eq 'Space'){0x39}elseif($Key -eq 'Enter'){0x1c}else{0x48}
 $inputs=New-Object NativeInput[] 2
 $inputs[0].type=1;$inputs[0].u.keyboard.scan=$scan;$inputs[0].u.keyboard.flags=$(if($Key -eq 'Up'){9}else{8})
 $inputs[1].type=1;$inputs[1].u.keyboard.scan=$scan;$inputs[1].u.keyboard.flags=$(if($Key -eq 'Up'){11}else{10})
 $size=[Runtime.InteropServices.Marshal]::SizeOf([type][NativeInput])
 $down=[TMSendScan]::SendInput(1,[NativeInput[]]@($inputs[0]),$size)
 Start-Sleep -Milliseconds 650
 $up=[TMSendScan]::SendInput(1,[NativeInput[]]@($inputs[1]),$size)
 if($down -ne 1 -or $up -ne 1){throw "SendInput failed: down $down up $up; win32 $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"}
 "PASS_SENDINPUT $Key to Trackmania size=$size"
} finally {
 if($b){[TMSendScan]::AttachThreadInput($me,$gt,$false)|Out-Null}
 if($a){[TMSendScan]::AttachThreadInput($me,$ft,$false)|Out-Null}
}