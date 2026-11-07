#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比对 kicad-cli 导出的网表 vs 生成器期望网表 (expected_nets.json)"""
import json, re, sys

def parse_netlist(path):
    src = open(path, encoding="utf-8").read()
    nets = {}
    # multi-line format: (net\n (code..)\n (name "..")\n (class..)\n (node\n (ref "..") (pin "..")...
    for m in re.finditer(r'\(net\s*\(code "[^"]+"\)\s*\(name "([^"]+)"\)([\s\S]*?)(?=\(net\s*\(code|\Z)', src):
        name, body = m.group(1), m.group(2)
        nodes = set()
        for nm in re.finditer(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', body):
            nodes.add((nm.group(1), nm.group(2)))
        nets[name] = nodes
    return nets

def canon(netname):
    """KiCad net name normalization for comparison."""
    n = netname.strip()
    # power nets: "/+3V3" or "+3V3"; labels: "I2C_SDA" or "/I2C_SDA" or "Net-...(global label)"
    n = n.lstrip("/")
    n = n.replace("+3V3", "+3V3").replace("Net-(", "N_(")
    return n

def main(got_path, exp_path):
    got = parse_netlist(got_path)
    exp_raw = json.load(open(exp_path, encoding="utf-8"))
    exp = {k: set(map(tuple, v)) for k, v in exp_raw.items()}
    # kicad names label nets like "Net-(D2-Pad1)" for local, but global labels keep raw name
    gmap = {}
    for name, nodes in got.items():
        gmap[canon(name)] = nodes
    ok = True
    seen_exp = set()
    for net, nodes in sorted(exp.items()):
        key = canon(net)
        g = gmap.get(key)
        if g is None:
            # try to find by nodes subset
            cand = [n for n, nd in gmap.items() if nodes <= nd]
            if len(cand) == 1:
                g = gmap[cand[0]]
        if g is None:
            print(f"MISSING net {net}: expected {sorted(nodes)}")
            ok = False
            continue
        if g != nodes:
            miss = nodes - g
            extra = g - nodes
            print(f"DIFF net {net}: missing={sorted(miss)} extra={sorted(extra)}")
            ok = False
        seen_exp.add(key)
    # report nets in kicad not expected (auto names ok)
    for name, nodes in sorted(gmap.items()):
        if name in seen_exp:
            continue
        single = len(nodes) <= 1
        print(f"{'(info)' if single else '(WARN)'} kicad-only net {name}: {sorted(nodes)}")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
