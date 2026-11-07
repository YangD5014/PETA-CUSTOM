#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 gen_schematic 的元件模型导出 BOM / 引脚映射 / 网表 CSV"""
import os, sys, csv, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_schematic as G

ROOT = G.OUT
BOMDIR = os.path.join(os.path.dirname(ROOT), "bom")
os.makedirs(BOMDIR, exist_ok=True)

MPN = {
    "ESP32-S3-WROOM-1-N8R8": "ESP32-S3-WROOM-1-N8R8",
    "TP4056": "TP4056-42-ESOP8", "TPS63061": "TPS63061DSJR",
    "MAX17048": "MAX17048G+T10", "USBLC6-2SC6": "USBLC6-2SC6",
    "AP2112K-1.8": "AP2112K-1.8TRG1", "MAX98357A": "MAX98357AATL/V+",
    "TCA9548A": "TCA9548APWR", "LSM6DS3TR-C": "LSM6DS3TR-C",
    "USB-C 16P": "TYPE-C-31-M-12", "电池1S": "1S 4000mAh 带PCM锂电包",
    "1S 4000mAh": "1S 4000mAh 带PCM锂电包",
}
CAT = lambda ref: {"U": "IC", "J": "连接器", "TP": "测试点", "SW": "开关",
                   "D": "二极管/LED", "L": "电感", "F": "保险丝", "C": "电容", "R": "电阻"} \
                  .get(ref[:2] if ref[:2] in ("TP", "SW") else ref[0], "其他")

def build():
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
    return sheets, node

def write_bom(path, comps, title):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([f"{title} — BOM", "", "", "", "", "", ""])
        w.writerow(["位号", "分类", "Value/规格", "封装", "推荐型号", "说明", "数量"])
        groups = {}
        for c in comps:
            key = (c.value, c.fp, c.desc)
            groups.setdefault(key, []).append(c.ref)
        for (val, fp, desc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            r0 = refs[0]
            w.writerow([" ".join(refs), CAT(r0), val, fp or "—",
                        MPN.get(val, MPN.get(desc, "") if not MPN.get(val) else ""),
                        desc, len(refs)])
    print("wrote", path)

def write_netlist_csv(path, sheets):
    nets = {}
    for sh in sheets:
        for c in sh.comps:
            for key, net in c.nets.items():
                if net == "NC":
                    continue
                for num, *_ in c.sd.pins_for_key(key):
                    nets.setdefault(net, []).append((c.ref, num))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["网络", "位号", "引脚"])
        for net in sorted(nets):
            for ref, pin in sorted(nets[net]):
                w.writerow([net, ref, pin])
    print("wrote", path, f"({len(nets)} nets)")

PINMAP = [
    ("IO0",  "输入/ strap", "BOOT按键(板载)", "下载模式进入"),
    ("IO1",  "ADC1", "电池分压 100k/100k", "电池电压监测"),
    ("IO2",  "输出", "MAX98357A SD_MODE", "功放使能(100k下拉默认关)"),
    ("IO3",  "输入/ strap", "MAX30102 INT(开漏+10k上拉)", "心率数据就绪"),
    ("IO4",  "I2S1", "INMP441 WS", "麦克风字选择"),
    ("IO5",  "I2S1", "INMP441 SCK", "麦克风位时钟"),
    ("IO6",  "I2S1", "INMP441 SD", "麦克风数据"),
    ("IO7",  "I2S0", "MAX98357A DIN", "功放数据"),
    ("IO8",  "I2C0", "I2C_SDA(2.2k上拉)", "OLED/心率/电量计/TCA9548A"),
    ("IO9",  "I2C0", "I2C_SCL(2.2k上拉)", "同上"),
    ("IO10", "I2S0", "MAX98357A BCLK", "功放位时钟"),
    ("IO11", "I2S0", "MAX98357A LRC", "功放左右声道"),
    ("IO12", "输出", "TCA9548A RESET(10k上拉)", "I2C复用器复位"),
    ("IO13-18", "输入", "IMU INT1-6", "六节点数据就绪(可选轮询)"),
    ("IO19/20", "USB", "USB_D-/USB_D+ 经USBLC6", "原生USB(烧录+串口)"),
    ("IO21", "UART1 TX", "GPS模块 RXD", "GPS配置/命令"),
    ("IO38", "UART1 RX", "GPS模块 TXD", "NMEA接收"),
    ("IO47", "输出", "蓝色LED 1k", "状态指示"),
    ("IO48", "输出", "RGB_DIN 测试点(外接WS2812可选)", "扩展"),
    ("EN",   "输入/ strap", "10k上拉+1µF+RESET键", "复位"),
    ("TXD0/RXD0", "UART0", "调试排针 J10", "日志"),
]

def main():
    sheets, node = build()
    write_bom(os.path.join(BOMDIR, "bom-petvest-hub.csv"),
              [c for s in sheets for c in s.comps], "PetVest 主控Hub板")
    write_bom(os.path.join(BOMDIR, "bom-petvest-imu-node.csv"),
              node.comps, "PetVest IMU卫星节点(×6)")
    write_netlist_csv(os.path.join(BOMDIR, "netlist-petvest-hub.csv"), sheets)
    with open(os.path.join(BOMDIR, "pinmap-esp32s3.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ESP32-S3 GPIO", "功能", "连接", "备注"])
        w.writerows(PINMAP)
    print("wrote pinmap-esp32s3.csv")

if __name__ == "__main__":
    main()
