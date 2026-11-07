#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PetVest — PCB 布局生成器
基于 gen_schematic 的网表模型, 从 KiCad 官方封装库嵌入真实封装,
完成布局(未布铜, 保留鼠线), 供 3D 导出/结构设计/后续布线。
输出: kicad/petvest-hub/petvest-hub.kicad_pcb
      kicad/petvest-imu-node/petvest-imu-node.kicad_pcb
"""
import os, re, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_schematic as G

FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
U = lambda s: str(uuid.uuid5(NS, "petvest-pcb/" + s))

FP_CACHE = {}
def load_fp(lib, name):
    key = (lib, name)
    if key not in FP_CACHE:
        p = os.path.join(FPLIB, lib + ".pretty", name + ".kicad_mod")
        FP_CACHE[key] = open(p, encoding="utf-8").read()
    return FP_CACHE[key]

def pad_blocks(raw):
    """yield (start, end, padname) for each pad block in raw"""
    out = []
    for m in re.finditer(r'\(pad "([^"]+)"', raw):
        i = m.start()
        depth = 0
        for j in range(i, len(raw)):
            if raw[j] == '(':
                depth += 1
            elif raw[j] == ')':
                depth -= 1
                if depth == 0:
                    out.append((i, j + 1, m.group(1)))
                    break
    return out

# 缺失 3D 模型的封装 → 用相近尺寸的现成模型替代 (仅影响 3D 显示)
MODEL_SUB = {
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12":
        "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
    "Fuse_1812_4532Metric": "Fuse_1206_3216Metric",
    "Texas_DRC0010J": "VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm",
    "DFN-8-1EP_2x2mm_P0.5mm_EP0.9x1.3mm": "DFN-8-1EP_2x2mm_P0.5mm_EP1.05x1.75mm",
    "QFN-16-1EP_3x3mm_P0.5mm_EP1.45x1.45mm": "QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
}

def place_fp(comp, x, y, rot, nets, extra_pad_nets=None, ref_dy=None, dnp=False):
    """嵌入封装: 重命名/定位/替换位号/挂网络"""
    flib, fname = comp.fp.split(":")[:2] if ":" in comp.fp else (comp.lib, comp.fp)
    raw = load_fp(flib, fname)
    fullname = f"{flib}:{fname}"
    m = re.match(r'\(footprint "([^"]+)"', raw)
    out = raw.replace(f'(footprint "{m.group(1)}"', f'(footprint "{fullname}"', 1)
    # 在根 (layer "F.Cu") 之后插入 (at) 与唯一 uuid
    anchor = '\n\t(layer "F.Cu")\n'
    i = out.find(anchor)
    assert i > 0, f"no root layer in {fullname}"
    ins = f'\t(at {x} {y} {rot})\n\t(uuid "{U("fp/" + comp.ref)}")\n'
    out = out[:i + len(anchor)] + ins + out[i + len(anchor):]
    if dnp:  # attr 附加 dnp 标志
        out = out.replace('(attr smd)', '(attr smd dnp)', 1).replace('(attr through_hole)', '(attr through_hole dnp)', 1)
    # 位号/值
    out = out.replace('(property "Reference" "REF**"', f'(property "Reference" "{comp.ref}"', 1)
    out = re.sub(r'(\(property "Value" )"[^"]*"', r'\g<1>"' + comp.value.replace('"', '') + '"', out, count=1)
    if ref_dy:
        out = re.sub(r'(\(property "Reference" "' + re.escape(comp.ref) + r'"\s*\(at )(-?[\d.]+) (-?[\d.]+)',
                     r'\g<1>\g<2> ' + str(float(ref_dy)), out, count=1)
    # pad -> net
    padnet = {}
    for key, net in comp.nets.items():
        if net == "NC":
            continue
        for num, *_ in comp.sd.pins_for_key(key):
            padnet[num] = net
    if extra_pad_nets:
        padnet.update(extra_pad_nets)
    pieces = []
    last = 0
    for s, e, pname in pad_blocks(out):
        pieces.append(out[last:s])
        blk = out[s:e]
        if pname in padnet:
            net = padnet[pname]
            idx = nets[net]
            blk = re.sub(r'(\(layers [^)]*\))', r'\g<1>\n\t\t\t(net ' + str(idx) + f' "{net}")', blk, count=1)
        pieces.append(blk)
        last = e
    pieces.append(out[last:])
    out = ''.join(pieces)
    sub = MODEL_SUB.get(fname)
    if sub:
        out = out.replace(f'${{KICAD10_3DMODEL_DIR}}/{flib}.3dshapes/{fname}.step',
                          f'${{KICAD10_3DMODEL_DIR}}/{flib}.3dshapes/{sub}.step')
    return out

def build_netindex(net_sets):
    idx = {}
    for s in net_sets:
        for n in s:
            if n not in idx:
                idx[n] = len(idx) + 1
    return idx

def gr_rect(layer, x0, y0, x1, y1, w=0.1, fill="no"):
    return (f'\t(gr_rect (start {x0} {y0}) (end {x1} {y1}) (stroke (width {w}) (type solid)) '
            f'(fill {fill}) (layer "{layer}") (uuid "{U(f"gr/{layer}/{x0},{y0}")}"))')

def gr_text(txt, x, y, layer="F.SilkS", size=1.0, angle=0, justify=None):
    j = f' (justify {justify})' if justify else ''
    return (f'\t(gr_text "{txt}" (at {x} {y} {angle}) (layer "{layer}") '
            f'(effects (font (size {size} {size}) (thickness 0.15)){j}) (uuid "{U(f"txt/{x},{y}/{txt[:8]}")}"))')

HUB_FP_DEF = [
    # 左边缘: USB-C(朝左插) / 电源开关 / 电池座 / 心率探头FPC(线均出左边)
    ("J1",  4.7, 14.0,  90, None, False),
    ("SW1", 5.0, 20.5,  90, None, False),
    ("J2",  4.2, 27.5,  90, None, False),
    ("J30", 4.6, 37.0, 270, None, False),
    # USB 输入保护 + 充电
    ("U1", 12.7,  9.5,   0, None, False),
    ("R1",  9.5,  6.4,   0, None, False),
    ("R2",  9.5,  7.7,   0, None, False),
    ("D1", 11.4, 14.0,   0, None, False),
    ("F1", 11.4, 20.3,   0, None, False),
    ("U2", 17.8, 24.1,   0, None, False),
    ("R3", 21.0, 27.9,  90, None, False),
    ("C1", 16.5, 19.7,  90, None, False),
    ("C2",  8.3, 34.9,   0, None, False),
    ("R4", 14.0, 28.6,   0, None, False),
    ("D2",  8.3, 28.6,   0, None, False),
    ("R5", 14.0, 31.1,   0, None, False),
    ("D3",  8.3, 31.1,   0, None, False),
    # buck-boost 3.3V
    ("U3", 26.7, 25.4,   0, None, False),
    ("L1", 26.7, 19.7,   0, None, False),
    ("C3", 21.6, 22.2,  90, None, False),
    ("C4", 21.6, 20.3,  90, None, False),
    ("C5", 32.4, 21.6,  90, None, False),
    ("C6", 32.4, 19.7,  90, None, False),
    ("C7", 31.1, 28.6,   0, None, False),
    # 电量计 + 电池分压
    ("U4", 32.4, 32.4,   0, {"9": "GND"}, False),
    ("C8", 36.2, 32.4,   0, None, False),
    ("R6", 17.5, 30.4,  90, None, False),
    ("R7", 17.5, 32.2,  90, None, False),
    ("C9", 20.1, 32.2,   0, None, False),
    # 音频: 功放(板载) + 去耦 + 关断下拉
    ("U40", 15.5, 15.5,  0, None, False),
    ("C17", 19.0, 15.5,  0, None, False),
    ("C18", 20.5, 17.0,  0, None, False),
    ("R14", 13.8, 18.0,  0, None, False),
    # 1.8V LDO (心率探头供电)
    ("U30", 34.5, 25.5,  0, None, False),
    ("C15", 33.5, 23.3,  0, None, False),
    ("C16", 36.0, 23.3,  0, None, False),
    ("R13", 34.5, 28.0,  0, None, False),
    # 主控 + 支路
    ("U10", 51.4, 21.6,  0, None, False),
    ("C10", 40.5, 19.0,  0, None, False),
    ("C11", 40.5, 20.5,  0, None, False),
    ("R8",  40.5, 22.5,  0, None, False),
    ("C12", 40.5, 24.0,  0, None, False),
    ("R9",  53.8, 35.8,  0, None, False),
    ("D4",  56.0, 35.8,  0, None, False),
    # 按键
    ("SW2", 24.0, 10.5,  0, None, False),
    ("SW3", 17.5, 10.5,  0, None, False),
    # I2C 复用器 + 上拉
    ("U20", 38.1, 12.7,  0, None, False),
    ("R10", 42.5,  6.4, 90, None, False),
    ("R11", 45.1,  6.4, 90, None, False),
    ("R12", 40.5, 17.0,  0, None, False),
    ("C13", 34.3,  7.0, 90, None, False),
    ("C14", 36.2,  7.0, 90, None, False),
    # 底边 FPC: IMU1-4 (线出下边)
    ("J21", 14.0, 37.5,  0, None, False),
    ("J22", 25.0, 37.5,  0, None, False),
    ("J23", 36.0, 37.5,  0, None, False),
    ("J24", 47.0, 37.5,  0, None, False),
    # 顶边 FPC: IMU5/6/预留 + 麦克风 + GPS + OLED (线出上边)
    ("J25",  8.0,  4.5, 180, None, False),
    ("J26", 19.0,  4.5, 180, None, False),
    ("J27", 30.0,  4.5, 180, None, False),
    ("J41", 40.0,  4.5, 180, None, False),
    ("C19", 49.0,  7.9,  0, None, False),
    ("J50", 49.0,  4.5, 180, None, False),
    ("J51", 56.8,  4.5, 180, None, False),
    # 喇叭座(线经底边出) + 调试口(开发时手工焊, DNP)
    ("J40", 27.5, 33.8,  0, None, False),
    ("J10", 53.5, 39.0,  90, None, True),
    # 测试点 (主控左侧立柱)
    ("TP1", 41.2, 26.0, 0, None, False),
    ("TP2", 41.2, 28.0, 0, None, False),
    ("TP3", 41.2, 30.0, 0, None, False),
    ("TP4", 41.2, 32.0, 0, None, False),
    ("TP5", 40.6, 35.8, 0, None, False),
]
HUB_HOLES = [(3.5, 3.5), (58.5, 3.5), (3.5, 39.5), (59.2, 36.5)]

NODE_FP_DEF = [
    ("U1", 7.0, 4.4, 0, None, False),
    ("C1", 4.4, 2.2, 90, None, False),
    ("C2", 9.6, 2.2, 90, None, False),
    ("J1", 7.0, 7.9, 0, None, False),
]

def emit_pcb(project, title, comps_by_ref, fp_defs, holes, W, H, outpath):
    nets = build_netindex([{n for c in comps_by_ref.values() for n in c.nets.values()} - {"NC"}])
    L = []
    L.append('(kicad_pcb (version 20260206) (generator "petvest_gen") (generator_version "1.0")')
    L.append('\t(general (thickness 1.6) (legacy_teardrops no))')
    L.append('\t(paper "A4")')
    L.append(f'\t(title_block (title "{title}") (date "2026-11-07") (rev "A"))')
    L.append('\t(layers')
    L.append('\t\t(0 "F.Cu" signal)\n\t\t(31 "B.Cu" signal)\n\t\t(37 "F.CrtYd" user)\n\t\t(39 "F.Fab" user)')
    L.append('\t\t(35 "F.Paste" user)\n\t\t(33 "F.Mask" user)\n\t\t(36 "B.SilkS" user "B.Silkscreen")\n\t\t(34 "B.Paste" user)')
    L.append('\t\t(32 "B.Mask" user)\n\t\t(5 "F.SilkS" user "F.Silkscreen")\n\t\t(44 "Edge.Cuts" user)\n\t\t(40 "F.Adhes" user "F.Adhesive")')
    L.append('\t\t(41 "B.Adhes" user "B.Adhesive")\n\t\t(43 "F.CrtYd" user)\n\t\t(42 "B.CrtYd" user)')
    L.append('\t)')
    L.append('\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))')
    for n, i in sorted(nets.items(), key=lambda kv: kv[1]):
        L.append(f'\t(net {i} "{n}")')
    # 板框
    L.append(gr_rect("Edge.Cuts", 0, 0, W, H))
    # 安装孔/缝纫孔
    for hx, hy in holes:
        raw = load_fp("MountingHole", "MountingHole_2.7mm")
        m = re.match(r'\(footprint "([^"]+)"', raw)
        blk = raw.replace(f'(footprint "{m.group(1)}"', '(footprint "MountingHole:MountingHole_2.7mm"', 1)
        if '\n\t(layer "F.Cu")\n' not in blk:
            blk = re.sub(r'(\(footprint "[^"]+"\n)', r'\g<1>\t(layer "F.Cu")\n', blk, count=1)
        a = blk.find('\n\t(layer "F.Cu")\n')
        blk = blk[:a] + blk[a:].replace('\n\t(layer "F.Cu")\n', '\n\t(layer "F.Cu")\n\t(at ' + f'{hx} {hy} 0)\n', 1)
        blk = blk.replace('(property "Reference" "REF**"', '(property "Reference" "H"', 1)
        L.append('\t' + blk.replace('\n\t', '\n\t\t').rstrip())
    # 元件
    for ref, x, y, rot, extra, dnp in fp_defs:
        c = comps_by_ref[ref]
        L.append('\t' + place_fp(c, x, y, rot, nets, extra, dnp=dnp))
    # 完整性检查: 原理图所有元件都必须在PCB上
    missing = set(comps_by_ref) - {r for r, *_ in fp_defs}
    assert not missing, f"PCB缺少封装: {sorted(missing)}"
    # 天线净空标注 (ESP32 右侧)
    L.append(gr_rect("F.CrtYd", 42.0, 8.0, W - 1.0, 15.5, w=0.15))
    L.append(gr_text("ANTENNA KEEPOUT", 51.4, 17.2, "F.SilkS", 0.7))
    L.append(gr_text("PetVest Hub rev.A", 26.5, 9.4, "F.SilkS", 1.2))
    L.append(gr_text("62x42mm 2L / ratsnest only", 26.5, 10.9, "F.SilkS", 0.75))
    L.append(')')
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f"wrote {outpath}  ({len(fp_defs)} footprints, {len(nets)} nets)")

def main():
    sheets, node = G.build_bom_model() if hasattr(G, "build_bom_model") else (None, None)
    # 直接复用 gen_schematic 的模型构建
    libx = G.LibIndex()
    for lib, names in {
        "RF_Module": ["ESP32-S3-WROOM-1"], "Battery_Management": ["TP4056-42-ESOP8"],
        "Regulator_Switching": ["TPS63061"], "Interface_Expansion": ["TCA9548APWR"],
        "Audio": ["MAX98357A"], "Power_Protection": ["USBLC6-2SC6"],
        "Regulator_Linear": ["AP2112K-1.8"],
        "Device": ["R", "C", "LED", "L", "Polyfuse", "D_TVS"],
        "Switch": ["SW_Push", "SW_SPDT"],
        "Connector": ["USB_C_Receptacle_USB2.0_16P", "TestPoint"],
        "Connector_Generic": ["Conn_01x02", "Conn_01x04", "Conn_01x05", "Conn_01x06"],
        "power": ["GND", "+3V3", "+BATT", "VBUS", "+1V8", "PWR_FLAG"],
        "Sensor_Motion": ["LSM6DS3"],
    }.items():
        libx.load(lib, names)
    max_raw = G.box_symbol("MAX17048G", "MAX17048",
        [("1", "VDD", "power_in"), ("2", "GND", "power_in"),
         ("3", "SDA", "bidirectional"), ("4", "SCL", "input")],
        [("5", "ALERT", "output")])
    md = G.SymDef("petvest", "MAX17048G", max_raw, None)
    for pm in G.PIN_RE.finditer(max_raw):
        et, x, y, rot, name, num = pm.groups()
        md.pins.append((num, name, float(x), float(y), int(rot), et))
    libx.defs[("petvest", "MAX17048G")] = md
    libx.extract_pins_all()
    sheets = G.build_hub()
    for s in sheets:
        s.resolve(libx)
    node = G.build_imu_node(libx, max_raw)
    hub_comps = {c.ref: c for s in sheets for c in s.comps}
    node_comps = {c.ref: c for c in node.comps}
    outdir = os.path.join(G.OUT, "petvest-hub")
    emit_pcb("petvest-hub", "PetVest 主控Hub板", hub_comps, HUB_FP_DEF, HUB_HOLES, 62.0, 42.0,
             os.path.join(outdir, "petvest-hub.kicad_pcb"))
    outdir2 = os.path.join(G.OUT, "petvest-imu-node")
    emit_pcb("petvest-imu-node", "PetVest IMU卫星节点", node_comps, NODE_FP_DEF, [(2.4, 5.0), (11.6, 5.0)], 14.0, 10.0,
             os.path.join(outdir2, "petvest-imu-node.kicad_pcb"))

if __name__ == "__main__":
    main()
