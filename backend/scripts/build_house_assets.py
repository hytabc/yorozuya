"""Build original, deterministic voxel furniture and seamless textures (no downloads).

Run from the repository root: backend/.venv/bin/python backend/scripts/build_house_assets.py
Shapes and palettes are authored for this project; see docs/house-assets.md.
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'frontend/public/house'
SLOTS = [
    ('wood', '木材', '#b58b63'), ('fabric', '布艺', '#e4d9c6'),
    ('metal', '金属', '#60666a'), ('accent', '装饰', '#879b87'),
    ('ceramic', '陶瓷', '#edeae1'), ('screen', '屏幕', '#263b43'),
    ('leaf', '枝叶', '#6c8760'), ('glass', '玻璃', '#a9c4c3'),
]
CATEGORIES = [
 ('sofa','沙发','双人布艺/三人布艺/L型转角/复古皮质/木框软垫'),
 ('chair','椅子','木质餐椅/软包餐椅/扶手椅/办公椅/高脚凳'),
 ('table','餐桌','四人方桌/六人长桌/圆桌/折叠桌/吧台桌'),
 ('coffee','茶几','方形木桌/圆形矮桌/双层茶几/嵌套茶几/抽屉茶几'),
 ('desk','书桌','简约书桌/抽屉书桌/转角书桌/电脑桌/梳妆书桌'),
 ('tv','电视','平板电视/复古显像管电视/支架电视/超宽电视/便携小电视'),
 ('tvstand','电视柜','开放矮柜/双门柜/抽屉柜/模块组合柜/复古高脚柜'),
 ('bed','床','单人床/双人木床/软包床/四柱床/上下铺'),
 ('nightstand','床头柜','单抽屉柜/双抽屉柜/开放层架柜/圆角柜/复古高脚柜'),
 ('wardrobe','衣柜','双门柜/三门柜/推拉门柜/开放衣架柜/镜面门柜'),
 ('chest','斗柜','三斗柜/五斗柜/宽矮斗柜/窄高斗柜/组合斗柜'),
 ('shelf','书架','窄高书架/宽书架/格子书架/阶梯书架/带门书柜'),
 ('lamp','台灯与落地灯','床头灯/阅读台灯/弧形落地灯/三脚落地灯/纸罩立灯'),
 ('pendant','顶灯','吊钟灯/圆盘吊灯/球形吊灯/三头吊灯/长条吊灯'),
 ('rug','地毯','长方形编织毯/圆毯/条纹毯/几何毯/绒毛毯'),
 ('plant','绿植','小盆栽/龟背竹/仙人掌/落地大叶植物/花瓶插花'),
 ('wall','墙面装饰','风景画/几何画/组合相框/挂钟/壁挂置物架'),
 ('fridge','冰箱','单门冰箱/双门冰箱/对开门冰箱/复古圆角冰箱/迷你冰箱'),
 ('stove','灶台','双眼灶/四眼灶/带烤箱灶/嵌入式灶台/复古炉台'),
 ('sink','厨房水槽柜','单槽柜/双槽柜/带沥水台柜/转角水槽柜/开放底架水槽'),
 ('vanity','洗手台','柱式盆/单盆浴室柜/双盆柜/圆盆木架台/悬挂式盆'),
 ('toilet','马桶','分体式/连体式/壁挂式/智能式/复古高水箱式'),
 ('bath','浴缸与淋浴','长方浴缸/圆角浴缸/独立脚浴缸/转角浴缸/淋浴间'),
 ('deco','小型装饰','书籍组合/茶具组合/收音机/抱枕组合/桌面摆件'),
]
STYLES = ['原木', '北欧', '奶油', '复古', '现代']
PALETTES = [
 ('cream','奶油原木',['#b58b63','#e4d9c6','#696c65','#bda784','#efece4','#263b43','#7f926b','#b9cccc']),
 ('sage','北欧鼠尾草',['#bb9d79','#9eafa0','#58615a','#dfd7bf','#f0ede3','#253e39','#6b8463','#b2c7c1']),
 ('grey','暖灰现代',['#9a8a7c','#bdb7ad','#454d52','#82979a','#e5e1d8','#26323d','#788873','#afc2c5']),
 ('walnut','胡桃复古',['#735039','#bfa37e','#6e6253','#8d685a','#ded2bb','#313833','#687451','#a5b9ac']),
 ('blue','雾蓝海盐',['#bda586','#a6bbc5','#616e78','#c2b89d','#edece5','#293b4c','#82998c','#c1d6da']),
 ('rose','低饱和莓粉',['#aa8b77','#c4a3a5','#736366','#a1a895','#eee3db','#3c3743','#849079','#c5cfd0']),
]

def build(kind, v):
    vox = {}
    def box(x,y,z,w,d,h,c=0):
        for a in range(x,x+w):
            for b in range(y,y+d):
                for k in range(z,z+h): vox[a,b,k]=c
    def disk(x,y,z,w,d,h,c=0):
        for a in range(w):
            for b in range(d):
                if ((a+.5-w/2)/(w/2))**2+((b+.5-d/2)/(d/2))**2 <= 1:
                    box(x+a,y+b,z,1,1,h,c)
    def legs(w,d,h,c=0):
        for x in (1,w-3):
            for y in (1,d-3): box(x,y,0,2,2,h,c)
    def cabinet(w,d,h,doors=2):
        box(0,0,2,w,d,2); box(0,0,h,w,d,2)
        box(0,0,2,2,d,h); box(w-2,0,2,2,d,h); box(0,d-2,2,w,2,h)
        legs(w,d,3)
        if doors:
            for i in range(doors):
                x=2+i*(w-4)//doors; end=2+(i+1)*(w-4)//doors
                box(x,0,4,end-x-1,2,h-4,0 if v%2==0 else 3)
                box(x+1,0,h//2,2,1,1,2)
    if kind=='sofa':
        w=[30,42,40,34,32][v]; d=16
        legs(w,d,4,0); box(0,0,4,w,d,4,0 if v==4 else 1)
        for x in range(3,w-3,11): box(x,1,8,min(10,w-3-x),12,3,1)
        box(0,13,7,w,3,14,1); box(0,0,7,3,16,10,0 if v==4 else 1); box(w-3,0,7,3,16,10,1)
        if v==2: box(0,-12,4,15,13,6,1)
        if v==3: box(3,14,12,w-6,1,2,3)
        box(4,10,11,5,3,5,3)
    elif kind=='chair':
        w,d=12,12; h=24 if v==4 else 13
        legs(w,d,h,2 if v==3 else 0); box(0,0,h,w,d,3,1 if v in (1,2,3) else 0)
        if v!=4: box(0,d-2,h+3,w,2,12,1 if v==2 else 0)
        if v==1: box(1,1,h+3,w-2,d-4,2,1)
        if v==2:
            box(0,0,h+3,2,d,5,0); box(w-2,0,h+3,2,d,5,0)
        if v==3:
            box(-2,4,0,16,3,1,2); box(4,-2,0,3,16,1,2)
    elif kind in ('table','coffee','desk'):
        w=[26,40,28,24,36][v]; d=[22,24,28,18,14][v]; h=10 if kind=='coffee' else 22
        if kind=='table' and v==4: h=30
        legs(w,d,h,2 if v==4 else 0)
        (disk if v==2 and kind=='table' or v==1 and kind=='coffee' else box)(0,0,h,w,d,3,0)
        if kind=='coffee' and v==2: box(0,0,4,w,d,2,0)
        if kind=='coffee' and v==3:
            box(w,2,0,2,12,7); box(w+10,2,0,2,12,7); box(w,2,7,12,12,2,3)
        if v==4 or kind=='desk' and v==1: box(3,0,h-6,w-6,3,5,3)
        if kind=='desk' and v==2: box(w-3,0,h,14,d+12,3); box(w+8,d+8,0,3,3,h)
        if kind=='desk' and v==3:
            box(8,12,h+3,2,2,5,2); box(3,12,h+8,18,2,10,2); box(4,11,h+9,16,1,8,5)
        if kind=='desk' and v==4: box(4,d-2,h+3,w-8,2,17,0); box(6,d-3,h+5,w-12,1,13,7)
    elif kind=='tv':
        w=[26,22,28,40,14][v]; d=10 if v==1 else 3; h=[17,18,20,15,12][v]
        box(0,0,4,w,d,h,0 if v==1 else 2); box(2,-1,6,w-4,1,h-4,5)
        box(4,0,0,2,d,4,2); box(w-6,0,0,2,d,4,2)
        if v==2: box(w//2-1,1,-8,2,2,12,2); box(2,0,-8,w-4,7,2,2)
        if v==4: box(w//2,1,h+4,1,1,6,2)
    elif kind in ('tvstand','nightstand','wardrobe','chest','shelf'):
        w= [34,38,32,44,36][v] if kind=='tvstand' else [16,18,14,20,16][v]
        d=12; h=12 if kind in ('tvstand','nightstand') else [36,42,24,46,32][v]
        if kind=='wardrobe': w=[24,34,32,30,28][v]; h=44
        if kind=='shelf': w=[14,30,28,30,24][v]; h=[44,36,32,38,40][v]
        cabinet(w,d,h,0 if v==0 and kind in ('tvstand','shelf') or v==2 and kind=='nightstand' or v==3 and kind=='wardrobe' else 3 if v==1 else 2)
        if kind in ('chest','shelf') or v==2:
            for z in range(8,h,7 if v==1 else 9):
                box(2,1,z,w-4,d-3,1,0)
                if kind=='chest': box(2,0,z-5,w-4,1,4,3); box(w//2,0,z-3,3,1,1,2)
        if kind=='shelf':
            if v==2: box(w//2,1,2,2,d-3,h-2)
            if v==3:
                for x in range(w//2,w):
                    for y in range(d):
                        for z in range(h//2,h+3): vox.pop((x,y,z),None)
            box(3,2,4,2,6,7,3); box(6,2,4,2,6,6,1)
        if kind=='wardrobe' and v==4: box(3,-1,6,w//2-4,1,h-10,7)
        if v==4: legs(w,d,6,2)
    elif kind=='bed':
        w=[20,32,34,30,22][v]; d=44
        legs(w,d,6); box(0,0,6,w,d,3,0); box(1,1,9,w-2,d-2,4,1)
        box(0,d-3,6,w,3,20,1 if v==2 else 0); box(1,1,13,w-2,28,2,3)
        box(3,32,13,w-6,8,3,4)
        if v==3:
            for x in (0,w-2):
                for y in (0,d-2): box(x,y,0,2,2,48)
            box(0,0,46,w,2,2); box(0,d-2,46,w,2,2)
        if v==4:
            box(0,0,34,w,d,3); box(1,1,37,w-2,d-2,4,1)
            for z in range(5,35,5): box(w,3,z,4,2,1,0)
            box(w+3,3,0,1,2,36); box(w,3,0,1,2,36)
    elif kind in ('lamp','pendant'):
        h=[14,20,40,36,32][v] if kind=='lamp' else [14,8,16,12,10][v]
        w=[12,10,16,14,10][v]; d=w
        disk(0,0,0,w,d,2,0); box(w//2-1,d//2-1,2,2,2,h,2)
        disk(0,0,h,w,d,6,1)
        if v==1: box(w//2,d//2,h-4,w,2,2,2); box(w,0,h,w,8,3,4)
        if v==2 and kind=='lamp': box(w//2,d//2,h-2,10,2,2,2); disk(w//2+4,0,h-5,10,10,4,1)
        if v==3:
            box(-5,d//2,h, w+10,2,2,2)
            for x in (-5,w//2,w+2): disk(x,0,h+2,6,6,4,4)
        if v==4: box(2,2,h,w-4,d-4,12,1)
    elif kind=='rug':
        w=[36,30,40,32,28][v]; d=[24,30,26,32,20][v]
        (disk if v==1 else box)(0,0,0,w,d,1,1)
        for (x,y,z) in list(vox):
            if v==2 and x%8<3 or v==3 and (x//6+y//6)%2==0 or v==0 and (x<2 or y<2 or x>w-3 or y>d-3): vox[x,y,z]=3
        if v==4:
            for x in range(0,w,3): box(x,0,1,1,d,1,1)
    elif kind=='plant':
        w=[8,14,10,16,9][v]; h=[8,12,10,18,12][v]
        disk(0,0,0,w,w,h,4 if v==4 else 3)
        box(w//2,w//2,h,1,1,h+8,0)
        if v==2:
            box(2,3,h,4,4,18,6); box(0,3,h+8,3,4,2,6); box(7,3,h+10,2,4,7,6)
        else:
            for i in range(3+v):
                x=round(w/2+math.cos(i*2)*w*.6); y=round(w/2+math.sin(i*2)*w*.6)
                disk(x-3,y-3,h+3+i*3,7+v,5+v,2,3 if v==4 else 6)
    elif kind=='wall':
        w=[22,20,30,16,26][v]; h=[16,20,22,16,12][v]
        box(0,0,0,w,2,h,0); box(2,-1,2,w-4,1,h-4,1)
        if v==0: box(3,-2,3,w-6,1,5,6); box(10,-2,8,6,1,4,3)
        if v==1: box(5,-2,5,8,1,8,3); box(11,-2,10,5,1,5,5)
        if v==2: box(w+2,0,2,10,2,12,0); box(2,0,h+2,12,2,9,0)
        if v==3: box(w//2,-2,4,1,1,5,2); box(w//2,-2,8,4,1,1,2)
        if v==4: box(0,-8,0,w,10,2); box(3,-5,2,2,4,7,3)
    elif kind=='fridge':
        w=[16,20,28,18,12][v]; h=[32,38,40,34,20][v]; d=14
        box(0,0,0,w,d,h,4); box(1,-1,2,w-2,1,h-4,3 if v==3 else 4)
        if v in (1,2): box(1,-2,h//2,w-2,1,1,2)
        if v==2: box(w//2,-2,2,1,1,h-4,2)
        box(w-4,-2,h//2,1,1,7,2)
    elif kind in ('stove','sink','vanity'):
        w=[22,30,24,28,20][v]; d=18; h=20
        cabinet(w,d,h,0 if v==4 or kind=='vanity' and v==0 else 2)
        box(0,0,h+2,w,d,2,4)
        if kind=='stove':
            for x in (3,w-8) if v!=0 else (3,):
                for y in (3,10): disk(x,y,h+4,5,5,1,2)
            if v==2: box(3,-1,5,w-6,1,10,5)
            if v==4: box(0,d-2,h+3,w,2,10,2)
        else:
            count=2 if v==1 or kind=='vanity' and v==2 else 1
            for i in range(count):
                x=3+i*w//2; bw=w//count-6
                box(x,4,h+4,bw,10,1,7); box(x,4,h+5,1,10,2,4); box(x+bw-1,4,h+5,1,10,2,4)
                box(x,4,h+5,bw,1,2,4); box(x,13,h+5,bw,1,2,4)
                box(x+2,15,h+4,1,1,6,2); box(x+2,12,h+9,1,4,1,2)
            if v==3: disk(2,2,h+4,w-4,14,3,4)
            if kind=='sink' and v==3: box(w-2,0,0,14,d+10,h+4,0)
            if kind=='vanity' and v==4:
                for p in list(vox):
                    if p[2]<h-2: vox.pop(p)
    elif kind=='toilet':
        w=[12,13,12,15,11][v]; d=[20,21,18,22,19][v]
        disk(1,0,0,w-2,d-5,9,4); disk(0,0,9,w,d-4,3,4); disk(3,3,12,w-6,d-10,1,7)
        if v!=2: box(0,d-5,0,w,5,22 if v!=4 else 34,4)
        if v==3: box(1,1,13,w-2,d-7,2,4)
        if v==4: box(w//2,d-3,10,1,1,22,2)
    elif kind=='bath':
        w=[24,26,22,30,24][v]; d=42 if v!=3 else 30; h=14
        if v==4:
            box(0,0,0,w,w,2,4); box(0,w-2,2,w,2,44,7); box(w-2,0,2,2,w,44,7)
            box(3,w-4,2,1,1,38,2); box(3,w-10,38,1,7,1,2); disk(0,w-12,38,7,7,1,2)
        else:
            box(0,0,3,w,d,2,4); box(0,0,5,3,d,h,4); box(w-3,0,5,3,d,h,4)
            box(0,0,5,w,3,h,4); box(0,d-3,5,w,3,h,4); box(3,3,5,w-6,d-6,1,7)
            if v==2: legs(w,d,4,2)
            if v==1:
                vox.clear()
                for x in range(w):
                    for y in range(d):
                        radius=((x+.5-w/2)/(w/2))**2+((y+.5-d/2)/(d/2))**2
                        if radius<=1:
                            box(x,y,3,1,1,2,4)
                            box(x,y,5,1,1,h if radius>.65 else 1,4 if radius>.65 else 7)
            if v==3: box(0,0,0,8,8,5,0)
    elif kind=='deco':
        if v==0:
            for i in range(4): box(i*3,0,0,2,8,8+i*2,i%4)
        elif v==1:
            box(0,0,0,18,12,1,0); disk(6,3,1,7,7,7,4)
            for x in (1,14): disk(x,2,1,3,3,3,4)
        elif v==2:
            box(0,0,0,16,7,11,0); disk(1,-1,2,6,1,6,2); box(9,-1,3,5,1,4,5); box(13,3,11,1,1,9,2)
        elif v==3:
            box(0,0,0,10,10,3,1); box(8,3,3,10,9,3,3)
        else:
            disk(0,0,0,10,10,2,0); box(3,3,2,4,4,10,3); disk(1,1,12,8,8,3,4)
    # Normalize occupied origin. One voxel == one room unit.
    origin=tuple(min(p[a] for p in vox) for a in range(3))
    return [[x-origin[0],y-origin[1],z-origin[2],c] for (x,y,z),c in sorted(vox.items())]

def thumbnail(vox, path, colors):
    cells={(x,y,z):c for x,y,z,c in vox}
    projected=[]
    for (x,y,z),c in sorted(cells.items(),key=lambda p:-p[0][0]-p[0][1]+p[0][2]):
        col=tuple(int(colors[c][i:i+2],16) for i in (1,3,5))
        points=lambda q: [(a-b,-(a+b)*.5-k*1.15) for a,b,k in q]
        for adjacent,verts,shade in [((x-1,y,z),[(x,y,z),(x,y+1,z),(x,y+1,z+1),(x,y,z+1)],.78),((x,y-1,z),[(x,y,z),(x+1,y,z),(x+1,y,z+1),(x,y,z+1)],.9),((x,y,z+1),[(x,y,z+1),(x+1,y,z+1),(x+1,y+1,z+1),(x,y+1,z+1)],1)]:
            if adjacent not in cells: projected.append((points(verts),tuple(round(k*shade) for k in col)))
    coords=[p for poly,c in projected for p in poly]; lo=[min(p[i] for p in coords) for i in range(2)]; hi=[max(p[i] for p in coords) for i in range(2)]
    scale=min(250/(hi[0]-lo[0]),225/(hi[1]-lo[1]))
    img=Image.new('RGB',(300,280),'#f2eee5'); draw=ImageDraw.Draw(img)
    for poly,col in projected: draw.polygon([(round((x-(lo[0]+hi[0])/2)*scale+150),round((y-(lo[1]+hi[1])/2)*scale+137)) for x,y in poly],fill=col)
    img.save(path)

def textures():
    result=[]
    for kind,label in [('wood','木纹'),('brick','砖墙'),('tile','瓷砖'),('stone','石材'),('paper','壁纸'),('cloth','织物')]:
        for v in range(5):
            color=PALETTES[v][2][0 if kind=='wood' else 1]; img=Image.new('RGB',(128,128),color); d=ImageDraw.Draw(img)
            if kind=='wood':
                for y in range(0,128,16):
                    d.line((0,y,127,y),fill='#8b7765',width=2)
                    for t in range(3): d.line((0,y+4+t*3,127,y+5+t*3),fill=PALETTES[v][2][3])
            elif kind in ('tile','brick'):
                for y in range(0,128,32):
                    d.line((0,y,127,y),fill='#eee8db',width=2)
                    for x in range(-32,160,32 if kind=='tile' else 64): d.line((x+(16 if y%64 else 0),y,x+(16 if y%64 else 0),y+32),fill='#eee8db',width=2)
            elif kind=='stone':
                for k in range(30):
                    x=(k*47+v*7)%128; y=(k*29)%128
                    d.line((x,y,(x+12)%128,(y+5)%128),fill=PALETTES[v][2][0],width=1)
            elif kind=='paper':
                for x in range(0,128,32):
                    for y in range(0,128,32): d.polygon([(x+16,y+6),(x+23,y+16),(x+16,y+26),(x+9,y+16)],fill=PALETTES[v][2][3])
            else:
                for t in range(0,128,4):
                    d.line((0,t,127,t),fill=PALETTES[v][2][4]); d.line((t,0,t,127),fill=PALETTES[v][2][3])
            ident=f'{kind}-{v+1}'; img.save(OUT/'textures'/f'{ident}.png')
            result.append({'id':ident,'name':f'{label} · {PALETTES[v][1]}','category':label,'url':f'/house/textures/{ident}.png'})
    return result

if __name__=='__main__':
    (OUT/'thumbnails').mkdir(parents=True,exist_ok=True); (OUT/'textures').mkdir(parents=True,exist_ok=True)
    models=[]
    for kind,label,names in CATEGORIES:
        for v,name in enumerate(names.split('/')):
            vox=build(kind,v); size=max(max(p[:3]) for p in vox)+1
            grid=next(s for s in (16,32,64) if size<=s)
            used=sorted({p[3] for p in vox}); mapping={old:i for i,old in enumerate(used)}
            slots=[{'key':SLOTS[i][0],'label':SLOTS[i][1],'color':PALETTES[v][2][i],'editable':SLOTS[i][0] not in ('screen','glass')} for i in used]
            ident=f'official-{kind}-{v+1}'
            models.append({'id':ident,'name':name,'category':kind,'categoryLabel':label,'style':STYLES[v],'mount':'wall' if kind=='wall' else 'ceiling' if kind=='pendant' else 'surface' if kind in ('tv','deco') else 'floor','gridSize':grid,'palette':slots,'voxels':[[x,y,z,mapping[c]] for x,y,z,c in vox],'thumbnail':f'/house/thumbnails/{ident}.png'})
            thumbnail(vox,OUT/'thumbnails'/f'{ident}.png',PALETTES[v][2])
    examples=[]
    for label,palette_index,layout in [
        ('奶油客厅',0,[('sofa',1,70,95,0),('coffee',1,76,70,0),('tvstand',1,70,40,0),('tv',1,74,42,14),('chair',3,112,90,0),('lamp',3,50,100,0),('plant',4,110,40,0)]),
        ('鼠尾草卧室',1,[('bed',2,85,80,0),('nightstand',1,65,108,0),('nightstand',2,125,108,0),('wardrobe',2,70,145,0),('chest',1,135,70,0),('plant',1,130,120,0)]),
        ('胡桃书房',3,[('desk',2,80,100,0),('chair',4,90,78,0),('shelf',2,70,140,0),('shelf',3,105,140,0),('lamp',1,85,104,25),('plant',2,135,100,0)]),
        ('雾蓝厨房',4,[('fridge',3,55,140,0),('sink',2,90,140,0),('stove',2,125,140,0),('table',3,90,85,0),('chair',1,78,90,0),('chair',2,120,90,0),('deco',2,95,90,25)]),
        ('暖灰卫浴',2,[('bath',2,70,90,0),('vanity',2,110,140,0),('toilet',4,120,90,0),('plant',1,140,140,0),('wall',4,100,252,38)]),
    ]:
        colors=dict(zip([s[0] for s in SLOTS],PALETTES[palette_index][2])); placements=[]
        for i,(kind,v,x,y,z) in enumerate(layout):
            ident=f'official-{kind}-{v}'
            model=next(m for m in models if m['id']==ident)
            placements.append({'id':f'example-{i}','versionId':ident+'-v1','position':{'x':x,'y':y,'z':z},'rotation':0,'paletteOverrides':{s['key']:colors[s['key']] for s in model['palette'] if s['editable']}})
        examples.append({'name':label,'state':{'schemaVersion':1,'name':label,'placements':placements,'floor':{'color':'#ffffff','textureId':f'wood-{palette_index+1}','mode':'repeat'},'wall':{'color':'#f2eee5','textureId':None,'mode':'repeat'}}})
    catalog={'schemaVersion':1,'categories':[{'id':k,'label':l} for k,l,n in CATEGORIES],'palettes':[{'id':i,'name':n,'colors':dict(zip([s[0] for s in SLOTS],c))} for i,n,c in PALETTES],'textures':textures(),'examples':examples,'models':models}
    (ROOT/'backend/app/house_catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')))
    print(f'Built {len(models)} models, {sum(len(m["voxels"]) for m in models)} voxels and 30 textures')
