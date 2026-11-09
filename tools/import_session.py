#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入 FreeRouting session (.ses) → 生成走线/过孔 → 补手工电源线 → 重铺铜"""
import re
import pcbnew

BOARD = '/Users/yangjianfei/Downloads/智能服装硬件/kicad/petvest-hub/petvest-hub.kicad_pcb'
SES   = '/Users/yangjianfei/Downloads/智能服装硬件/tools/freerouting/hub.ses'

b = pcbnew.LoadBoard(BOARD)
H = 42.0

# ---------- 1. 解析 ses ----------
src = open(SES, encoding='utf-8').read()
routes_i = src.find('(routes')
seg = src[routes_i:]

# network_out 中逐网解析 (wire/via)
net_blocks = re.split(r'\(net "', seg)
tracks_spec = []   # (layer, width_mm, [(x,y)...], netname)
vias_spec = []     # (x, y, size, drill, netname)
def find_paren(s, i):
    depth=0
    for j in range(i, len(s)):
        if s[j]=='(': depth+=1
        elif s[j]==')':
            depth-=1
            if depth==0: return j+1
    return len(s)

for blk in net_blocks[1:]:
    name = blk.split('"')[0].strip()
    k = 0
    while True:
        w = blk.find('(wire', k)
        v = blk.find('(via', k)
        if w < 0 and v < 0: break
        if w >= 0 and (v < 0 or w < v):
            e = find_paren(blk, w)  # wire 块
            inner = blk[blk.find('(', w+1)+1:e-1].replace('(',' ').replace(')',' ')
            toks = inner.split()
            if len(toks) >= 6 and toks[0] == 'path':
                layer, width = toks[1], int(float(toks[2]))
                vals = [float(v) for v in toks[3:]]
                if len(vals) % 2 == 0 and len(vals) >= 4:
                    pts = [(vals[i]/10000.0, H + vals[i+1]/10000.0) for i in range(0, len(vals), 2)]
                    tracks_spec.append((layer, width/10000.0, pts, name))
            k = e
        else:
            e = find_paren(blk, v)
            inner = blk[blk.find('(', v+1)+1:e-1].replace('(',' ').replace(')',' ')
            toks = inner.split()
            if len(toks) >= 3 and toks[0].startswith('Via'):
                vname, x, y = toks[0], float(toks[1]), float(toks[2])
                size, drill = (0.6, 0.3) if '600' in vname else (0.5, 0.25)
                vias_spec.append((x/10000.0, H + y/10000.0, size, drill, name))
            k = e

print(f"ses: {len(tracks_spec)} 条走线, {len(vias_spec)} 个过孔", flush=True)

# net name → code
netcodes = {p.GetNetname(): p.GetNetCode() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()}
def add_track(pts_mm, width_mm, layer_id, netname):
    netc = netcodes.get(netname, 0)
    for i in range(len(pts_mm)-1):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(int(pts_mm[i][0]*1e6), int(pts_mm[i][1]*1e6)))
        t.SetEnd(pcbnew.VECTOR2I(int(pts_mm[i+1][0]*1e6), int(pts_mm[i+1][1]*1e6)))
        t.SetWidth(int(width_mm*1e6))
        t.SetLayer(layer_id)
        t.SetNetCode(netc)
        b.Add(t)

L_F = pcbnew.F_Cu; L_B = pcbnew.B_Cu
for layer, width, pts, name in tracks_spec:
    add_track(pts, width, L_F if layer=='F.Cu' else L_B, name)
for x, y, size, drill, name in vias_spec:
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(int(x*1e6), int(y*1e6)))
    v.SetWidth(int(size*1e6))
    v.SetDrill(int(drill*1e6))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(L_F, L_B)
    v.SetNetCode(netcodes.get(name, 0))
    b.Add(v)

# ---------- 2. 手工电源线 (F.Cu) ----------
def padpos(ref, num):
    for fp in b.GetFootprints():
        if fp.GetReference() == ref:
            p = fp.FindPadByNumber(num)
            pos = p.GetPosition()
            return (pos.x/1e6, pos.y/1e6)
    raise RuntimeError(f"pad {ref}.{num} not found")

def power_route(netname, pads, width=0.5):
    pts = [padpos(r, n) for r, n in pads]
    # 顺序链: 水平→垂直 两段式
    chain = [pts[0]]
    for nxt in pts[1:]:
        cur = chain[-1]
        chain.append((nxt[0], cur[1]))  # 先水平
        chain.append(nxt)               # 再垂直
    add_track(chain, width, L_F, netname)
    print(f"  power {netname}: {len(pts)} pads", flush=True)

print("手工电源线:")
power_route('+BATT', [('J2','1'),('SW1','1'),('C2','1'),('R6','1'),('U2','5'),('U4','1'),('TP3','1'),('C8','1')], 0.6)
power_route('VBUS', [('J1','B4'),('J1','A4'),('D1','1'),('F1','1'),('TP4','1')], 0.6)
power_route('VBUS_F', [('F1','2'),('C1','1'),('U2','4'),('U2','8'),('R4','1'),('R5','1')], 0.6)
power_route('VSW', [('SW1','2'),('C3','1'),('C4','1'),('U3','2'),('U40','7'),('U40','8')], 0.6)
power_route('+1V8', [('U30','5'),('C16','1'),('J30','2')], 0.4)
power_route('NET_SPKN', [('U40','10'),('J40','1')], 0.5)

# ---------- 3. 重铺铜 + 保存 ----------
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(BOARD)
segs = sum(1 for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
vias2 = sum(1 for t in b.GetTracks() if t.GetClass()=='VIA')
print(f"完成: tracks={segs} vias={vias2}")
