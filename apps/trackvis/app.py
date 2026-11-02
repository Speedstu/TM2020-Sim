#!/usr/bin/env python3
"""TrackVis · standalone native GTK4 top-down Trackmania spectator.

GTK4/Cairo. Absolutely no browser, web server or Codex integration.
Ctrl+C closes the GUI and stops/joins its own native-physics spectator thread.
"""
from __future__ import annotations
import argparse, math, os, signal, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
from gi.repository import Gtk,Gdk,GLib,Gio
import cairo
from common import load_stats,fmt_num,fmt_time
from simulator import Spectator
from scene import MapAtlas,rect,color

DARK='#0b1017'; PANEL='#131c27'; EDGE='#263440'
AQUA='#53f5ce'; MUTED='#8797a8'; WHITE='#e9f3f7'
PALETTE=['#53f5ce','#ffbb72','#86a6ff','#ed8bcf','#e3e66f','#77d2ff','#fc8d83','#bfa2fc',
         '#81e6b2','#f4b18d','#c3ecff','#d6dca1','#e6a6bc','#8cb9b2','#b1c8ff','#fbd4a5']
def rgba(h,a=1):
    h=h.lstrip('#');return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))+(a,)
def txt(cr,x,y,s,size=14,weight=0,c=WHITE,spacing=0):
    cr.save()
    cr.select_font_face('DejaVu Sans',cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if weight else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    color(cr,c)
    cr.move_to(x,y)
    cr.show_text(str(s))
    cr.restore()
def line(cr,x1,y1,x2,y2,col,width=1,alpha=1.):
    cr.save();color(cr,col,alpha);cr.set_line_width(width);cr.move_to(x1,y1);cr.line_to(x2,y2);cr.stroke();cr.restore()
def border(cr,x,y,w,h,col=EDGE,r=12):
    cr.save();cr.set_line_width(1);color(cr,col)
    cr.new_sub_path();cr.arc(x+w-r,y+r,r,-math.pi/2,0);cr.arc(x+w-r,y+h-r,r,0,math.pi/2)
    cr.arc(x+r,y+h-r,r,math.pi/2,math.pi);cr.arc(x+r,y+r,r,math.pi,3*math.pi/2);cr.close_path()
    cr.stroke();cr.restore()
def box(cr,x,y,w,h,bg=PANEL,r=12,edge=True):
    rect(cr,x,y,w,h,bg,r)
    if edge:border(cr,x+.5,y+.5,w-1,h-1,EDGE,r)
def ellipsize(s,n):return s[:n-1]+'…' if len(s)>n else s
def metric(cr,x,y,title,value,foot=None,accent=AQUA):
    txt(cr,x,y,title.upper(),10,1,MUTED)
    txt(cr,x,y+34,value,23,1,WHITE)
    if foot:txt(cr,x,y+53,foot,10,0,accent)

class TrackWindow(Gtk.Application):
    def __init__(self,count=16):
        super().__init__(application_id='local.trackvis.spectator',flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.count=count
        self.sim=Spectator(count)
        self.scene=None
        self.win=None
        self.atlas_cache=None
        self.atlas_cache_key=None
        self.zoom=1.0;self.pan=[0.,0.]
        self.fit='track'
        self.selected=0
        self.stats={};self.last_poll=0
        self.start_time=time.monotonic()
        self.last_refresh=time.monotonic()
        self.canvas=None
        self.running=True
        self.drag_start=(0,0)
        self.drag_pan=(0,0)
        self.tick_id=None
        self.sig_id=None
        self.connect('activate',self.activate)
        self.connect('shutdown',self.on_shutdown)
    def activate(self,*args):
        if self.win:
            self.win.present();return
        self.scene=MapAtlas()
        self.win=Gtk.ApplicationWindow(application=self,title='TRACK / VIS — Fall 2026-01')
        self.win.set_default_size(1600,960)
        self.win.set_size_request(1020,650)
        self.win.connect('close-request',self.close_request)
        self.canvas=Gtk.DrawingArea()
        self.canvas.set_draw_func(self.draw)
        self.canvas.set_hexpand(True);self.canvas.set_vexpand(True)
        self.win.set_child(self.canvas)
        drag=Gtk.GestureDrag()
        drag.connect('drag-begin',self.drag_begin)
        drag.connect('drag-update',self.drag_update)
        drag.connect('drag-end',self.drag_end)
        self.canvas.add_controller(drag)
        click=Gtk.GestureClick()
        click.connect('pressed',self.clicked)
        self.canvas.add_controller(click)
        scroll=Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll',self.scrolled)
        self.canvas.add_controller(scroll)
        key=Gtk.EventControllerKey()
        key.connect('key-pressed',self.keydown)
        self.win.add_controller(key)
        self.sim.start()
        self.win.present()
        self.sig_id=GLib.unix_signal_add(GLib.PRIORITY_HIGH,signal.SIGINT,self.exit_signal)
        self.tick_id=GLib.timeout_add(16,self.paint_tick)
    def exit_signal(self):
        self.quit();return GLib.SOURCE_REMOVE
    def close_request(self,*_):
        self.quit();return False
    def on_shutdown(self,*_):
        self.running=False;self.sim.close()
    def paint_tick(self):
        if not self.running:return GLib.SOURCE_REMOVE
        if time.monotonic()-self.last_poll>.65:
            self.stats=load_stats();self.last_poll=time.monotonic()
        if self.canvas:self.canvas.queue_draw()
        return GLib.SOURCE_CONTINUE
    def frame(self,w,h):
        x=22;y=140
        rw=max(200,w-390-30)
        rh=max(200,h-166)
        return x,y,rw,rh
    def transform(self,w,h):
        x,y,rw,rh=self.frame(w,h)
        xmin,zmin,xmax,zmax=(self.scene.track_bounds if self.fit=='track'
                             else (0,0,2048,2048))
        centerx=(xmin+xmax)/2+self.pan[0]
        centerz=(zmin+zmax)/2+self.pan[1]
        scale=min(rw/(xmax-xmin),rh/(zmax-zmin))*.92*self.zoom
        return x,y,rw,rh,centerx,centerz,scale
    def coord(self,x,z,w,h):
        mx,my,mw,mh,cx,cz,sc=self.transform(w,h)
        return mx+mw/2+(x-cx)*sc,my+mh/2+(z-cz)*sc
    def drag_begin(self,g,x,y):
        self.drag_start=(x,y);self.drag_pan=tuple(self.pan)
    def drag_update(self,g,dx,dy):
        if not self.win:return
        sc=self.transform(self.canvas.get_width(),self.canvas.get_height())[-1]
        self.pan=[self.drag_pan[0]-dx/sc,self.drag_pan[1]-dy/sc]
    def drag_end(self,*_):pass
    def clicked(self,g,n,x,y):
        snap=self.sim.latest()
        w=self.canvas.get_width();h=self.canvas.get_height()
        nearest=None;dist=1e9
        for a in snap.get('cars',[]):
            px,py=self.coord(a['x'],a['z'],w,h)
            d=math.hypot(px-x,py-y)
            if d<24 and d<dist:nearest=a['id'];dist=d
        if nearest:self.selected=nearest
    def scrolled(self,g,dx,dy):
        self.zoom=max(.35,min(6.,self.zoom*(1.12**(-dy))))
        return True
    def keydown(self,ctrl,keycode,keyval,mods):
        key=Gdk.keyval_name(keyval)
        if key in ('Escape','q','Q'):
            self.quit();return True
        if key=='space':
            if self.sim.paused.is_set():self.sim.paused.clear()
            else:self.sim.paused.set()
            return True
        if key in ('r','R'):
            self.sim.reset.set();return True
        if key in ('m','M'):
            self.fit='world' if self.fit=='track' else 'track'
            self.pan=[0,0];self.zoom=1
            return True
        if key in ('f','F','Home'):
            self.fit='track';self.pan=[0,0];self.zoom=1
            return True
        if key in ('plus','KP_Add','equal'):
            self.zoom=min(self.zoom*1.2,6);return True
        if key in ('minus','KP_Subtract'):
            self.zoom=max(self.zoom/1.2,.35);return True
        return False
    def draw(self,widget,cr,w,h):
        now=time.monotonic()
        snap=self.sim.latest()
        cars=snap.get('cars',[])
        # App chromatic foundations
        rect(cr,0,0,w,h,DARK)
        grad=cairo.LinearGradient(0,0,w,300)
        grad.add_color_stop_rgba(0,.05,.10,.14,1)
        grad.add_color_stop_rgba(1,.04,.07,.105,1)
        cr.set_source(grad);cr.rectangle(0,0,w,120);cr.fill()
        line(cr,0,119,w,119,EDGE)
        rect(cr,24,28,5,34,AQUA,2)
        txt(cr,42,55,'TRACK / VIS',26,1,WHITE)
        txt(cr,44,76,'STADIUM SIMULATOR  /  TOP-DOWN SPECTATOR',10,1,MUTED)
        txt(cr,330,53,'FALL 2026 — 01',15,1,WHITE)
        txt(cr,332,75,'NADEO · ORIGINAL MAP BLOCK LAYOUT',10,0,MUTED)
        rstate=self.stats.get('state','searching')
        state_col=('#60e6b7' if rstate=='training' else '#f7bb75')
        box(cr,w-370,27,344,66,'#15212c',11)
        rect(cr,w-352,47,8,8,state_col,4)
        txt(cr,w-334,54,'TRAINING / '+rstate.upper(),12,1,WHITE)
        txt(cr,w-335,75,'LIVE TRAINING STATS · READ ONLY',10,0,MUTED)
        mx,my,mw,mh,cx,cz,sc=self.transform(w,h)
        # Cache the top-down map as a *panel-size bitmap*. Full 2048x2048
        # resampling is only needed after zoom/pan/resize, not at 60 FPS.
        box(cr,mx,my,mw,mh,'#0c1e2b',16)
        cache_key=(round(mw),round(mh),round(cx,3),round(cz,3),round(sc,5))
        if cache_key!=self.atlas_cache_key:
            atlas=cairo.ImageSurface(cairo.FORMAT_ARGB32,round(mw),round(mh))
            ctx=cairo.Context(atlas)
            ctx.set_source_rgb(.06,.12,.16);ctx.paint()
            ctx.translate(mw/2,mh/2)
            ctx.scale(sc,sc)
            ctx.translate(-cx,-cz)
            ctx.set_source_surface(self.scene.surface,0,0)
            ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
            ctx.paint()
            color(ctx,'#79adbc',.09);ctx.set_line_width(max(.5,.7/sc))
            for v in range(0,2049,32):
                ctx.move_to(v,0);ctx.line_to(v,2048)
                ctx.move_to(0,v);ctx.line_to(2048,v)
            ctx.stroke()
            atlas.flush()
            self.atlas_cache=atlas
            self.atlas_cache_key=cache_key
        cr.save()
        cr.rectangle(mx+1,my+1,mw-2,mh-2);cr.clip()
        cr.set_source_surface(self.atlas_cache,mx,my)
        cr.paint()
        # motion trails
        cr.save()
        cr.translate(mx+mw/2,my+mh/2)
        cr.scale(sc,sc)
        cr.translate(-cx,-cz)
        for a in cars:
            trail=a.get('trail') or ()
            if len(trail)<2:continue
            clr=PALETTE[(a['id']-1)%len(PALETTE)]
            col=rgba(clr,.54 if a['id']==self.selected else .35)
            cr.set_source_rgba(*col)
            cr.set_line_width((2.1 if a['id']==self.selected else 1.3)/sc)
            cr.move_to(*trail[0])
            for xx,zz in trail[1:]:cr.line_to(xx,zz)
            cr.stroke()
        cr.restore()
        cr.restore()
        # Top left glass overlay + legend
        box(cr,mx+16,my+16,265,65,'#10212d',10)
        rect(cr,mx+29,my+32,7,7,AQUA,3)
        txt(cr,mx+44,my+40,'MAP / AERIAL OVERVIEW',12,1,WHITE)
        txt(cr,mx+29,my+63,'LIVE SPECTATOR SIM · 32m GRID',10,0,MUTED)
        box(cr,mx+mw-163,my+16,146,56,'#10212d',10)
        txt(cr,mx+mw-148,my+36,'ZOOM',10,1,MUTED)
        txt(cr,mx+mw-148,my+59,f'{sc:.2f}×',18,1,WHITE)
        # Correct position of simulated cars: rotation based on quaternion.
        for a in cars:
            px,py=self.coord(a['x'],a['z'],w,h)
            if px<mx+8 or px>mx+mw-8 or py<my+8 or py>my+mh-8:continue
            selected=a['id']==self.selected
            clr=PALETTE[(a['id']-1)%len(PALETTE)]
            cr.save();cr.translate(px,py);cr.rotate(-a['heading'])
            if selected:
                cr.set_source_rgba(*rgba(clr,.18));cr.arc(0,0,22,0,2*math.pi);cr.fill()
                color(cr,clr,.55);cr.set_line_width(1.5);cr.arc(0,0,17,0,2*math.pi);cr.stroke()
            cr.set_source_rgba(0,0,0,.6)
            cr.move_to(-5,8);cr.line_to(0,-11);cr.line_to(5,8);cr.close_path();cr.fill()
            color(cr,clr)
            cr.move_to(-4,6);cr.line_to(0,-10);cr.line_to(4,6);cr.close_path();cr.fill()
            cr.restore()
            if selected:
                box(cr,px+11,py-30,61,20,'#0f2029',6)
                txt(cr,px+19,py-16,f'BOT {a["id"]:02}',10,1,clr)
        # Bottom map legend
        box(cr,mx+16,my+mh-63,min(630,mw-32),47,'#10212d',9)
        txt(cr,mx+28,my+mh-44,f'{self.count:02d} SPECTATOR CARS',11,1,AQUA)
        txt(cr,mx+198,my+mh-44,f'{snap.get("fps",0):.0f} SIM Hz',11,1,WHITE)
        txt(cr,mx+308,my+mh-44,'50ms PHYSICS / STEP',10,0,MUTED)
        txt(cr,mx+28,my+mh-26,'F   FIT TRACK     M   FULL MAP     SCROLL   ZOOM     DRAG   PAN',10,0,MUTED)
        # Sidebar
        sx=mx+mw+15;sw=w-sx-22
        box(cr,sx,my,sw,122,PANEL,14)
        txt(cr,sx+19,my+30,'TRAINING TELEMETRY',12,1,AQUA)
        line(cr,sx+18,my+41,sx+sw-18,my+41,EDGE)
        txt(cr,sx+19,my+73,'SPS',11,1,MUTED)
        txt(cr,sx+104,my+76,fmt_num(self.stats.get('sps')),25,1,WHITE)
        txt(cr,sx+19,my+102,ellipsize(self.stats.get('run','—'),30),11,0,MUTED)
        box(cr,sx,my+134,sw,132,PANEL,14)
        txt(cr,sx+19,my+161,'BEST SIMULATED LAP',10,1,MUTED)
        txt(cr,sx+19,my+204,fmt_time(self.stats.get('bestMs')),34,1,WHITE)
        txt(cr,sx+19,my+239,'MEAN  '+fmt_time(self.stats.get('meanMs')),11,1,AQUA)
        box(cr,sx,my+278,sw,145,PANEL,14)
        txt(cr,sx+19,my+305,'TRAINING PROGRESS',12,1,WHITE)
        line(cr,sx+19,my+318,sx+sw-19,my+318,EDGE)
        txt(cr,sx+19,my+346,'UPDATES',10,1,MUTED)
        txt(cr,sx+sw*.53,my+346,'TRANSITIONS',10,1,MUTED)
        txt(cr,sx+19,my+377,fmt_num(self.stats.get('update')),21,1,WHITE)
        txt(cr,sx+sw*.53,my+377,fmt_num(self.stats.get('transitions')),18,1,AQUA)
        txt(cr,sx+19,my+405,'Only read from current PPO status file',10,0,MUTED)
        list_y=my+437
        list_h=max(127,mh-580)
        box(cr,sx,list_y,sw,list_h,PANEL,14)
        txt(cr,sx+19,list_y+30,'ALL CARS',12,1,WHITE)
        txt(cr,sx+sw-75,list_y+30,f'{len(cars):02} LIVE',10,1,AQUA)
        line(cr,sx+18,list_y+42,sx+sw-18,list_y+42,EDGE)
        visible=min(len(cars),max(1,int((list_h-60)//30)))
        chosen=sorted(cars,key=lambda a:(a['id']!=self.selected,a['id']))
        for i,a in enumerate(chosen[:visible]):
            row_y=list_y+63+i*30;cl=PALETTE[(a['id']-1)%len(PALETTE)]
            if a['id']==self.selected:rect(cr,sx+10,row_y-17,sw-20,27,'#233440',7)
            rect(cr,sx+19,row_y-10,7,7,cl,3)
            txt(cr,sx+34,row_y,'BOT '+f'{a["id"]:02}',11,1,WHITE)
            txt(cr,sx+120,row_y,f'{a["speed"]:5.0f} km/h',10,0,MUTED)
            txt(cr,sx+sw-63,row_y,f'CP {a["checkpoint"]}',10,1,AQUA)
        # Sidebar footer: controls and read-only warning
        foot_y=my+mh-129
        box(cr,sx,foot_y,sw,129,'#15212c',14)
        txt(cr,sx+19,foot_y+27,'CONTROLS',11,1,WHITE)
        txt(cr,sx+19,foot_y+50,'SPACE  Pause     R  Restart cars',10,0,MUTED)
        txt(cr,sx+19,foot_y+69,'ESC / Q  Close     Ctrl+C  Close',10,0,MUTED)
        line(cr,sx+17,foot_y+80,sx+sw-17,foot_y+80,EDGE)
        txt(cr,sx+19,foot_y+100,'INDEPENDENT PHYSICS · NO GAME HOOK',9,1,AQUA)
        txt(cr,sx+19,foot_y+117,'Does not show private PPO worker positions',9,0,MUTED)
        # status error overlay
        if snap.get('error'):
            box(cr,mx+mw/2-215,my+mh/2-44,430,88,'#421e27',12)
            txt(cr,mx+mw/2-195,my+mh/2-13,'SIMULATOR ERROR',15,1,'#ffc5bd')
            txt(cr,mx+mw/2-195,my+mh/2+14,ellipsize(snap['error'],48),11,0,WHITE)
        elif not snap.get('connected'):
            box(cr,mx+mw/2-170,my+mh/2-37,340,74,'#142530',12)
            txt(cr,mx+mw/2-145,my+mh/2-5,'LOADING PHYSICS ENGINE…',14,1,AQUA)
            txt(cr,mx+mw/2-145,my+mh/2+20,'Initializing native rollout workers',11,0,MUTED)
        if self.sim.paused.is_set():
            box(cr,mx+mw/2-76,my+mh/2-20,152,40,'#162734',8)
            txt(cr,mx+mw/2-46,my+mh/2+6,'PAUSED',15,1,AQUA)

def main():
    a=argparse.ArgumentParser(description='Standalone GTK4 top-down Trackmania spectator (no browser)')
    a.add_argument('--cars',type=int,default=16,help='Independent simulated cars (2-32)')
    args=a.parse_args()
    if not 2<=args.cars<=32:a.error('cars must be in 2..32')
    app=TrackWindow(args.cars)
    return app.run(None)
if __name__=='__main__':
    raise SystemExit(main())
