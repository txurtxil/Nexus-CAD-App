import flet as ft
import os, base64, json, threading, http.server, socketserver, socket, time, warnings, traceback, shutil, struct

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from urllib.parse import urlparse, unquote

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS DEL SISTEMA Y ANDROID
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
os.makedirs(EXPORT_DIR, exist_ok=True)
DOWNLOAD_DIR = "/storage/emulated/0/Download"

def get_android_root():
    paths = ["/storage/emulated/0", os.path.expanduser("~/storage/shared"), BASE_DIR]
    for p in paths:
        try:
            os.listdir(p)
            return p
        except: pass
    return BASE_DIR

ANDROID_ROOT = get_android_root()

# =========================================================
# GLOBALES DE ESTADO
# =========================================================
LAN_IP = "127.0.0.1"
LOCAL_PORT = 8556
LATEST_CODE_B64 = ""
LATEST_NEEDS_STL = False

MAX_ASSEMBLY_PARTS = 10
ASSEMBLY_PARTS_STATE = [{"active": False, "file": "", "mat": "pla", "x": 0, "y": 0, "z": 0} for _ in range(MAX_ASSEMBLY_PARTS)]
PBR_STATE = {"mode": "single", "parts": []}

def update_pbr_state():
    global PBR_STATE
    PBR_STATE["mode"] = "assembly"
    PBR_STATE["parts"] = [p for p in ASSEMBLY_PARTS_STATE if p["active"]]

def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL:
        cpu_p = psutil.cpu_percent()
        ram_p = psutil.virtual_memory().percent
    return cpu_p, ram_p, cores

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: return "127.0.0.1"

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        LOCAL_PORT = s.getsockname()[1]
except: pass

LAN_IP = get_lan_ip()

def get_stl_hash():
    path = os.path.join(EXPORT_DIR, "imported.stl")
    if os.path.exists(path):
        try:
            sz = os.path.getsize(path)
            if sz > 84: return f"{os.path.getmtime(path)}_{sz}"
        except: pass
    return ""

def validate_stl(filepath):
    try:
        sz = os.path.getsize(filepath)
        if sz < 84: return False, "El archivo es demasiado pequeño."
        with open(filepath, 'rb') as f:
            header = f.read(80)
            if b'solid ' in header[:10]: return True, "ASCII STL Detectado"
            tris = int.from_bytes(f.read(4), byteorder='little')
            expected = 84 + (tris * 50)
            if sz == expected: return True, "Binario STL Válido"
            return False, f"STL Incompleto/Roto: Pesa {sz}B, Motor exige {expected}B."
    except Exception as e: return False, f"Error lectura: {e}"

def convert_stl_to_obj(stl_path, obj_path):
    try:
        with open(stl_path, 'rb') as f:
            f.read(80)
            tris = int.from_bytes(f.read(4), 'little')
            with open(obj_path, 'w') as out:
                out.write("# NEXUS CAD Export\no Nexus_Mesh\n")
                v_idx = 1
                for _ in range(tris):
                    data = f.read(50)
                    if len(data) < 50: break
                    v1 = struct.unpack('<3f', data[12:24])
                    v2 = struct.unpack('<3f', data[24:36])
                    v3 = struct.unpack('<3f', data[36:48])
                    out.write(f"v {v1[0]} {v1[1]} {v1[2]}\nv {v2[0]} {v2[1]} {v2[2]}\nv {v3[0]} {v3[1]} {v3[2]}\nf {v_idx} {v_idx+1} {v_idx+2}\n")
                    v_idx += 3
        return True, "Convertido y guardado exitosamente."
    except Exception as e: return False, str(e)

def analyze_stl(filepath):
    try:
        with open(filepath, 'rb') as f:
            if b'solid ' in f.read(80)[:10]: return None
            f.seek(80)
            tri_count = int.from_bytes(f.read(4), byteorder='little')
            min_x = min_y = min_z = float('inf')
            max_x = max_y = max_z = float('-inf')
            volume = 0.0
            for _ in range(tri_count):
                data = f.read(50)
                if len(data) < 50: break
                v1 = struct.unpack('<3f', data[12:24])
                v2 = struct.unpack('<3f', data[24:36])
                v3 = struct.unpack('<3f', data[36:48])
                for v in (v1, v2, v3):
                    if v[0] < min_x: min_x = v[0]
                    if v[0] > max_x: max_x = v[0]
                    if v[1] < min_y: min_y = v[1]
                    if v[1] > max_y: max_y = v[1]
                    if v[2] < min_z: min_z = v[2]
                    if v[2] > max_z: max_z = v[2]
                v321 = v3[0]*v2[1]*v1[2]; v231 = v2[0]*v3[1]*v1[2]; v312 = v3[0]*v1[1]*v2[2]
                v132 = v1[0]*v3[1]*v2[2]; v213 = v2[0]*v1[1]*v3[2]; v123 = v1[0]*v2[1]*v3[2]
                volume += (1.0/6.0)*(-v321 + v231 + v312 - v132 - v213 + v123)
            vol_cm3 = abs(volume) / 1000.0; weight_pla = vol_cm3 * 1.24
            return {"dx": round(max_x - min_x, 2), "dy": round(max_y - min_y, 2), "dz": round(max_z - min_z, 2), "vol_cm3": round(vol_cm3, 2), "weight_g": round(weight_pla, 2)}
    except: return None

DUMMY_VALID_STL = b'NEXUS_DUMMY_STL' + (b'\x00' * 65) + (1).to_bytes(4, 'little') + (b'\x00' * 50)

PBR_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEXUS PBR STUDIO</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    <style>body{margin:0;overflow:hidden;background:#0B0E14;font-family:sans-serif;} canvas{display:block;} .panel{position:absolute;top:10px;left:10px;background:rgba(22,27,34,0.85);padding:15px;border-radius:10px;border:1px solid #C51162;box-shadow: 0 4px 6px rgba(0,0,0,0.3); backdrop-filter: blur(5px); width:220px;}</style>
</head>
<body>
    <div class="panel">
        <h3 style="margin:0 0 10px 0;color:#FF007F;font-size:16px;">🎨 PBR STUDIO PRO</h3>
        <div id="singleMatContainer">
            <select id="matSelect" style="width:100%;background:#0B0E14;color:#00E5FF;padding:8px;border:1px solid #30363D;border-radius:5px;outline:none;font-weight:bold;margin-bottom:10px;">
                <option value="carbon">Fibra de Carbono</option>
                <option value="wood">Madera Bambú</option>
                <option value="petg">PETG Translúcido</option>
                <option value="aluminum">Aluminio</option>
                <option value="gold">Oro Puro</option>
                <option value="pla" selected>PLA Gris</option>
            </select>
        </div>
        <div style="margin-bottom:10px;">
            <label style="color:#00E676;font-size:12px;font-weight:bold;">💡 Intensidad Luz</label>
            <input type="range" id="lightSlider" min="0.1" max="4.0" step="0.1" value="1.5" style="width:100%;">
        </div>
        <button onclick="takeScreenshot()" style="width:100%;background:#0D47A1;color:#fff;padding:10px;border:none;border-radius:5px;cursor:pointer;font-weight:bold;margin-top:5px;">📸 TOMAR FOTO (PNG)</button>
        <div id="toast" style="display:none; margin-top:10px; color:#00E676; font-size:12px; font-weight:bold; text-align:center;">¡Render guardado!</div>
        <p id="modeText" style="color:#FFAB00;font-size:10px;margin:10px 0 0 0;text-align:center;"></p>
    </div>
    
    <script>
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0B0E14);
        scene.fog = new THREE.FogExp2(0x0B0E14, 0.002);

        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 1.0); scene.add(hemiLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.5); dirLight.position.set(50, 100, 50); scene.add(dirLight);
        const backLight = new THREE.DirectionalLight(0x00E5FF, 1.0); backLight.position.set(-50, 50, -50); scene.add(backLight);

        document.getElementById('lightSlider').addEventListener('input', (e) => { dirLight.intensity = parseFloat(e.target.value); hemiLight.intensity = parseFloat(e.target.value) * 0.6; });

        const camera = new THREE.PerspectiveCamera(45, window.innerWidth/window.innerHeight, 0.1, 2000);
        camera.position.set(150, 150, 150);

        const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.outputEncoding = THREE.sRGBEncoding; renderer.toneMapping = THREE.ACESFilmicToneMapping;
        document.body.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement); controls.enableDamping = true;

        function takeScreenshot() {
            renderer.render(scene, camera); const dataURL = renderer.domElement.toDataURL("image/png");
            fetch('/api/save_image', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: 'render_' + Date.now() + '.png', image_data: dataURL}) }).then(r => r.json()).then(d => {
                const t = document.getElementById('toast'); t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 3000);
            });
        }

        function createTex(type) {
            const c = document.createElement('canvas'); c.width=256; c.height=256; const ctx = c.getContext('2d');
            if(type==='carbon') {
                ctx.fillStyle='#111'; ctx.fillRect(0,0,256,256); ctx.fillStyle='#2a2a2a'; ctx.fillRect(0,0,128,128); ctx.fillRect(128,128,128,128);
                const tex = new THREE.CanvasTexture(c); tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(16,16); return tex;
            } else if(type==='aluminum') {
                ctx.fillStyle='#999'; ctx.fillRect(0,0,256,256);
                for(let i=0;i<1000;i++){ ctx.fillStyle=Math.random()>0.5?'rgba(255,255,255,0.1)':'rgba(0,0,0,0.1)'; ctx.fillRect(0,Math.random()*256,256,2); }
                const tex = new THREE.CanvasTexture(c); tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(4,4); return tex;
            } else {
                ctx.fillStyle='#dcb68a'; ctx.fillRect(0,0,256,256);
                for(let i=0;i<500;i++){ ctx.fillStyle='rgba(139,69,19,0.1)'; ctx.fillRect(Math.random()*256,0,2,256); }
                const tex = new THREE.CanvasTexture(c); tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; return tex;
            }
        }

        const mats = {
            pla: new THREE.MeshStandardMaterial({color: 0x666666, roughness: 0.8, metalness: 0.1}),
            petg: new THREE.MeshPhysicalMaterial({color: 0xddffff, transmission: 0.95, opacity: 1, transparent: true, roughness: 0.05, ior: 1.5, thickness: 3.0}),
            carbon: new THREE.MeshPhysicalMaterial({color: 0x333333, roughness: 0.6, metalness: 0.5, map: createTex('carbon'), clearcoat: 1.0}),
            aluminum: new THREE.MeshStandardMaterial({color: 0xb0b0b0, roughness: 0.4, metalness: 0.9, map: createTex('aluminum')}),
            wood: new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.8, map: createTex('wood')}),
            gold: new THREE.MeshStandardMaterial({color: 0xffd700, roughness: 0.15, metalness: 1.0})
        };

        let currentGroup = null; let stateHash = ""; const loader = new THREE.STLLoader(); let geomCache = {};

        function checkState() {
            fetch('/api/assembly_state.json?t=' + Date.now()).then(r => r.json()).then(state => {
                let newHash = JSON.stringify(state);
                if(newHash !== stateHash) { stateHash = newHash; buildScene(state); }
            }).catch(()=>{});
        }
        setInterval(checkState, 1000);

        function buildScene(state) {
            if(currentGroup) scene.remove(currentGroup);
            currentGroup = new THREE.Group(); scene.add(currentGroup);
            if(state.mode === 'single') {
                document.getElementById('singleMatContainer').style.display = 'block'; document.getElementById('modeText').innerText = "Modo: Pieza Única";
                let matKey = document.getElementById('matSelect').value;
                loadStlFile('/imported.stl?t='+Date.now(), 0, 0, 0, matKey, true);
            } else {
                document.getElementById('singleMatContainer').style.display = 'none'; document.getElementById('modeText').innerText = "Modo: Mesa Ensamblaje";
                state.parts.forEach(p => { if(p.file) loadStlFile('/descargar/' + encodeURIComponent(p.file), p.x, p.y, p.z, p.mat, false); });
            }
        }

        function loadStlFile(url, x, y, z, matKey, centerCam) {
            if(geomCache[url] && !url.includes('?')) addMeshToGroup(geomCache[url], x, y, z, matKey, centerCam);
            else loader.load(url, geom => { geom.center(); geom.computeVertexNormals(); if(!url.includes('?')) geomCache[url] = geom; addMeshToGroup(geom, x, y, z, matKey, centerCam); });
        }

        function addMeshToGroup(geom, x, y, z, matKey, centerCam) {
            let mesh = new THREE.Mesh(geom, mats[matKey] || mats.pla);
            mesh.rotation.x = -Math.PI / 2; mesh.position.set(x, z, -y);
            currentGroup.add(mesh);
            if(centerCam) { geom.computeBoundingSphere(); const r = geom.boundingSphere.radius; camera.position.set(r*1.5, r*1.5, r*1.5); controls.target.set(0,0,0); }
        }

        document.getElementById('matSelect').addEventListener('change', () => { stateHash = ""; checkState(); });
        function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); } animate();
        window.addEventListener('resize', () => { camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); });
    </script>
</body>
</html>"""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, File-Name")
        self.send_header("Connection", "close") 

    def do_OPTIONS(self):
        self.send_response(200); self._send_cors(); self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path in ['/api/save_export', '/api/save_model']:
            cl = int(self.headers.get('Content-Length', 0))
            if cl > 0:
                try:
                    data = json.loads(self.rfile.read(cl).decode('utf-8'))
                    filename = data.get('filename', f'nexus_export_{int(time.time())}.stl')
                    file_data = data.get('data', '')
                    if isinstance(file_data, str) and file_data.startswith('data:'):
                        b64_data = file_data.split(',')[1]
                        file_bytes = base64.b64decode(b64_data)
                        mode = 'wb'
                    else:
                        file_bytes = file_data.encode('utf-8') if isinstance(file_data, str) else file_data
                        mode = 'wb' if isinstance(file_bytes, bytes) else 'w'
                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    with open(os.path.join(DOWNLOAD_DIR, filename), mode) as f: f.write(file_bytes)
                    with open(os.path.join(EXPORT_DIR, filename), mode) as f: f.write(file_bytes)
                    self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
                    return
                except Exception: pass
            self.send_response(500); self._send_cors(); self.end_headers()
            
        elif parsed.path == '/api/save_image':
            cl = int(self.headers.get('Content-Length', 0))
            if cl > 0:
                try:
                    data = json.loads(self.rfile.read(cl).decode('utf-8'))
                    img_data = data['image_data'].split(',')[1]
                    filepath = os.path.join(EXPORT_DIR, data['filename'])
                    with open(filepath, 'wb') as f: f.write(base64.b64decode(img_data))
                    resp = b'{"status": "ok"}'
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.send_header("Content-Length", str(len(resp))); self._send_cors(); self.end_headers(); self.wfile.write(resp)
                    return
                except: pass
            self.send_response(500); self._send_cors(); self.end_headers()

        # =================================================================
        # FIX Carga Archivos Pesados: Lectura en Chunks en lugar de Todo en RAM
        # =================================================================
        elif parsed.path == '/api/upload':
            cl = int(self.headers.get('Content-Length', 0))
            fn = unquote(self.headers.get('File-Name', 'uploaded_file.stl'))
            if cl > 0:
                try:
                    filepath = os.path.join(EXPORT_DIR, fn)
                    with open(filepath, 'wb') as f:
                        bytes_read = 0
                        chunk_size = 65536  # 64KB buffers para que fluya constante
                        while bytes_read < cl:
                            chunk = self.rfile.read(min(chunk_size, cl - bytes_read))
                            if not chunk: break
                            f.write(chunk)
                            bytes_read += len(chunk)
                    
                    resp = b'ok'
                    self.send_response(200); self.send_header("Content-type", "text/plain"); self.send_header("Content-Length", str(len(resp))); self._send_cors(); self.end_headers(); self.wfile.write(resp)
                    return
                except Exception as e:
                    pass
            self.send_response(500); self._send_cors(); self.end_headers()

    def do_GET(self):
        global LATEST_CODE_B64, LATEST_NEEDS_STL, PBR_STATE
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/get_code_b64.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self._send_cors(); self.end_headers()
            hash_val = get_stl_hash() if LATEST_NEEDS_STL else ""
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64, "stl_hash": hash_val}).encode())
            LATEST_CODE_B64 = "" 
            
        elif parsed.path == '/api/assembly_state.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self._send_cors(); self.end_headers()
            self.wfile.write(json.dumps(PBR_STATE).encode('utf-8'))

        elif parsed.path == '/imported.stl':
            filepath = os.path.join(EXPORT_DIR, "imported.stl")
            data_to_send = DUMMY_VALID_STL
            if os.path.exists(filepath):
                try:
                    sz = os.path.getsize(filepath)
                    if sz >= 84:
                        with open(filepath, "rb") as f:
                            data_to_send = f.read()
                except Exception: pass
            
            self.send_response(200)
            self.send_header("Content-type", "model/stl")
            self.send_header("Content-Length", str(len(data_to_send)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self._send_cors()
            self.end_headers()
            
            try:
                chunk_size = 65536
                for i in range(0, len(data_to_send), chunk_size):
                    self.wfile.write(data_to_send[i:i+chunk_size])
            except Exception: pass

        elif parsed.path == '/pbr_studio.html':
            self.send_response(200); self.send_header("Content-type", "text/html"); self.send_header("Content-Length", str(len(PBR_HTML_TEMPLATE.encode('utf-8')))); self._send_cors(); self.end_headers(); self.wfile.write(PBR_HTML_TEMPLATE.encode('utf-8'))

        elif parsed.path == '/upload_ui':
            html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta charset="UTF-8"></head><body style="background:#0B0E14; color:#E6EDF3; font-family:sans-serif; text-align:center; padding:20px;"><h2 style="color:#00E676;">🚀 INYECCIÓN WEB NEXUS</h2><div style="background:#161B22; padding:20px; border-radius:8px; border:1px solid #30363D; display:inline-block; width:90%; max-width:400px;"><input type="file" id="f" style="margin-bottom:20px; color:white; width:100%;"><button onclick="up()" style="background:#00E5FF; color:black; padding:15px; width:100%; font-weight:bold; border:none; border-radius:8px; cursor:pointer;">INYECTAR ARCHIVO</button><div id="pb-container" style="display:none; width:100%; background:#30363D; border-radius:4px; margin-top:20px; height:12px; overflow:hidden;"><div id="pb-fill" style="width:0%; background:#00E5FF; height:100%; transition:width 0.2s;"></div></div><p id="s" style="margin-top:15px; font-weight:bold; font-size:15px;"></p></div><script>function up() { var f = document.getElementById('f').files[0]; if(!f) return; var s = document.getElementById('s'); var pbc = document.getElementById('pb-container'); var pbf = document.getElementById('pb-fill'); s.style.color = '#FFAB00'; s.innerText = 'Iniciando inyección...'; pbc.style.display = 'block'; pbf.style.width = '0%'; pbf.style.background = '#00E5FF'; var xhr = new XMLHttpRequest(); xhr.open('POST', '/api/upload', true); xhr.setRequestHeader('File-Name', encodeURIComponent(f.name)); xhr.setRequestHeader('Content-Type', 'application/octet-stream'); xhr.upload.onprogress = function(e) { if (e.lengthComputable) { var pc = (e.loaded / e.total) * 100; pbf.style.width = pc + '%'; s.innerText = 'Inyectando... ' + Math.round(pc) + '%'; } }; xhr.onload = function() { if (xhr.status == 200) { s.style.color = '#00E676'; s.innerText = '✓ ¡ÉXITO! Vuelve a la App y pulsa REFRESCAR.'; pbf.style.width = '100%'; pbf.style.background = '#00E676'; } else { s.style.color = '#FF5252'; s.innerText = '❌ Error: ' + xhr.status; pbf.style.background = '#FF5252'; } }; xhr.onerror = function() { s.style.color = '#FF5252'; s.innerText = '❌ Error de red'; pbf.style.background = '#FF5252'; }; xhr.send(f); }</script></body></html>"""
            self.send_response(200); self.send_header("Content-type", "text/html"); self.send_header("Content-Length", str(len(html.encode('utf-8')))); self._send_cors(); self.end_headers(); self.wfile.write(html.encode('utf-8'))
            
        elif parsed.path.startswith('/descargar/'):
            filename = unquote(parsed.path.replace('/descargar/', ''))
            filepath = os.path.join(EXPORT_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.send_response(200); self.send_header("Content-Disposition", f'attachment; filename="{filename}"'); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            else: self.send_response(404); self._send_cors(); self.end_headers()
            
        elif parsed.path == '/' or parsed.path == '/openscad_engine.html':
            try:
                fn = "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, fn), "r", encoding="utf-8") as f:
                    content = f.read()
                
                stl_path = os.path.join(EXPORT_DIR, "imported.stl")
                b64_stl = base64.b64encode(DUMMY_VALID_STL).decode('utf-8')
                if os.path.exists(stl_path):
                    sz = os.path.getsize(stl_path)
                    if sz >= 84:
                        with open(stl_path, "rb") as stl_file:
                            b64_stl = base64.b64encode(stl_file.read()).decode('utf-8')
                
                injector = '''
                <script>
                (function() {
                    var stlData = "data:application/octet-stream;base64,__B64_STL__";
                    var origOpen = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(method, url) {
                        if (url && typeof url === "string" && url.indexOf("imported.stl") !== -1) {
                            arguments[1] = stlData;
                        }
                        return origOpen.apply(this, arguments);
                    };
                    if(window.fetch) {
                        var origFetch = window.fetch;
                        window.fetch = function(resource, config) {
                            if (resource && typeof resource === "string" && resource.indexOf("imported.stl") !== -1) {
                                resource = stlData;
                            }
                            return origFetch.call(this, resource, config);
                        };
                    }
                    if(window.Worker) {
                        var origWorker = window.Worker;
                        window.Worker = function(scriptURL, options) {
                            var absUrl = new URL(scriptURL, location.href).href;
                            var code = "var stlData = '" + stlData + "'; var origOpen = XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open = function(m, u) { if (u && typeof u === 'string' && u.indexOf('imported.stl') !== -1) { arguments[1] = stlData; } return origOpen.apply(this, arguments); }; if(self.fetch) { var origFetch = self.fetch; self.fetch = function(r, c) { if (r && typeof r === 'string' && r.indexOf('imported.stl') !== -1) { r = stlData; } return origFetch.call(this, r, c); }; } importScripts('" + absUrl + "');";
                            var blob = new Blob([code], { type: "application/javascript" });
                            return new origWorker(URL.createObjectURL(blob), options);
                        };
                    }
                })();
                </script>
                '''.replace("__B64_STL__", b64_stl)
                
                if "<head>" in content: content = content.replace("<head>", "<head>" + injector)
                else: content = injector + content
                    
                encoded_content = content.encode('utf-8')
                self.send_response(200); self.send_header("Content-type", "text/html"); self.send_header("Content-Length", str(len(encoded_content))); self._send_cors(); self.end_headers(); self.wfile.write(encoded_content)
                return
            except Exception as e:
                self.send_response(500); self._send_cors(); self.end_headers(); self.wfile.write(str(e).encode())

        else:
            try:
                fn = self.path.strip("/")
                with open(os.path.join(ASSETS_DIR, fn), "rb") as f:
                    self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self._send_cors(); self.end_headers()
            
    def log_message(self, *args): pass

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

threading.Thread(target=lambda: ThreadedHTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APP FLET MAIN
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v20.67 TITAN FORGE"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v20.67 TITAN | Web Worker Bypass Activo", color="#00E676", weight="bold")

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

        ensamble_stack = []
        herramienta_actual = "custom"
        modo_ensamble = False

        def clear_editor():
            nonlocal ensamble_stack
            ensamble_stack = []
            txt_code.value = "function main() {\n  return CSG.cube({radius:[0.01,0.01,0.01]});\n}"
            status.value = "✓ Código borrado."; status.color = "#B71C1C"
            txt_code.update(); page.update()

        def update_code_wrapper(e=None): 
            if not modo_ensamble: generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=45, text_align="right", size=13, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"; txt_val.update(); 
                if not modo_ensamble: update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="#E6EDF3"), sl, txt_val])

        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False); sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False); sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False); sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False); sl_g_tol, r_g_tol = create_slider("Tol. Global (G_TOL)", 0.0, 2.0, 0.2, False); sl_kine, r_kine = create_slider("Animación (º)", 0, 360, 0, True)

        dd_mat = ft.Dropdown(options=[ft.dropdown.Option("PLA Gris Mate"), ft.dropdown.Option("PETG Transparente"), ft.dropdown.Option("Fibra de Carbono"), ft.dropdown.Option("Aluminio Mecanizado"), ft.dropdown.Option("Madera Bambú"), ft.dropdown.Option("Oro Puro"), ft.dropdown.Option("Neón Cyan")], value="PLA Gris Mate", bgcolor="#161B22", color="#00E5FF", expand=True, text_size=12)
        dd_mat.on_change = update_code_wrapper

        def prepare_js_payload():
            c_val = {"PLA Gris Mate": "[0.5, 0.5, 0.5, 1.0]", "PETG Transparente": "[0.8, 0.9, 0.9, 0.45]", "Fibra de Carbono": "[0.15, 0.15, 0.15, 1.0]", "Aluminio Mecanizado": "[0.7, 0.75, 0.8, 1.0]", "Madera Bambú": "[0.6, 0.4, 0.2, 1.0]", "Oro Puro": "[0.9, 0.75, 0.1, 1.0]", "Neón Cyan": "[0.0, 1.0, 1.0, 0.8]"}.get(dd_mat.value, "[0.5, 0.5, 0.5, 1.0]")
            header = f"  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value}; var G_TOL = {sl_g_tol.value}; var KINE_T = {sl_kine.value}; var MAT_C = {c_val};\n"
            utils_block = """  if(typeof CSG !== 'undefined' && typeof CSG.Matrix4x4 === 'undefined' && typeof Matrix4x4 !== 'undefined') { CSG.Matrix4x4 = Matrix4x4; }
  var UTILS = { 
    trans: function(o, v) { if(!o) return o; try { if(Array.isArray(o)) return o.map(function(x){return UTILS.trans(x, v);}); if(typeof o.translate === 'function') return o.translate(v); if(typeof translate !== 'undefined') return translate(v, o); } catch(e) {} return o; },
    scale: function(o, v) { if(!o) return o; try { if(Array.isArray(o)) return o.map(function(x){return UTILS.scale(x, v);}); if(typeof o.scale === 'function') return o.scale(v); if(typeof scale !== 'undefined') return scale(v, o); } catch(e) {} return o; },
    rotZ: function(o, d) { if(!o) return o; try { if(Array.isArray(o)) return o.map(function(x){return UTILS.rotZ(x, d);}); if(typeof o.rotateZ === 'function') return o.rotateZ(d); if(typeof rotate !== 'undefined') return rotate([0,0,d], o); } catch(e) {} return o; },
    rotX: function(o, d) { if(!o) return o; try { if(Array.isArray(o)) return o.map(function(x){return UTILS.rotX(x, d);}); if(typeof o.rotateX === 'function') return o.rotateX(d); if(typeof rotate !== 'undefined') return rotate([d,0,0], o); } catch(e) {} return o; },
    rotY: function(o, d) { if(!o) return o; try { if(Array.isArray(o)) return o.map(function(x){return UTILS.rotY(x, d);}); if(typeof o.rotateY === 'function') return o.rotateY(d); if(typeof rotate !== 'undefined') return rotate([0,d,0], o); } catch(e) {} return o; },
    mat: function(o) { if(!o) return CSG.cube({radius:[0.01,0.01,0.01]}); try { if(Array.isArray(o)) return o.map(function(x){return UTILS.mat(x);}); if(typeof o.setColor === 'function') return o.setColor(MAT_C); } catch(e) {} return o; } 
  };\n"""
            header += utils_block
            param_def = "function getParameterDefinitions() { return [{name: 'KINE_T', type: 'slider', initial: 0, min: 0, max: 360, step: 1, caption: 'Cinemática (º)'}]; }\n"
            c = txt_code.value
            if "getParameterDefinitions" not in c:
                if "function main(" in c: c = param_def + c.replace("function main(params) {", "function main(params) {\n" + header + "  if(params && params.KINE_T !== undefined) KINE_T = params.KINE_T;\n", 1).replace("function main() {", "function main(params) {\n" + header + "  if(params && params.KINE_T !== undefined) KINE_T = params.KINE_T;\n", 1)
                else: c = param_def + header + "\n" + c
            else:
                if "function main(" in c: c = c.replace("function main(params) {", "function main(params) {\n" + header + "  if(params && params.KINE_T !== undefined) KINE_T = params.KINE_T;\n", 1).replace("function main() {", "function main(params) {\n" + header + "  if(params && params.KINE_T !== undefined) KINE_T = params.KINE_T;\n", 1)
                else: c = header + "\n" + c
            return c

        def run_render():
            global LATEST_CODE_B64, LATEST_NEEDS_STL
            js_payload = prepare_js_payload()
            LATEST_CODE_B64 = base64.b64encode(js_payload.encode('utf-8')).decode()
            LATEST_NEEDS_STL = ("IMPORTED_STL" in js_payload) or herramienta_actual.startswith("stl")
            set_tab(2); page.update()

        sw_ensamble = ft.Switch(label="Manejo Código Ensamblador", value=False, active_color="#FFAB00")
        
        def parse_current_tool_to_stack_var():
            code_lines = txt_code.value.split('\n')
            var_name = f"obj_{len(ensamble_stack)}"
            body = []
            for line in code_lines[1:-1]:
                if line.strip().startswith("return "):
                    ret_val = line.replace("return UTILS.mat(", "").replace("return ", "").replace(");", "").replace(";", "").strip()
                    body.append(f"  var {var_name} = {ret_val};")
                else: body.append(line)
            return "\n".join(body), var_name

        def add_to_stack(op_type):
            nonlocal ensamble_stack
            body, var_name = parse_current_tool_to_stack_var()
            if not ensamble_stack: ensamble_stack.append({"body": body, "var": var_name, "op": "base"})
            else: ensamble_stack.append({"body": body, "var": var_name, "op": op_type})
            compile_stack_to_editor()

        def compile_stack_to_editor():
            if not ensamble_stack: return
            final_code = "function main() {\n"
            final_var = ""
            for i, item in enumerate(ensamble_stack):
                final_code += f"  // --- Modificador {i} ({item['op']}) ---\n{item['body']}\n"
                if item["op"] == "base": final_var = item["var"]
                elif item["op"] == "union": final_code += f"  {final_var} = {final_var}.union({item['var']});\n"
                elif item["op"] == "subtract": final_code += f"  {final_var} = {final_var}.subtract({item['var']});\n"
            final_code += f"  return UTILS.mat({final_var});\n}}"
            txt_code.value = final_code; txt_code.update(); page.update()

        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton(content=ft.Text("➕ UNIR PIEZA", color="white"), on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", expand=True),
            ft.ElevatedButton(content=ft.Text("➖ RESTAR PIEZA", color="white"), on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", expand=True)
        ], visible=False)

        def toggle_ensamble(e):
            nonlocal modo_ensamble
            modo_ensamble = sw_ensamble.value
            panel_ensamble_ops.visible = modo_ensamble
            page.update()
            
        sw_ensamble.on_change = toggle_ensamble

        panel_globales = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11), sw_ensamble], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), 
            r_g_w, r_g_l, r_g_h, r_g_t, r_g_tol, ft.Divider(color="#333333"), 
            ft.Row([ft.Text("🎨 TEXTURA / RENDER:", color="#E6EDF3", size=11, width=130), dd_mat]), ft.Divider(color="#333333"), 
            ft.Text("🎬 CINEMÁTICA INTERACTIVA", color="#B388FF", weight="bold", size=11), r_kine,
            panel_ensamble_ops
        ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        col_custom = ft.Column([ft.Text("Modo Código Libre (Edita en la pestaña CODE)", color="#00E676")], visible=True)
        def inst(texto): return ft.Text("ℹ️ " + texto, color="#FFD54F", size=11, italic=True)

        tf_sketch_pts = ft.TextField(label="Coordenadas (X, Y) - Una por línea", value="0,0\n50,0\n50,20\n25,40\n0,20", multiline=True, height=150, bgcolor="#161B22", color="#00E5FF"); tf_sketch_pts.on_change = update_code_wrapper; sl_sketch_h, r_sketch_h = create_slider("Altura (Z)", 1, 300, 20, False); col_sketcher = ft.Column([ft.Text("Sketcher 2D / Extrusor Libre", color="#2962FF", weight="bold"), inst("Pega tabla Excel."), ft.Container(content=ft.Column([tf_sketch_pts, r_sketch_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        lbl_stl_status = ft.Text("Ningún STL cargado.", color="#8B949E", size=11)
        sl_stl_sc, r_stl_sc = create_slider("Escala (%)", 1, 500, 100, True); sl_stl_x, r_stl_x = create_slider("Mover X", -150, 150, 0, False); sl_stl_y, r_stl_y = create_slider("Mover Y", -150, 150, 0, False); sl_stl_z, r_stl_z = create_slider("Mover Z", -150, 150, 0, False)
        panel_stl_transform = ft.Container(content=ft.Column([ft.Row([ft.Text("🔄 TRANSF. BASE STL", color="#00E676", weight="bold"), lbl_stl_status]), ft.ElevatedButton(content=ft.Text("📂 IR A FILES", color="black"), on_click=lambda _: set_tab(5), bgcolor="#00E5FF", width=float('inf')), r_stl_sc, r_stl_x, r_stl_y, r_stl_z]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"), visible=False)

        col_stl = ft.Column([ft.Text("Visor STL Original", color="#00E676", weight="bold")], visible=False)
        sl_stlf_z, r_stlf_z = create_slider("Corte Z (mm)", 0, 50, 1, False); col_stl_flatten = ft.Column([ft.Text("Aplanar Base (Flatten)", color="#00E676", weight="bold"), r_stlf_z], visible=False)
        dd_stls_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E"); dd_stls_axis.on_change = update_code_wrapper; sl_stls_pos, r_stls_pos = create_slider("Punto Corte", -150, 150, 0, False); col_stl_split = ft.Column([ft.Text("Split XYZ", color="#00E676", weight="bold"), dd_stls_axis, r_stls_pos], visible=False)
        sl_stlc_s, r_stlc_s = create_slider("Caja Tamaño", 10, 300, 50, False); col_stl_crop = ft.Column([ft.Text("Crop Box", color="#00E676", weight="bold"), r_stlc_s], visible=False)
        dd_stld_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E"); dd_stld_axis.on_change = update_code_wrapper; sl_stld_r, r_stld_r = create_slider("Radio Perfo.", 0.5, 20, 1.6, False); sl_stld_px, r_stld_px = create_slider("Coord 1", -150, 150, 0, False); sl_stld_py, r_stld_py = create_slider("Coord 2", -150, 150, 0, False); col_stl_drill = ft.Column([ft.Text("Taladro 3D", color="#00E676", weight="bold"), dd_stld_axis, r_stld_r, r_stld_px, r_stld_py], visible=False)
        sl_stlm_w, r_stlm_w = create_slider("Ancho Orejeta", 10, 100, 40, False); sl_stlm_d, r_stlm_d = create_slider("Separación Ext.", 20, 200, 80, False); col_stl_mount = ft.Column([ft.Text("Orejetas", color="#00E676", weight="bold"), r_stlm_w, r_stlm_d], visible=False)
        sl_stle_r, r_stle_r = create_slider("Radio Disco", 5, 30, 15, False); sl_stle_d, r_stle_d = create_slider("Apertura XY", 10, 200, 50, False); col_stl_ears = ft.Column([ft.Text("Mouse Ears", color="#00E676", weight="bold"), r_stle_r, r_stle_d], visible=False)
        sl_stlp_sx, r_stlp_sx = create_slider("Largo Parche X", 5, 100, 20, False); sl_stlp_sy, r_stlp_sy = create_slider("Ancho Parche Y", 5, 100, 20, False); sl_stlp_sz, r_stlp_sz = create_slider("Alto Parche Z", 1, 50, 5, False); col_stl_patch = ft.Column([ft.Text("Parche Refuerzo", color="#00E676", weight="bold"), r_stlp_sx, r_stlp_sy, r_stlp_sz], visible=False)
        sl_stlh_r, r_stlh_r = create_slider("Tamaño Hex", 2, 20, 5, False); col_stl_honeycomb = ft.Column([ft.Text("Aligerado Honeycomb", color="#00E676", weight="bold"), r_stlh_r], visible=False)
        sl_stlpg_r, r_stlpg_r = create_slider("Radio Hélice", 10, 100, 40, False); sl_stlpg_t, r_stlpg_t = create_slider("Grosor Aro", 1, 10, 3, False); sl_stlpg_x, r_stlpg_x = create_slider("Centro X", -100, 100, 0, False); sl_stlpg_y, r_stlpg_y = create_slider("Centro Y", -100, 100, 0, False); col_stl_propguard = ft.Column([ft.Text("Prop-Guard", color="#00E676", weight="bold"), r_stlpg_r, r_stlpg_t, r_stlpg_x, r_stlpg_y], visible=False)

        tf_texto = ft.TextField(label="Escribe Texto", value="NEXUS", max_length=15, bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Fino"), ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Braille")], value="Voxel Grueso", expand=True, bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Solo Texto"), ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Soporte de Mesa"), ft.dropdown.Option("Colgante Militar"), ft.dropdown.Option("Placa Ovalada")], value="Colgante Militar", expand=True, bgcolor="#161B22")
        sw_txt_grabado = ft.Switch(label="Texto Grabado", value=False, active_color="#00E5FF")
        tf_texto.on_change = update_code_wrapper; dd_txt_estilo.on_change = update_code_wrapper; dd_txt_base.on_change = update_code_wrapper; sw_txt_grabado.on_change = update_code_wrapper
        col_texto = ft.Column([ft.Text("Placas Especiales", color="#880E4F", weight="bold"), ft.Container(content=ft.Column([tf_texto, ft.Row([dd_txt_estilo, dd_txt_base]), sw_txt_grabado]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_las_x, r_las_x = create_slider("Ancho Objeto", 10, 200, 50, False); sl_las_y, r_las_y = create_slider("Largo Objeto", 10, 200, 50, False); sl_las_z, r_las_z = create_slider("Altura Z Corte", 0, 100, 5, False); col_laser = ft.Column([ft.Text("Perfil Láser", color="#D50000"), ft.Container(content=ft.Column([r_las_x, r_las_y, r_las_z]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_alin_f, r_alin_f = create_slider("Filas (Y)", 1, 10, 3, True); sl_alin_c, r_alin_c = create_slider("Columnas (X)", 1, 10, 3, True); sl_alin_dx, r_alin_dx = create_slider("Distancia X", 5, 100, 20, False); sl_alin_dy, r_alin_dy = create_slider("Distancia Y", 5, 100, 20, False); sl_alin_h, r_alin_h = create_slider("Altura Base", 2, 50, 10, False); col_array_lin = ft.Column([ft.Text("Matriz Lineal Grid", color="#00B0FF"), ft.Container(content=ft.Column([r_alin_f, r_alin_c, r_alin_dx, r_alin_dy, r_alin_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_apol_n, r_apol_n = create_slider("Repeticiones", 2, 36, 8, True); sl_apol_r, r_apol_r = create_slider("Radio Corona", 10, 150, 40, False); sl_apol_rp, r_apol_rp = create_slider("Radio Pieza", 2, 20, 5, False); sl_apol_h, r_apol_h = create_slider("Grosor (Z)", 2, 50, 5, False); col_array_pol = ft.Column([ft.Text("Matriz Polar Circular", color="#00B0FF"), ft.Container(content=ft.Column([r_apol_n, r_apol_r, r_apol_rp, r_apol_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_loft_w, r_loft_w = create_slider("Ancho Base SQ", 10, 150, 60, False); sl_loft_r, r_loft_r = create_slider("Radio Top", 5, 100, 20, False); sl_loft_h, r_loft_h = create_slider("Altura Z", 10, 200, 80, False); sl_loft_g, r_loft_g = create_slider("Grosor Pared", 1, 10, 2, False); col_loft = ft.Column([ft.Text("Lofting Adaptador", color="#D50000"), ft.Container(content=ft.Column([r_loft_w, r_loft_r, r_loft_h, r_loft_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_pan_x, r_pan_x = create_slider("Ancho X", 20, 200, 80, False); sl_pan_y, r_pan_y = create_slider("Largo Y", 20, 200, 80, False); sl_pan_z, r_pan_z = create_slider("Alto Z", 2, 50, 10, False); sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False); col_panal = ft.Column([ft.Text("Panal Honeycomb", color="#FBC02D"), ft.Container(content=ft.Column([r_pan_x, r_pan_y, r_pan_z, r_pan_r]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_vor_ro, r_vor_ro = create_slider("Radio Ext", 10, 100, 40, False); sl_vor_ri, r_vor_ri = create_slider("Radio Int", 5, 95, 35, False); sl_vor_h, r_vor_h = create_slider("Altura Tubo", 20, 200, 100, False); sl_vor_d, r_vor_d = create_slider("Densidad Red", 4, 24, 12, True); col_voronoi = ft.Column([ft.Text("Carcasa Voronoi", color="#FBC02D"), ft.Container(content=ft.Column([r_vor_ro, r_vor_ri, r_vor_h, r_vor_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_evo_d, r_evo_d = create_slider("Nº Dientes", 8, 60, 20, True); sl_evo_m, r_evo_m = create_slider("Módulo", 1, 10, 2, False); sl_evo_h, r_evo_h = create_slider("Grosor (Z)", 2, 50, 10, False); col_evolvente = ft.Column([ft.Text("Engranaje Evolvente", color="#FFAB00"), ft.Container(content=ft.Column([r_evo_d, r_evo_m, r_evo_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_crem_d, r_crem_d = create_slider("Nº Dientes", 5, 50, 15, True); sl_crem_m, r_crem_m = create_slider("Módulo", 1, 10, 2, False); sl_crem_h, r_crem_h = create_slider("Grosor (Z)", 2, 50, 10, False); sl_crem_w, r_crem_w = create_slider("Ancho Base", 2, 50, 8, False); col_cremallera = ft.Column([ft.Text("Cremallera", color="#FFAB00"), ft.Container(content=ft.Column([r_crem_d, r_crem_m, r_crem_h, r_crem_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_con_d, r_con_d = create_slider("Nº Dientes", 8, 40, 16, True); sl_con_rb, r_con_rb = create_slider("Radio Base", 10, 100, 30, False); sl_con_rt, r_con_rt = create_slider("Radio Top", 5, 80, 15, False); sl_con_h, r_con_h = create_slider("Altura Cono", 5, 100, 20, False); col_conico = ft.Column([ft.Text("Engranaje Cónico", color="#FFAB00"), ft.Container(content=ft.Column([r_con_d, r_con_rb, r_con_rt, r_con_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_mc_x, r_mc_x = create_slider("Ancho X", 20, 200, 60, False); sl_mc_y, r_mc_y = create_slider("Largo Y", 20, 200, 40, False); sl_mc_z, r_mc_z = create_slider("Alto Z", 10, 100, 30, False); sl_mc_tol, r_mc_tol = create_slider("Tol. Encaje", 0.0, 2.0, 0.4, False); sl_mc_sep, r_mc_sep = create_slider("Sep. Visual", 0, 50, 15, False); col_multicaja = ft.Column([ft.Text("Caja+Tapa (Multicuerpo)", color="#7CB342"), ft.Container(content=ft.Column([r_mc_x, r_mc_y, r_mc_z, r_mc_tol, r_mc_sep]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_perf_p, r_perf_p = create_slider("Nº Puntas", 3, 20, 5, True); sl_perf_re, r_perf_re = create_slider("Radio Ext", 10, 100, 40, False); sl_perf_ri, r_perf_ri = create_slider("Radio Int", 5, 80, 15, False); sl_perf_h, r_perf_h = create_slider("Grosor (Z)", 2, 50, 10, False); col_perfil = ft.Column([ft.Text("Estrella Paramétrica 2D", color="#AB47BC"), ft.Container(content=ft.Column([r_perf_p, r_perf_re, r_perf_ri, r_perf_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_rev_h, r_rev_h = create_slider("Altura Total", 20, 200, 80, False); sl_rev_r1, r_rev_r1 = create_slider("Radio Base", 10, 100, 30, False); sl_rev_r2, r_rev_r2 = create_slider("Radio Cuello", 5, 80, 15, False); sl_rev_g, r_rev_g = create_slider("Grosor Pared", 0, 15, 2, False); col_revolucion = ft.Column([ft.Text("Sólido de Revolución", color="#AB47BC"), ft.Container(content=ft.Column([r_rev_h, r_rev_r1, r_rev_r2, r_rev_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_c_grosor, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False); col_cubo = ft.Column([ft.Text("Cubo Paramétrico", color="#8B949E"), r_c_g], visible=False)
        sl_p_rint, r_p_rint = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_lados, r_p_lados = create_slider("Caras (LowPoly)", 3, 64, 64, True); col_cilindro = ft.Column([ft.Text("Cilindro / Prisma", color="#8B949E"), r_p_rint, r_p_lados], visible=False)
        sl_l_largo, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False); sl_l_ancho, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False); sl_l_grosor, r_l_g = create_slider("Grosor Chapa", 1, 20, 3, False); sl_l_hueco, r_l_h = create_slider("Agujero", 0, 10, 2, False); sl_l_chaf, r_l_chaf = create_slider("Refuerzo Int", 0, 20, 5, False); col_escuadra = ft.Column([ft.Text("Escuadra Tipo L", color="#8B949E"), ft.Container(content=ft.Column([r_l_l, r_l_a, r_l_g, r_l_h, r_l_chaf]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_e_dientes, r_e_d = create_slider("Dientes", 6, 40, 16, True); sl_e_radio, r_e_r = create_slider("Radio Base", 10, 100, 30, False); sl_e_grosor, r_e_g = create_slider("Grosor", 2, 50, 5, False); sl_e_eje, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False); col_engranaje = ft.Column([ft.Text("Piñón Cuadrado Básico", color="#8B949E"), ft.Container(content=ft.Column([r_e_d, r_e_r, r_e_g, r_e_e]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False); sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False); sl_pcb_h, r_pcb_h = create_slider("Altura Caja", 10, 100, 20, False); sl_pcb_t, r_pcb_t = create_slider("Grosor Pared", 1, 10, 2, False); col_pcb = ft.Column([ft.Text("Caja para Electrónica", color="#8B949E"), ft.Container(content=ft.Column([r_pcb_x, r_pcb_y, r_pcb_h, r_pcb_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_v_l, r_v_l = create_slider("Longitud", 10, 300, 50, False); col_vslot = ft.Column([ft.Text("Perfil V-Slot 2020", color="#8B949E"), ft.Container(content=ft.Column([r_v_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False); sl_bi_d, r_bi_d = create_slider("Diámetro Eje", 5, 30, 10, False); col_bisagra = ft.Column([ft.Text("Bisagra Print-in-Place", color="#8B949E"), ft.Container(content=ft.Column([r_bi_l, r_bi_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_clamp_d, r_clamp_d = create_slider("Ø Tubo", 10, 100, 25, False); sl_clamp_g, r_clamp_g = create_slider("Grosor Arco", 2, 15, 5, False); sl_clamp_w, r_clamp_w = create_slider("Ancho Pieza", 5, 50, 15, False); col_abrazadera = ft.Column([ft.Text("Abrazadera de Tubo", color="#8B949E"), ft.Container(content=ft.Column([r_clamp_d, r_clamp_g, r_clamp_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True); sl_fij_l, r_fij_l = create_slider("Largo Tornillo", 0, 100, 30, False); col_fijacion = ft.Column([ft.Text("Tuerca / Tornillo Hex", color="#FFAB00"), ft.Container(content=ft.Column([r_fij_m, r_fij_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_rod_dint, r_rod_dint = create_slider("Ø Eje Interno", 3, 50, 8, False); sl_rod_dext, r_rod_dext = create_slider("Ø Externo", 10, 100, 22, False); sl_rod_h, r_rod_h = create_slider("Altura", 3, 30, 7, False); col_rodamiento = ft.Column([ft.Text("Rodamiento de Bolas", color="#FFAB00"), ft.Container(content=ft.Column([r_rod_dint, r_rod_dext, r_rod_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_plan_rs, r_plan_rs = create_slider("Radio Sol", 5, 40, 10, False); sl_plan_rp, r_plan_rp = create_slider("Radio Planetas", 4, 30, 8, False); sl_plan_h, r_plan_h = create_slider("Grosor Total", 3, 30, 6, False); col_planetario = ft.Column([ft.Text("Mecanismo Planetario (Soporta Cinemática)", color="#FFAB00"), ft.Container(content=ft.Column([r_plan_rs, r_plan_rp, r_plan_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_pol_t, r_pol_t = create_slider("Nº Dientes", 10, 60, 20, True); sl_pol_w, r_pol_w = create_slider("Ancho Correa", 4, 20, 6, False); sl_pol_d, r_pol_d = create_slider("Ø Eje Motor", 2, 12, 5, False); col_polea = ft.Column([ft.Text("Polea Dentada GT2", color="#00E5FF"), ft.Container(content=ft.Column([r_pol_t, r_pol_w, r_pol_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_hel_r, r_hel_r = create_slider("Radio Total", 20, 150, 50, False); sl_hel_n, r_hel_n = create_slider("Nº Aspas", 2, 12, 4, True); sl_hel_p, r_hel_p = create_slider("Torsión", 10, 80, 45, False); col_helice = ft.Column([ft.Text("Hélice Paramétrica", color="#00E5FF"), ft.Container(content=ft.Column([r_hel_r, r_hel_n, r_hel_p]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_rot_r, r_rot_r = create_slider("Radio Bola", 5, 30, 10, False); col_rotula = ft.Column([ft.Text("Rótula Articulada", color="#00E5FF"), ft.Container(content=ft.Column([r_rot_r]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_car_x, r_car_x = create_slider("Ancho (X)", 20, 200, 80, False); sl_car_y, r_car_y = create_slider("Largo (Y)", 20, 200, 120, False); sl_car_z, r_car_z = create_slider("Alto (Z)", 10, 100, 30, False); sl_car_t, r_car_t = create_slider("Grosor Pared", 1, 5, 2, False); col_carcasa = ft.Column([ft.Text("Carcasa Smart con Ventilación", color="#00E5FF"), ft.Container(content=ft.Column([r_car_x, r_car_y, r_car_z, r_car_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_mue_r, r_mue_r = create_slider("Radio Resorte", 5, 50, 15, False); sl_mue_h, r_mue_h = create_slider("Radio Hilo", 1, 10, 2, False); sl_mue_v, r_mue_v = create_slider("Nº Vueltas", 2, 20, 5, False); sl_mue_alt, r_mue_alt = create_slider("Altura Total", 10, 200, 40, False); col_muelle = ft.Column([ft.Text("Muelle Helicoidal", color="#FFAB00"), ft.Container(content=ft.Column([r_mue_r, r_mue_h, r_mue_v, r_mue_alt]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_acme_d, r_acme_d = create_slider("Diámetro Eje", 4, 30, 8, False); sl_acme_p, r_acme_p = create_slider("Paso (Pitch)", 1, 10, 2, False); sl_acme_l, r_acme_l = create_slider("Longitud", 10, 200, 50, False); col_acme = ft.Column([ft.Text("Eje Roscado (ACME)", color="#FFAB00"), ft.Container(content=ft.Column([r_acme_d, r_acme_p, r_acme_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_codo_r, r_codo_r = create_slider("Radio Tubo", 2, 50, 10, False); sl_codo_c, r_codo_c = create_slider("Radio Curva", 10, 150, 30, False); sl_codo_a, r_codo_a = create_slider("Ángulo Giroº", 10, 180, 90, False); sl_codo_g, r_codo_g = create_slider("Grosor Hueco", 0, 10, 2, False); col_codo = ft.Column([ft.Text("Tubería y Codos", color="#00E5FF"), ft.Container(content=ft.Column([r_codo_r, r_codo_c, r_codo_a, r_codo_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_naca_c, r_naca_c = create_slider("Cuerda", 20, 200, 80, False); sl_naca_g, r_naca_g = create_slider("Grosor Max %", 5, 30, 15, False); sl_naca_e, r_naca_e = create_slider("Envergadura Z", 10, 300, 100, False); col_naca = ft.Column([ft.Text("Perfil Alar NACA", color="#00E5FF"), ft.Container(content=ft.Column([r_naca_c, r_naca_g, r_naca_e]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_st_ang, r_st_ang = create_slider("Inclinación º", 5, 45, 15, False); sl_st_w, r_st_w = create_slider("Ancho Base", 40, 120, 70, False); sl_st_t, r_st_t = create_slider("Grosor Dispo.", 6, 20, 12, False); col_stand_movil = ft.Column([ft.Text("Soporte para Móvil/Tablet", color="#00E676"), ft.Container(content=ft.Column([r_st_ang, r_st_w, r_st_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_clip_d, r_clip_d = create_slider("Ø Cable", 3, 15, 6, False); sl_clip_w, r_clip_w = create_slider("Ancho Adhesivo", 10, 40, 20, False); col_clip_cable = ft.Column([ft.Text("Clip de Cables (Desk)", color="#00E676"), ft.Container(content=ft.Column([r_clip_d, r_clip_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_vr_s, r_vr_s = create_slider("Tamaño Base", 50, 500, 200, False); col_vr_pedestal = ft.Column([ft.Text("Pedestal de Exhibición (Modo VR)", color="#B388FF"), ft.Container(content=ft.Column([r_vr_s]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        def get_stl_base_js():
            sc = sl_stl_sc.value / 100.0; tx = sl_stl_x.value; ty = sl_stl_y.value; tz = sl_stl_z.value
            return f"  var sc = {sc}; var tx = {tx}; var ty = {ty}; var tz = {tz};\n  var dron = null;\n  if (typeof IMPORTED_STL !== 'undefined') {{ var parts = Array.isArray(IMPORTED_STL) ? IMPORTED_STL : [IMPORTED_STL]; for(var i=0; i<parts.length; i++) {{ var p = parts[i]; if(p && p.polygons && typeof p.scale !== 'function') {{ try {{ p = CSG.fromPolygons(p.polygons); }} catch(e) {{}} }} if(p && typeof p.union === 'function') {{ if(!dron) dron = p; else dron = dron.union(p); }} }} }}\n  if(!dron || typeof dron.union !== 'function') {{ return CSG.cube({{radius:[0.01, 0.01, 0.01]}}); }}\n  dron = UTILS.scale(dron, [sc, sc, sc]); dron = UTILS.trans(dron, [tx, ty, tz]);\n"

        def generate_param_code():
            h = herramienta_actual
            code = "function main() {\n"
            if h == "custom": pass
            elif h == "sketcher":
                code += f"  var h_ext = {sl_sketch_h.value};\n  var raw_pts = `{tf_sketch_pts.value.replace(chr(10), '\\n')}`;\n  var lines = raw_pts.split('\\n'); var pts = [];\n  for(var i=0; i<lines.length; i++) {{ var str = lines[i].replace(/[\\[\\]]/g, '').trim(); var coords = str.split(/[,;|\\t ]+/); var coords_filtered = coords.filter(x => x !== ''); if(coords_filtered.length >= 2) pts.push([parseFloat(coords_filtered[0]), parseFloat(coords_filtered[1])]); }}\n  if(pts.length < 3) return CSG.cube({{radius:[0.01,0.01,0.01]}});\n  try {{ return UTILS.mat(CAG.fromPoints(pts).extrude({{offset: [0, 0, h_ext]}})); }} catch(e) {{ return CSG.cube({{radius:[5,5,5]}}); }}\n}}"
            elif h.startswith("stl"):
                code += get_stl_base_js()
                if h == "stl": code += "  return UTILS.mat(dron);\n}"
                elif h == "stl_flatten": code += f"  return UTILS.mat(dron.subtract(CSG.cube({{center:[0,0,-500+{sl_stlf_z.value}], radius:[1000,1000,500]}})));\n}}"
                elif h == "stl_split":
                    ax = dd_stls_axis.value; p = sl_stls_pos.value
                    cx = p-500 if ax=='X' else 0; cy = p-500 if ax=='Y' else 0; cz = p-500 if ax=='Z' else 0
                    code += f"  return UTILS.mat(dron.subtract(CSG.cube({{center:[{cx},{cy},{cz}], radius:[1000,1000,1000]}})));\n}}"
                elif h == "stl_crop": S = sl_stlc_s.value / 2.0; code += f"  return UTILS.mat(dron.intersect(CSG.cube({{center:[0,0,0], radius:[{S},{S},{S}]}})));\n}}"
                elif h == "stl_drill":
                    ax = dd_stld_axis.value; R = sl_stld_r.value; p1 = sl_stld_px.value; p2 = sl_stld_py.value
                    st = f"[-500,{p1},{p2}]" if ax=='X' else (f"[{p1},-500,{p2}]" if ax=='Y' else f"[{p1},{p2},-500]")
                    en = f"[500,{p1},{p2}]" if ax=='X' else (f"[{p1},500,{p2}]" if ax=='Y' else f"[{p1},{p2},500]")
                    code += f"  return UTILS.mat(dron.subtract(CSG.cylinder({{start:{st}, end:{en}, radius:{R}}})));\n}}"
                elif h == "stl_mount":
                    w = sl_stlm_w.value; d = sl_stlm_d.value
                    code += f"  var m1 = CSG.cube({{center:[{d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{d/2},0,-5], end:[{d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  var m2 = CSG.cube({{center:[{-d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{-d/2},0,-5], end:[{-d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  return UTILS.mat(dron.union(m1).union(m2));\n}}"
                elif h == "stl_ears":
                    r = sl_stle_r.value; d = sl_stle_d.value
                    code += f"  var c1=CSG.cylinder({{start:[{d/2},{d/2},0], end:[{d/2},{d/2},0.4], radius:{r}}}); var c2=CSG.cylinder({{start:[{-d/2},{d/2},0], end:[{-d/2},{d/2},0.4], radius:{r}}});\n"
                    code += f"  var c3=CSG.cylinder({{start:[{d/2},{-d/2},0], end:[{d/2},{-d/2},0.4], radius:{r}}}); var c4=CSG.cylinder({{start:[{-d/2},{-d/2},0], end:[{-d/2},{-d/2},0.4], radius:{r}}});\n"
                    code += f"  return UTILS.mat(dron.union(c1).union(c2).union(c3).union(c4));\n}}"
                elif h == "stl_patch": code += f"  return UTILS.mat(dron.union(CSG.cube({{center:[0,0,0], radius:[{sl_stlp_sx.value/2},{sl_stlp_sy.value/2},{sl_stlp_sz.value/2}]}})));\n}}"
                elif h == "stl_honeycomb":
                    hex_r = sl_stlh_r.value
                    code += f"  var dx = {hex_r}*1.732+2; var dy = {hex_r}*1.5+2; var holes = null;\n"
                    code += f"  for(var x = -100; x < 100; x += dx) {{ for(var y = -100; y < 100; y += dy) {{\n      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0;\n"
                    code += f"      var hex = CSG.cylinder({{start:[x+offset, y, -500], end:[x+offset, y, 500], radius:{hex_r}, slices:6}});\n      if(!holes) holes = hex; else holes = holes.union(hex);\n  }} }}\n  if(holes) return UTILS.mat(dron.subtract(holes));\n  return UTILS.mat(dron);\n}}"
                elif h == "stl_propguard":
                    r = sl_stlpg_r.value; t = sl_stlpg_t.value; px = sl_stlpg_x.value; py = sl_stlpg_y.value
                    code += f"  var out = CSG.cylinder({{start:[{px},{py},0], end:[{px},{py},10], radius:{r+t}, slices:32}});\n  var inn = CSG.cylinder({{start:[{px},{py},-1], end:[{px},{py},11], radius:{r}, slices:32}});\n"
                    code += f"  return UTILS.mat(dron.union(out.subtract(inn)));\n}}"
            elif h == "texto":
                txt_input = tf_texto.value.upper()[:15]; estilo = dd_txt_estilo.value; base = dd_txt_base.value; grabado = sw_txt_grabado.value
                if not txt_input: txt_input = " "
                code += f"  var texto = \"{txt_input}\"; var h = GH;\n"
                code += f"  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0], '0':[14,17,17,17,14], '1':[4,12,4,4,14], '2':[14,1,14,16,31], '3':[14,1,14,1,14], '4':[18,18,31,2,2], '5':[31,16,14,1,14], '6':[14,16,30,17,14], '7':[31,1,2,4,8], '8':[14,17,14,17,14], '9':[14,17,15,1,14] }};\n"
                z_start = "h/2" if not grabado else "h - 1"; h_letra = "h/2" if not grabado else "h+2"
                if "Voxel" in estilo:
                    es_grueso = "1.1" if "Grueso" in estilo else "2.1"
                    code += f"  var pText = null; var vSize = 2; var charWidth = 6 * vSize;\n  for(var i=0; i<texto.length; i++) {{ var cMat = font[texto[i]] || font[' ']; var offX = i * charWidth; for(var r=0; r<5; r++) {{ for(var c=0; c<5; c++) {{ if ((cMat[r] >> (4 - c)) & 1) {{ var vox = CSG.cube({{center:[offX+(c*vSize), (4-r)*vSize, {z_start}], radius:[vSize/{es_grueso}, vSize/{es_grueso}, {h_letra}/2]}}); if(!pText) pText = vox; else pText = pText.union(vox); }} }} }} }}\n  var totalL = Math.max(texto.length * charWidth, 10);\n"
                elif estilo == "Braille":
                    rad_braille = "1.5" if not grabado else "1.8"
                    code += f"  var braille = {{ 'A':[1], 'B':[1,2], 'C':[1,4], 'D':[1,4,5], 'E':[1,5], 'F':[1,2,4], 'G':[1,2,4,5], 'H':[1,2,5], 'I':[2,4], 'J':[2,4,5], 'K':[1,3], 'L':[1,2,3], 'M':[1,3,4], 'N':[1,3,4,5], 'O':[1,3,5], 'P':[1,2,3,4], 'Q':[1,2,3,4,5], 'R':[1,2,3,5], 'S':[2,3,4], 'T':[2,3,4,5], 'U':[1,3,6], 'V':[1,2,3,6], 'W':[2,4,5,6], 'X':[1,3,4,6], 'Y':[1,3,4,5,6], 'Z':[1,3,5,6], ' ':[0] }};\n  var pText = null; var stepX = 4; var stepY = 4; var charWidth = 10;\n  for(var i=0; i<texto.length; i++) {{ var dots = braille[texto[i]] || [1]; var offX = i * charWidth; for(var d=0; d<dots.length; d++) {{ var p = dots[d]; if (p === 0) continue; var cx = (p>3) ? stepX : 0; var cy = ((p-1)%3 === 0) ? stepY*2 : (((p-1)%3 === 1) ? stepY : 0); var domo = CSG.sphere({{center:[offX+cx, cy, {z_start}], radius:{rad_braille}, resolution:16}}); if(!pText) pText = domo; else pText = pText.union(domo); }} }}\n  var totalL = Math.max(texto.length * charWidth, 10);\n"
                code += "  if (!pText) pText = CSG.cube({center:[0,0,0], radius:[0.01, 0.01, 0.01]});\n  var baseObj = null;\n"
                if base == "Llavero (Anilla)": code += "  var bc = CSG.cube({center:[(totalL/2)-3, 3, h/4], radius:[(totalL/2)+2, 8, h/4]}); var anclaje = CSG.cylinder({start:[totalL, 3, 0], end:[totalL, 3, h/2], radius:6, slices:32}).subtract(CSG.cylinder({start:[totalL, 3, -1], end:[totalL, 3, h/2+1], radius:3, slices:16})); baseObj = bc.union(anclaje);\n"
                elif base == "Placa Atornillable": code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+10, 10, h/4]}); var h1 = CSG.cylinder({start:[-8, 3, -1], end:[-8, 3, h], radius:2.5, slices:16}); var h2 = CSG.cylinder({start:[totalL+2, 3, -1], end:[totalL+2, 3, h], radius:2.5, slices:16}); baseObj = bc.subtract(h1).subtract(h2);\n"
                elif base == "Soporte de Mesa": code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+2, 5, h/4]}); var pata = CSG.cube({center:[totalL/2-3, -5, h/8], radius:[totalL/2+2, 10, h/8]}); baseObj = bc.union(pata);\n"
                elif base == "Colgante Militar": code += "  var b_cen = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 10, h/4]}); var b_izq = CSG.cylinder({start:[-4, 4, 0], end:[-4, 4, h/2], radius:10, slices:32}); var b_der = CSG.cylinder({start:[totalL-2, 4, 0], end:[totalL-2, 4, h/2], radius:10, slices:32}); var agujero = CSG.cylinder({start:[-8, 4, -1], end:[-8, 4, h], radius:2.5, slices:16}); baseObj = b_cen.union(b_izq).union(b_der).subtract(agujero);\n"
                elif base == "Placa Ovalada": code += "  var c1 = CSG.cylinder({start:[-2, 4, 0], end:[-2, 4, h/2], radius:12, slices:64}); var c2 = CSG.cylinder({start:[totalL-4, 4, 0], end:[totalL-4, 4, h/2], radius:12, slices:64}); var p_med = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 12, h/4]}); baseObj = p_med.union(c1).union(c2);\n"
                code += "  if(baseObj) {\n"
                if grabado: code += "      return UTILS.mat(baseObj.subtract(pText));\n  } else {\n      return UTILS.mat(pText);\n  }\n}"
                else: code += "      return UTILS.mat(baseObj.union(pText));\n  } else {\n      return UTILS.mat(pText);\n  }\n}"

            elif h == "laser":
                code += f"  var w = {sl_las_x.value}; var l = {sl_las_y.value}; var z_cut = {sl_las_z.value};\n"
                code += f"  var base_obj = CSG.cube({{center:[0,0,10], radius:[w/2, l/2, 10]}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,21], radius:5, slices:16}}));\n"
                code += f"  var cut_plane = CSG.cube({{center:[0,0,z_cut], radius:[w, l, 0.5]}});\n  return UTILS.mat(base_obj.intersect(cut_plane));\n}}"
            elif h == "array_lin":
                code += f"  var filas = {int(sl_alin_f.value)}; var columnas = {int(sl_alin_c.value)}; var dx = {sl_alin_dx.value}; var dy = {sl_alin_dy.value}; var h = {sl_alin_h.value};\n"
                code += f"  var array_obj = null; var start_x = -((columnas - 1) * dx) / 2; var start_y = -((filas - 1) * dy) / 2;\n"
                code += f"  for(var i=0; i<filas; i++) {{ for(var j=0; j<columnas; j++) {{\n"
                code += f"      var px = start_x + (j * dx); var py = start_y + (i * dy);\n"
                code += f"      var pieza = CSG.cylinder({{start:[px,py,0], end:[px,py,h], radius:5, slices:16}});\n"
                code += f"      if(!array_obj) array_obj = pieza; else array_obj = array_obj.union(pieza);\n"
                code += f"  }} }}\n  return UTILS.mat(array_obj || CSG.cube({{radius:[1,1,1]}}));\n}}"
            elif h == "array_pol":
                code += f"  var n = {int(sl_apol_n.value)}; var radio_corona = {sl_apol_r.value}; var r_pieza = {sl_apol_rp.value}; var h = {sl_apol_h.value};\n"
                code += f"  var array_obj = null;\n"
                code += f"  for(var i=0; i<n; i++) {{\n      var a = (i * Math.PI * 2) / n; var px = Math.cos(a) * radio_corona; var py = Math.sin(a) * radio_corona;\n"
                code += f"      var pieza = CSG.cylinder({{start:[px,py,0], end:[px,py,h], radius:r_pieza, slices:16}});\n"
                code += f"      if(!array_obj) array_obj = pieza; else array_obj = array_obj.union(pieza);\n  }}\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,h/2], radius:radio_corona + r_pieza + 2, slices:32}});\n"
                code += f"  if(array_obj) base = base.subtract(array_obj);\n  return UTILS.mat(base);\n}}"
            elif h == "loft":
                code += f"  var side_base = {sl_loft_w.value}; var r_top = {sl_loft_r.value}; var h = {sl_loft_h.value}; var wall = {sl_loft_g.value};\n"
                code += f"  var res = 40; var dz = h / res; var loft_obj = null; var hueco = null;\n"
                code += f"  for(var i=0; i<res; i++) {{\n      var z = i * dz; var t = i / res; var slice_res = 32;\n"
                code += f"      for(var j=0; j<slice_res; j++) {{\n          var a1 = (j * Math.PI * 2) / slice_res;\n"
                code += f"          var cx1 = Math.cos(a1) * r_top; var cy1 = Math.sin(a1) * r_top; var sec = Math.floor(j / (slice_res/4));\n"
                code += f"          var sqx1 = 0; var sqy1 = 0; var m = side_base/2;\n"
                code += f"          if(sec==0) {{ sqx1=m; sqy1=m * Math.tan(a1); }} else if(sec==1) {{ sqx1=m/Math.tan(a1); sqy1=m; }} else if(sec==2) {{ sqx1=-m; sqy1=-m*Math.tan(a1); }} else {{ sqx1=-m/Math.tan(a1); sqy1=-m; }}\n"
                code += f"          if(Math.abs(sqx1)>m) sqx1 = Math.sign(sqx1)*m; if(Math.abs(sqy1)>m) sqy1 = Math.sign(sqy1)*m;\n"
                code += f"          var x_curr = sqx1*(1-t) + cx1*t; var y_curr = sqy1*(1-t) + cy1*t;\n"
                code += f"          var x_int = (Math.abs(sqx1)>0 ? sqx1-Math.sign(sqx1)*wall : 0)*(1-t) + Math.cos(a1)*(r_top-wall)*t;\n"
                code += f"          var y_int = (Math.abs(sqy1)>0 ? sqy1-Math.sign(sqy1)*wall : 0)*(1-t) + Math.sin(a1)*(r_top-wall)*t;\n"
                code += f"          var p_ext = CSG.cylinder({{start:[x_curr, y_curr, z], end:[x_curr, y_curr, z+dz+0.1], radius:wall/2, slices:8}});\n"
                code += f"          var p_int = CSG.cylinder({{start:[x_int, y_int, z], end:[x_int, y_int, z+dz+0.1], radius:wall/4, slices:4}});\n"
                code += f"          if(!loft_obj) loft_obj = p_ext; else loft_obj = loft_obj.union(p_ext);\n"
                code += f"          if(!hueco) hueco = p_int; else hueco = hueco.union(p_int);\n      }}\n  }}\n"
                code += f"  if(hueco) loft_obj = loft_obj.subtract(hueco);\n  return UTILS.mat(loft_obj || CSG.cube({{radius:[1,1,1]}}));\n}}"
            elif h == "voronoi":
                code += f"  var r_out = {sl_vor_ro.value}; var r_in = {sl_vor_ri.value}; var h = {sl_vor_h.value}; var d = {int(sl_vor_d.value)};\n"
                code += f"  var pipe = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_out, slices:32}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:r_in, slices:32}}));\n"
                code += f"  var holes = null; var z_step = (r_out - r_in) * 2.5; var r_esfera = (r_out - r_in) * 1.8; var t = 0;\n"
                code += f"  for(var z = z_step; z < h - z_step; z += z_step) {{\n      var offset_a = (t % 2 === 1) ? Math.PI/d : 0;\n"
                code += f"      for(var i=0; i<d; i++) {{\n          var a = (i * Math.PI * 2 / d) + offset_a;\n"
                code += f"          var cx = Math.cos(a) * (r_out - (r_out-r_in)/2); var cy = Math.sin(a) * (r_out - (r_out-r_in)/2);\n"
                code += f"          var hole = CSG.sphere({{center:[cx, cy, z], radius:r_esfera, resolution:8}});\n"
                code += f"          if(!holes) holes = hole; else holes = holes.union(hole);\n      }}\n      t++;\n  }}\n"
                code += f"  if(holes) return UTILS.mat(pipe.subtract(holes));\n  return UTILS.mat(pipe);\n}}"
            elif h == "evolvente":
                code += f"  var dientes = {int(sl_evo_d.value)}; var m = {sl_evo_m.value}; var h = {sl_evo_h.value};\n"
                code += f"  var r_pitch = (dientes * m) / 2; var r_ext = r_pitch + m; var r_root = r_pitch - 1.25 * m;\n"
                code += f"  var gear = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_root, slices:64}});\n"
                code += f"  var t_w = (Math.PI * r_pitch / dientes) * 0.8;\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n      var a = (i * Math.PI * 2) / dientes;\n"
                code += f"      var cx1 = Math.cos(a)*(r_root + m*0.3); var cy1 = Math.sin(a)*(r_root + m*0.3);\n"
                code += f"      var cx2 = Math.cos(a)*r_pitch;          var cy2 = Math.sin(a)*r_pitch;\n"
                code += f"      var cx3 = Math.cos(a)*(r_ext - m*0.2);  var cy3 = Math.sin(a)*(r_ext - m*0.2);\n"
                code += f"      var t1 = CSG.cylinder({{start:[cx1,cy1,0], end:[cx1,cy1,h], radius:t_w*0.6, slices:16}});\n"
                code += f"      var t2 = CSG.cylinder({{start:[cx2,cy2,0], end:[cx2,cy2,h], radius:t_w*0.4, slices:16}});\n"
                code += f"      var t3 = CSG.cylinder({{start:[cx3,cy3,0], end:[cx3,cy3,h], radius:t_w*0.15, slices:16}});\n"
                code += f"      gear = gear.union(t1).union(t2).union(t3);\n  }}\n"
                code += f"  var hole = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius: r_root * 0.3, slices:32}});\n"
                code += f"  return UTILS.mat(UTILS.rotZ(gear.subtract(hole), KINE_T));\n}}"
            elif h == "cremallera":
                code += f"  var dientes = {int(sl_crem_d.value)}; var m = {sl_crem_m.value}; var h = {sl_crem_h.value}; var w = {sl_crem_w.value};\n"
                code += f"  var pitch = Math.PI * m; var len = dientes * pitch;\n"
                code += f"  var rack = CSG.cube({{center:[len/2, w/2, h/2], radius:[len/2, w/2, h/2]}}); var t_w = pitch / 2;\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n      var px = i * pitch + pitch/2;\n"
                code += f"      var t1 = CSG.cube({{center:[px, w + m*0.2, h/2], radius:[t_w*0.4, m*0.3, h/2]}});\n"
                code += f"      var t2 = CSG.cube({{center:[px, w + m*0.7, h/2], radius:[t_w*0.2, m*0.4, h/2]}});\n"
                code += f"      rack = rack.union(t1).union(t2);\n  }}\n  return UTILS.mat(UTILS.trans(rack, [KINE_T/10, 0, 0]));\n}}"
            elif h == "conico":
                code += f"  var dientes = {int(sl_con_d.value)}; var rb = {sl_con_rb.value}; var rt = {sl_con_rt.value}; var h = {sl_con_h.value};\n"
                code += f"  var res = 20; var dz = h / res; var gear = null; var m = rb / (dientes/2);\n"
                code += f"  for(var z=0; z<res; z++) {{\n      var z_pos = z * dz; var r_curr = rb - (rb - rt)*(z/res); var r_root = Math.max(0.1, r_curr - m);\n"
                code += f"      var core = CSG.cylinder({{start:[0,0,z_pos], end:[0,0,z_pos+dz], radius:r_root, slices:32}});\n"
                code += f"      if(!gear) gear = core; else gear = gear.union(core);\n"
                code += f"      var t_w = (Math.PI * r_curr / dientes) * 0.8;\n"
                code += f"      for(var i=0; i<dientes; i++) {{\n          var a = (i * Math.PI * 2) / dientes;\n"
                code += f"          var cx1 = Math.cos(a)*(r_root + m*0.3); var cy1 = Math.sin(a)*(r_root + m*0.3);\n"
                code += f"          var cx2 = Math.cos(a)*r_curr;           var cy2 = Math.sin(a)*r_curr;\n"
                code += f"          var t1 = CSG.cylinder({{start:[cx1,cy1,z_pos], end:[cx1,cy1,z_pos+dz], radius:t_w*0.6, slices:8}});\n"
                code += f"          var t2 = CSG.cylinder({{start:[cx2,cy2,z_pos], end:[cx2,cy2,z_pos+dz], radius:t_w*0.3, slices:8}});\n"
                code += f"          gear = gear.union(t1).union(t2);\n      }}\n  }}\n"
                code += f"  var hole = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius: rt * 0.3, slices:16}});\n"
                code += f"  if(gear) return UTILS.mat(UTILS.rotZ(gear.subtract(hole), KINE_T));\n  return UTILS.mat(CSG.cube({{radius:[1,1,1]}}));\n}}"
            elif h == "multicaja":
                code += f"  var w = {sl_mc_x.value}; var l = {sl_mc_y.value}; var h = {sl_mc_z.value}; var tol = {sl_mc_tol.value}; var sep = {sl_mc_sep.value};\n"
                code += f"  var t = 2; var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}});\n"
                code += f"  var int_box = CSG.cube({{center:[0,0,h/2+t], radius:[w/2-t, l/2-t, h/2]}}); var caja = ext.subtract(int_box);\n"
                code += f"  var offsetZ = h + sep + (KINE_T/5); var tapa_b = CSG.cube({{center:[0,0, offsetZ + t/2], radius:[w/2, l/2, t/2]}});\n"
                code += f"  var tapa_i = CSG.cube({{center:[0,0, offsetZ - t/2], radius:[w/2-t-tol, l/2-t-tol, t/2]}}); var tapa = tapa_b.union(tapa_i);\n"
                code += f"  return UTILS.mat(caja.union(tapa));\n}}"
            elif h == "perfil":
                code += f"  var puntas = {int(sl_perf_p.value)}; var rext = {sl_perf_re.value}; var rint = {sl_perf_ri.value}; var h = {sl_perf_h.value};\n"
                code += f"  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:rint, slices:32}});\n"
                code += f"  var d_theta = (Math.PI * 2) / puntas; var r_punta = (rext - rint) / 1.5;\n"
                code += f"  for(var i=0; i<puntas; i++) {{\n     var a = i * d_theta; var px = Math.cos(a) * (rint + r_punta*0.8); var py = Math.sin(a) * (rint + r_punta*0.8);\n"
                code += f"     var punta = CSG.cylinder({{start:[px, py, 0], end:[px, py, h], radius:r_punta, slices:16}});\n"
                code += f"     pieza = pieza.union(punta);\n  }}\n  return UTILS.mat(UTILS.rotZ(pieza, KINE_T));\n}}"
            elif h == "revolucion":
                code += f"  var h = {sl_rev_h.value}; var r1 = {sl_rev_r1.value}; var r2 = {sl_rev_r2.value}; var grosor = {sl_rev_g.value};\n"
                code += f"  var res = 60; var dz = h / res; var solido = null; var hueco = null;\n"
                code += f"  for(var i=0; i<res; i++) {{\n      var z = i * dz; var f = Math.sin((z/h) * Math.PI); var rad = r1 + (r2 - r1)*(z/h) + (f * 15);\n"
                code += f"      var capa = CSG.cylinder({{start:[0,0,z], end:[0,0,z+dz], radius:rad, slices:32}});\n"
                code += f"      if(!solido) solido = capa; else solido = solido.union(capa);\n"
                code += f"      if (grosor > 0 && z > grosor) {{\n         var r_int = Math.max(0.1, rad - grosor);\n"
                code += f"         var capa_h = CSG.cylinder({{start:[0,0,z], end:[0,0,z+dz+0.1], radius:r_int, slices:32}});\n"
                code += f"         if(!hueco) hueco = capa_h; else hueco = hueco.union(capa_h);\n      }}\n  }}\n"
                code += f"  if(grosor > 0 && hueco) solido = solido.subtract(hueco);\n  return UTILS.mat(solido);\n}}"
            elif h == "cubo":
                g = sl_c_grosor.value
                code += f"  var pieza = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}});\n"
                if g > 0: code += f"  var int_box = CSG.cube({{center:[0,0,GH/2 + {g}], radius:[GW/2 - {g}, GL/2 - {g}, GH/2]}});\n  pieza = pieza.subtract(int_box);\n"
                code += f"  return UTILS.mat(pieza);\n}}"
            elif h == "cilindro":
                rint = sl_p_rint.value; c = int(sl_p_lados.value)
                code += f"  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:{c}}});\n"
                if rint > 0: code += f"  var int_cyl = CSG.cylinder({{start:[0,0,-1], end:[0,0,GH+2], radius:{rint}, slices:{c}}});\n  pieza = pieza.subtract(int_cyl);\n"
                code += f"  return UTILS.mat(pieza);\n}}"
            elif h == "escuadra":
                code += f"  var l = {sl_l_largo.value}; var w = {sl_l_ancho.value}; var t = {sl_l_grosor.value}; var r = {sl_l_hueco.value}; var chaf = {sl_l_chaf.value};\n"
                code += f"  var base = CSG.cube({{center:[l/2, w/2, t/2], radius:[l/2, w/2, t/2]}}); var wall = CSG.cube({{center:[t/2, w/2, l/2], radius:[t/2, w/2, l/2]}}); var pieza = base.union(wall);\n"
                if sl_l_chaf.value > 0: code += f"  var fillet = CSG.cylinder({{start:[t, 0, t], end:[t, w, t], radius:chaf, slices:16}}); pieza = pieza.union(fillet);\n"
                if sl_l_hueco.value > 0: code += f"  var h1 = CSG.cylinder({{start:[l*0.7, w/2, -1], end:[l*0.7, w/2, t+1], radius:r, slices:32}});\n  var h2 = CSG.cylinder({{start:[-1, w/2, l*0.7], end:[t+1, w/2, l*0.7], radius:r, slices:32}});\n  pieza = pieza.subtract(h1).subtract(h2);\n"
                code += f"  return UTILS.mat(pieza);\n}}"
            elif h == "engranaje":
                code += f"  var dientes = {int(sl_e_dientes.value)}; var r = {sl_e_radio.value}; var h = {sl_e_grosor.value};\n"
                code += f"  var d_x = r*0.15; var d_y = r*0.2;\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var diente = CSG.cube({{center:[Math.cos(a)*r, Math.sin(a)*r, h/2], radius:[d_x, d_y, h/2]}}); pieza = pieza.union(diente);\n  }}\n"
                if sl_e_eje.value > 0: code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{sl_e_eje.value} + G_TOL, slices:32}}); pieza = pieza.subtract(hueco);\n"
                code += f"  return UTILS.mat(UTILS.rotZ(pieza, KINE_T));\n}}"
            elif h == "pcb":
                code += f"  var px = {sl_pcb_x.value}; var py = {sl_pcb_y.value}; var h = {sl_pcb_h.value}; var t = {sl_pcb_t.value};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[px/2 + t, py/2 + t, h/2]}});\n"
                code += f"  var int_box = CSG.cube({{center:[0,0,h/2 + t], radius:[px/2, py/2, h/2]}}); var pieza = ext.subtract(int_box);\n"
                code += f"  var dx = px/2 - 3.5; var dy = py/2 - 3.5; var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n    var cyl = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 0], end:[m[i][0]*dx, m[i][1]*dy, h-2], radius: 3.5, slices:16}});\n"
                code += f"    var hole = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 2], end:[m[i][0]*dx, m[i][1]*dy, h], radius: 1.5 + (G_TOL/2), slices:16}});\n"
                code += f"    pieza = pieza.union(cyl).subtract(hole);\n  }}\n  return UTILS.mat(pieza);\n}}"
            elif h == "vslot":
                code += f"  var l = {sl_v_l.value};\n  var pieza = CSG.cube({{center:[0,0,l/2], radius:[10,10,l/2]}});\n"
                code += f"  var ch = CSG.cylinder({{start:[0,0,-1], end:[0,0,l+1], radius:2.1 + (G_TOL/2), slices:32}}); pieza = pieza.subtract(ch);\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,-10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,-8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[-10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[-8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  return UTILS.mat(pieza);\n}}"
            elif h == "bisagra":
                code += f"  var l = {sl_bi_l.value}; var d = {sl_bi_d.value};\n"
                code += f"  var fix = CSG.cylinder({{start:[0,0,0], end:[0,0,l/3], radius:d/2, slices:32}});\n"
                code += f"  var fix2 = CSG.cylinder({{start:[0,0,2*l/3], end:[0,0,l], radius:d/2, slices:32}});\n"
                code += f"  var move = CSG.cylinder({{start:[0,0,l/3+G_TOL], end:[0,0,2*l/3-G_TOL], radius:d/2, slices:32}});\n"
                code += f"  var pin = CSG.cylinder({{start:[0,0,l/3-d/4], end:[0,0,2*l/3+d/4], radius:(d/4)-G_TOL, slices:32}});\n"
                code += f"  var cut_pin = CSG.cylinder({{start:[0,0,l/3-d/2], end:[0,0,2*l/3+d/2], radius:d/4, slices:32}});\n"
                code += f"  var fijo = fix.union(fix2).subtract(cut_pin).union(pin);\n  var movil = move.subtract(cut_pin);\n"
                code += f"  movil = UTILS.trans(movil, [0,0,-l/2]); movil = UTILS.rotX(movil, KINE_T); movil = UTILS.trans(movil, [0,0,l/2]);\n"
                code += f"  return UTILS.mat(fijo.union(movil));\n}}"
            elif h == "abrazadera":
                code += f"  var diam = {sl_clamp_d.value}; var grosor = {sl_clamp_g.value}; var ancho = {sl_clamp_w.value};\n"
                code += f"  var ext = CSG.cylinder({{start:[0,0,0], end:[0,0,ancho], radius:(diam/2)+grosor, slices:64}});\n"
                code += f"  var int_cyl = CSG.cylinder({{start:[0,0,-1], end:[0,0,ancho+1], radius:diam/2 + G_TOL, slices:64}});\n"
                code += f"  var corteInf = CSG.cube({{center:[0, -50, ancho/2], radius:[50, 50, ancho]}});\n"
                code += f"  var arco = ext.subtract(int_cyl).subtract(corteInf);\n"
                code += f"  var distPestana = (diam/2) + grosor + 5;\n"
                code += f"  var pestana = CSG.cube({{center:[ distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n"
                code += f"  var pestana2 = CSG.cube({{center:[ -distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n"
                code += f"  var m3 = CSG.cylinder({{start:[ distPestana, 10, ancho/2 ], end:[ distPestana, -10, ancho/2 ], radius:1.7 + (G_TOL/2), slices:16}});\n"
                code += f"  var m3_2 = CSG.cylinder({{start:[ -distPestana, 10, ancho/2 ], end:[ -distPestana, -10, ancho/2 ], radius:1.7 + (G_TOL/2), slices:16}});\n"
                code += f"  return UTILS.mat(arco.union(pestana).union(pestana2).subtract(m3).subtract(m3_2));\n}}"
            elif h == "fijacion":
                m, l_tornillo = sl_fij_m.value, sl_fij_l.value
                r_hex = (m * 1.8) / 2; h_cabeza = m * 0.8; r_eje = m / 2
                if l_tornillo == 0: 
                    code += f"  var m = {m}; var h = {h_cabeza};\n  var cuerpo = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:{r_hex}, slices:6}});\n  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:({r_eje} + G_TOL), slices:32}});\n  return UTILS.mat(cuerpo.subtract(agujero));\n}}"
                else: 
                    code += f"  var m = {m}; var l_tornillo = {l_tornillo}; var h_cabeza = {h_cabeza}; var r_hex = {r_hex};\n  var cabeza = CSG.cylinder({{start:[0,0,0], end:[0,0,h_cabeza], radius:r_hex, slices:6}});\n  var eje = CSG.cylinder({{start:[0,0,h_cabeza - 0.1], end:[0,0,h_cabeza + l_tornillo], radius:({r_eje} - G_TOL) - (m*0.08), slices:32}});\n  var pieza = cabeza.union(eje); var paso = m * 0.15;\n  for(var z = h_cabeza + 1; z < h_cabeza + l_tornillo - 1; z += paso*1.5) {{\n      var anillo = CSG.cylinder({{start:[0,0,z], end:[0,0,z+paso], radius:({r_eje} - G_TOL), slices:16}});\n      pieza = pieza.union(anillo);\n  }}\n  return UTILS.mat(UTILS.rotZ(pieza, KINE_T));\n}}"
            elif h == "rodamiento":
                code += f"  var d_int = {sl_rod_dint.value}; var d_ext = {sl_rod_dext.value}; var h = {sl_rod_h.value};\n"
                code += f"  var pista_ext = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:d_ext/2, slices:64}}).subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:(d_ext/2)-2 + G_TOL, slices:64}}) );\n"
                code += f"  var pista_int_base = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:(d_int/2)+2 - G_TOL, slices:64}}).subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:d_int/2, slices:64}}) );\n"
                code += f"  var pista_int = UTILS.rotZ(pista_int_base, KINE_T);\n"
                code += f"  var pieza = pista_ext.union(pista_int);\n"
                code += f"  var r_espacio = (((d_ext/2)-2) - ((d_int/2)+2)) / 2; var radio_centro = ((d_int/2)+2 + (d_ext/2)-2)/2;\n"
                code += f"  var n_bolas = Math.floor((Math.PI * 2 * radio_centro) / (r_espacio * 2.2));\n"
                code += f"  for(var i=0; i<n_bolas; i++) {{\n      var a = (i * Math.PI * 2) / n_bolas; var bx = Math.cos(a + KINE_T/100) * radio_centro; var by = Math.sin(a + KINE_T/100) * radio_centro;\n"
                code += f"      var bola = CSG.sphere({{center:[bx, by, h/2], radius:(r_espacio*0.95) - (G_TOL/2), resolution:16}});\n"
                code += f"      pieza = pieza.union(bola);\n  }}\n  return UTILS.mat(pieza);\n}}"
            elif h == "planetario":
                code += f"  var r_sol = {sl_plan_rs.value}; var r_planeta = {sl_plan_rp.value}; var h = {sl_plan_h.value};\n"
                code += f"  var r_anillo = r_sol + (r_planeta*2); var dist_centros = r_sol + r_planeta;\n"
                code += f"  var T = KINE_T; var carrier_T = T * (r_sol / (r_sol + r_anillo)); var planet_T = T * (r_sol / r_planeta);\n"
                code += f"  var sol_base = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_sol - 1, slices:32}});\n"
                code += f"  var dientes_sol = Math.floor(r_sol * 1.5);\n"
                code += f"  for(var i=0; i<dientes_sol; i++) {{\n      var a = (i * Math.PI * 2) / dientes_sol;\n"
                code += f"      var diente = CSG.cylinder({{start:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, 0], end:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, h], radius:1.2, slices:12}});\n"
                code += f"      sol_base = sol_base.union(diente);\n  }}\n"
                code += f"  var sol = UTILS.rotZ(sol_base.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:3, slices:16}})), T);\n"
                code += f"  var planetas = null; var dientes_planeta = Math.floor(r_planeta * 1.5);\n"
                code += f"  for(var p=0; p<3; p++) {{\n      var ap = (p * Math.PI * 2) / 3;\n"
                code += f"      var planeta = CSG.cylinder({{start:[0, 0, 0], end:[0, 0, h], radius:r_planeta - 1 - G_TOL, slices:32}});\n"
                code += f"      for(var i=0; i<dientes_planeta; i++) {{\n          var a = (i * Math.PI * 2) / dientes_planeta;\n"
                code += f"          var px = Math.cos(a)*(r_planeta - G_TOL); var py = Math.sin(a)*(r_planeta - G_TOL);\n"
                code += f"          var diente_p = CSG.cylinder({{start:[px, py, 0], end:[px, py, h], radius:1.2 - (G_TOL/2), slices:12}});\n"
                code += f"          planeta = planeta.union(diente_p);\n      }}\n"
                code += f"      planeta = planeta.subtract(CSG.cylinder({{start:[0, 0, -1], end:[0, 0, h+1], radius:2, slices:12}}));\n"
                code += f"      planeta = UTILS.rotZ(planeta, -planet_T);\n"
                code += f"      var angulo_pos = ap + (carrier_T * Math.PI / 180);\n"
                code += f"      var cx = Math.cos(angulo_pos) * dist_centros; var cy = Math.sin(angulo_pos) * dist_centros;\n"
                code += f"      planeta = UTILS.trans(planeta, [cx, cy, 0]);\n"
                code += f"      if(!planetas) planetas = planeta; else planetas = planetas.union(planeta);\n  }}\n"
                code += f"  var corona = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_anillo + 5, slices:64}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:r_anillo + G_TOL, slices:64}}));\n"
                code += f"  var dientes_corona = Math.floor(r_anillo * 1.5); var anillo_dientes = null;\n"
                code += f"  for(var i=0; i<dientes_corona; i++) {{\n      var a = (i * Math.PI * 2) / dientes_corona;\n"
                code += f"      var diente_c = CSG.cylinder({{start:[Math.cos(a)*(r_anillo + G_TOL), Math.sin(a)*(r_anillo + G_TOL), 0], end:[Math.cos(a)*(r_anillo + G_TOL), Math.sin(a)*(r_anillo + G_TOL), h], radius:1.2, slices:12}});\n"
                code += f"      if(!anillo_dientes) anillo_dientes = diente_c; else anillo_dientes = anillo_dientes.union(diente_c);\n  }}\n"
                code += f"  if(anillo_dientes) corona = corona.union(anillo_dientes);\n"
                code += f"  var obj = sol.union(corona);\n  if(planetas) obj = obj.union(planetas);\n  return UTILS.mat(obj);\n}}"
            elif h == "polea":
                code += f"  var dientes = {int(sl_pol_t.value)}; var ancho = {sl_pol_w.value}; var r_eje = {sl_pol_d.value/2};\n"
                code += f"  var pitch = 2; var r_primitivo = (dientes * pitch) / (2 * Math.PI); var r_ext = r_primitivo - 0.25;\n"
                code += f"  var cuerpo = CSG.cylinder({{start:[0,0,1.5], end:[0,0,1.5+ancho], radius:r_ext, slices:64}});\n"
                code += f"  var matriz_dientes = null;\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n      var a = (i * Math.PI * 2) / dientes;\n"
                code += f"      var d = CSG.cylinder({{start:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 1], end:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 2+ancho], radius:0.55, slices:8}});\n"
                code += f"      if(!matriz_dientes) matriz_dientes = d; else matriz_dientes = matriz_dientes.union(d);\n  }}\n"
                code += f"  if(matriz_dientes) cuerpo = cuerpo.subtract(matriz_dientes);\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,1.5], radius:r_ext + 1, slices:64}});\n"
                code += f"  var tapa = CSG.cylinder({{start:[0,0,1.5+ancho], end:[0,0,3+ancho], radius:r_ext + 1, slices:64}});\n"
                code += f"  var polea = base.union(cuerpo).union(tapa);\n"
                code += f"  polea = polea.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,5+ancho], radius:r_eje + (G_TOL/2), slices:32}}));\n  return UTILS.mat(UTILS.rotZ(polea, KINE_T));\n}}"
            elif h == "helice":
                code += f"  var rad = {sl_hel_r.value}; var n = {int(sl_hel_n.value)}; var pitch = {sl_hel_p.value};\n"
                code += f"  var hub = CSG.cylinder({{start:[0,0,0], end:[0,0,10], radius:8, slices:32}});\n"
                code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,11], radius:2.5 + G_TOL, slices:16}});\n"
                code += f"  var aspas = null;\n"
                code += f"  for(var i=0; i<n; i++) {{\n    var a = (i * Math.PI * 2) / n; var dx = Math.cos(a); var dy = Math.sin(a);\n"
                code += f"    var aspa = CSG.cylinder({{start:[6*dx, 6*dy, 5 - (pitch/10)], end:[rad*dx, rad*dy, 5 + (pitch/10)], radius: 3, slices: 4}});\n"
                code += f"    if(!aspas) aspas = aspa; else aspas = aspas.union(aspa);\n  }}\n"
                code += f"  if(aspas) hub = hub.union(aspas);\n  return UTILS.mat(UTILS.rotZ(hub.subtract(agujero), KINE_T));\n}}"
            elif h == "rotula":
                code += f"  var r_bola = {sl_rot_r.value};\n"
                code += f"  var bola = CSG.sphere({{center:[0,0,0], radius:r_bola, resolution:32}}); var eje_bola = CSG.cylinder({{start:[0,0,0], end:[0,0,-r_bola*2], radius:r_bola*0.6, slices:32}});\n"
                code += f"  var componente_bola = UTILS.rotY(UTILS.rotX(bola.union(eje_bola), KINE_T/4), KINE_T/4);\n"
                code += f"  var copa_ext = CSG.cylinder({{start:[0,0,-r_bola*0.2], end:[0,0,r_bola*1.5], radius:r_bola+4, slices:32}});\n"
                code += f"  var hueco_bola = CSG.sphere({{center:[0,0,0], radius:r_bola+G_TOL, resolution:32}}); var apertura = CSG.cylinder({{start:[0,0,r_bola*0.5], end:[0,0,r_bola*2], radius:r_bola*0.8, slices:32}});\n"
                code += f"  var componente_copa = copa_ext.subtract(hueco_bola).subtract(apertura);\n  return UTILS.mat(componente_bola.union(componente_copa));\n}}"
            elif h == "carcasa":
                code += f"  var w = {sl_car_x.value}; var l = {sl_car_y.value}; var h = {sl_car_z.value}; var t = {sl_car_t.value};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}}); var int_box = CSG.cube({{center:[0,0,(h/2)+t], radius:[(w/2)-t, (l/2)-t, h/2]}}); var base = ext.subtract(int_box);\n"
                code += f"  var r_post = 3.5; var r_hole = 1.5; var h_post = 6; var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n      var px = m[i][0] * ((w/2) - t - r_post - 1); var py = m[i][1] * ((l/2) - t - r_post - 1);\n"
                code += f"      var post = CSG.cylinder({{start:[px,py,t], end:[px,py,t+h_post], radius:r_post, slices:16}});\n"
                code += f"      var hole = CSG.cylinder({{start:[px,py,t], end:[px,py,t+h_post+1], radius:r_hole + (G_TOL/2), slices:16}});\n"
                code += f"      base = base.union(post).subtract(hole);\n  }}\n"
                code += f"  var vents = null;\n  for(var vx=-(w/2)+15; vx < (w/2)-15; vx += 7) {{\n      for(var vy=-(l/2)+15; vy < (l/2)-15; vy += 7) {{\n"
                code += f"          var agujero = CSG.cylinder({{start:[vx,vy,-1], end:[vx,vy,t+1], radius:2, slices:8}});\n"
                code += f"          if(!vents) vents = agujero; else vents = vents.union(agujero);\n      }}\n  }}\n"
                code += f"  if(vents) base = base.subtract(vents);\n  return UTILS.mat(base);\n}}"
            elif h == "muelle":
                code += f"  var r_res = {sl_mue_r.value}; var r_hilo = {sl_mue_h.value}; var h = {sl_mue_alt.value}; var vueltas = {sl_mue_v.value};\n"
                code += f"  var resorte = null; var pasos = Math.floor(vueltas * 24); var paso_z = h / pasos; var a_step = (Math.PI * 2 * vueltas) / pasos;\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n      var a1 = i * a_step; var a2 = (i+1) * a_step;\n"
                code += f"      var x1 = Math.cos(a1)*r_res; var y1 = Math.sin(a1)*r_res; var z1 = i*paso_z;\n"
                code += f"      var x2 = Math.cos(a2)*r_res; var y2 = Math.sin(a2)*r_res; var z2 = (i+1)*paso_z;\n"
                code += f"      var seg = CSG.cylinder({{start:[x1,y1,z1], end:[x2,y2,z2], radius:r_hilo, slices:8}});\n"
                code += f"      var esp = CSG.sphere({{center:[x2,y2,z2], radius:r_hilo, resolution:8}});\n"
                code += f"      if(!resorte) resorte = seg.union(esp); else resorte = resorte.union(seg).union(esp);\n  }}\n  return UTILS.mat(resorte);\n}}"
            elif h == "acme":
                code += f"  var r = {sl_acme_d.value/2}; var pitch = {sl_acme_p.value}; var len = {sl_acme_l.value};\n"
                code += f"  var r_core = r - (pitch * 0.4); var eje = CSG.cylinder({{start:[0,0,0], end:[0,0,len], radius:r_core, slices:32}});\n"
                code += f"  var thread = null; var steps = Math.floor((len / pitch) * 24); var z_step = len / steps; var a_step = (Math.PI * 2 * (len/pitch)) / steps; var w = pitch * 0.35;\n"
                code += f"  for(var i=0; i<steps; i++) {{\n      var a1 = i * a_step; var a2 = (i+1) * a_step; var z1 = i * z_step; var z2 = (i+1) * z_step;\n"
                code += f"      var seg = CSG.cylinder({{start:[Math.cos(a1)*r, Math.sin(a1)*r, z1], end:[Math.cos(a2)*r, Math.sin(a2)*r, z2], radius:w, slices:8}});\n"
                code += f"      if(!thread) thread = seg; else thread = thread.union(seg);\n  }}\n"
                code += f"  if(thread) eje = eje.union(thread);\n  return UTILS.mat(UTILS.rotZ(eje, KINE_T));\n}}"
            elif h == "codo":
                code += f"  var r_tubo = {sl_codo_r.value}; var r_curva = {sl_codo_c.value}; var angulo = {sl_codo_a.value}; var grosor = {sl_codo_g.value};\n"
                code += f"  var codo = null; var pasos = Math.max(8, Math.floor(angulo / 5));\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n      var a1 = (i * (angulo/pasos)) * Math.PI / 180; var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"      var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva; var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"      var ext = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo, slices:16}});\n"
                code += f"      var esf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo, resolution:16}});\n"
                code += f"      var sol = ext.union(esf);\n      if(!codo) codo = sol; else codo = codo.union(sol);\n  }}\n"
                code += f"  if(grosor > 0) {{\n     var hueco = null;\n     for(var i=0; i<pasos; i++) {{\n"
                code += f"         var a1 = (i * (angulo/pasos)) * Math.PI / 180; var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"         var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva; var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"         var int_c = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo-grosor, slices:12}});\n"
                code += f"         var isf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo-grosor, resolution:12}});\n"
                code += f"         var hol = int_c.union(isf); if(!hueco) hueco = hol; else hueco = hueco.union(hol);\n"
                code += f"     }}\n     if(hueco) codo = codo.subtract(hueco);\n  }}\n  return UTILS.mat(codo);\n}}"
            elif h == "naca":
                code += f"  var cuerda = {sl_naca_c.value}; var grosor = {sl_naca_g.value}; var envergadura = {sl_naca_e.value};\n"
                code += f"  var ala = null; var num_pasos = 40;\n"
                code += f"  for(var i=0; i<=num_pasos; i++) {{\n      var x = i/num_pasos;\n"
                code += f"      var yt = 5 * (grosor/100) * (0.2969*Math.sqrt(x) - 0.1260*x - 0.3516*(x*x) + 0.2843*Math.pow(x,3) - 0.1015*Math.pow(x,4));\n"
                code += f"      var x_real = x * cuerda; var yt_real = Math.max(yt * cuerda, 0.1);\n"
                code += f"      var cyl = CSG.cylinder({{start:[x_real, 0, 0], end:[x_real, 0, envergadura], radius: yt_real, slices: 16}});\n"
                code += f"      if(!ala) ala = cyl; else ala = ala.union(cyl);\n  }}\n  return UTILS.mat(ala);\n}}"
            elif h == "stand_movil":
                code += f"  var ang = {sl_st_ang.value} * Math.PI / 180; var w = {sl_st_w.value}; var t = {sl_st_t.value};\n"
                code += f"  var base = CSG.cube({{center:[0, -20, t/2], radius:[w/2, 40, t/2]}});\n"
                code += f"  var h_back = 80; var dx = Math.sin(ang)*h_back; var dy = Math.cos(ang)*h_back;\n"
                code += f"  var back = CSG.cube({{center:[0, dy/2, dx/2], radius:[w/2, dy/2, dx/2]}});\n"
                code += f"  var lip = CSG.cube({{center:[0, -50, t + 5], radius:[w/2, t/2, 5]}});\n"
                code += f"  return UTILS.mat(base.union(back).union(lip));\n}}"
            elif h == "clip_cable":
                code += f"  var d = {sl_clip_d.value}; var w = {sl_clip_w.value}; var t = 3;\n"
                code += f"  var base = CSG.cube({{center:[0, 0, t/2], radius:[w/2, w/2, t/2]}});\n"
                code += f"  var anillo = CSG.cylinder({{start:[0,0,t], end:[0,0,t+w], radius:(d/2)+t, slices:32}});\n"
                code += f"  var hueco = CSG.cylinder({{start:[0,0,t-1], end:[0,0,t+w+1], radius:(d/2), slices:32}});\n"
                code += f"  var slot = CSG.cube({{center:[0, d, t+(w/2)], radius:[(d/2)-0.5, d, w/2+1]}});\n"
                code += f"  return UTILS.mat(base.union(anillo).subtract(hueco).subtract(slot));\n}}"
            elif h == "vr_pedestal":
                code += f"  var s = {sl_vr_s.value};\n"
                code += f"  var base1 = CSG.cube({{center:[0, 0, 10], radius:[s/2, s/2, 10]}});\n"
                code += f"  var base2 = CSG.cube({{center:[0, 0, 30], radius:[(s/2)-20, (s/2)-20, 10]}});\n"
                code += f"  var pillar = CSG.cylinder({{start:[0,0,40], end:[0,0,150], radius: s/4, slices:32}});\n"
                code += f"  var top = CSG.cylinder({{start:[0,0,150], end:[0,0,160], radius: (s/4)+10, slices:32}});\n"
                code += f"  return UTILS.mat(UTILS.rotZ(base1.union(base2).union(pillar).union(top), KINE_T));\n}}"

            if not modo_ensamble and h != "custom": txt_code.value = code
            txt_code.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            tool_panels = {"custom": col_custom, "sketcher": col_sketcher, "stl": col_stl, "stl_flatten": col_stl_flatten, "stl_split": col_stl_split, "stl_crop": col_stl_crop, "stl_drill": col_stl_drill, "stl_mount": col_stl_mount, "stl_ears": col_stl_ears, "stl_patch": col_stl_patch, "stl_honeycomb": col_stl_honeycomb, "stl_propguard": col_stl_propguard, "texto": col_texto, "cubo": col_cubo, "cilindro": col_cilindro, "laser": col_laser, "array_lin": col_array_lin, "array_pol": col_array_pol, "loft": col_loft, "panal": col_panal, "voronoi": col_voronoi, "evolvente": col_evolvente, "cremallera": col_cremallera, "conico": col_conico, "multicaja": col_multicaja, "perfil": col_perfil, "revolucion": col_revolucion, "escuadra": col_escuadra, "engranaje": col_engranaje, "pcb": col_pcb, "vslot": col_vslot, "bisagra": col_bisagra, "abrazadera": col_abrazadera, "fijacion": col_fijacion, "rodamiento": col_rodamiento, "planetario": col_planetario, "polea": col_polea, "helice": col_helice, "rotula": col_rotula, "carcasa": col_carcasa, "muelle": col_muelle, "acme": col_acme, "codo": col_codo, "naca": col_naca, "stand_movil": col_stand_movil, "clip_cable": col_clip_cable, "vr_pedestal": col_vr_pedestal}
            for k, p in tool_panels.items(): p.visible = (k == nombre_herramienta)
            panel_stl_transform.visible = nombre_herramienta.startswith("stl")
            generate_param_code(); page.update()

        def thumbnail(icon, title, tool_id, color): return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_especial = ft.Row([thumbnail("🧠", "Código Libre", "custom", "#000000"), thumbnail("🔠", "Placas Texto", "texto", "#880E4F"), thumbnail("🥽", "Pedestal VR", "vr_pedestal", "#B388FF")], scroll="auto")
        cat_bocetos = ft.Row([thumbnail("✍️", "Sketch 2D", "sketcher", "#2962FF")], scroll="auto")
        cat_stl_forge = ft.Row([thumbnail("🧊", "Híbrido Base", "stl", "#00C853"), thumbnail("📏", "Flatten", "stl_flatten", "#00C853"), thumbnail("✂️", "Split XYZ", "stl_split", "#00C853"), thumbnail("📦", "Crop Box", "stl_crop", "#00C853"), thumbnail("🕳️", "Taladro 3D", "stl_drill", "#00C853"), thumbnail("🔩", "Orejetas", "stl_mount", "#00C853"), thumbnail("🖱️", "Mouse Ears", "stl_ears", "#00C853"), thumbnail("🧱", "Bloque Ref", "stl_patch", "#00C853"), thumbnail("🐝", "Honeycomb", "stl_honeycomb", "#00C853"), thumbnail("🛡️", "Prop Guard", "stl_propguard", "#00C853")], scroll="auto")
        cat_accesorios = ft.Row([thumbnail("📱", "Stand Móvil", "stand_movil", "#00C853"), thumbnail("🔌", "Clip Cables", "clip_cable", "#00C853")], scroll="auto")
        cat_produccion = ft.Row([thumbnail("🔪", "Perfil Láser", "laser", "#D50000"), thumbnail("🔲", "Matriz Grid", "array_lin", "#0091EA"), thumbnail("🎡", "Matriz Polar", "array_pol", "#00B0FF")], scroll="auto")
        cat_lofting = ft.Row([thumbnail("🌪️", "Adap. Loft", "loft", "#D50000")], scroll="auto")
        cat_topologia = ft.Row([thumbnail("🐝", "Panal Hex", "panal", "#F57F17"), thumbnail("🕸️", "Voronoi", "voronoi", "#6A1B9A")], scroll="auto")
        cat_engranajes = ft.Row([thumbnail("⚙️", "Evolvente", "evolvente", "#E65100"), thumbnail("🛤️", "Cremallera", "cremallera", "#5D4037"), thumbnail("🍦", "Cónico", "conico", "#D84315")], scroll="auto")
        cat_multicuerpo = ft.Row([thumbnail("📦", "Caja+Tapa", "multicaja", "#33691E")], scroll="auto")
        cat_perfiles = ft.Row([thumbnail("⭐", "Estrella 2D", "perfil", "#F57F17"), thumbnail("🏺", "Revolución", "revolucion", "#6A1B9A")], scroll="auto")
        cat_aero = ft.Row([thumbnail("✈️", "Perfil NACA", "naca", "#01579B"), thumbnail("🚁", "Hélice", "helice", "#006064"), thumbnail("🚰", "Tubo Curvo", "codo", "#004D40")], scroll="auto")
        cat_mecanismos = ft.Row([thumbnail("🌀", "Muelle", "muelle", "#3E2723"), thumbnail("🦾", "Rótula", "rotula", "#BF360C"), thumbnail("⚙️", "Planetario", "planetario", "#E65100"), thumbnail("🛼", "Polea", "polea", "#0277BD"), thumbnail("🛞", "Rodamiento", "rodamiento", "#4E342E")], scroll="auto")
        cat_ingenieria = ft.Row([thumbnail("🚧", "Eje ACME", "acme", "#212121"), thumbnail("🗃️", "Carcasa", "carcasa", "#1B5E20"), thumbnail("🔩", "Tornillos", "fijacion", "#B71C1C"), thumbnail("🗜️", "Abrazadera", "abrazadera", "#0D47A1"), thumbnail("🔌", "Caja PCB", "pcb", "#004D40"), thumbnail("🚪", "Bisagra", "bisagra", "#311B92"), thumbnail("🏗️", "V-Slot", "vslot", "#1A237E")], scroll="auto")
        cat_basico = ft.Row([thumbnail("📦", "Cubo G", "cubo", "#263238"), thumbnail("🛢️", "Cilindro G", "cilindro", "#263238"), thumbnail("📐", "Escuadra", "escuadra", "#D84315"), thumbnail("⚙️", "Piñón SQ", "engranaje", "#FF6F00")], scroll="auto")

        view_constructor = ft.Column([
            panel_globales, 
            ft.Text("💡 Opciones Especiales:", size=12, color="#8B949E"), cat_especial,
            ft.Text("📐 Bocetos y Perfiles 2D:", size=12, color="#2962FF", weight="bold"), cat_bocetos,
            ft.Text("⚔️ ULTIMATE STL FORGE:", size=12, color="#00E676", weight="bold"), cat_stl_forge,
            ft.Text("🔋 Accesorios Prácticos:", size=12, color="#00E676"), cat_accesorios,
            ft.Text("🏭 Producción y Láser:", size=12, color="#00B0FF"), cat_produccion,
            ft.Text("🌪️ Transición de Formas:", size=12, color="#D50000"), cat_lofting,
            ft.Text("🧬 Topología y Voronoi:", size=12, color="#FBC02D"), cat_topologia,
            ft.Text("⚙️ Engranajes Avanzados:", size=12, color="#FF9100"), cat_engranajes,
            ft.Text("🧱 Ensamblajes Multi-Cuerpo:", size=12, color="#7CB342"), cat_multicuerpo,
            ft.Text("📐 Perfiles y Revolución 2D->3D:", size=12, color="#AB47BC"), cat_perfiles,
            ft.Text("🛸 Aero y Orgánico:", size=12, color="#00E5FF"), cat_aero,
            ft.Text("⚙️ Cinemática y Mecanismos:", size=12, color="#FFAB00"), cat_mecanismos,
            ft.Text("🛠️ Ingeniería:", size=12, color="#FF9100"), cat_ingenieria,
            ft.Text("📦 Geometría Básica:", size=12, color="#8B949E"), cat_basico,
            ft.Divider(color="#30363D"), panel_stl_transform,
            col_custom, col_sketcher, col_stl, col_stl_flatten, col_stl_split, col_stl_crop, col_stl_drill, col_stl_mount, col_stl_ears, col_stl_patch, col_stl_honeycomb, col_stl_propguard,
            col_texto, col_cubo, col_cilindro, col_laser, col_array_lin, col_array_pol, col_loft, col_panal, col_voronoi, col_evolvente, col_cremallera, col_conico, col_multicaja, col_perfil, col_revolucion, col_escuadra, col_engranaje, col_pcb, col_vslot, col_bisagra, col_abrazadera, col_fijacion, col_rodamiento, col_planetario, col_polea, col_helice, col_rotula, col_carcasa, col_muelle, col_acme, col_codo, col_naca, col_stand_movil, col_clip_cable, col_vr_pedestal,
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), bgcolor="#00E676", color="black", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR LOCAL", on_click=lambda _: save_project_to_nexus(), bgcolor="#0D47A1", color="white"), ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), bgcolor="#B71C1C", color="white")], scroll="auto"),
            txt_code
        ], expand=True)

        pb_cpu = ft.ProgressBar(width=100, color="#FFAB00", bgcolor="#30363D", value=0, expand=True)
        txt_cpu_val = ft.Text("0.0%", size=11, color="#FFAB00", width=40, text_align="right")
        pb_ram = ft.ProgressBar(width=100, color="#00E5FF", bgcolor="#30363D", value=0, expand=True)
        txt_ram_val = ft.Text("0.0%", size=11, color="#00E5FF", width=40, text_align="right")
        txt_cores = ft.Text("CORES: ?", size=11, color="#8B949E", weight="bold")

        hw_panel = ft.Container(content=ft.Column([ft.Row([ft.Text("📊 TELEMETRÍA HARDWARE", size=11, color="#E6EDF3", weight="bold"), txt_cores], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Row([ft.Text("CPU", size=11, color="#FFAB00", weight="bold", width=30), pb_cpu, txt_cpu_val]), ft.Row([ft.Text("RAM", size=11, color="#00E5FF", weight="bold", width=30), pb_ram, txt_ram_val])], spacing=5), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        def hw_monitor_loop():
            while True:
                time.sleep(1.5)
                try:
                    if main_container.content == view_visor:
                        cpu, ram, cores = get_sys_info()
                        pb_cpu.value = cpu / 100.0; txt_cpu_val.value = f"{cpu:.1f}%"
                        pb_ram.value = ram / 100.0; txt_ram_val.value = f"{ram:.1f}%"
                        txt_cores.value = f"CORES: {cores}"; hw_panel.update()
                except: pass

        threading.Thread(target=hw_monitor_loop, daemon=True).start()

        view_visor = ft.Column([
            ft.Container(height=5), hw_panel, ft.Container(height=5),
            ft.Container(content=ft.Column([ft.Text("🥽 MODO GAFAS VR O PC EXTERNO", color="#B388FF", weight="bold", size=11), ft.TextField(value=f"http://{LAN_IP}:{LOCAL_PORT}/openscad_engine.html", read_only=True, text_size=16, text_align="center", bgcolor="#161B22", color="#00E676")]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#B388FF")),
            ft.Container(height=5),
            ft.Text("Motor Web Worker (Exportación 100% Nativa TITAN)", text_align="center", color="#00E5FF", weight="bold"),
            ft.ElevatedButton("🔄 ABRIR VISOR 3D (ESTÁNDAR)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/openscad_engine.html", bgcolor="#00E676", color="black", height=60, width=float('inf')),
        ], expand=True, scroll="auto")
        
        # =========================================================
        # TAB 3: ENSAMBLADOR VISUAL PBR 
        # =========================================================
        def build_static_assembly_cards():
            cards = []
            for i in range(MAX_ASSEMBLY_PARTS):
                df = ft.Dropdown(options=[], width=160, text_size=12, bgcolor="#0B0E14", color="#00E5FF")
                dm = ft.Dropdown(options=[ft.dropdown.Option("pla"), ft.dropdown.Option("petg"), ft.dropdown.Option("carbon"), ft.dropdown.Option("aluminum"), ft.dropdown.Option("wood"), ft.dropdown.Option("gold")], value="pla", width=100, text_size=12, bgcolor="#0B0E14")
                
                sl_x = ft.Slider(min=-200, max=200, value=0, expand=True)
                sl_y = ft.Slider(min=-200, max=200, value=0, expand=True)
                sl_z = ft.Slider(min=-200, max=200, value=0, expand=True)
                
                card = ft.Container(bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#C51162"), visible=False)
                
                def make_change_handler(idx, d_f, d_m, s_x, s_y, s_z):
                    def handler(e):
                        if not ASSEMBLY_PARTS_STATE[idx]["active"]: return
                        ASSEMBLY_PARTS_STATE[idx]["file"] = d_f.value
                        ASSEMBLY_PARTS_STATE[idx]["mat"] = d_m.value
                        ASSEMBLY_PARTS_STATE[idx]["x"] = s_x.value
                        ASSEMBLY_PARTS_STATE[idx]["y"] = s_y.value
                        ASSEMBLY_PARTS_STATE[idx]["z"] = s_z.value
                        update_pbr_state()
                    return handler
                    
                change_handler = make_change_handler(i, df, dm, sl_x, sl_y, sl_z)
                df.on_change = change_handler; dm.on_change = change_handler; sl_x.on_change = change_handler; sl_y.on_change = change_handler; sl_z.on_change = change_handler
                
                def make_delete_handler(idx, c):
                    def handler(e):
                        ASSEMBLY_PARTS_STATE[idx]["active"] = False
                        c.visible = False
                        update_pbr_state()
                        check_empty_assembly()
                        page.update()  # IMPORTANTE: No usar c.update() directo si no está en pantalla
                    return handler
                    
                btn_del = ft.IconButton(icon="delete", icon_color="red", on_click=make_delete_handler(i, card))
                
                card.content = ft.Column([
                    ft.Row([df, dm, btn_del], alignment="spaceBetween"),
                    ft.Row([ft.Text("X", size=10, color="#8B949E", width=15), sl_x]),
                    ft.Row([ft.Text("Y", size=10, color="#8B949E", width=15), sl_y]),
                    ft.Row([ft.Text("Z", size=10, color="#8B949E", width=15), sl_z])
                ])
                
                def refresh_opts(d=df, idx=i):
                    files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
                    d.options = [ft.dropdown.Option(f) for f in files]
                    if not d.value and files: d.value = files[0]
                    elif d.value not in files and files: d.value = files[0]
                    if files: ASSEMBLY_PARTS_STATE[idx]["file"] = d.value
                    
                card.data = {"refresh": refresh_opts, "df": df, "dm": dm, "sx": sl_x, "sy": sl_y, "sz": sl_z}
                cards.append(card)
            return cards

        col_assembly_cards = build_static_assembly_cards()
        lbl_ensamble_warn = ft.Text("⚠️ DB de STLs vacía.\nVe a la pestaña FILES y sube o guarda STLs primero.", color="#FFAB00", weight="bold", visible=False)
        col_assembly = ft.Column([lbl_ensamble_warn] + col_assembly_cards, scroll="auto", expand=True)

        def check_empty_assembly():
            has_active = any(p["active"] for p in ASSEMBLY_PARTS_STATE)
            files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
            lbl_ensamble_warn.visible = not has_active and not files

        def add_assembly_part(e):
            files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
            if not files:
                status.value = "❌ No hay STLs para añadir. Sube archivos en la pestaña FILES."
                status.color = "#FF5252"; page.update(); return
                
            for i in range(MAX_ASSEMBLY_PARTS):
                if not ASSEMBLY_PARTS_STATE[i]["active"]:
                    ASSEMBLY_PARTS_STATE[i]["active"] = True
                    card = col_assembly_cards[i]
                    card.data["refresh"]()
                    card.data["sx"].value = 0; card.data["sy"].value = 0; card.data["sz"].value = 0
                    ASSEMBLY_PARTS_STATE[i]["x"] = 0; ASSEMBLY_PARTS_STATE[i]["y"] = 0; ASSEMBLY_PARTS_STATE[i]["z"] = 0
                    ASSEMBLY_PARTS_STATE[i]["mat"] = card.data["dm"].value
                    card.visible = True
                    update_pbr_state()
                    check_empty_assembly()
                    page.update()  # IMPORTANTE: Reemplaza card.update() para evitar cuelgues
                    return
            status.value = "❌ Límite máximo de piezas (10) alcanzado."
            status.color = "#FFAB00"; page.update()

        def render_assembly_ui():
            files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
            if not files:
                lbl_ensamble_warn.visible = True
                for i in range(MAX_ASSEMBLY_PARTS):
                    col_assembly_cards[i].visible = False
                    ASSEMBLY_PARTS_STATE[i]["active"] = False
            else:
                lbl_ensamble_warn.visible = not any(p["active"] for p in ASSEMBLY_PARTS_STATE)
                for i, card in enumerate(col_assembly_cards):
                    if ASSEMBLY_PARTS_STATE[i]["active"]:
                        card.data["refresh"]()

        view_ensamble = ft.Column([
            ft.Text("🧩 MESA DE ENSAMBLAJE", size=20, color="#FFAB00", weight="bold"),
            ft.Text("Une hasta 10 STLs. Se reflejará instantáneamente en PBR.", color="#8B949E", size=11),
            ft.Row([ft.ElevatedButton("➕ AÑADIR PIEZA", on_click=add_assembly_part, bgcolor="#1B5E20", color="white"), ft.ElevatedButton("👁️ ABRIR PBR", on_click=lambda _: set_tab(4), bgcolor="#C51162", color="white")]),
            ft.Divider(), col_assembly
        ], expand=True)

        view_pbr = ft.Column([
            ft.Container(height=20),
            ft.Text("🎨 PBR STUDIO PRO", size=24, color="#FF007F", weight="bold", text_align="center"),
            ft.Text("Renderizado Físico Realista con Shaders Procedurales.", color="#E6EDF3", text_align="center"),
            ft.Container(height=20),
            ft.Container(content=ft.Column([ft.Text("Soporta la Pieza Única (PARAM) o Ensamble (MESA).", color="#00E676"), ft.Text("El botón 'Tomar Foto' guarda el render en NEXUS DB.", color="#00E676", weight="bold")]), bgcolor="#161B22", padding=15, border_radius=8, border=ft.border.all(1, "#C51162")),
            ft.Container(height=20),
            ft.ElevatedButton("🚀 ABRIR PBR STUDIO", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/pbr_studio.html", bgcolor="#C51162", color="white", height=80, width=float('inf'))
        ], expand=True, horizontal_alignment="center")

        # PANEL CALIBRE 3D
        txt_dim_x = ft.Text("0.0 mm", color="#00E5FF", weight="bold"); txt_dim_y = ft.Text("0.0 mm", color="#00E5FF", weight="bold"); txt_dim_z = ft.Text("0.0 mm", color="#00E5FF", weight="bold")
        txt_vol = ft.Text("0.0 cm³", color="#FFAB00", weight="bold"); txt_peso = ft.Text("0.0 g", color="#00E676", weight="bold")
        panel_calibre = ft.Container(content=ft.Column([ft.Text("📐 CALIBRE 3D Y PRESUPUESTO (STL ACTUAL)", color="#E6EDF3", weight="bold"), ft.Row([ft.Text("Ancho (X):", color="#8B949E", width=80), txt_dim_x]), ft.Row([ft.Text("Largo (Y):", color="#8B949E", width=80), txt_dim_y]), ft.Row([ft.Text("Alto (Z):", color="#8B949E", width=80), txt_dim_z]), ft.Divider(color="#30363D"), ft.Row([ft.Text("Volumen:", color="#8B949E", width=80), txt_vol]), ft.Row([ft.Text("Peso PLA:", color="#8B949E", width=80), txt_peso])]), bgcolor="#161B22", padding=15, border_radius=8, border=ft.border.all(1, "#2962FF"))

        list_nexus_db = ft.ListView(height=250, spacing=5)

        def custom_icon_btn(text, action, tooltip_txt):
            return ft.Container(content=ft.Text(text, size=16), padding=5, bgcolor="#30363D", border_radius=5, on_click=action, tooltip=tooltip_txt, ink=True)

        def direct_download_file(e, filename):
            src = os.path.join(EXPORT_DIR, filename)
            dest = os.path.join(DOWNLOAD_DIR, filename)
            try:
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                shutil.copy(src, dest)
                status.value = f"✓ {filename} guardado en Descargas de Android."
                status.color = "#00E676"
            except Exception as ex:
                status.value = f"❌ Error guardando: {ex}"
                status.color = "#FF5252"
            page.update()

        def export_obj_file(e, filename):
            stl_path = os.path.join(EXPORT_DIR, filename)
            obj_name = filename.replace('.stl', '.obj')
            obj_path = os.path.join(DOWNLOAD_DIR, obj_name)
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            success, msg = convert_stl_to_obj(stl_path, obj_path)
            if success:
                status.value = f"✓ Convertido a OBJ y guardado en Descargas."
                status.color = "#00E5FF"
            else:
                status.value = f"❌ Error al exportar OBJ: {msg}"
                status.color = "#FF5252"
            page.update()

        def refresh_nexus_db():
            list_nexus_db.controls.clear()
            try:
                files = [f for f in os.listdir(EXPORT_DIR) if not f.startswith('.') and f != "imported.stl"]
                if not files: list_nexus_db.controls.append(ft.Text("Vacío. Inyecta un archivo.", color="#8B949E", italic=True))
                for f in files:
                    ext = f.lower().split('.')[-1]; p = os.path.join(EXPORT_DIR, f)
                    icon = "🧊" if ext=="stl" else ("🖼️" if ext=="png" else "🧩")
                    color = "#00E676" if ext=="stl" else ("#C51162" if ext=="png" else "white")
                    
                    actions = [
                        custom_icon_btn("⬇️", lambda e, fn=f: direct_download_file(e, fn), "Guardar a Download"),
                        custom_icon_btn("🗑️", lambda e, fp=p: [os.remove(fp), refresh_nexus_db()], "Borrar")
                    ]
                    if ext == "stl":
                        actions.insert(0, custom_icon_btn("📦", lambda e, fn=f: export_obj_file(e, fn), "Exportar OBJ (Descargas)"))
                        actions.insert(0, custom_icon_btn("▶️", lambda e, fp=p: load_file(fp), "Cargar STL"))
                    elif ext == "jscad": 
                        actions.insert(0, custom_icon_btn("▶️", lambda e, fp=p: load_file(fp), "Cargar Código"))
                        
                    list_nexus_db.controls.append(ft.Container(content=ft.Row([ft.Text(icon, size=20), ft.Text(f, color=color, weight="bold", expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)] + actions), bgcolor="#21262D", padding=5, border_radius=5))
            except Exception as e: list_nexus_db.controls.append(ft.Text(f"Error DB: {e}"))
            page.update()

        def load_file(filepath):
            fn = os.path.basename(filepath); ext = fn.lower().split('.')[-1]
            if ext == "stl":
                is_valid, msg = validate_stl(filepath)
                if not is_valid: status.value = f"❌ {msg}"; status.color = "#FF5252"; page.update(); return
                
                metrics = analyze_stl(filepath)
                if metrics:
                    txt_dim_x.value = f"{metrics['dx']} mm"; txt_dim_y.value = f"{metrics['dy']} mm"; txt_dim_z.value = f"{metrics['dz']} mm"
                    txt_vol.value = f"{metrics['vol_cm3']} cm³"; txt_peso.value = f"{metrics['weight_g']} g"

                shutil.copy(filepath, os.path.join(EXPORT_DIR, "imported.stl"))
                lbl_stl_status.value = f"✓ Activo: {fn}"; lbl_stl_status.color = "#00E676"
                select_tool("stl"); set_tab(1); update_code_wrapper()
                status.value = f"✓ STL Inyectado en Memoria"
            elif ext == "jscad": txt_code.value = open(filepath).read(); set_tab(0); status.value = "✓ Código Cargado"
            page.update()

        current_android_dir = ANDROID_ROOT
        tf_path = ft.TextField(value=current_android_dir, expand=True, bgcolor="#161B22", height=40, text_size=12)
        list_android = ft.ListView(height=400, spacing=5)

        def file_action(filepath):
            ext = filepath.lower().split('.')[-1] if '.' in filepath else ''
            if ext in ["stl", "jscad"]: load_file(filepath)
            else: status.value = f"⚠️ Formato .{ext} no soportado."; status.color = "#FFAB00"; page.update()

        def refresh_explorer(path):
            list_android.controls.clear()
            try:
                items = os.listdir(path)
                dirs = [d for d in items if os.path.isdir(os.path.join(path, d))]
                files = [f for f in items if os.path.isfile(os.path.join(path, f))]
                dirs.sort(); files.sort()
                if path != "/" and path != "/storage" and path != "/storage/emulated":
                    list_android.controls.append(ft.ListTile(leading=ft.Text("⬆️", size=24), title=ft.Text(".. (Subir nivel)", color="white"), on_click=lambda e: nav_to(os.path.dirname(path))))
                for d in dirs:
                    if d.startswith('.'): continue
                    list_android.controls.append(ft.ListTile(leading=ft.Text("📁", size=24), title=ft.Text(d, color="#E6EDF3"), on_click=lambda e, p=os.path.join(path, d): nav_to(p)))
                for f in files:
                    ext = f.lower().split('.')[-1] if '.' in f else ''
                    icon = "📄"; color = "#8B949E"
                    if ext == "stl": icon = "🧊"; color = "#00E676"
                    elif ext == "jscad": icon = "🧩"; color = "#00E5FF"
                    elif ext == "png": icon = "🖼️"; color = "#C51162"
                    list_android.controls.append(ft.ListTile(leading=ft.Text(icon, size=24), title=ft.Text(f, color=color), subtitle=ft.Text(f"{os.path.getsize(os.path.join(path, f)) // 1024} KB", size=10), on_click=lambda e, p=os.path.join(path, f): file_action(p)))
            except PermissionError: list_android.controls.append(ft.Text("❌ Permiso Denegado.", color="red", weight="bold"))
            except Exception as ex: list_android.controls.append(ft.Text(f"Error: {ex}", color="red"))
            tf_path.value = path; page.update()

        def nav_to(path): nonlocal current_android_dir; current_android_dir = path; refresh_explorer(path)

        def save_to_android(e):
            if not os.path.isdir(current_android_dir): return
            fname = f"nexus_{int(time.time())}.jscad"
            try:
                with open(os.path.join(current_android_dir, fname), "w") as f: f.write(txt_code.value)
                status.value = f"✓ Guardado en Android: {fname}"; status.color = "#00E676"; refresh_explorer(current_android_dir)
            except Exception as ex: status.value = f"❌ Error guardando: {ex}"; status.color = "red"
            page.update()

        def save_project_to_nexus():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = f"✓ Guardado en DB Interna: {fname}"; page.update()

        row_quick_paths = ft.Row([
            ft.ElevatedButton("🏠 Android", on_click=lambda _: nav_to("/storage/emulated/0"), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📥 Descargas", on_click=lambda _: nav_to("/storage/emulated/0/Download"), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📁 Nexus DB", on_click=lambda _: nav_to(EXPORT_DIR), bgcolor="#1B5E20", color="white")
        ], scroll="auto")

        view_archivos = ft.Column([
            panel_calibre,
            ft.Container(content=ft.Column([
                ft.Text("🌐 INYECCIÓN WEB & NEXUS DB", color="#00E676", weight="bold"),
                ft.ElevatedButton("🚀 INYECTAR ARCHIVO (VÍA PC)", url=f"http://127.0.0.1:{LOCAL_PORT}/upload_ui", bgcolor="#00E676", color="black", width=float('inf')),
                ft.Row([ft.Text("Archivos y Renders listos:", color="#E6EDF3", size=11), ft.ElevatedButton("🔄", on_click=lambda _: refresh_nexus_db(), bgcolor="#1E1E1E", width=50)], alignment="spaceBetween"),
                ft.Container(content=list_nexus_db, bgcolor="#0B0E14", border_radius=5, padding=5)
            ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676")),
            ft.Container(content=ft.Column([
                ft.Text("📱 EXPLORADOR NATIVO ANDROID", color="#00E5FF", weight="bold"),
                row_quick_paths, ft.Row([tf_path, ft.ElevatedButton("Ir", on_click=lambda _: nav_to(tf_path.value), bgcolor="#FFAB00", color="black")]),
                ft.ElevatedButton("💾 GUARDAR CÓDIGO AQUÍ", on_click=save_to_android, bgcolor="#0D47A1", color="white", width=float('inf')),
                ft.Container(content=list_android, bgcolor="#0B0E14", border_radius=5, padding=5)
            ]), bgcolor="#161B22", padding=10, border_radius=8)
        ], expand=True, scroll="auto")

        # =========================================================
        # TAB 6: IA ASSISTANT
        # =========================================================
        chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)
        ia_input = ft.TextField(label="Pide a la IA que diseñe algo...", expand=True, bgcolor="#161B22", border_color="#B388FF")

        def apply_ia_code(code):
            txt_code.value = code
            set_tab(0)
            status.value = "✓ Código de IA aplicado al editor."
            page.update()

        def send_ia(e=None):
            user_text = ia_input.value.strip()
            if not user_text: return
            chat_list.controls.append(ft.Container(content=ft.Text(f"👤 {user_text}", color="white"), bgcolor="#21262D", padding=10, border_radius=8))
            ia_input.value = ""
            page.update()
            
            def think():
                time.sleep(1)
                # Template base IA
                code_template = f"function main(params) {{\n  // Plantilla inteligente para: {user_text}\n  // Ajusta los valores según necesites.\n  var W = GW || 50;\n  var L = GL || 50;\n  var H = GH || 20;\n  var obj = CSG.cube({{radius: [W/2, L/2, H/2]}});\n  return UTILS.mat(obj);\n}}"
                
                btn_apply = ft.ElevatedButton("📥 APLICAR CÓDIGO AL EDITOR", on_click=lambda _: apply_ia_code(code_template), bgcolor="#00E676", color="black")
                
                resp_container = ft.Container(content=ft.Column([
                    ft.Text(f"🤖 ¡Listo! He procesado una plantilla basada en tu petición: '{user_text}'. Puedes aplicarla al entorno CODE de inmediato.", color="#00E676", size=12),
                    ft.Container(content=ft.Text(code_template, size=10, color="#58A6FF", font_family="monospace"), bgcolor="#0B0E14", padding=10, border_radius=5),
                    btn_apply
                ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"))
                
                chat_list.controls.append(resp_container)
                page.update()
            
            threading.Thread(target=think, daemon=True).start()

        ia_input.on_submit = send_ia
        btn_send_ia = ft.IconButton(icon="send", icon_color="#00E676", on_click=send_ia)

        view_ia = ft.Column([
            ft.Row([ft.Text("🤖 NEXUS AI ASSISTANT", size=20, color="#B388FF", weight="bold")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text("Asistente interno para generación de plantillas JS-CSG a través de lenguaje natural.", color="#8B949E", size=11),
            ft.Container(content=chat_list, expand=True, bgcolor="#0B0E14", padding=10, border_radius=8, border=ft.border.all(1, "#30363D")),
            ft.Row([ia_input, btn_send_ia])
        ], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            global PBR_STATE, LATEST_CODE_B64, LATEST_NEEDS_STL
            if idx in [0, 1, 2, 6]: PBR_STATE["mode"] = "single"
            if idx == 3: render_assembly_ui()
            if idx == 5: refresh_nexus_db(); refresh_explorer(current_android_dir)
            main_container.content = [view_editor, view_constructor, view_visor, view_ensamble, view_pbr, view_archivos, view_ia][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🌐 PARAM", on_click=lambda _: set_tab(1), bgcolor="#FFAB00", color="black"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), bgcolor="#00E5FF", color="black"),
            ft.ElevatedButton("🧩 ENS", on_click=lambda _: set_tab(3), bgcolor="#7CB342", color="white"),
            ft.ElevatedButton("🎨 PBR", on_click=lambda _: set_tab(4), bgcolor="#C51162", color="white"),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(5), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🤖 IA", on_click=lambda _: set_tab(6), bgcolor="#B388FF", color="black"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        select_tool("planetario"); refresh_explorer(current_android_dir)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)