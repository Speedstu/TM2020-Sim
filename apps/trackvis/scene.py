"""Premium Cairo track atlas from the real Fall 2026-01 GBX block inventory."""
import json,math,random
from pathlib import Path
import cairo
from common import ROOT

TILE=32
PXS=1.0
BG=(.037,.065,.089)
def color(cr,hexcode,alpha=1.):
    s=hexcode.lstrip('#')
    r,g,b=[int(s[i:i+2],16)/255 for i in (0,2,4)]
    cr.set_source_rgba(r,g,b,alpha)
def rect(cr,x,y,w,h,c,rad=0):
    color(cr,c)
    if rad<=0:cr.rectangle(x,y,w,h)
    else:
        r=min(rad,w/2,h/2);cr.new_sub_path()
        cr.arc(x+w-r,y+r,r,-math.pi/2,0)
        cr.arc(x+w-r,y+h-r,r,0,math.pi/2)
        cr.arc(x+r,y+h-r,r,math.pi/2,math.pi)
        cr.arc(x+r,y+r,r,math.pi,3*math.pi/2);cr.close_path()
    cr.fill()
class MapAtlas:
    def __init__(self):
        self.map=json.loads((ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.json').read_text())
        self.w=64*TILE;self.h=64*TILE
        self.surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,self.w,self.h)
        self.cr=cairo.Context(self.surface)
        self.road=[b for b in self.map['blocks'] if
            b['name'].startswith(('RoadTech','PlatformTech'))]
        self.track_bounds=(
           (min(b['grid'][0] for b in self.road)-3)*32,
           (min(b['grid'][2] for b in self.road)-4)*32,
           (max(b['grid'][0] for b in self.road)+4)*32,
           (max(b['grid'][2] for b in self.road)+4)*32,
        )
        self.paint()
    def paint(self):
        c=self.cr
        rect(c,0,0,self.w,self.h,'#102c3e')
        # Fine marine texture: actual world uses water base tiles.
        for z in range(64):
            for x in range(64):
                seed=(x*73856093)^(z*19349663)
                shade=(seed%10)/1300
                c.set_source_rgba(.07+shade,.18+shade,.24+shade,1)
                c.rectangle(x*TILE,z*TILE,TILE,TILE);c.fill()
                if seed%5==0:
                    color(c,'#266176',.17)
                    c.set_line_width(.7)
                    sy=z*TILE+9+(seed%13)
                    c.move_to(x*TILE+5,sy);c.line_to(x*TILE+24,sy-2)
                    c.stroke()
        # Natural islands and terrain. True map block centers and block families.
        tiles={}
        for b in self.map['blocks']:
            x,y,z=b['grid'];name=b['name']
            if name.startswith(('Dirt','DecoTerrain','WaterHill','Structure')):
                if name.startswith('WaterHill'):kind='waterhill'
                elif name.startswith('Structure'):kind='structure'
                elif name.startswith('DecoTerrain'):kind='deco'
                else:kind='dirt'
                old=tiles.get((x,z))
                if old is None or (kind=='dirt' and old!='dirt'):tiles[(x,z)]=kind
        for (x,z),kind in sorted(tiles.items(),key=lambda v:(v[1]!='waterhill',v[1]!='deco',v[1]!='dirt')):
            px=x*32;pz=z*32
            if kind=='dirt':
                rect(c,px,pz,32,32,'#576b53')
                rect(c,px+2,pz+2,28,28,'#68745a')
                color(c,'#324a42',.24);c.set_line_width(1.5)
                for j in range(3):
                    c.move_to(px+4+j*8,pz+27);c.line_to(px+10+j*8,pz+3);c.stroke()
            elif kind=='waterhill':
                rect(c,px,pz,32,32,'#1a3948')
            elif kind=='structure':
                rect(c,px+4,pz+4,24,24,'#51606a',2)
                rect(c,px+9,pz+9,14,14,'#283740',2)
            else:rect(c,px,pz,32,32,'#51604d')
        # Trees from real item coordinates, not fabricated scenery.
        rng=random.Random(39)
        for item in self.map['items']:
            model=item.get('model','').lower()
            if not ('tree' in model or 'bush' in model or 'plant' in model):continue
            xyz=item.get('positionInMap')
            if not xyz:continue
            x,z=xyz[0],xyz[2]
            r=rng.uniform(3,6)
            color(c,'#102d2c',.7);c.arc(x+1.5,z+2,r+1,0,2*math.pi);c.fill()
            color(c,'#1a4a41',.85);c.arc(x,z,r,0,2*math.pi);c.fill()
            color(c,'#547b59',.5);c.arc(x-1,z-1,r*.52,0,2*math.pi);c.fill()
        # Road-tech blocks: map-derived placement and orientation. Render stylized
        # bounding decks, not a claim of exact collision triangles.
        for b in sorted(self.road,key=lambda b:b['grid'][1]):
            x,y,z=b['grid'];name=b['name'];cx=x*32+16;cz=z*32+16
            angle={'North':0,'East':math.pi/2,'South':math.pi,'West':-math.pi/2}.get(b['direction'],0)
            length=30
            if 'X3' in name or 'Curve3' in name:length=88
            elif 'X2' in name or 'Curve2' in name:length=60
            elif 'Curve4' in name:length=108
            elif 'Slope' in name:length=58
            c.save();c.translate(cx,cz);c.rotate(angle)
            rect(c,-17,-length/2+2,34,length,'#111b24',5)
            rect(c,-14,-length/2,28,length,'#69717b',4)
            rect(c,-12,-length/2,24,length,'#373f4a',4)
            color(c,'#a5b4bb',.75);c.set_line_width(.7)
            c.move_to(-10,-length/2);c.line_to(-10,length/2);c.stroke()
            c.move_to(10,-length/2);c.line_to(10,length/2);c.stroke()
            if 'Start' in name:
                rect(c,-14,-5,28,10,'#dbe8ee')
                for i in range(-14,14,7):
                    rect(c,i,-5,7,5,'#202934')
                    rect(c,i+3.5,0,3.5,5,'#202934')
            if 'Checkpoint' in name:
                rect(c,-14,-3,28,5,'#47dfba')
            if 'Tilt' in name:
                color(c,'#58caba',.3);c.set_line_width(2);c.move_to(0,-length/2+5);c.line_to(0,length/2-5);c.stroke()
            c.restore()
        # Elevation construction accents.
        for b in self.road:
            if b['name'].startswith('Platform'):
                x,y,z=b['grid']
                color(c,'#d3dde0',.25);c.set_line_width(2)
                c.rectangle(x*32+4,z*32+4,24,24);c.stroke()
        self.surface.flush()
