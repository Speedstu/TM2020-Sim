Add-Type -AssemblyName System.Drawing
if (-not ('TMWinCapture' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TMWinCapture {
 [DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")]public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint f);
 [StructLayout(LayoutKind.Sequential)]public struct Rect{public int Left,Top,Right,Bottom;}
}
'@
}
$p=Get-Process Trackmania -ErrorAction Stop|Where-Object {$_.MainWindowHandle -ne 0}|Select-Object -First 1
if(-not $p){throw 'No Trackmania GUI found'}
$rect=[TMWinCapture+Rect]::new()
[TMWinCapture]::GetWindowRect($p.MainWindowHandle,[ref]$rect)|Out-Null
$w=$rect.Right-$rect.Left;$h=$rect.Bottom-$rect.Top
if($w -lt 100 -or $h -lt 100){throw "Bad game window size: $w x $h"}
$bitmap=New-Object System.Drawing.Bitmap $w,$h
$g=[System.Drawing.Graphics]::FromImage($bitmap)
$dc=$g.GetHdc()
[TMWinCapture]::PrintWindow($p.MainWindowHandle,$dc,2)|Out-Null
$g.ReleaseHdc($dc)
$g.Dispose()
$out=New-Object System.Drawing.Bitmap 760,456
$g2=[System.Drawing.Graphics]::FromImage($out)
$g2.DrawImage($bitmap,0,0,760,456)
$path='H:\Projects\Trackmania2020-RE\local\recon\game-post-login.jpg'
$codec=[System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders()|Where-Object {$_.MimeType -eq 'image/jpeg'}|Select-Object -First 1
$params=New-Object System.Drawing.Imaging.EncoderParameters 1
$params.Param[0]=New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality),55L
$out.Save($path,$codec,$params)
$g2.Dispose();$bitmap.Dispose();$out.Dispose()
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes($path))