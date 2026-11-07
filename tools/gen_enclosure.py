#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PetVest Hub 主控盒 3D 打印外壳生成器 (纯Python, 输出二进制STL, 单位mm)
- 底壳: 地板 + 四壁 + 自攻螺丝柱, 开口: USB-C/电源开关/电池线(左壁),
        顶部排线槽(6×FPC出线), 底部排线槽(4×FPC出线), 右壁+左壁织带缝合槽
- 盖板: 4×螺丝过孔 + 2×LED透光孔
与 petvest-hub.kicad_pcb (62x42mm) 对位: PCB原点在壳内 (2.1, 2.1)。
打印参数: 0.2mm层厚 / 壁厚≥1.8mm(4圈) / 顶底3层 / PETG或TPU; 切片时多个实体请勾选"合并/Union"。
"""
import struct, os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "3d")

# ---------- 几何参数 (mm) ----------
OW, OH = 66.2, 46.2          # 外形
WT = 1.8                     # 壁厚
FL = 1.6                     # 底厚
LID_T = 1.6                  # 盖厚
LID_Z = 7.5                  # 盖底面高度
WH = LID_Z + LID_T           # 壁总高 9.1
OX, OY = 2.1, 2.1            # PCB原点在壳内的偏移
BOSS_H = 2.0                 # 螺丝柱高(PCB距地板)
# PCB 上的安装孔 -> 壳内坐标
HOLES = [(3.5+OX, 3.5+OY), (58.5+OX, 3.5+OY), (3.5+OX, 39.5+OY), (59.2+OX, 36.5+OY)]
BOSS_R, PILOT_R = 2.7, 1.1

tris = []
def box(x0, y0, z0, x1, y1, z1):
    """轴对齐长方体 → 12三角形 (法线朝外)"""
    p = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
         (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    f = [(0,2,1),(0,3,2), (4,5,6),(4,6,7), (0,1,5),(0,5,4), (2,3,7),(2,7,6), (1,2,6),(1,6,5), (3,0,4),(3,4,7)]
    for a,b,c in f:
        tris.append((p[a],p[b],p[c]))

def ngon(cx, cy, r, n, z0, z1):
    """凸 n 边形柱 (螺丝柱)"""
    pts = [(cx + r*__import__('math').cos(2*__import__('math').pi*i/n),
            cy + r*__import__('math').sin(2*__import__('math').pi*i/n)) for i in range(n)]
    for i in range(n):
        x0,y0 = pts[i]; x1,y1 = pts[(i+1)%n]
        box(min(x0,x1), min(y0,y1), z0, max(x0,x1), max(y0,y1), z1) if False else None
        # 侧面用楔形近似: 直接三棱柱
        tris.append(((x0,y0,z0),(x1,y1,z0),(x1,y1,z1)))
        tris.append(((x0,y0,z0),(x1,y1,z1),(x0,y0,z1)))
    # 顶/底面 (扇形)
    for i in range(1, n-1):
        tris.append(((pts[0][0],pts[0][1],z0),(pts[i][0],pts[i][1],z0),(pts[i+1][0],pts[i+1][1],z0)))
        tris.append(((pts[0][0],pts[0][1],z1),(pts[i+1][0],pts[i+1][1],z1),(pts[i][0],pts[i][1],z1)))

def write_stl(path):
    with open(path, 'wb') as f:
        f.write(b'PetVest enclosure (union of boxes; slicer: union)'.ljust(80, b' '))
        f.write(struct.pack('<I', len(tris)))
        for a, b, c in tris:
            # 法线
            ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
            vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
            nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
            l = (nx*nx+ny*ny+nz*nz) ** 0.5 or 1.0
            f.write(struct.pack('<3f', nx/l, ny/l, nz/l))
            for p in (a, b, c):
                f.write(struct.pack('<3f', *p))
            f.write(struct.pack('<H', 0))
    print(f"wrote {path}  ({len(tris)} triangles)")

def base():
    # 地板
    box(0, 0, 0, OW, OH, FL)
    # 螺丝柱 + 导向孔(柱内盲孔用小方柱负空间近似→此处留实心+盖板过孔, 自攻直接拧入)
    for cx, cy in HOLES:
        ngon(cx, cy, BOSS_R, 16, FL, FL + BOSS_H)
    # ---- 左壁 (x 0..WT) ----
    segs = [
        (1.8, 11.8, 0, WH),      # 上段(全高)
        (11.8, 20.4, 0, 3.2), (11.8, 20.4, 7.1, WH),   # USB-C 让位
        (20.4, 20.6, 0, WH),
        (20.6, 24.6, 0, 4.0), (20.6, 24.6, 6.5, WH),   # 电源开关拨嘴
        (24.6, 25.0, 0, WH),
        (25.0, 33.6, 0, 2.8), (25.0, 33.6, 6.4, WH),   # 电池出线孔
        (33.6, 36.4, 0, WH),
        (36.4, 41.6, 0, 4.0), (36.4, 41.6, 7.2, WH),   # 心率探头FPC出线
        (41.6, 44.4, 0, WH),
    ]
    for y0, y1, z0, z1 in segs:
        box(0, y0, z0, WT, y1, z1)
    # ---- 右壁 (x OW-WT..OW) ----
    for y0, y1, z0, z1 in [
        (1.8, 8.0, 0, WH),
        (8.0, 12.0, 0, 4.2), (8.0, 12.0, 7.2, WH),     # 织带槽
        (12.0, 32.0, 0, WH),
        (32.0, 36.0, 0, 4.2), (32.0, 36.0, 7.2, WH),   # 织带槽
        (36.0, 44.4, 0, WH),
    ]:
        box(OW-WT, y0, z0, OW, y1, z1)
    # ---- 顶壁 (y 0..WT): 6×FPC 出线槽 ----
    for x0, x1, z0, z1 in [
        (WT, 4.0, 0, WH),
        (4.0, 63.0, 0, 4.6), (4.0, 63.0, 7.6, WH),
        (63.0, OW-WT, 0, WH),
    ]:
        box(x0, 0, z0, x1, WT, z1)
    # ---- 底壁 (y OH-WT..OH): 4×FPC 出线槽 + 右端织带槽 ----
    for x0, x1, z0, z1 in [
        (WT, 10.0, 0, WH),
        (10.0, 53.4, 0, 4.6), (10.0, 53.4, 7.6, WH),
        (53.4, 54.0, 0, WH),
        (54.0, 63.5, 0, 4.2), (54.0, 63.5, 7.2, WH),   # 织带槽
        (63.5, OW-WT, 0, WH),
    ]:
        box(x0, OH-WT, z0, x1, OH, z1)

def plate_with_holes(x0, x1, y0, y1, z0, z1, holes):
    """矩形板挖矩形孔: 按 y 分带 + x 区间裁剪"""
    ys = sorted({y0, y1} | {h[1] for h in holes} | {h[3] for h in holes})
    for a, b in zip(ys, ys[1:]):
        if b - a < 1e-9:
            continue
        cuts = sorted([h for h in holes if h[1] <= a and b <= h[3]], key=lambda h: h[0])
        cx = x0
        for hx0, hy0, hx1, hy1 in cuts:
            if hx0 > cx:
                box(cx, a, z0, min(hx0, x1), b, z1)
            cx = max(cx, hx1)
        if cx < x1:
            box(cx, a, z0, x1, b, z1)

def lid():
    holes = []
    for cx, cy in HOLES:
        holes.append((cx-1.3, cy-1.3, cx+1.3, cy+1.3))          # M2.5 螺丝过孔 2.6
    # LED 透光孔 (D2/D3: PCB(8.3,28.6)/(8.3,31.1))
    for _, py in [(0, 28.6+OY), (0, 31.1+OY)]:
        holes.append((8.3+OX-1.1, py-1.1, 8.3+OX+1.1, py+1.1))
    plate_with_holes(0, OW, 0, OH, LID_Z, LID_Z + LID_T, holes)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    tris.clear(); base();   write_stl(os.path.join(OUT, "petvest-hub-外壳底壳.stl"))
    tris.clear(); lid();    write_stl(os.path.join(OUT, "petvest-hub-外壳盖板.stl"))
    # 尺寸报告
    print(f"底壳外形 {OW}x{OH}x{WH}mm, PCB 62x42 置于({OX},{OY}), PCB顶面z={FL+BOSS_H:.1f}, 盖板z={LID_Z}..{LID_Z+LID_T}")
    print("开口: 左壁 USB-C(y11.8-20.4)/开关(y20.6-24.6)/电池线(y27.6-33.6)/织带(y36-40); "
          "右壁织带×2; 顶壁排线槽x4-63; 底壁排线槽x10-53.4")
