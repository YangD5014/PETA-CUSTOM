#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动布局修复: DRC 间距违规 → 按优先级推开元件 → 重铺铜 → 迭代到收敛"""
import json, os, re, subprocess, sys
import pcbnew

KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
BOARD = "/Users/yangjianfei/Downloads/智能服装硬件/kicad/petvest-hub/petvest-hub.kicad_pcb"
BOARD_W, BOARD_H = 70.0, 42.0
# 固定不动: 边缘接口 + 主控模块 + 行上 FPC
FIXED = {"J1","SW1","J2","J30","U10","J21","J22","J23","J24","J25","J26","J27",
         "J40","J41","J50","J51","J10"}
RANK = {"TP": 1, "R": 2, "C": 2, "D": 2, "L": 3, "U": 3}  # 数字越大越优先移动

def rank(ref):
    if ref in FIXED:
        return 0
    m = re.match(r"[A-Z]+", ref)
    return RANK.get(m.group(0) if m else "Z", 4)

def parse_pair(desc):
    zh = re.search(r"上 (\S+) 的焊盘 ([^\s\[]+)", desc)
    if zh:
        return zh.group(1), zh.group(2).strip("~")
    en = re.search(r"Pad '?([^']+)'? of (\S+)", desc)
    if en:
        return en.group(2), en.group(1).strip("'")
    return None, None

def run_drc():
    subprocess.run([KC, "pcb", "drc", "--format", "json", "--output", "/tmp/drc.json",
                    "--severity-error", BOARD], capture_output=True)
    d = json.load(open("/tmp/drc.json"))
    return [v for v in d.get("violations", []) if v["type"] == "clearance"]

def pad_pos(ref, padnum, b):
    for fp in b.GetFootprints():
        if fp.GetReference() == ref:
            p = fp.FindPadByNumber(padnum)
            if p:
                pos = p.GetPosition()
                return pos.x / 1e6, pos.y / 1e6
    return None

def move_ref(ref, dx, dy, b):
    for fp in b.GetFootprints():
        if fp.GetReference() == ref:
            pos = fp.GetPosition()
            nx = min(max(pos.x + int(dx * 1e6), int(3.0 * 1e6)), int((BOARD_W - 3.0) * 1e6))
            ny = min(max(pos.y + int(dy * 1e6), int(3.0 * 1e6)), int((BOARD_H - 3.0) * 1e6))
            fp.SetPosition(pcbnew.VECTOR2I(nx, ny))
            return True
    return False

def refill():
    b = pcbnew.GetBoard()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.Flush() if hasattr(pcbnew, "Flush") else None
    b.Save(BOARD)

def main():
    b = pcbnew.LoadBoard(BOARD)
    max_iter = 10
    moved_count = {}
    for it in range(1, max_iter + 1):
        vios = run_drc()
        shorts = [v for v in vios if v['type'] == 'shorting_items']
        clear  = [v for v in vios if v['type'] == 'clearance']
        if not vios:
            print(f"iter {it}: CLEAN ✓")
            break
        print(f"iter {it}: {len(clear)} clearance + {len(shorts)} shorts")
        # 短路 = 真实重叠: 按 0.25mm 需求处理
        for v in shorts:
            v['required_value'] = int(0.25 * 1e6)
            v['actual_value'] = 0
        vios = clear + shorts
        moves = []
        for v in vios:
            req, act = v.get("required_value", 0), v.get("actual_value", 0)
            refs = []
            for item in v["items"]:
                r, p = parse_pair(item.get("description", ""))
                if r and p:
                    refs.append((r, p))
            if len(refs) != 2 or refs[0][0] == refs[1][0]:
                continue
            (ra, pa), (rb, pb) = refs
            ka, kb = rank(ra), rank(rb)
            if ka == 0 and kb == 0:
                posa, posb = pad_pos(ra, pa, b), pad_pos(rb, pb, b)
                print(f"  ! 双固定冲突: {ra}.{pa}@{posa} vs {rb}.{pb}@{posb}")
                continue
            mover, other = (ra, rb) if ka >= kb else (rb, ra)
            pos_m = pad_pos(mover, pa if mover == ra else pb, b)
            pos_o = pad_pos(other, pb if mover == ra else pa, b)
            if not pos_m or not pos_o:
                continue
            dx, dy = pos_m[0] - pos_o[0], pos_m[1] - pos_o[1]
            d = (dx*dx + dy*dy) ** 0.5
            need = (req - act) / 1e6 + 0.3
            if d < 0.05:
                dx, dy = 0.0, 1.0
                d = 1.0
            moves.append((mover, dx / d * need, dy / d * need))
        if not moves:
            print("  无可自动修复项, 停止")
            break
        moved = set()
        for mover, dx, dy in moves:
            if moved_count.get(mover, 0) >= 2:
                continue
            if mover in moved:
                continue
            if move_ref(mover, dx, dy, b):
                moved.add(mover)
                moved_count[mover] = moved_count.get(mover, 0) + 1
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(BOARD)
        print(f"  moved: {sorted(moved)}")
    print("done")

main()
