#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 3d/viewer.html — 独立 3D 查看器(双击即可打开, 离线可用)
- 加载真实 petvest-hub.glb / petvest-imu-node.glb (KiCad 导出)
- 组装外壳 STL(底壳+盖板), 与 PCB 按 (2.1, 2.1, 2.0) 对位
- 视图: 组装 / 爆炸 / 仅PCB / 卫星节点; 悬停显示位号
"""
import base64, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D3 = os.path.join(HERE, "3d")

def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()

LABELS = {
    "J1": "USB-C", "SW1": "电源开关", "J2": "电池", "J30": "心率探头", "J40": "喇叭",
    "J10": "调试UART(DNP)", "U10": "ESP32-S3-WROOM-1", "U20": "TCA9548A I2C复用",
    "U2": "TP4056 充电", "U3": "TPS63061 3.3V", "U4": "MAX17048 电量计",
    "U40": "MAX98357A 功放", "U30": "AP2112K 1.8V", "U1": "USBLC6 ESD",
    "L1": "1.5µH 电感", "F1": "PTC 保险丝", "D1": "TVS", "D2": "LED 充电", "D3": "LED 充满",
    "D4": "LED 状态", "SW2": "RESET 键", "SW3": "BOOT 键",
    "J21": "IMU1 颈部", "J22": "IMU2 左前肩", "J23": "IMU3 右前肩", "J24": "IMU4 左后髋",
    "J25": "IMU5 右后髋", "J26": "IMU6 尾根", "J27": "预留通道", "J41": "麦克风", "J50": "GPS", "J51": "OLED",
}

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>PetVest 3D 查看器 — 主控Hub板 + 外壳</title>
<style>
  body { margin:0; background:#17191c; color:#e8eaed; font:14px/1.5 system-ui,-apple-system,"PingFang SC",sans-serif; }
  header { padding:12px 18px 6px; }
  header h1 { font-size:16px; margin:0 0 2px; font-weight:600; }
  header .sub { color:#9aa0a6; font-size:12px; }
  #bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; padding:8px 18px; }
  #bar button { background:#2a2d31; color:#e8eaed; border:1px solid #3a3d41; border-radius:8px;
                padding:6px 14px; font-size:13px; cursor:pointer; }
  #bar button.on { background:#3d6b52; border-color:#4d8a68; }
  #bar label { font-size:13px; color:#c6c9cd; display:flex; align-items:center; gap:6px; }
  #stage { position:relative; width:100vw; height:calc(100vh - 96px); min-height:420px; }
  #tip { position:absolute; display:none; pointer-events:none; background:rgba(20,22,25,.92);
         border:1px solid #3a3d41; padding:4px 10px; border-radius:6px; font-size:13px; z-index:5; }
  #err { color:#ff8a80; padding:0 18px; font-size:13px; white-space:pre-wrap; }
</style>
</head>
<body>
<header>
  <h1>PetVest 主控 Hub 板 · 3D 查看器</h1>
  <div class="sub">真实 KiCad 导出模型 · 拖动旋转 / 滚轮缩放 / 悬停查看位号 · PCB 62×42mm · 外壳 66.2×46.2×10.7mm</div>
</header>
<div id="bar">
  <button id="m-asm" class="on">组装</button>
  <button id="m-exp">爆炸图</button>
  <button id="m-pcb">仅 PCB</button>
  <button id="m-node">卫星节点</button>
  <label><input type="checkbox" id="ck-shell" checked> 外壳</label>
  <label><input type="checkbox" id="ck-lid" checked> 盖板</label>
</div>
<div id="stage"><div id="tip"></div></div>
<div id="err"></div>

<script src="libs/three.min.js"></script>
<script src="libs/OrbitControls.js"></script>
<script src="libs/GLTFLoader.js"></script>
<script src="libs/STLLoader.js"></script>
<script>
const B64 = {
  hub:  "__HUB_GLB__",
  node: "__NODE_GLB__",
  base: "__BASE_STL__",
  lid:  "__LID_STL__"
};
const LABELS = __LABELS__;

const stage = document.getElementById('stage'), tip = document.getElementById('tip');
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(stage.clientWidth, stage.clientHeight);
renderer.outputEncoding = THREE.sRGBEncoding;
stage.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x17191c);
const cam = new THREE.PerspectiveCamera(42, stage.clientWidth/stage.clientHeight, 0.1, 5000);
const controls = new THREE.OrbitControls(cam, renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.AmbientLight(0xffffff, .55));
const d1 = new THREE.DirectionalLight(0xffffff, 1.1); d1.position.set(120,180,90); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, .45); d2.position.set(-120,60,-100); scene.add(d2);

const asm = new THREE.Group();      // Z-up 装配组 (mm)
asm.rotation.x = -Math.PI/2;        // 转成 three Y-up 显示
scene.add(asm);
const gBase = new THREE.Group(), gLid = new THREE.Group(), gPcb = new THREE.Group();
asm.add(gBase, gLid, gPcb);
let gNode = null;

function loadSTL(b64, mat, parent){
  const buf = Uint8Array.from(atob(b64), c=>c.charCodeAt(0)).buffer;
  const geo = new THREE.STLLoader().parse(buf);
  const mesh = new THREE.Mesh(geo, mat);
  parent.add(mesh); return mesh;
}
const shellMat = new THREE.MeshStandardMaterial({color:0x9fb8a8, transparent:true, opacity:.34, roughness:.7});
const lidMat   = new THREE.MeshStandardMaterial({color:0x9fb8a8, transparent:true, opacity:.34, roughness:.7, side:THREE.DoubleSide});
loadSTL(B64.base, shellMat, gBase);
loadSTL(B64.lid,  lidMat,  gLid);

const picker = [];   // 可拾取网格
const gltf = new THREE.GLTFLoader();
gltf.parse(Uint8Array.from(atob(B64.hub), c=>c.charCodeAt(0)).buffer, '', (g)=>{
  const hub = g.scene;
  hub.scale.setScalar(1000);                       // m → mm
  // glb: X=板宽62, Z=板高42, Y=厚 → 壳坐标(X+2.1, Y+2.1, Z+2.0)
  const wrap = new THREE.Group();
  wrap.add(hub);
  // Rx(+90°): glb(x,y,z)→(x,-z,y): 元件面(Y)朝壳Z上方, 板高Z反向进壳Y
  wrap.rotation.x = Math.PI/2;
  wrap.position.set(2.1, 44.1, 2.0);
  gPcb.add(wrap);
  hub.traverse(o=>{
    if (o.isMesh){ o.castShadow = false; picker.push(o); }
  });
  apply();
}, (e)=>{ document.getElementById('err').textContent = 'PCB 模型解析进度 '+JSON.stringify(e); });

gltf.parse(Uint8Array.from(atob(B64.node), c=>c.charCodeAt(0)).buffer, '', (g)=>{
  gNode = new THREE.Group();
  g.scene.scale.setScalar(1000);
  g.scene.position.set(-7, -5, 0);
  gNode.add(g.scene);
  gNode.rotation.y = -Math.PI/8;
  gNode.visible = false;
  scene.add(gNode);
  apply();
});

// ---- 视图模式 ----
let mode = 'asm';
const btn = id => document.getElementById(id);
function setMode(m){
  mode = m;
  for (const [id,v] of [['m-asm','asm'],['m-exp','exp'],['m-pcb','pcb'],['m-node','node']])
    btn(id).classList.toggle('on', v===m);
  apply();
}
function apply(){
  gNode.visible = (mode==='node') && !!gNode;
  gBase.visible = gLid.visible = (mode!=='pcb') && (mode!=='node') && document.getElementById('ck-shell').checked;
  gLid.visible = gLid.visible && document.getElementById('ck-lid').checked;
  gPcb.visible = (mode!=='node');
  gLid.position.z = (mode==='exp') ? 9 : 0;    // 壳坐标 Z 向上
  gPcb.position.z = (mode==='exp') ? 4 : 0;
  fit();
}
btn('m-asm').onclick=()=>setMode('asm'); btn('m-exp').onclick=()=>setMode('exp');
btn('m-pcb').onclick=()=>setMode('pcb'); btn('m-node').onclick=()=>setMode('node');
document.getElementById('ck-shell').onchange = apply;
document.getElementById('ck-lid').onchange = apply;

function fit(){
  const box = new THREE.Box3();
  const targets = (mode==='node' && gNode) ? [gNode] : [asm];
  for (const t of targets) box.setFromObject(t);
  if (box.isEmpty()) return;
  const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
  const r = Math.max(s.x, s.y, s.z);
  controls.target.copy(c);
  cam.position.set(c.x + r*1.05, c.y + r*0.85, c.z + r*1.15);
  cam.near = r/100; cam.far = r*50; cam.updateProjectionMatrix();
  controls.update();
}

// ---- 悬停位号 ----
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
renderer.domElement.addEventListener('pointermove', (e)=>{
  const r = renderer.domElement.getBoundingClientRect();
  mouse.x = ((e.clientX-r.left)/r.width)*2-1;
  mouse.y = -((e.clientY-r.top)/r.height)*2+1;
  ray.setFromCamera(mouse, cam);
  const hits = ray.intersectObjects(picker.filter(o=>o.parent && gPcb.visible), false);
  if (hits.length){
    let o = hits[0].object, name='';
    while (o){ if (o.name && /^[A-Z]{1,3}\d/.test(o.name)) { name = o.name; break; } o = o.parent; }
    tip.textContent = name ? (name + (LABELS[name] ? ' · '+LABELS[name] : '')) : '元件';
    tip.style.display='block';
    tip.style.left = Math.min(e.clientX-r.left+14, r.width-160)+'px';
    tip.style.top  = (e.clientY-r.top+14)+'px';
  } else tip.style.display='none';
});
renderer.domElement.addEventListener('pointerleave', ()=> tip.style.display='none');

window.addEventListener('resize', ()=>{
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  cam.aspect = stage.clientWidth/stage.clientHeight; cam.updateProjectionMatrix();
});
renderer.setAnimationLoop(()=>{ controls.update(); renderer.render(scene, cam); });

// 供脚本控制截图: __pv.setMode(m), __pv.frame(dx,dy,dz) 以模型中心取景
window.__pv = { cam, controls, scene, setMode, apply, mode: ()=>mode,
  frame(dx,dy,dz){
    const root = (mode==='node' && gNode) ? gNode : asm;
    const box = new THREE.Box3().setFromObject(root);
    const c = box.getCenter(new THREE.Vector3());
    controls.target.copy(c);
    cam.position.set(c.x+dx, c.y+dy, c.z+dz);
    controls.update();
  }};
</script>
</body>
</html>
"""

html = (HTML
        .replace("__HUB_GLB__", b64(os.path.join(D3, "petvest-hub.glb")))
        .replace("__NODE_GLB__", b64(os.path.join(D3, "petvest-imu-node.glb")))
        .replace("__BASE_STL__", b64(os.path.join(D3, "petvest-hub-外壳底壳.stl")))
        .replace("__LID_STL__", b64(os.path.join(D3, "petvest-hub-外壳盖板.stl")))
        .replace("__LABELS__", str(LABELS).replace("'", '"')))
out = os.path.join(D3, "viewer.html")
open(out, "w", encoding="utf-8").write(html)
print(f"wrote {out}  ({os.path.getsize(out)/1e6:.1f} MB)")
