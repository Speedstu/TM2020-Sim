// SPDX-License-Identifier: GPL-3.0-or-later
// Explicit menu/reset key sent only to the foreground Trackmania process.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <string>
int main(int argc,char** argv){
    if(argc!=2)return 2;const std::string key=argv[1];WORD code{};
    if(key=="Return")code=VK_RETURN;else if(key=="Escape")code=VK_ESCAPE;
    else if(key=="Down")code=VK_DOWN;else if(key=="BackSpace")code=VK_BACK;
    else if(key=="Delete")code=VK_DELETE;else return 2;
    DWORD pid{};GetWindowThreadProcessId(GetForegroundWindow(),&pid);
    const auto process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
    if(!process)return 3;wchar_t path[32768]{};DWORD length=32768;
    const bool valid=QueryFullProcessImageNameW(process,0,path,&length)&&
        _wcsicmp(std::filesystem::path(path).filename().c_str(),L"Trackmania.exe")==0;
    CloseHandle(process);if(!valid)return 4;
    INPUT event{};event.type=INPUT_KEYBOARD;event.ki.wVk=code;
    const bool pressed=SendInput(1,&event,sizeof(event))==1;Sleep(100);
    event.ki.dwFlags=KEYEVENTF_KEYUP;const bool released=SendInput(1,&event,sizeof(event))==1;
    return pressed&&released?0:5;
}
