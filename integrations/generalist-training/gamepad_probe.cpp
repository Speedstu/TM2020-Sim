// SPDX-License-Identifier: GPL-3.0-or-later
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xinput.h>
#include <cstdio>
int main(){
    auto module=LoadLibraryW(L"xinput1_4.dll");
    if(!module)return 2;
    const auto get=reinterpret_cast<DWORD (WINAPI*)(DWORD,XINPUT_STATE*)>(GetProcAddress(module,"XInputGetState"));
    if(!get)return 3;
    std::puts("ms,index,packet,lx,ly,gas,brake");
    for(unsigned step=0;step<120;++step){
        for(DWORD i=0;i<4;++i){XINPUT_STATE state{};if(get(i,&state)==0)
            std::printf("%u,%lu,%lu,%d,%d,%u,%u\n",step*50,i,state.dwPacketNumber,state.Gamepad.sThumbLX,state.Gamepad.sThumbLY,state.Gamepad.bRightTrigger,state.Gamepad.bLeftTrigger);}
        std::fflush(stdout);Sleep(50);
    }
    FreeLibrary(module);
}
