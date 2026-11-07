#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PetVest 宠物智能服装 — KiCad 原理图生成器
生成: kicad/petvest-hub (分层原理图 6 张) + kicad/petvest-imu-node (IMU卫星节点)

方法: 从 KiCad 官方符号库提取符号定义嵌入 lib_symbols; 引脚通过全局标签/
电源符号连接(无需布线); 输出 KiCad 9/10 (version 20250114) 格式。
"""
import os, re, csv, json, uuid

KLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "kicad")
NS   = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def U(name):
    return str(uuid.uuid5(NS, name))

# ---------------------------------------------------------------- sexpr helpers
def find_def(src, sym_name):
    pat = '\n\t(symbol "' + sym_name + '"'
    i = src.find(pat)
    if i < 0:
        return None
    i += 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '(':
            depth += 1
        elif src[j] == ')':
            depth -= 1
            if depth == 0:
                return src[i:j+1].lstrip()
    return None

PIN_RE = re.compile(
    r'\(pin (\w+ \w+)\s*\(at (-?[\d.]+) (-?[\d.]+) (-?\d+)\)\s*\(length [\d.]+\)'
    r'[\s\S]*?\(name "([^"]*)"[\s\S]*?\(number "([^"]*)"')

def norm_pin(n):
    return n.replace("~{", "").replace("{", "").replace("}", "").upper()

class SymDef:
    def __init__(self, lib, name, raw, extends):
        self.lib, self.name, self.raw, self.extends = lib, name, raw, extends
        self.pins = []  # (num, name, x, y, rot, etype)
    def pinmaps(self):
        by_name, by_num = {}, {}
        for num, name, x, y, rot, et in self.pins:
            by_name.setdefault(norm_pin(name), (num, x, y, rot, et))
            by_num[num] = (num, x, y, rot, et)
        return by_name, by_num
    def pins_for_key(self, key):
        """all pin entries matching normalized-name key or pin number"""
        by_name, by_num = self.pinmaps()
        if key in by_num:
            return [by_num[key]]
        if key in by_name:
            nm = by_name[key]
            hits = [(p[0], p[2], p[3], p[4], p[5]) for p in self.pins
                    if norm_pin(p[1]) == key]
            return hits or [nm]
        return None
    def all_pin_nums(self):
        return sorted({p[0] for p in self.pins}, key=lambda s: (len(s), s))
    def bbox(self):
        xs = [p[2] for p in self.pins]; ys = [p[3] for p in self.pins]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else (-10, -10, 10, 10)

class LibIndex:
    def __init__(self):
        self.defs = {}
        self.cache = {}
    def load(self, libnick, names):
        path = os.path.join(KLIB, libnick + ".kicad_sym")
        if libnick not in self.cache:
            self.cache[libnick] = open(path, encoding="utf-8").read()
        src = self.cache[libnick]
        out = []
        for n in names:
            key = (libnick, n)
            if key not in self.defs:
                raw = find_def(src, n)
                if raw is None:
                    raise RuntimeError(f"symbol not found: {libnick}:{n}")
                ext = re.search(r'\(extends "([^"]+)"\)', raw)
                d = SymDef(libnick, n, raw, ext.group(1) if ext else None)
                self.defs[key] = d
                if d.extends:
                    self.load(libnick, [d.extends])
            out.append(self.defs[key])
        return out
    def extract_pins_all(self):
        for d in self.defs.values():
            if d.pins:
                continue
            if d.extends:
                d.pins = self.defs[(d.lib, d.extends)].pins
                continue
            for m in re.finditer(r'\(symbol "' + re.escape(d.name) + r'_(\d+)_(\d+)"', d.raw):
                i = d.raw.rfind('(', 0, m.start() + 1)
                depth = 0
                for j in range(i, len(d.raw)):
                    if d.raw[j] == '(':
                        depth += 1
                    elif d.raw[j] == ')':
                        depth -= 1
                        if depth == 0:
                            sub = d.raw[i:j+1]
                            break
                for pm in PIN_RE.finditer(sub):
                    et, x, y, rot, name, num = pm.groups()
                    d.pins.append((num, name, float(x), float(y), int(rot), et))
            if not d.pins:
                for pm in PIN_RE.finditer(d.raw):
                    et, x, y, rot, name, num = pm.groups()
                    d.pins.append((num, name, float(x), float(y), int(rot), et))

def box_symbol(name, value, left, right):
    """left/right: [(pinnum, pinname, etype)]"""
    n = max(len(left), len(right))
    hh = max(12.7, (n + 1) * 2.54 / 2 + 2.54)
    unit1 = []
    def pin_text(num, pname, et, x, y, rot):
        return (f'(pin {et} line (at {x} {y} {rot}) (length 2.54) '
                f'(name "{pname}" (effects (font (size 1.27 1.27)))) '
                f'(number "{num}" (effects (font (size 1.27 1.27)))))')
    for side, items in (("L", left), ("R", right)):
        y0 = ((len(items) - 1) * 2.54) / 2
        for i, (num, pname, et) in enumerate(items):
            x = -hh if side == "L" else hh
            rot = 0 if side == "L" else 180
            unit1.append(pin_text(num, pname, et, x, y0 - i * 2.54, rot))
    unit1.append(f'(rectangle (start {-hh} {hh}) (end {hh} {-hh}) '
                 f'(stroke (width 0.254) (type default)) (fill (type background)))')
    return (f'(symbol "{name}"\n(pin_names (offset 1.016))\n(exclude_from_sim no) (in_bom yes) (on_board yes)\n'
            f'(property "Reference" "U" (at 0 {hh+2.54} 0) (effects (font (size 1.27 1.27))))\n'
            f'(property "Value" "{value}" (at 0 {-hh-2.54} 0) (effects (font (size 1.27 1.27))))\n'
            f'(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'(symbol "{name}_0_1" {unit1[-1]})\n(symbol "{name}_1_1" {" ".join(unit1[:-1])})\n)')

# ---------------------------------------------------------------- model
POWER_SYMBOL_LIBS = {"GND": "power:GND", "+3V3": "power:+3V3", "+BATT": "power:+BATT",
                     "VBUS": "power:VBUS", "+1V8": "power:+1V8"}

class Comp:
    def __init__(self, ref, lib, sym, value, fp, x, y, nets=None, dnp=False, desc=""):
        self.ref, self.lib, self.sym, self.value = ref, lib, sym, value
        self.fp, self.x, self.y = fp, x, y
        self.nets = nets or {}
        self.dnp, self.desc = dnp, desc
        self.sd = None

class Sheet:
    def __init__(self, fname, sname, title, tag):
        self.fname, self.sname, self.title, self.tag = fname, sname, title, tag
        self.comps, self.texts, self.flags = [], [], []
        self.pwr, self.labels, self.ncs, self.wires = [], [], [], []
        self.pwr_syms, self.flag_syms = [], []
        self.uuid = U("petvest-hub/" + fname)
        self._pwri = 0
        self._flgi = 0

    def add(self, *comps):
        self.comps.extend(comps)
        return comps
    def text(self, x, y, s, size=1.5):
        self.texts.append((x, y, s, size))
    def pwrflag(self, net, x, y):
        self.flags.append((net, x, y))

    def resolve(self, libx):
        for c in self.comps:
            c.x = round(c.x / 1.27) * 1.27
            c.y = round(c.y / 1.27) * 1.27
            c.sd = libx.defs[(c.lib, c.sym)]
        for c in self.comps:
            for key, net in c.nets.items():
                entries = c.sd.pins_for_key(key)
                if not entries:
                    raise RuntimeError(f"{c.ref} ({c.lib}:{c.sym}): pin '{key}' not found")
                for num, px, py, prot, et in entries:
                    ax, ay = c.x + px, c.y - py  # 画布Y向下: 库内y需取反
                    if net == "NC":
                        self.ncs.append((ax, ay, f"{c.ref}p{num}"))
                    elif net in POWER_SYMBOL_LIBS:
                        self.pwr.append((net, ax, ay, prot))
                    else:
                        # 画布角度: 上边引脚(rot270)→标签向上(90); 下边(rot90)→270
                        lrot = {0: 180, 180: 0, 270: 90, 90: 270}[prot]
                        self.labels.append((net, ax, ay, lrot))
        # power symbols (dedupe per coordinate), offset outward + wire
        seen = set()
        for net, ax, ay, prot in sorted(self.pwr):
            if (net, ax, ay) in seen:
                continue
            seen.add((net, ax, ay))
            ox, oy = {0: (-5.08, 0), 180: (5.08, 0), 270: (0, -5.08), 90: (0, 5.08)}[prot]
            srot = 0
            if net == "GND" and prot == 270: srot = 180
            elif net != "GND" and prot == 90: srot = 180
            self._pwri += 1
            self.wires.append((ax, ay, ax + ox, ay + oy))
            self.pwr_syms.append((net, ax + ox, ay + oy, srot,
                                  f"#PWR{self.tag*100 + self._pwri:03d}"))
        # PWR_FLAG: 库电源网络→叠在专用电源符号上; 其他网络→挂到同网全局标签锚点
        label_pos = {}
        for net, x, y, rot in self.labels:
            label_pos.setdefault(net, []).append((x, y))
        for net, x, y in self.flags:
            x = round(x / 1.27) * 1.27
            y = round(y / 1.27) * 1.27
            self._flgi += 1
            ref = f"#FLG{self.tag * 10 + self._flgi}"
            if net in POWER_SYMBOL_LIBS:
                self.pwr_syms.append((net, x, y, 0, f"#PWR{self.tag*100 + 90 + self._flgi:03d}"))
                self.flag_syms.append((ref, x + 2.54, y))
                self.wires.append((x, y, x + 2.54, y))
            else:
                pts = label_pos.get(net)
                if pts:
                    self.flag_syms.append((ref, pts[0][0], pts[0][1]))
                else:
                    self.labels.append((net, x, y, 180))
                    self.flag_syms.append((ref, x, y))

# ---------------------------------------------------------------- emitter
def esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

def emit_symbol_instance(c, project, path):
    d = c.sd
    bx0, by0, bx1, by1 = d.bbox()
    L = ['(symbol',
         f'\t(lib_id "{c.lib}:{c.sym}")',
         f'\t(at {c.x} {c.y} 0)', '\t(unit 1)',
         '\t(exclude_from_sim no)', '\t(in_bom yes)', '\t(on_board yes)',
         f'\t(dnp {"yes" if c.dnp else "no"})',
         f'\t(uuid "{U("sym/" + c.ref + "/" + path)}")',
         f'\t(property "Reference" "{c.ref}" (at {c.x} {c.y + by0 - 2.54} 0) (effects (font (size 1.27 1.27))))',
         f'\t(property "Value" "{esc(c.value)}" (at {c.x} {c.y + by1 + 2.54} 0) (effects (font (size 1.27 1.27))))',
         f'\t(property "Footprint" "{c.fp}" (at {c.x} {c.y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
         f'\t(property "Datasheet" "~" (at {c.x} {c.y} 0) (effects (font (size 1.27 1.27)) (hide yes)))']
    for num in d.all_pin_nums():
        L.append(f'\t(pin "{num}" (uuid "{U(f"pin/{c.ref}/{num}/{path}")}"))')
    L.append(f'\t(instances (project "{project}" (path "{path}" (reference "{c.ref}") (unit 1))))')
    L.append(')')
    return '\n'.join(L)

def emit_pwr_instance(net, x, y, rot, ref, path, project):
    lib = POWER_SYMBOL_LIBS[net]
    ry = y + (-2.54 if net != "GND" else 2.54)
    return '\n'.join([
        '(symbol',
        f'\t(lib_id "{lib}")', f'\t(at {x} {y} {rot})', '\t(unit 1)',
        '\t(exclude_from_sim no)', '\t(in_bom yes)', '\t(on_board yes)', '\t(dnp no)',
        f'\t(uuid "{U(f"pwr/{ref}/{net}/{path}")}")',
        f'\t(property "Reference" "{ref}" (at {ry} {ry} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(property "Value" "{net}" (at {x} {y + (2.54 if net != "GND" else -2.54)} 0) (effects (font (size 1.27 1.27))))',
        f'\t(property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(pin "1" (uuid "{U(f"pwrpin/{ref}/{net}/{path}")}"))',
        f'\t(instances (project "{project}" (path "{path}" (reference "{ref}") (unit 1))))', ')'])

def emit_flag_instance(ref, x, y, path, project):
    return '\n'.join([
        '(symbol',
        '\t(lib_id "power:PWR_FLAG")', f'\t(at {x} {y} 0)', '\t(unit 1)',
        '\t(exclude_from_sim no)', '\t(in_bom yes)', '\t(on_board yes)', '\t(dnp no)',
        f'\t(uuid "{U(f"flag/{ref}/{path}")}")',
        f'\t(property "Reference" "{ref}" (at {x} {y-3.81} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(property "Value" "PWR_FLAG" (at {x} {y-1.27} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(property "Datasheet" "~" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        f'\t(pin "1" (uuid "{U(f"flagpin/{ref}/{path}")}"))',
        f'\t(instances (project "{project}" (path "{path}" (reference "{ref}") (unit 1))))', ')'])

def rename_def(raw, newname):
    """顶层 def 改名为 Nick:Name; 子定义保持裸名 (KiCad 规范)"""
    m = re.match(r'\(symbol "([^"]+)"', raw)
    old = m.group(1)
    return raw.replace(f'(symbol "{old}"', f'(symbol "{newname}"', 1)

def materialize_def(child_raw, parent_raw, newname):
    """extends 符号物化: 父定义改名(顶层带前缀, 子定义用子符号裸名) + 子属性值覆盖"""
    out = parent_raw
    m = re.match(r'\(symbol "([^"]+)"', out)
    pname = m.group(1)
    bare = newname.split(":")[-1]
    out = out.replace(f'(symbol "{pname}"', f'(symbol "{newname}"', 1)
    out = out.replace(f'(symbol "{pname}_', f'(symbol "{bare}_')
    for prop in ("Value", "Datasheet", "Description"):
        cm = re.search(r'\(property "%s" "([^"]*)"' % prop, child_raw)
        if cm:
            out = re.sub(r'(\(property "%s" )"[^"]*"' % prop,
                         lambda mm, v=cm.group(1): mm.group(1) + '"%s"' % v, out, count=1)
    return out

def emit_sheet(sh, project, root_uuid, libx, extra_libsyms, outdir):
    libsyms = {}
    for c in sh.comps:
        d = c.sd
        full = f"{c.lib}:{c.sym}"
        if d.extends:
            parent = libx.defs[(c.lib, d.extends)]
            libsyms[full] = materialize_def(d.raw, parent.raw, full)
        else:
            libsyms[full] = rename_def(d.raw, full)
    for net, *_ in sh.pwr_syms:
        if net in POWER_SYMBOL_LIBS:
            full = POWER_SYMBOL_LIBS[net]
            libsyms[full] = rename_def(libx.defs[(full.split(":")[0], full.split(":")[1])].raw, full)
    libsyms.update(extra_libsyms)
    if sh.flag_syms:
        libsyms["power:PWR_FLAG"] = rename_def(libx.defs[("power", "PWR_FLAG")].raw, "power:PWR_FLAG")
    path = "/" + root_uuid + "/" + sh.uuid
    L = ['(kicad_sch',
         '\t(version 20250114)',
         '\t(generator "petvest_gen")',
         '\t(generator_version "1.0")',
         f'\t(uuid "{sh.uuid}")',
         '\t(paper "A3")',
         f'\t(title_block (title "{esc(sh.title)}") (date "2026-11-07") (rev "A") (company "PetVest 智能宠物服装") (comment 1 "tools/gen_schematic.py 自动生成"))',
         '\t(lib_symbols']
    L += ['\t\t' + raw.replace('\n', '\n\t\t') for raw in libsyms.values()]
    L.append('\t)')
    for x1, y1, x2, y2 in sh.wires:
        L.append(f'\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{U(f"wire/{x1},{y1}-{x2},{y2}/{path}")}"))')
    for net, x, y, rot in sh.labels:
        L.append(f'\t(global_label "{esc(net)}" (shape passive) (at {x} {y} {rot})'
                 f' (effects (font (size 1.27 1.27)) (justify left)) (uuid "{U(f"lbl/{net}/{x},{y}/{path}")}"))')
    for x, y, tag in sh.ncs:
        L.append(f'\t(no_connect (at {x} {y}) (uuid "{U(f"nc/{x},{y}/{tag}/{path}")}"))')
    for net, x, y, rot, ref in sh.pwr_syms:
        L.append(emit_pwr_instance(net, x, y, rot, ref, path, project))
    for ref, x, y in sh.flag_syms:
        L.append(emit_flag_instance(ref, x, y, path, project))
    for c in sh.comps:
        L.append(emit_symbol_instance(c, project, path))
    for x, y, s, size in sh.texts:
        L.append(f'\t(text "{esc(s)}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {size} {size})) (justify left bottom)) (uuid "{U(f"text/{x},{y}/{path}")}"))')
    L.append(')')
    with open(os.path.join(outdir, sh.fname), 'w', encoding="utf-8") as f:
        f.write('\n'.join(L))
    return path

def emit_root(project, root_file, sheets, outdir):
    root_uuid = U("petvest-hub/root")
    L = ['(kicad_sch', '\t(version 20250114)', '\t(generator "petvest_gen")',
         '\t(generator_version "1.0")', f'\t(uuid "{root_uuid}")', '\t(paper "A3")',
         '\t(title_block (title "PetVest 智能宠物服装 · 主控Hub板") (date "2026-11-07") (rev "A") (company "PetVest") (comment 1 "1S锂电 / ESP32-S3 / 6路IMU / I2S音频 / GNSS / 心率"))',
         '\t(lib_symbols', '\t)']
    pos = [(40, 45), (255, 45), (40, 135), (255, 135), (40, 225), (255, 225)]
    for i, sh in enumerate(sheets):
        x, y = pos[i]
        L.append(f'\t(sheet (at {x} {y}) (size 90 60) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000))')
        L.append(f'\t\t(uuid "{sh.uuid}")')
        L.append(f'\t\t(property "Sheetname" "{sh.sname}" (at {x} {y - 2.54} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))')
        L.append(f'\t\t(property "Sheetfile" "{sh.fname}" (at {x} {y + 62.54} 0) (effects (font (size 1.27 1.27)) (justify left top)))')
        L.append(f'\t\t(instances (project "{project}" (path "/{root_uuid}" (page "{i + 2}"))))')
        L.append('\t)')
    L.append(f'\t(text "PetVest Hub: 各图纸间用全局标签连接 (I2C_SDA/I2C_SCL/I2S_*/IMU_INT*/GPS_*/USB_DP…)" (exclude_from_sim no) (at 40 28 0) (effects (font (size 2 2)) (justify left bottom)) (uuid "{U("text/root-note")}"))')
    L.append(')')
    with open(os.path.join(outdir, root_file), 'w', encoding="utf-8") as f:
        f.write('\n'.join(L))
    return root_uuid

def write_pro(project, outdir, sheets, root_uuid):
    pro = {
        "board": {}, "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": project + ".kicad_pro", "version": 3},
        "net_settings": {"classes": [{"bus_width": 12, "clearance": 0.2, "diff_pair_gap": 0.25,
                                      "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
                                      "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Default",
                                      "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                                      "track_width": 0.2, "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6}],
                         "meta": {"version": 4}},
        "schematic": {"annotate_start_num": 0, "legacy_lib_dir": "", "legacy_lib_list": [],
                      "meta": {"version": 1}, "net_format_version": 2, "page_layout_descr_file": "",
                      "plot_directory": "", "spice_save_all_currents": False,
                      "subpart_first_id": 65, "subpart_id_separator": 0},
        "sheets": [[root_uuid, "Root"]] + [[s.uuid, s.sname] for s in sheets],
        "text_variables": {}
    }
    with open(os.path.join(outdir, project + ".kicad_pro"), "w", encoding="utf-8") as f:
        json.dump(pro, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- helpers
def R(ref, val, x, y, n1, n2, fp="Resistor_SMD:R_0603_1608Metric", desc=""):
    return Comp(ref, "Device", "R", val, fp, x, y, {"1": n1, "2": n2}, desc=desc)
def C(ref, val, x, y, n1, n2, fp="Capacitor_SMD:C_0603_1608Metric", desc=""):
    return Comp(ref, "Device", "C", val, fp, x, y, {"1": n1, "2": n2}, desc=desc)
def LED(ref, val, x, y, nA, nK, desc=""):
    return Comp(ref, "Device", "LED", val, "LED_SMD:LED_0603_1608Metric", x, y,
                {"2": nA, "1": nK}, desc=desc)
def CONN(ref, n, x, y, netmap, fp, desc=""):
    nets = {f"PIN_{i+1}": netmap[i] for i in range(len(netmap))}
    return Comp(ref, "Connector_Generic", f"Conn_01x0{n}", f"Conn_01x0{n}", fp, x, y, nets, desc=desc)
FPC = lambda n: f"Connector_FFC-FPC:TE_84953-{n}_1x0{n}-1MP_P1.0mm_Horizontal"

# ================================================================ HUB
def build_hub():
    sheets = []
    # ---------------- 01 POWER ----------------
    s = Sheet("01_power.kicad_sch", "01_Power", "电源: USB-C充电 / 1S锂电 / 3.3V buck-boost / 电量计", 1)
    s.add(Comp("J1", "Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C 16P",
               "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 45, 60,
               {"CC1": "NET_CC1", "CC2": "NET_CC2", "D+": "USB_DP_C", "D-": "USB_DM_C",
                "VBUS": "VBUS", "GND": "GND", "SHIELD": "GND", "SBU1": "NC", "SBU2": "NC"}, desc="USB-C 16P"))
    s.add(R("R1", "5.1k", 75, 55, "NET_CC1", "GND"), R("R2", "5.1k", 75, 65, "NET_CC2", "GND"))
    s.text(28, 33, "USB-C: CC1/CC2 5.1k下拉声明默认5V供电; D+/D-经USBLC6 ESD后接ESP32-S3原生USB(IO19/20)", 1.4)
    s.add(Comp("F1", "Device", "Polyfuse", "2A/9V", "Fuse:Fuse_1812_4532Metric", 105, 40,
               {"1": "VBUS", "2": "VBUS_F"}, desc="PTC自恢复保险丝 2A"))
    s.add(Comp("D1", "Device", "D_TVS", "PESD5V0S1BA", "Diode_SMD:D_SOD-323", 105, 52,
               {"1": "VBUS", "2": "GND"}, desc="VBUS TVS 5V"))
    s.add(Comp("U1", "Power_Protection", "USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", 105, 75,
               {"1": "USB_DP", "6": "USB_DP_C", "3": "USB_DM", "4": "USB_DM_C", "2": "GND", "5": "VBUS"},
               desc="USB D+/D- ESD (流穿式: 左=MCU侧, 右=连接器侧)"))
    s.add(Comp("U2", "Battery_Management", "TP4056-42-ESOP8", "TP4056",
               "Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm", 150, 68,
               {"4": "VBUS_F", "BAT": "+BATT", "PROG": "NET_PROG", "TEMP": "GND",
                "CHRG": "NET_CHRG", "STDBY": "NET_STDY", "CE": "VBUS_F", "GND": "GND", "EPAD": "GND"},
               desc="1A锂电池充电"))
    s.add(R("R3", "1.2k", 178, 80, "NET_PROG", "GND"))
    s.add(R("R4", "1k", 120, 95, "VBUS_F", "NET_LCHG_A"), LED("D2", "红·充电中", 137, 95, "NET_LCHG_A", "NET_CHRG"))
    s.add(R("R5", "1k", 120, 107, "VBUS_F", "NET_LSTD_A"), LED("D3", "绿·已充满", 137, 107, "NET_LSTD_A", "NET_STDY"))
    s.add(C("C1", "10µF", 120, 118, "VBUS_F", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.text(140, 42, "TP4056: R3=1.2k → 充电1A; TEMP接地禁用温度检测(电池包自带PCM); CE接VBUS_F=插USB即充", 1.4)
    s.add(Comp("J2", "Connector_Generic", "Conn_01x02", "1S 4000mAh",
               "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal", 45, 135,
               {"PIN_1": "+BATT", "PIN_2": "GND"}, desc="锂电池(必须带保护板PCM)"))
    s.add(C("C2", "10µF", 70, 150, "+BATT", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(Comp("SW1", "Switch", "SW_SPDT", "POWER", "Button_Switch_SMD:SW_SPDT_PCM12", 100, 135,
               {"1": "+BATT", "2": "VSW", "3": "NC"}, desc="电源开关"))
    s.add(Comp("U3", "Regulator_Switching", "TPS63061", "TPS63061", "Package_SON:Texas_DRC0010J", 175, 135,
               {"VIN": "VSW", "EN": "VSW", "GND": "GND", "PGND": "GND", "L1": "NET_L1", "L2": "NET_L2",
                "VOUT": "+3V3", "FB": "+3V3", "VAUX": "NET_VAUX", "PS/SYNC": "GND", "PG": "NC"},
               desc="buck-boost 3.3V/1.2A"))
    s.add(Comp("L1", "Device", "L", "1.5µH 3.5A", "Inductor_SMD:L_Bourns-SRN4018", 175, 110,
               {"1": "NET_L1", "2": "NET_L2"}, desc="功率电感"))
    s.add(C("C3", "22µF", 148, 112, "VSW", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C4", "22µF", 148, 122, "VSW", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C5", "22µF", 205, 112, "+3V3", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C6", "22µF", 205, 122, "+3V3", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C7", "100nF", 200, 148, "NET_VAUX", "GND"))
    s.text(145, 95, "TPS63061: 2.9-4.5V输入→固定3.3V/1.2A; PS/SYNC=GND自动PFM; FB接VOUT", 1.4)
    s.add(Comp("U4", "petvest", "MAX17048G", "MAX17048", "Package_DFN_QFN:DFN-8-1EP_2x2mm_P0.5mm_EP0.9x1.3mm", 255, 135,
               {"VDD": "+BATT", "GND": "GND", "SDA": "I2C_SDA", "SCL": "I2C_SCL", "ALERT": "NC"},
               desc="电量计 I2C 0x36 (待验证封装)"))
    s.add(C("C8", "100nF", 275, 125, "+BATT", "GND"))
    s.add(R("R6", "100k", 45, 180, "+BATT", "NET_BATADC"), R("R7", "100k", 45, 195, "NET_BATADC", "GND"),
          C("C9", "100nF", 70, 195, "NET_BATADC", "GND"))
    s.add(Comp("TP1", "Connector", "TestPoint", "3V3", "TestPoint:TestPoint_Pad_D1.5mm", 250, 180, {"1": "+3V3"}),
          Comp("TP2", "Connector", "TestPoint", "GND", "TestPoint:TestPoint_Pad_D1.5mm", 262, 180, {"1": "GND"}),
          Comp("TP3", "Connector", "TestPoint", "BATT", "TestPoint:TestPoint_Pad_D1.5mm", 274, 180, {"1": "+BATT"}),
          Comp("TP4", "Connector", "TestPoint", "VBUS", "TestPoint:TestPoint_Pad_D1.5mm", 286, 180, {"1": "VBUS"}))
    s.pwrflag("VBUS", 100, 28)
    s.pwrflag("VBUS_F", 128, 40)
    s.pwrflag("VSW", 122, 135)
    s.pwrflag("GND", 300, 160)
    s.text(240, 18,
           "电源预算(18h续航目标, 1S 4000mAh≈14.8Wh):\n"
           "  ESP32-S3 WiFi间歇上报 ~80mA | GNSS ~40mA | 6×IMU@104Hz ~5mA\n"
           "  OLED ~12mA | 心率(占空比) ~3mA | 音频待机 ~1mA | 电量计/漏 ~1mA\n"
           "  合计~140-150mA → 18h需≥2700mAh; 4000mAh≈25h在线/40h+(休眠策略)", 1.5)
    sheets.append(s)

    # ---------------- 02 MCU ----------------
    s = Sheet("02_mcu.kicad_sch", "02_MCU", "主控: ESP32-S3-WROOM-1 (WiFi+BLE+原生USB)", 2)
    s.add(Comp("U10", "RF_Module", "ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N8R8",
               "RF_Module:ESP32-S3-WROOM-1", 210, 130,
               {"3V3": "+3V3", "GND": "GND", "EN": "NET_EN", "IO0": "NET_BOOT", "IO1": "NET_BATADC",
                "IO2": "NET_AMPSD", "IO3": "HR_INT", "IO4": "I2S_MIC_WS", "IO5": "I2S_MIC_SCK",
                "IO6": "I2S_MIC_SD", "IO7": "I2S_AMP_DIN", "IO8": "I2C_SDA", "IO9": "I2C_SCL",
                "IO10": "I2S_AMP_BCLK", "IO11": "I2S_AMP_LRC", "IO12": "NET_MUXRST",
                "IO13": "IMU_INT1", "IO14": "IMU_INT2", "IO15": "IMU_INT3", "IO16": "IMU_INT4",
                "IO17": "IMU_INT5", "IO18": "IMU_INT6", "IO21": "GPS_TXD", "IO38": "GPS_RXD",
                "IO47": "NET_LED47", "IO48": "RGB_DIN",
                "USB_D+": "USB_DP", "USB_D-": "USB_DM", "TXD0": "DEBUG_TX", "RXD0": "DEBUG_RX",
                "IO35": "NC", "IO36": "NC", "IO37": "NC", "IO39": "NC", "IO40": "NC",
                "IO41": "NC", "IO42": "NC", "IO45": "NC", "IO46": "NC"},
               desc="8MB Flash + 8MB Octal PSRAM"))
    s.add(C("C10", "10µF", 210, 92, "+3V3", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C11", "100nF", 225, 92, "+3V3", "GND"))
    s.add(R("R8", "10k", 150, 108, "+3V3", "NET_EN"))
    s.add(C("C12", "1µF", 150, 122, "NET_EN", "GND"))
    s.add(Comp("SW2", "Switch", "SW_Push", "RESET", "Button_Switch_SMD:SW_SPST_SKQG_WithStem", 172, 115,
               {"1": "NET_EN", "2": "GND"}))
    s.add(Comp("SW3", "Switch", "SW_Push", "BOOT", "Button_Switch_SMD:SW_SPST_SKQG_WithStem", 150, 88,
               {"1": "NET_BOOT", "2": "GND"}))
    s.add(R("R9", "1k", 265, 90, "NET_LED47", "NET_LED_A"), LED("D4", "蓝·状态", 282, 90, "NET_LED_A", "GND"))
    s.add(CONN("J10", 4, 310, 120, ["+3V3", "DEBUG_TX", "DEBUG_RX", "GND"],
               "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", desc="调试UART+3V3"))
    s.add(Comp("TP5", "Connector", "TestPoint", "RGB_DIN", "TestPoint:TestPoint_Pad_D1.5mm", 265, 130, {"1": "RGB_DIN"}))
    s.text(28, 35,
           "ESP32-S3-WROOM-1-N8R8 GPIO分配:\n"
           "  IO0 BOOT键 | IO1 电池分压ADC | IO2 功放SD | IO3 心率INT\n"
           "  IO4/5/6 I2S麦克风 WS/SCK/SD | IO7/10/11 I2S功放 DIN/BCLK/LRC\n"
           "  IO8/9 I2C0 SDA/SCL | IO12 复用器RESET | IO13-18 IMU INT1-6\n"
           "  IO19/20=USB_D-/D+ | IO21→GPS_RX | IO38←GPS_TX | IO47 LED | IO48 RGB扩展\n"
           "  IO35-37(OctalPSRAM)/IO39-42(仅输入)/IO45-46(boot strap) 悬空NC", 1.4)
    s.text(28, 128, "⚠ 天线朝板边; 天线区及两侧≥8mm禁止铺铜走线; 底层勿布高速线", 1.4)
    sheets.append(s)

    # ---------------- 03 IMU MUX ----------------
    s = Sheet("03_imu_mux.kicad_sch", "03_IMU_Mux", "姿态采集: TCA9548A 8ch I2C复用 → 6×IMU卫星节点", 3)
    s.add(Comp("U20", "Interface_Expansion", "TCA9548APWR", "TCA9548A", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", 190, 140,
               {"VCC": "+3V3", "GND": "GND", "A0": "GND", "A1": "GND", "A2": "GND",
                "SDA": "I2C_SDA", "SCL": "I2C_SCL", "RESET": "NET_MUXRST",
                "SD0": "IMU1_SDA", "SC0": "IMU1_SCL", "SD1": "IMU2_SDA", "SC1": "IMU2_SCL",
                "SD2": "IMU3_SDA", "SC2": "IMU3_SCL", "SD3": "IMU4_SDA", "SC3": "IMU4_SCL",
                "SD4": "IMU5_SDA", "SC4": "IMU5_SCL", "SD5": "IMU6_SDA", "SC5": "IMU6_SCL",
                "SD6": "NC", "SC6": "NC", "SD7": "SPARE_SDA", "SC7": "SPARE_SCL"},
               desc="I2C 0x70, EN=1A+1A+1A"))
    s.add(R("R10", "2.2k", 140, 100, "I2C_SDA", "+3V3"))
    s.add(R("R11", "2.2k", 158, 100, "I2C_SCL", "+3V3"))
    s.add(R("R12", "10k", 140, 122, "NET_MUXRST", "+3V3"))
    s.add(C("C13", "100nF", 190, 105, "+3V3", "GND"))
    s.add(C("C14", "4.7µF", 206, 105, "+3V3", "GND"))
    names = ["颈部", "左前肩", "右前肩", "左后髋", "右后髋", "尾部"]
    for i in range(6):
        s.add(CONN(f"J2{i+1}", 5, 305, 52 + i * 26,
                   ["+3V3", "GND", f"IMU{i+1}_SDA", f"IMU{i+1}_SCL", f"IMU_INT{i+1}"],
                   FPC(5), desc=f"IMU节点{i+1}·{names[i]}"))
    s.add(CONN("J27", 5, 305, 215, ["+3V3", "GND", "SPARE_SDA", "SPARE_SCL", "NC"], FPC(5),
               desc="预留扩展通道CH7"))
    s.text(28, 28,
           "IMU卫星节点 = LSM6DS3TR-C(LGA-14)+2颗电容, 详见 petvest-imu-node 工程\n"
           "节点I2C地址0x6A(SA0=GND); 上拉电阻仅主控侧2.2k(通道导通时全总线连通)\n"
           "FPC-5P 1.0mm 线序: 1=3V3 2=GND 3=SDA 4=SCL 5=INT; 软排线≤30cm @400kHz", 1.4)
    sheets.append(s)

    # ---------------- 04 HEALTH ----------------
    s = Sheet("04_health.kicad_sch", "04_Health", "心率血氧: MAX30102探头卫星 (主板供电/总线)", 4)
    s.add(Comp("U30", "Regulator_Linear", "AP2112K-1.8", "AP2112K-1.8", "Package_TO_SOT_SMD:SOT-23-5", 130, 85,
               {"VIN": "+3V3", "EN": "+3V3", "GND": "GND", "VOUT": "+1V8"},
               desc="1.8V LDO 600mA→MAX30102 VDD"))
    s.add(C("C15", "1µF", 105, 72, "+3V3", "GND"))
    s.add(C("C16", "2.2µF", 162, 72, "+1V8", "GND"))
    s.add(CONN("J30", 6, 235, 85, ["+3V3", "+1V8", "GND", "I2C_SDA", "I2C_SCL", "HR_INT"], FPC(6),
               desc="MAX30102探头 FPC-6"))
    s.add(R("R13", "10k", 205, 115, "HR_INT", "+3V3"))
    s.text(28, 35,
           "探头卫星板 = MAX30102(OLGA-14) + 100nF/4.7µF, 柔性耳夹或胸贴封装\n"
           "  探头引脚: VDD=1.8V(本板LDO经FPC供电) VLED+=3.3V INT=开漏(本板10k上拉)\n"
           "⚠ 犬类毛发遮挡: 反射式PPG建议贴耳廓内侧/大腿内侧, 先验证信号质量再定型", 1.4)
    sheets.append(s)

    # ---------------- 05 AUDIO ----------------
    s = Sheet("05_audio.kicad_sch", "05_Audio", "语音: INMP441 I2S麦克风(卫星) + MAX98357A功放", 5)
    s.add(Comp("U40", "Audio", "MAX98357A", "MAX98357A",
               "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.45x1.45mm", 235, 105,
               {"VDD": "VSW", "GND": "GND", "PAD": "GND",
                "DIN": "I2S_AMP_DIN", "BCLK": "I2S_AMP_BCLK", "LRCLK": "I2S_AMP_LRC",
                "GAIN_SLOT": "GND", "SD_MODE": "NET_AMPSD", "OUTP": "NET_SPKP", "OUTN": "NET_SPKN",
                "5": "NC", "6": "NC", "12": "NC", "13": "NC"},
               desc="I2S D类功放3W"))
    s.add(C("C17", "10µF", 208, 82, "VSW", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(C("C18", "1µF", 224, 82, "VSW", "GND"))
    s.add(R("R14", "100k", 205, 120, "NET_AMPSD", "GND"))
    s.add(CONN("J40", 2, 305, 105, ["NET_SPKP", "NET_SPKN"],
               "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal", desc="喇叭8Ω2W(推荐)"))
    s.add(CONN("J41", 6, 100, 105, ["+3V3", "GND", "I2S_MIC_SD", "I2S_MIC_SCK", "I2S_MIC_WS", "GND"],
               FPC(6), desc="INMP441麦克风卫星"))
    s.text(28, 35,
           "功放VDD接VSW(开关后电池3.0-4.2V)→音量最大; SD_MODE 100k下拉=默认关断\n"
           "GAIN_SLOT接地=12dB(量产前按喇叭灵敏度复核); 麦克风L/R接地=左声道\n"
           "⚠ 喇叭/麦克风开孔与3D打印外壳声学腔对齐, 加防水透声膜", 1.4)
    sheets.append(s)

    # ---------------- 06 GNSS + DISPLAY ----------------
    s = Sheet("06_gnss_display.kicad_sch", "06_GNSS_Display", "定位 GNSS模块 + OLED显示", 6)
    s.add(CONN("J50", 4, 120, 85, ["+3V3", "GND", "GPS_RXD", "GPS_TXD"], FPC(4),
               desc="GNSS模块接口(NEO-6M/ATGM336H)"))
    s.add(C("C19", "10µF", 155, 105, "+3V3", "GND", fp="Capacitor_SMD:C_0805_2012Metric"))
    s.add(CONN("J51", 4, 120, 155, ["+3V3", "GND", "I2C_SCL", "I2C_SDA"], FPC(4),
               desc="OLED 0.96寸 SSD1306"))
    s.text(28, 35,
           "GNSS: 引脚3=模块TXD→主控IO38(RX); 引脚4=模块RXD←主控IO21(TX); 需3.3V逻辑模块\n"
           "  天线面朝上, 远离ESP32天线/功放/USB; 犬背上方开窗对天线\n"
           "OLED: SSD1306 128x64 I2C 0x3C, 挂I2C0直连(不经复用器), 位置=胸带正面", 1.4)
    sheets.append(s)
    return sheets

# ================================================================ IMU NODE
def build_imu_node(libx, max17048_unused):
    outdir = os.path.join(OUT, "petvest-imu-node")
    os.makedirs(outdir, exist_ok=True)
    sh = Sheet("petvest-imu-node.kicad_sch", "IMU_Node", "IMU卫星节点", 9)
    sh.uuid = U("petvest-imu-node/root")
    sh.add(Comp("U1", "Sensor_Motion", "LSM6DS3", "LSM6DS3TR-C", "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y", 170, 110,
                {"VDD": "+3V3", "VDDIO": "+3V3", "GND": "GND", "SDA": "SDA", "SCL": "SCL",
                 "INT1": "INT1", "CS": "+3V3", "SDO/SA0": "GND",
                 "2": "NC", "3": "NC", "9": "NC", "10": "NC", "11": "NC"},
                desc="6轴IMU I2C 0x6A"))
    sh.add(C("C1", "100nF", 140, 82, "GND", "+3V3"))
    sh.add(C("C2", "4.7µF", 158, 82, "GND", "+3V3"))
    sh.add(CONN("J1", 5, 275, 110, ["+3V3", "GND", "SDA", "SCL", "INT1"], FPC(5),
                desc="至Hub TCA9548A通道"))
    sh.pwrflag("+3V3", 200, 140)
    sh.pwrflag("GND", 220, 140)
    sh.text(28, 30,
            "PetVest IMU卫星节点 ×6 (Hub的03_IMU_Mux每通道接一片)\n"
            "  SA0=GND → I2C 0x6A (改接3V3=0x6B, 用于通道冲突排查)\n"
            "  CS接3V3禁用SPI; INT1数据就绪; 上拉电阻在Hub侧, 节点不加", 1.5)
    sh.resolve(libx)
    libsyms = {}
    for c in sh.comps:
        d = c.sd
        full = f"{c.lib}:{c.sym}"
        if d.extends:
            parent = libx.defs[(c.lib, d.extends)]
            libsyms[full] = materialize_def(d.raw, parent.raw, full)
        else:
            libsyms[full] = rename_def(d.raw, full)
    for net, *_ in sh.pwr_syms:
        if net in POWER_SYMBOL_LIBS:
            full = POWER_SYMBOL_LIBS[net]
            libsyms[full] = rename_def(libx.defs[(full.split(":")[0], full.split(":")[1])].raw, full)
    if sh.flag_syms:
        libsyms["power:PWR_FLAG"] = rename_def(libx.defs[("power", "PWR_FLAG")].raw, "power:PWR_FLAG")
    path = "/" + sh.uuid
    L = ['(kicad_sch', '\t(version 20250114)', '\t(generator "petvest_gen")', '\t(generator_version "1.0")',
         f'\t(uuid "{sh.uuid}")', '\t(paper "A4")',
         '\t(title_block (title "PetVest IMU卫星节点 LSM6DS3TR-C") (date "2026-11-07") (rev "A") (company "PetVest"))',
         '\t(lib_symbols']
    L += ['\t\t' + raw.replace('\n', '\n\t\t') for raw in libsyms.values()]
    L.append('\t)')
    for x1, y1, x2, y2 in sh.wires:
        L.append(f'\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{U(f"wire/{x1},{y1}-{x2},{y2}")}"))')
    for net, x, y, rot in sh.labels:
        L.append(f'\t(global_label "{esc(net)}" (shape passive) (at {x} {y} {rot}) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{U(f"lbl/{net}/{x},{y}")}"))')
    for x, y, tag in sh.ncs:
        L.append(f'\t(no_connect (at {x} {y}) (uuid "{U(f"nc/{x},{y}/{tag}")}"))')
    for net, x, y, rot, ref in sh.pwr_syms:
        L.append(emit_pwr_instance(net, x, y, rot, ref, path, "petvest-imu-node"))
    for ref, x, y in sh.flag_syms:
        L.append(emit_flag_instance(ref, x, y, path, "petvest-imu-node"))
    for c in sh.comps:
        L.append(emit_symbol_instance(c, "petvest-imu-node", path))
    for x, y, s, size in sh.texts:
        L.append(f'\t(text "{esc(s)}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {size} {size})) (justify left bottom)) (uuid "{U(f"text/{x},{y}")}"))')
    L.append(')')
    with open(os.path.join(outdir, "petvest-imu-node.kicad_sch"), 'w', encoding="utf-8") as f:
        f.write('\n'.join(L))
    write_pro("petvest-imu-node", outdir, [], sh.uuid)
    return sh

# ================================================================ MAIN
def main():
    os.makedirs(OUT, exist_ok=True)
    outdir = os.path.join(OUT, "petvest-hub")
    os.makedirs(outdir, exist_ok=True)
    libx = LibIndex()
    for lib, names in {
        "RF_Module": ["ESP32-S3-WROOM-1"],
        "Battery_Management": ["TP4056-42-ESOP8"],
        "Regulator_Switching": ["TPS63061"],
        "Interface_Expansion": ["TCA9548APWR"],
        "Audio": ["MAX98357A"],
        "Power_Protection": ["USBLC6-2SC6"],
        "Regulator_Linear": ["AP2112K-1.8"],
        "Device": ["R", "C", "LED", "L", "Polyfuse", "D_TVS"],
        "Switch": ["SW_Push", "SW_SPDT"],
        "Connector": ["USB_C_Receptacle_USB2.0_16P", "TestPoint"],
        "Connector_Generic": ["Conn_01x02", "Conn_01x04", "Conn_01x05", "Conn_01x06"],
        "power": ["GND", "+3V3", "+BATT", "VBUS", "+1V8", "PWR_FLAG"],
        "Sensor_Motion": ["LSM6DS3"],
    }.items():
        libx.load(lib, names)
    # 自定义 MAX17048 电量计符号
    max17048_raw = box_symbol("MAX17048G", "MAX17048",
        [("1", "VDD", "power_in"), ("2", "GND", "power_in"),
         ("3", "SDA", "bidirectional"), ("4", "SCL", "input")],
        [("5", "ALERT", "output")])
    md = SymDef("petvest", "MAX17048G", max17048_raw, None)
    for pm in PIN_RE.finditer(max17048_raw):
        et, x, y, rot, name, num = pm.groups()
        md.pins.append((num, name, float(x), float(y), int(rot), et))
    libx.defs[("petvest", "MAX17048G")] = md
    libx.extract_pins_all()

    sheets = build_hub()
    for s in sheets:
        s.resolve(libx)
    root_uuid = emit_root("petvest-hub", "petvest-hub.kicad_sch", sheets, outdir)
    for sh in sheets:
        emit_sheet(sh, "petvest-hub", root_uuid, libx, {}, outdir)
    write_pro("petvest-hub", outdir, sheets, root_uuid)
    node = build_imu_node(libx, max17048_raw)

    # ---- 期望网表 (供 kicad-cli 交叉校验; 网表不含#PWR/#FLG, 两项目分开建模) ----
    def build_model(sh_list):
        nets = {}
        def add(net, ref, pin):
            if net and net != "NC":
                nets.setdefault(net, set()).add((ref, str(pin)))
        for sh in sh_list:
            for c in sh.comps:
                for key, net in c.nets.items():
                    for num, *_ in c.sd.pins_for_key(key):
                        add(net, c.ref, num)
        return nets
    # 项目符号库 (自定义 MAX17048G) + sym-lib-table
    with open(os.path.join(outdir, "petvest.kicad_sym"), "w", encoding="utf-8") as f:
        f.write('(kicad_symbol_lib (version 20241209) (generator "petvest_gen") (generator_version "1.0")\n'
                + max17048_raw + '\n)\n')
    with open(os.path.join(outdir, "sym-lib-table"), "w", encoding="utf-8") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "petvest")(type "KiCad")(uri "${KIPRJMOD}/petvest.kicad_sym")(options "")(descr "PetVest custom symbols"))\n)\n')
    hub_nets = build_model(sheets)
    node_nets = build_model([node])
    with open(os.path.join(OUT, "expected_nets.json"), "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in hub_nets.items()}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "expected_nets_node.json"), "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in node_nets.items()}, f, ensure_ascii=False, indent=1)
    print(f"OK: hub={len(sheets)}张({len(hub_nets)}网) + imu-node({len(node_nets)}网); "
          f"comps={sum(len(s.comps) for s in sheets)+len(node.comps)}")

if __name__ == "__main__":
    main()
