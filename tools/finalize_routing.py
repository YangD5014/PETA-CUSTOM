#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""布线管线最终一步: 导入 ses 走线 → 补电源线 → 文本法插入过孔 → 铺铜 → 保存
前置: gen_pcb.py 已重新生成干净板 (无走线)"""
import pcbnew, re, os

BOARD = '/Users/yangjianfei/Downloads/智能服装硬件/kicad/petvest-hub/petvest-hub.kicad_pcb'
SES   = '/Users/yangjianfei/Downloads/智能服装硬件/tools/freerouting/hub_v9.ses'
H = 42.0

b = pcbnew.LoadBoard(BOARD)
FPS = list(b.GetFootprints())
netcodes = {p.GetNetname(): p.GetNetCode() for fp in FPS for p in fp.Pads() if p.GetNetname()}
PADPOS = {(fp.GetReference(), p.GetNumber()): (p.GetPosition().x/1e6, p.GetPosition().y/1e6)
          for fp in FPS for p in fp.Pads()}

added_t = added_v = 0

# ---------- 1. ses 走线 (正确变换: x=sx/1e4, y=-sy/1e4) ----------
src = open(SES, encoding='utf-8').read()
out_seg = src[src.find('(network_out'):]
# 平衡括号精确切分 (net "X" ...) 块
def blocks_of(s, tag):
    out=[]
    k=0
    while True:
        i = s.find('(%s "' % tag, k)
        if i < 0: break
        d=0
        for j in range(i, len(s)):
            if s[j]=='(': d+=1
            elif s[j]==')':
                d-=1
                if d==0: out.append((i, j+1)); k=j+1; break
        else: break
    return out
for bi,(bs,be) in enumerate(blocks_of(out_seg, 'net')):
    blk = out_seg[bs:be]
    name = re.search(r'\(net "([^"]+)"', blk).group(1)
    nc = netcodes.get(name, 0)
    for wm in re.finditer(r'\(wire\s*\(path (\S+) (\d+)\s*([\d\s.-]+)\)\s*\)', blk):
        layer_s, width, coords = wm.group(1), int(wm.group(2)), wm.group(3)
        vals = [float(v) for v in coords.split()]
        pts = [(vals[i]/10000.0, -vals[i+1]/10000.0) for i in range(0, len(vals), 2)]
        lid = pcbnew.F_Cu if layer_s == 'F.Cu' else pcbnew.B_Cu
        for i in range(len(pts)-1):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(int(pts[i][0]*1e6), int(pts[i][1]*1e6)))
            t.SetEnd(pcbnew.VECTOR2I(int(pts[i+1][0]*1e6), int(pts[i+1][1]*1e6)))
            t.SetWidth(int(width/10000.0*1e6))
            t.SetLayer(lid)
            t.SetNetCode(nc)
            b.Add(t); added_t += 1
    for vm in re.finditer(r'\(via "(Via[^"]*)" (-?[\d.]+) (-?[\d.]+)', blk):
        x, y = float(vm.group(2))/10000.0, -float(vm.group(3))/10000.0
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(int(x*1e6), int(y*1e6)))
        v.SetWidth(int(0.6*1e6)); v.SetDrill(int(0.3*1e6))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNetCode(nc)
        b.Add(v); added_v += 1
print(f"ses 走线: {added_t} 过孔: {added_v}", flush=True)

# ---------- 2. 手工电源线 (F.Cu) ----------
def padpos(ref, num):
    return PADPOS[(ref, num)]

def power_route(netname, pads, width=0.5):
    global added_t
    pts = [PADPOS[(r, n)] for r, n in pads]
    chain = [pts[0]]
    for nxt in pts[1:]:
        cur = chain[-1]
        chain.append((nxt[0], cur[1]))
        chain.append(nxt)
    nc = netcodes[netname]
    for i in range(len(chain)-1):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(int(chain[i][0]*1e6), int(chain[i][1]*1e6)))
        t.SetEnd(pcbnew.VECTOR2I(int(chain[i+1][0]*1e6), int(chain[i+1][1]*1e6)))
        t.SetWidth(int(width*1e6))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNetCode(nc)
        b.Add(t); added_t += 1

power_route('+BATT', [('J2','1'),('SW1','1'),('C2','1'),('R6','1'),('U2','5'),('U4','1'),('TP3','1'),('C8','1')], 0.6)
power_route('VBUS', [('J1','B4'),('J1','A4'),('D1','1'),('F1','1'),('TP4','1')], 0.6)
power_route('VBUS_F', [('F1','2'),('C1','1'),('U2','4'),('U2','8'),('R4','1'),('R5','1')], 0.6)
power_route('VSW', [('SW1','2'),('C3','1'),('C4','1'),('U3','2'),('U40','7'),('U40','8')], 0.6)
power_route('+1V8', [('U30','5'),('C16','1'),('J30','2')], 0.4)
print(f"电源线完成, tracks={added_t}", flush=True)

# ---------- 3. 铺铜区对象 (GND 底层 / 3V3 顶层 / 天线禁布) ----------
z = pcbnew.ZONE(b); z.SetLayer(pcbnew.B_Cu); z.SetNetCode(b.FindNet("GND").GetNetCode())
o = z.Outline(); o.NewOutline()
for x, y in [(1,1),(75,1),(75,41),(1,41)]: o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
z.SetMinThickness(int(pcbnew.FromMM(0.2))); z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
b.Add(z)
z2 = pcbnew.ZONE(b); z2.SetLayer(pcbnew.F_Cu); z2.SetNetCode(b.FindNet("+3V3").GetNetCode())
o2 = z2.Outline(); o2.NewOutline()
for x, y in [(1,1),(75,1),(75,41),(1,41)]: o2.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
z2.SetMinThickness(int(pcbnew.FromMM(0.3))); z2.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
z2.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
b.Add(z2)
k = pcbnew.ZONE(b); k.SetIsRuleArea(True)
ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu); k.SetLayerSet(ls)
ko = k.Outline(); ko.NewOutline()
for x, y in [(48.0,8.0),(67.0,8.0),(67.0,15.5),(48.0,15.5)]: ko.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
b.Add(k)

# 保存 (尚未填充铺铜 — 过孔先插入)
b.Save(BOARD)
print("阶段1保存完成 (走线+电源+铺铜区轮廓)", flush=True)

# ---------- 5. 重载 + 铺铜填充 + 保存 ----------
b2 = pcbnew.LoadBoard(BOARD)
n_via = sum(1 for t in b2.GetTracks() if t.GetClass() == 'VIA')
n_seg = sum(1 for t in b2.GetTracks() if t.GetClass() == 'PCB_TRACK')
print(f"重载: tracks={n_seg} vias={n_via}", flush=True)
pcbnew.ZONE_FILLER(b2).Fill(b2.Zones())
b2.Save(BOARD)
print("铺铜填充完成, 全部保存 ✓", flush=True)
