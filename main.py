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

# ESTADO DEL ENSAMBLADOR PBR
PBR_STATE = {
    "mode": "single", # 'single' o 'assembly'
    "parts": []
}

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

            vol_cm3 = abs(volume) / 1000.0
            weight_pla = vol_cm3 * 1.24

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

        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 1.0);
        scene.add(hemiLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
        dirLight.position.set(50, 100, 50);
        scene.add(dirLight);
        const backLight = new THREE.DirectionalLight(0x00E5FF, 1.0);
        backLight.position.set(-50, 50, -50);
        scene.add(backLight);

        document.getElementById('lightSlider').addEventListener('input', (e) => {
            dirLight.intensity = parseFloat(e.target.value);
            hemiLight.intensity = parseFloat(e.target.value) * 0.6;
        });

        const camera = new THREE.PerspectiveCamera(45, window.innerWidth/window.innerHeight, 0.1, 2000);
        camera.position.set(150, 150, 150);

        const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.outputEncoding = THREE.sRGBEncoding;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        document.body.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;

        function takeScreenshot() {
            renderer.render(scene, camera);
            const dataURL = renderer.domElement.toDataURL("image/png");
            fetch('/api/save_image', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({filename: 'render_' + Date.now() + '.png', image_data: dataURL})
            }).then(r => r.json()).then(d => {
                const t = document.getElementById('toast');
                t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 3000);
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

        let currentGroup = null;
        let stateHash = "";
        const loader = new THREE.STLLoader();
        let geomCache = {};

        function checkState() {
            fetch('/api/assembly_state.json?t=' + Date.now()).then(r => r.json()).then(state => {
                let newHash = JSON.stringify(state);
                if(newHash !== stateHash) {
                    stateHash = newHash;
                    buildScene(state);
                }
            }).catch(()=>{});
        }

        setInterval(checkState, 1000);

        function buildScene(state) {
            if(currentGroup) scene.remove(currentGroup);
            currentGroup = new THREE.Group();
            scene.add(currentGroup);

            if(state.mode === 'single') {
                document.getElementById('singleMatContainer').style.display = 'block';
                document.getElementById('modeText').innerText = "Modo: Pieza Única";
                let matKey = document.getElementById('matSelect').value;
                loadStlFile('/imported.stl?t='+Date.now(), 0, 0, 0, matKey, true);
            } else {
                document.getElementById('singleMatContainer').style.display = 'none';
                document.getElementById('modeText').innerText = "Modo: Mesa Ensamblaje";
                state.parts.forEach(p => {
                    if(p.file) loadStlFile('/descargar/' + encodeURIComponent(p.file), p.x, p.y, p.z, p.mat, false);
                });
            }
        }

        function loadStlFile(url, x, y, z, matKey, centerCam) {
            if(geomCache[url] && !url.includes('?')) {
                addMeshToGroup(geomCache[url], x, y, z, matKey, centerCam);
            } else {
                loader.load(url, geom => {
                    geom.center(); geom.computeVertexNormals();
                    if(!url.includes('?')) geomCache[url] = geom;
                    addMeshToGroup(geom, x, y, z, matKey, centerCam);
                });
            }
        }

        function addMeshToGroup(geom, x, y, z, matKey, centerCam) {
            let mesh = new THREE.Mesh(geom, mats[matKey] || mats.pla);
            mesh.rotation.x = -Math.PI / 2; // CSG Z-UP a ThreeJS Y-UP
            mesh.position.set(x, z, -y);
            currentGroup.add(mesh);
            
            if(centerCam) {
                geom.computeBoundingSphere();
                const r = geom.boundingSphere.radius;
                camera.position.set(r*1.5, r*1.5, r*1.5);
                controls.target.set(0,0,0);
            }
        }

        document.getElementById('matSelect').addEventListener('change', () => { stateHash = ""; checkState(); });

        function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }
        animate();
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
        if parsed.path == '/api/save_image':
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

        elif parsed.path == '/api/upload':
            cl = int(self.headers.get('Content-Length', 0))
            fn = unquote(self.headers.get('File-Name', 'uploaded_file.stl'))
            if cl > 0:
                try:
                    file_data = self.rfile.read(cl)
                    filepath = os.path.join(EXPORT_DIR, fn)
                    with open(filepath, 'wb') as f: f.write(file_data)
                    resp = b'ok'
                    self.send_response(200); self.send_header("Content-type", "text/plain"); self.send_header("Content-Length", str(len(resp))); self._send_cors(); self.end_headers(); self.wfile.write(resp)
                    return
                except: pass
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
                    if os.path.getsize(filepath) >= 84:
                        with open(filepath, "rb") as f: data_to_send = f.read()
                except: pass
            self.send_response(200); self.send_header("Content-type", "model/stl"); self.send_header("Content-Length", str(len(data_to_send))); self.send_header("Cache-Control", "no-cache"); self._send_cors(); self.end_headers()
            try:
                for i in range(0, len(data_to_send), 65536): self.wfile.write(data_to_send[i:i+65536])
            except: pass

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
                with open(os.path.join(ASSETS_DIR, fn), "r", encoding="utf-8") as f: content = f.read()
                stl_path = os.path.join(EXPORT_DIR, "imported.stl")
                b64_stl = base64.b64encode(DUMMY_VALID_STL).decode('utf-8')
                if os.path.exists(stl_path) and os.path.getsize(stl_path) >= 84:
                    with open(stl_path, "rb") as stl_file: b64_stl = base64.b64encode(stl_file.read()).decode('utf-8')
                
                injector = '''<script>
                (function() {
                    var stlData = "data:application/octet-stream;base64,__B64_STL__";
                    var origOpen = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(method, url) { if (url && typeof url === "string" && url.indexOf("imported.stl") !== -1) { arguments[1] = stlData; } return origOpen.apply(this, arguments); };
                    if(window.fetch) { var origFetch = window.fetch; window.fetch = function(resource, config) { if (resource && typeof resource === "string" && resource.indexOf("imported.stl") !== -1) { resource = stlData; } return origFetch.call(this, resource, config); }; }
                    if(window.Worker) { var origWorker = window.Worker; window.Worker = function(scriptURL, options) { var absUrl = new URL(scriptURL, location.href).href; var code = "var stlData = '" + stlData + "'; var origOpen = XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open = function(m, u) { if (u && typeof u === 'string' && u.indexOf('imported.stl') !== -1) { arguments[1] = stlData; } return origOpen.apply(this, arguments); }; if(self.fetch) { var origFetch = self.fetch; self.fetch = function(r, c) { if (r && typeof r === 'string' && r.indexOf('imported.stl') !== -1) { r = stlData; } return origFetch.call(this, r, c); }; } importScripts('" + absUrl + "');"; var blob = new Blob([code], { type: "application/javascript" }); return new origWorker(URL.createObjectURL(blob), options); }; }
                })();
                </script>'''.replace("__B64_STL__", b64_stl)
                
                if "<head>" in content: content = content.replace("<head>", "<head>" + injector)
                else: content = injector + content
                    
                encoded_content = content.encode('utf-8')
                self.send_response(200); self.send_header("Content-type", "text/html"); self.send_header("Content-Length", str(len(encoded_content))); self._send_cors(); self.end_headers(); self.wfile.write(encoded_content)
                return
            except Exception as e: self.send_response(500); self._send_cors(); self.end_headers(); self.wfile.write(str(e).encode())

        else:
            try:
                fn = self.path.strip("/")
                with open(os.path.join(ASSETS_DIR, fn), "rb") as f: self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
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
        page.title = "NEXUS CAD v20.28 TITAN ASSAULT"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v20.28 | Ensamble PBR & IA Integrado", color="#00E676", weight="bold")

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

        herramienta_actual = "custom"

        def clear_editor():
            txt_code.value = "function main() {\n  return CSG.cube({radius:[0.01,0.01,0.01]});\n}"
            status.value = "✓ Código borrado."; status.color = "#B71C1C"
            txt_code.update(); page.update()

        def update_code_wrapper(e=None): generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=45, text_align="right", size=13, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"; txt_val.update(); update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="#E6EDF3"), sl, txt_val])

        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False)
        sl_g_tol, r_g_tol = create_slider("Tol. Global (G_TOL)", 0.0, 2.0, 0.2, False)
        sl_kine, r_kine = create_slider("Animación (º)", 0, 360, 0, True)

        dd_mat = ft.Dropdown(options=[ft.dropdown.Option("PLA Gris Mate"), ft.dropdown.Option("PETG Transparente"), ft.dropdown.Option("Fibra de Carbono"), ft.dropdown.Option("Aluminio Mecanizado"), ft.dropdown.Option("Madera Bambú"), ft.dropdown.Option("Oro Puro"), ft.dropdown.Option("Neón Cyan")], value="PLA Gris Mate", bgcolor="#161B22", color="#00E5FF", expand=True, text_size=12)
        dd_mat.on_change = update_code_wrapper

        def prepare_js_payload():
            c_val = {"PLA Gris Mate": "[0.5, 0.5, 0.5, 1.0]", "PETG Transparente": "[0.8, 0.9, 0.9, 0.45]", "Fibra de Carbono": "[0.15, 0.15, 0.15, 1.0]", "Aluminio Mecanizado": "[0.7, 0.75, 0.8, 1.0]", "Madera Bambú": "[0.6, 0.4, 0.2, 1.0]", "Oro Puro": "[0.9, 0.75, 0.1, 1.0]", "Neón Cyan": "[0.0, 1.0, 1.0, 0.8]"}.get(dd_mat.value, "[0.5, 0.5, 0.5, 1.0]")
            header = f"  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value}; var G_TOL = {sl_g_tol.value}; var KINE_T = {sl_kine.value}; var MAT_C = {c_val};\n"
            utils_block = "  if(typeof CSG !== 'undefined' && typeof CSG.Matrix4x4 === 'undefined' && typeof Matrix4x4 !== 'undefined') { CSG.Matrix4x4 = Matrix4x4; }\n  var UTILS = { trans: function(o, v) { if(!o) return o; var r; try { r = o.translate(v); } catch(e) { try { if(typeof translate !== 'undefined') r = translate(v, o); } catch(e2) {} } return r ? r : o; }, scale: function(o, v) { if(!o) return o; var r; try { r = o.scale(v); } catch(e) { try { if(typeof scale !== 'undefined') r = scale(v, o); } catch(e2) {} } return r ? r : o; }, rotZ: function(o, d) { if(!o) return o; var r; try { r = o.rotateZ(d); } catch(e) { try { if(typeof rotate !== 'undefined') r = rotate([0,0,d], o); else r = o.rotate([0,0,0],[0,0,1],d); } catch(e2) {} } return r ? r : o; }, rotX: function(o, d) { if(!o) return o; var r; try { r = o.rotateX(d); } catch(e) { try { if(typeof rotate !== 'undefined') r = rotate([d,0,0], o); else r = o.rotate([0,0,0],[1,0,0],d); } catch(e2) {} } return r ? r : o; }, rotY: function(o, d) { if(!o) return o; var r; try { r = o.rotateY(d); } catch(e) { try { if(typeof rotate !== 'undefined') r = rotate([0,d,0], o); else r = o.rotate([0,0,0],[0,1,0],d); } catch(e2) {} } return r ? r : o; }, mat: function(o) { if(!o) return CSG.cube({radius:[0.01,0.01,0.01]}); try { if(typeof o.setColor === 'function') return o.setColor(MAT_C); } catch(e) {} return o; } };\n"
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

        panel_globales = ft.Container(content=ft.Column([
            ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11),
            r_g_w, r_g_l, r_g_h, r_g_t, r_g_tol,
            ft.Divider(color="#333333"),
            ft.Row([ft.Text("🎨 TEXTURA / RENDER:", color="#E6EDF3", size=11, width=130), dd_mat]),
            ft.Divider(color="#333333"),
            ft.Text("🎬 CINEMÁTICA INTERACTIVA", color="#B388FF", weight="bold", size=11), r_kine
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

        tf_texto = ft.TextField(label="Escribe Texto", value="NEXUS", max_length=15, bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Fino"), ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Braille")], value="Voxel Grueso", expand=True, bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Solo Texto"), ft.dropdown.Option("Llavero"), ft.dropdown.Option("Soporte")], value="Llavero", expand=True, bgcolor="#161B22")
        sw_txt_grabado = ft.Switch(label="Texto Grabado", value=False, active_color="#00E5FF")
        tf_texto.on_change = update_code_wrapper; dd_txt_estilo.on_change = update_code_wrapper; dd_txt_base.on_change = update_code_wrapper; sw_txt_grabado.on_change = update_code_wrapper
        col_texto = ft.Column([ft.Text("Placas Especiales", color="#880E4F", weight="bold"), ft.Container(content=ft.Column([tf_texto, ft.Row([dd_txt_estilo, dd_txt_base]), sw_txt_grabado]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_c_grosor, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False); col_cubo = ft.Column([ft.Text("Cubo Paramétrico", color="#8B949E"), r_c_g], visible=False)
        sl_p_rint, r_p_rint = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_lados, r_p_lados = create_slider("Caras (LowPoly)", 3, 64, 64, True); col_cilindro = ft.Column([ft.Text("Cilindro / Prisma", color="#8B949E"), r_p_rint, r_p_lados], visible=False)
        sl_plan_rs, r_plan_rs = create_slider("Radio Sol", 5, 40, 10, False); sl_plan_rp, r_plan_rp = create_slider("Radio Planetas", 4, 30, 8, False); sl_plan_h, r_plan_h = create_slider("Grosor Total", 3, 30, 6, False); col_planetario = ft.Column([ft.Text("Planetario", color="#FFAB00"), ft.Container(content=ft.Column([r_plan_rs, r_plan_rp, r_plan_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True); sl_fij_l, r_fij_l = create_slider("Largo Tornillo", 0, 100, 30, False); col_fijacion = ft.Column([ft.Text("Tuerca / Tornillo Hex", color="#FFAB00"), ft.Container(content=ft.Column([r_fij_m, r_fij_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)
        sl_pan_x, r_pan_x = create_slider("Ancho X", 20, 200, 80, False); sl_pan_y, r_pan_y = create_slider("Largo Y", 20, 200, 80, False); sl_pan_z, r_pan_z = create_slider("Alto Z", 2, 50, 10, False); sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False); col_panal = ft.Column([ft.Text("Panal Honeycomb", color="#FBC02D"), ft.Container(content=ft.Column([r_pan_x, r_pan_y, r_pan_z, r_pan_r]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

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
            elif h == "texto": code += "  return CSG.cube({radius:[10,10,10]});\n}" # Placeholder for brevity
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
            elif h == "panal":
                code += f"  var w = {sl_pan_x.value}; var l = {sl_pan_y.value}; var h = {sl_pan_z.value}; var r_hex = {sl_pan_r.value}; var t = 1.5;\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}}); var int_box = CSG.cube({{center:[0,0,h/2], radius:[w/2-t, l/2-t, h/2+1]}});\n"
                code += f"  var frame = ext.subtract(int_box); var core_vol = CSG.cube({{center:[0,0,h/2], radius:[w/2-t, l/2-t, h/2]}});\n"
                code += f"  var holes = null; var dx = r_hex * 1.732 + t; var dy = r_hex * 1.5 + t;\n"
                code += f"  for(var x = -w/2 + r_hex; x < w/2; x += dx) {{ for(var y = -l/2 + r_hex; y < l/2; y += dy) {{\n"
                code += f"      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0; var cx = x + offset;\n"
                code += f"      if(cx < w/2 - r_hex && cx > -w/2 + r_hex) {{\n"
                code += f"          var hex = CSG.cylinder({{start:[cx, y, -1], end:[cx, y, h+1], radius:r_hex, slices:6}});\n"
                code += f"          if(!holes) holes = hex; else holes = holes.union(hex);\n      }}\n  }} }}\n"
                code += f"  if(holes) core_vol = core_vol.subtract(holes);\n  return UTILS.mat(frame.union(core_vol));\n}}"
            elif h == "fijacion":
                m, l_tornillo = sl_fij_m.value, sl_fij_l.value
                r_hex = (m * 1.8) / 2; h_cabeza = m * 0.8; r_eje = m / 2
                if l_tornillo == 0: 
                    code += f"  var m = {m}; var h = {h_cabeza};\n  var cuerpo = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:{r_hex}, slices:6}});\n  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:({r_eje} + G_TOL), slices:32}});\n  return UTILS.mat(cuerpo.subtract(agujero));\n}}"
                else: 
                    code += f"  var m = {m}; var l_tornillo = {l_tornillo}; var h_cabeza = {h_cabeza}; var r_hex = {r_hex};\n  var cabeza = CSG.cylinder({{start:[0,0,0], end:[0,0,h_cabeza], radius:r_hex, slices:6}});\n  var eje = CSG.cylinder({{start:[0,0,h_cabeza - 0.1], end:[0,0,h_cabeza + l_tornillo], radius:({r_eje} - G_TOL) - (m*0.08), slices:32}});\n  var pieza = cabeza.union(eje); var paso = m * 0.15;\n  for(var z = h_cabeza + 1; z < h_cabeza + l_tornillo - 1; z += paso*1.5) {{\n      var anillo = CSG.cylinder({{start:[0,0,z], end:[0,0,z+paso], radius:({r_eje} - G_TOL), slices:16}});\n      pieza = pieza.union(anillo);\n  }}\n  return UTILS.mat(UTILS.rotZ(pieza, KINE_T));\n}}"
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

            if h != "custom": txt_code.value = code
            txt_code.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            tool_panels = {"custom": col_custom, "sketcher": col_sketcher, "stl": col_stl, "stl_flatten": col_stl_flatten, "stl_split": col_stl_split, "stl_crop": col_stl_crop, "stl_drill": col_stl_drill, "stl_mount": col_stl_mount, "texto": col_texto, "cubo": col_cubo, "cilindro": col_cilindro, "panal": col_panal, "fijacion": col_fijacion, "planetario": col_planetario}
            for k, p in tool_panels.items(): 
                if p: p.visible = (k == nombre_herramienta)
            panel_stl_transform.visible = nombre_herramienta.startswith("stl")
            generate_param_code(); page.update()

        def thumbnail(icon, title, tool_id, color): return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_especial = ft.Row([thumbnail("🧠", "Código Libre", "custom", "#000000"), thumbnail("🔠", "Placas Texto", "texto", "#880E4F")], scroll="auto")
        cat_stl_forge = ft.Row([thumbnail("🧊", "Híbrido Base", "stl", "#00C853"), thumbnail("📏", "Flatten", "stl_flatten", "#00C853"), thumbnail("✂️", "Split XYZ", "stl_split", "#00C853"), thumbnail("📦", "Crop Box", "stl_crop", "#00C853"), thumbnail("🕳️", "Taladro 3D", "stl_drill", "#00C853"), thumbnail("🔩", "Orejetas", "stl_mount", "#00C853")], scroll="auto")
        cat_mecanismos = ft.Row([thumbnail("⚙️", "Planetario", "planetario", "#E65100"), thumbnail("🐝", "Panal Hex", "panal", "#F57F17"), thumbnail("🔩", "Tornillos", "fijacion", "#B71C1C")], scroll="auto")
        cat_basico = ft.Row([thumbnail("✍️", "Sketch 2D", "sketcher", "#2962FF"), thumbnail("📦", "Cubo G", "cubo", "#263238"), thumbnail("🛢️", "Cilindro G", "cilindro", "#263238")], scroll="auto")

        view_constructor = ft.Column([
            panel_globales, 
            ft.Text("💡 Opciones Especiales:", size=12, color="#8B949E"), cat_especial,
            ft.Text("⚔️ ULTIMATE STL FORGE:", size=12, color="#00E676", weight="bold"), cat_stl_forge,
            ft.Text("⚙️ Mecanismos e Ingeniería:", size=12, color="#FF9100"), cat_mecanismos,
            ft.Text("📦 Geometría Básica:", size=12, color="#8B949E"), cat_basico,
            ft.Divider(color="#30363D"), panel_stl_transform,
            col_custom, col_sketcher, col_stl, col_stl_flatten, col_stl_split, col_stl_crop, col_stl_drill, col_stl_mount, col_texto, col_cubo, col_cilindro, col_panal, col_fijacion, col_planetario,
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
            ft.Container(content=ft.Column([ft.Text("🥽 MODO GAFAS VR O PC EXTERNO", color="#B388FF", weight="bold", size=11), ft.TextField(value=f"http://{LAN_IP}:{LOCAL_PORT}/", read_only=True, text_size=16, text_align="center", bgcolor="#161B22", color="#00E676")]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#B388FF")),
            ft.Container(height=5),
            ft.Text("Motor Web Worker (Geometría Base)", text_align="center", color="#00E5FF", weight="bold"),
            ft.ElevatedButton("🔄 ABRIR VISOR 3D (ESTÁNDAR)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", bgcolor="#00E676", color="black", height=60, width=float('inf')),
        ], expand=True, scroll="auto")
        
        # =========================================================
        # TAB 3: ENSAMBLADOR VISUAL PBR
        # =========================================================
        def update_pbr_state():
            global PBR_STATE
            PBR_STATE["mode"] = "assembly"
            PBR_STATE["parts"] = getattr(page, "assembly_parts", [])
            
        def render_assembly_ui():
            col_assembly.controls.clear()
            files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
            opts = [ft.dropdown.Option(f) for f in files]
            if not opts: col_assembly.controls.append(ft.Text("⚠️ DB vacía. Inyecta STLs en FILES.", color="#FFAB00"))
            
            for idx, p in enumerate(getattr(page, "assembly_parts", [])):
                df = ft.Dropdown(options=opts, value=p.get("file"), width=160, text_size=12, bgcolor="#0B0E14", color="#00E5FF")
                dm = ft.Dropdown(options=[ft.dropdown.Option("pla"), ft.dropdown.Option("petg"), ft.dropdown.Option("carbon"), ft.dropdown.Option("aluminum"), ft.dropdown.Option("wood"), ft.dropdown.Option("gold")], value=p.get("mat", "pla"), width=100, text_size=12, bgcolor="#0B0E14")
                
                def sl(k, l):
                    s = ft.Slider(min=-200, max=200, value=p.get(k, 0), expand=True)
                    def oc(e, key=k, part=p): part[key] = e.control.value; update_pbr_state()
                    s.on_change = oc
                    return ft.Row([ft.Text(l, size=10, color="#8B949E"), s])
                
                def onf(e, part=p): part["file"] = e.control.value; update_pbr_state()
                def onm(e, part=p): part["mat"] = e.control.value; update_pbr_state()
                def ond(e, i=idx): getattr(page, "assembly_parts").pop(i); render_assembly_ui(); update_pbr_state()
                
                df.on_change = onf; dm.on_change = onm
                card = ft.Container(content=ft.Column([
                    ft.Row([df, dm, ft.IconButton(ft.icons.DELETE, icon_color="red", on_click=ond)], alignment="spaceBetween"),
                    sl("x","X"), sl("y","Y"), sl("z","Z")
                ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#C51162"))
                col_assembly.controls.append(card)
            page.update()

        def add_assembly_part(e):
            if not hasattr(page, "assembly_parts"): page.assembly_parts = []
            files = [f for f in os.listdir(EXPORT_DIR) if f.lower().endswith('.stl') and f != "imported.stl"]
            page.assembly_parts.append({"file": files[0] if files else "", "mat": "pla", "x": 0, "y": 0, "z": 0})
            render_assembly_ui(); update_pbr_state()

        col_assembly = ft.Column(scroll="auto", expand=True)
        view_ensamble = ft.Column([
            ft.Text("🧩 MESA DE ENSAMBLAJE", size=20, color="#FFAB00", weight="bold"),
            ft.Text("Une múltiples STLs de la DB. Se reflejará instantáneamente en la pestaña PBR.", color="#8B949E", size=11),
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

        list_nexus_db = ft.ListView(height=220, spacing=5)

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
                    if ext in ["stl", "jscad"]: actions.insert(0, custom_icon_btn("▶️", lambda e, fp=p: load_file(fp), "Cargar"))
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
                status.value = f"✓ STL Inyectado en Memoria (Bypass Activado)"
            elif ext == "jscad": txt_code.value = open(filepath).read(); set_tab(0); status.value = "✓ Código Cargado"
            page.update()

        current_android_dir = ANDROID_ROOT
        tf_path = ft.TextField(value=current_android_dir, expand=True, bgcolor="#161B22", height=40, text_size=12)
        list_android = ft.ListView(height=350, spacing=5)

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
        # TAB 6: IA INTEGRADA
        # =========================================================
        ia_code = ft.TextField(multiline=True, expand=True, bgcolor="#161B22", color="#00E676", text_size=12, border_color="#8E24AA")
        def inject_ia_code(e):
            if ia_code.value.strip():
                txt_code.value = ia_code.value; txt_code.update()
                set_tab(2); run_render()
                status.value = "✓ Código IA Inyectado y Renderizado."; status.color = "#8E24AA"; page.update()
            else:
                status.value = "❌ Pega primero el código."; status.color = "red"; page.update()

        view_ia = ft.Column([
            ft.Text("🤖 ASISTENTE IA NEXUS", size=20, color="#8E24AA", weight="bold"),
            ft.Text("1. Ve al chat de Gemini (conmigo) y pídeme: 'Diseña el código JS-CSG de una caja de 50x50...'\n2. Pega el bloque de código que te doy aquí abajo.", color="#E6EDF3", size=11),
            ia_code,
            ft.ElevatedButton("🚀 INYECTAR Y RENDERIZAR EN 3D", on_click=inject_ia_code, bgcolor="#8E24AA", color="white", height=60, width=float('inf'))
        ], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            global PBR_STATE, LATEST_CODE_B64, LATEST_NEEDS_STL
            if idx in [0, 1, 2]: PBR_STATE["mode"] = "single"
            if idx == 3: render_assembly_ui()
            if idx == 5: refresh_nexus_db(); refresh_explorer(current_android_dir)
            main_container.content = [view_editor, view_constructor, view_visor, view_ensamble, view_pbr, view_archivos, view_ia][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🌐 PARAM", on_click=lambda _: set_tab(1), bgcolor="#FFAB00", color="black"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), bgcolor="#00E5FF", color="black"),
            ft.ElevatedButton("🧩 ENSAMBLE", on_click=lambda _: set_tab(3), bgcolor="#7CB342", color="white"),
            ft.ElevatedButton("🎨 PBR", on_click=lambda _: set_tab(4), bgcolor="#C51162", color="white"),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(5), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🤖 IA", on_click=lambda _: set_tab(6), bgcolor="#8E24AA", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        select_tool("planetario"); refresh_explorer(current_android_dir)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)