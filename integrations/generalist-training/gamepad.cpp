// SPDX-License-Identifier: GPL-3.0-or-later
// Linux uinput companion. Protocol EOF/errors and a 250 ms watchdog neutralize.
#include <linux/uinput.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
struct Gamepad {
    int fd=-1,lock=-1;bool created=false;
    bool buttons[BTN_THUMBR-BTN_SOUTH+1]{};
    void emit(unsigned short type,unsigned short code,int value){
        input_event e{};e.type=type;e.code=code;e.value=value;
        check(write(fd,&e,sizeof(e))==sizeof(e),"uinput event write failed");
    }
    void apply(double gas,double brake,double steer){
        emit(EV_ABS,ABS_X,int(std::round(steer*32767.)));
        emit(EV_ABS,ABS_RZ,int(std::round(gas*255.)));
        emit(EV_ABS,ABS_Z,int(std::round(brake*255.)));
        emit(EV_SYN,SYN_REPORT,0);
    }
    void button(unsigned code,bool down){
        check(code>=BTN_SOUTH&&code<=BTN_THUMBR,"gamepad button out of range");
        buttons[code-BTN_SOUTH]=down;emit(EV_KEY,code,down);emit(EV_SYN,SYN_REPORT,0);
    }
    void neutral(){
        for(unsigned code=BTN_SOUTH;code<=BTN_THUMBR;++code)if(buttons[code-BTN_SOUTH])button(code,false);
        apply(0.,0.,0.);
    }
    void open(){
        const auto path="/run/user/"+std::to_string(getuid())+"/tm2020-analog-gamepad.lock";
        lock=::open(path.c_str(),O_CREAT|O_CLOEXEC|O_RDWR|O_NOFOLLOW,0600);
        check(lock>=0&&flock(lock,LOCK_EX|LOCK_NB)==0,"Another analog companion owns the gamepad");
        fd=::open("/dev/uinput",O_WRONLY|O_NONBLOCK|O_CLOEXEC);
        check(fd>=0,"Cannot open /dev/uinput");
        check(ioctl(fd,UI_SET_EVBIT,EV_KEY)==0&&ioctl(fd,UI_SET_EVBIT,EV_ABS)==0,"uinput capabilities failed");
        for(int key=BTN_SOUTH;key<=BTN_THUMBR;++key)check(ioctl(fd,UI_SET_KEYBIT,key)==0,"uinput button failed");
        for(auto code:{ABS_X,ABS_Y,ABS_RX,ABS_RY,ABS_Z,ABS_RZ,ABS_HAT0X,ABS_HAT0Y}){
            uinput_abs_setup axis{};axis.code=code;
            if(code==ABS_Z||code==ABS_RZ){axis.absinfo.minimum=0;axis.absinfo.maximum=255;}
            else if(code==ABS_HAT0X||code==ABS_HAT0Y){axis.absinfo.minimum=-1;axis.absinfo.maximum=1;}
            else{axis.absinfo.minimum=-32767;axis.absinfo.maximum=32767;}
            check(ioctl(fd,UI_ABS_SETUP,&axis)==0,"uinput axis failed");
        }
        uinput_setup setup{};setup.id={BUS_USB,0x045e,0x028e,0x0114};
        std::strcpy(setup.name,"TM2020 PPO Analog Gamepad");
        check(ioctl(fd,UI_DEV_SETUP,&setup)==0&&ioctl(fd,UI_DEV_CREATE)==0,"uinput creation failed");
        created=true;apply(0.,0.,0.);
        char sysname[128]{};check(ioctl(fd,UI_GET_SYSNAME(sizeof(sysname)),sysname)>=0,"uinput identity failed");
        std::cout<<"TM2020_GAMEPAD_READY "<<sysname<<std::endl;
    }
    ~Gamepad(){
        if(created){try{neutral();}catch(...){}ioctl(fd,UI_DEV_DESTROY);}
        if(fd>=0)close(fd);if(lock>=0)close(lock);
    }
};
int main(){
    try{
        Gamepad gamepad;gamepad.open();std::string pending;
        for(;;){
            pollfd event{STDIN_FILENO,POLLIN,0};const int count=poll(&event,1,250);
            check(count>=0,"gamepad stdin poll failed");
            if(!count){gamepad.neutral();continue;}
            char buffer[256];const auto n=read(STDIN_FILENO,buffer,sizeof(buffer));
            if(!n)break;check(n>0,"gamepad stdin read failed");pending.append(buffer,n);
            check(pending.size()<=4096,"oversized gamepad command");
            for(auto end=pending.find('\n');end!=std::string::npos;end=pending.find('\n')){
                std::istringstream input(pending.substr(0,end));pending.erase(0,end+1);
                std::string tag,trailing;double gas{},brake{},steer{};
                check(bool(input>>tag),"empty gamepad command");
                if(tag=="TM2020_GAMEPAD_RELEASE_V1"){
                    check(!(input>>trailing),"invalid release command");gamepad.neutral();continue;
                }
                if(tag=="TM2020_GAMEPAD_BUTTON_V1"){
                    unsigned code{};int down{};
                    check(bool(input>>code>>down)&&!(input>>trailing)&&(down==0||down==1),"invalid button command");
                    gamepad.button(code,bool(down));continue;
                }
                check(bool(input>>gas>>brake>>steer)&&!(input>>trailing)&&tag=="TM2020_GAMEPAD_V1"&&
                    std::isfinite(gas)&&std::isfinite(brake)&&std::isfinite(steer)&&
                    (gas==0.||gas==1.)&&(brake==0.||brake==1.)&&std::abs(steer)<=1.,"invalid gamepad command");
                gamepad.apply(gas,brake,steer);
            }
        }
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
