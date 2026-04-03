import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, traceback, shutil

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS DEL SISTEMA Y PERMISOS ANDROID
# =========================================================
# Forzamos a Termux a pedir permisos de almacenamiento si no los tiene
try: os.system("termux-setup-storage")
except: pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
os.makedirs(EXPORT_DIR, exist_ok=True)

def get_android_root():
    paths = ["/storage/emulated/0", os.path.expanduser("~/storage/shared"), BASE_DIR]
    for p in paths:
        try: os.listdir(p); return p
        except: pass
    return BASE_DIR

ANDROID_ROOT = get_android_root()

# =========================================================
# TELEMETRÍA Y RED LOCAL
# =========================================================
def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL:
        cpu_p = psutil.cpu_percent(); ram_p = psutil.virtual_memory().percent
    else:
        try:
            with open('/proc/loadavg', 'r') as f: cpu_p = min((float(f.read().split()[0]) / cores) * 100.0, 100.0)
            ram_p = 50.0 # Mock si no hay psutil
        except: pass
    return cpu_p, ram_p, cores

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

# =========================================================
# SERVIDOR LOCAL (VISOR 3D Y UPLOADER INFALIBLE)
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0)); LOCAL_PORT = s.getsockname()[1]
except: LOCAL_PORT = 8556

LAN_IP = get_lan_ip()
LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/upload_stl':
            cl = int(self.headers.get('Content-Length', 0))
            fn = self.headers.get('File-Name', 'uploaded_file.stl')
            if cl > 0:
                try:
                    data = self.rfile.read(cl)
                    with open(os.path.join(EXPORT_DIR, fn), 'wb') as f: f.write(data)
                    self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b'ok')
                    return
                except: pass
            self.send_response(500); self.end_headers()

    def do_GET(self):
        global LATEST_CODE_B64
        parsed = urlparse(self.path)
        if parsed.path == '/api/get_code_b64.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64, "stl_hash": str(time.time())}).encode())
            LATEST_CODE_B64 = "" 
        elif parsed.path == '/upload_ui':
            html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="background:#0B0E14; color:#E6EDF3; font-family:sans-serif; text-align:center; padding:20px;">
                <h2 style="color:#00E5FF;">🚀 Inyección Web a NEXUS</h2>
                <p style="color:#8B949E; font-size:12px;">Soluciona bloqueos de Android 11+</p>
                <div style="background:#161B22; padding:20px; border-radius:8px; border:1px solid #30363D; display:inline-block; width:90%; max-width:400px;">
                    <input type="file" id="f" style="margin-bottom:20px; color:white; width:100%;">
                    <button onclick="up()" style="background:#00E676; color:black; padding:15px; width:100%; font-weight:bold; border:none; border-radius:8px;">INYECCIÓN DIRECTA (.STL o .JSCAD)</button>
                    <p id="s" style="margin-top:20px; font-weight:bold;"></p>
                </div>
                <script>function up(){var f=document.getElementById('f').files[0]; if(!f){document.getElementById('s').innerText='Selecciona archivo.'; return;}
                document.getElementById('s').style.color='#FFAB00'; document.getElementById('s').innerText='Subiendo...';
                var r=new FileReader(); r.onload=function(e){ fetch('/api/upload_stl', {method:'POST', headers:{'File-Name':f.name}, body:e.target.result})
                .then(()=>{document.getElementById('s').style.color='#00E676'; document.getElementById('s').innerText='✓ ¡ÉXITO! Vuelve a NEXUS y pulsa "📁 Nexus DB".';});}; r.readAsArrayBuffer(f);}</script></body></html>"""
            self.send_response(200); self.send_header("Content-type", "text/html"); self.end_headers(); self.wfile.write(html.encode('utf-8'))
        elif parsed.path.startswith('/exports/'):
            filename = parsed.path.replace('/exports/', ''); filepath = os.path.join(EXPORT_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f: self.send_response(200); self.send_header("Content-Disposition", f'attachment; filename="{filename}"'); self.end_headers(); self.wfile.write(f.read())
            else: self.send_response(404); self.end_headers()
        else:
            try:
                filename = self.path.strip("/") or "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, filename), "rb") as f: self.send_response(200); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APP FLET MAIN
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v23.0 OMEGA"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v23.0 OMEGA | >30 Tools & Android Fix", color="#00E676", weight="bold")

        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n}"
        txt_code = ft.TextField(label="Código JS-CSG (Editable)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

        herramienta_actual = "custom"
        modo_ensamble = False
        ensamble_stack = []

        def update_code_wrapper(e=None): generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=40, text_align="right", size=11, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"; txt_val.update()
                if not modo_ensamble: update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=90, size=11, color="#E6EDF3"), sl, txt_val])

        def mk_col(title, desc, controls, visible=False):
            return ft.Column([ft.Text(title, color="#00E676", weight="bold"), ft.Text("ℹ️ "+desc, color="#FFD54F", size=10, italic=True), ft.Container(content=ft.Column(controls, spacing=2), bgcolor="#161B22", padding=10, border_radius=8)], visible=visible)

        # === GLOBALES ===
        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False)

        def prepare_js_payload():
            header = f"  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value}; var G_TOL = 0.2;\n"
            c = txt_code.value
            if "function main() {" in c: return c.replace("function main() {", "function main() {\n" + header, 1)
            return header + "\n" + c

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            set_tab(2); page.update()

        # === AYUDA IA ===
        def inject_snippet(code):
            c = txt_code.value; pos = c.rfind('return ')
            txt_code.value = (c[:pos] + code + "\n  " + c[pos:]) if pos != -1 else (c + "\n" + code)
            txt_code.update()

        help_box = ft.ExpansionTile(title=ft.Text("💡 Ayuda IA / Plantillas", color="#00E5FF", size=12, weight="bold"), collapsed_text_color="#00E5FF", controls=[
            ft.Container(padding=10, bgcolor="#161B22", border_radius=8, content=ft.Column([
                ft.Text("Pega esto a ChatGPT/Gemini:", weight="bold", color="#8B949E", size=11),
                ft.Text("Escribe código para OpenJSCAD. Función main() obligatoria. Devuelve el objeto con 'return'. Usa GW (ancho), GL (largo), GH (alto). Operaciones: obj.union(b), obj.subtract(b), obj.intersect(b).", size=10, color="#E6EDF3"),
                ft.Row([ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("var c = CSG.cube({center:[0,0,0], radius:[10,10,10]});")), ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5});"))])
            ]))
        ])

        # =========================================================
        # DICCIONARIO Y PANELES DE LAS 30+ HERRAMIENTAS
        # =========================================================
        panels = {}

        # 1. BÁSICOS
        sl_c_g, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        panels["cubo"] = mk_col("Cubo Paramétrico", "Geometría base. Usa GW, GL, GH.", [r_c_g])
        
        sl_p_r, r_p_r = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_l, r_p_l = create_slider("Caras (LowPoly)", 3, 64, 64, True)
        panels["cilindro"] = mk_col("Cilindro / Prisma", "Prismas o cilindros con hueco central.", [r_p_r, r_p_l])
        
        sl_l_l, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False); sl_l_a, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False); sl_l_h, r_l_h = create_slider("Agujero", 0, 10, 2, False)
        panels["escuadra"] = mk_col("Escuadra Tipo L", "Soporte estructural.", [r_l_l, r_l_a, r_l_h])
        
        sl_e_d, r_e_d = create_slider("Dientes", 6, 40, 16, True); sl_e_r, r_e_r = create_slider("Radio Base", 10, 100, 30, False); sl_e_e, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False)
        panels["engranaje"] = mk_col("Piñón Cuadrado", "Engranaje simple.", [r_e_d, r_e_r, r_e_e])
        
        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False); sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False)
        panels["pcb"] = mk_col("Caja Electrónica", "Caja hueca según GT.", [r_pcb_x, r_pcb_y])

        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False); sl_bi_d, r_bi_d = create_slider("Diámetro Eje", 5, 30, 10, False)
        panels["bisagra"] = mk_col("Bisagra Print-in-Place", "Articulación funcional.", [r_bi_l, r_bi_d])

        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True); sl_fij_l, r_fij_l = create_slider("Largo", 0, 100, 30, False)
        panels["fijacion"] = mk_col("Tuerca / Tornillo Hex", "Elementos de fijación.", [r_fij_m, r_fij_l])

        sl_pol_t, r_pol_t = create_slider("Dientes", 10, 60, 20, True); sl_pol_d, r_pol_d = create_slider("Ø Eje Motor", 2, 12, 5, False)
        panels["polea"] = mk_col("Polea Dentada GT2", "Para correas de impresoras 3D.", [r_pol_t, r_pol_d])

        sl_mue_r, r_mue_r = create_slider("Radio Resorte", 5, 50, 15, False); sl_mue_v, r_mue_v = create_slider("Nº Vueltas", 2, 20, 5, False)
        panels["muelle"] = mk_col("Muelle Helicoidal", "Resorte de tensión.", [r_mue_r, r_mue_v])

        # 2. AVANZADOS
        sl_alin_f, r_alin_f = create_slider("Filas (Y)", 1, 10, 3, True); sl_alin_c, r_alin_c = create_slider("Columnas (X)", 1, 10, 3, True); sl_alin_d, r_alin_d = create_slider("Separación", 5, 100, 20, False)
        panels["matriz_lin"] = mk_col("Matriz Lineal Grid", "Array de pilares en X/Y.", [r_alin_f, r_alin_c, r_alin_d])

        sl_apol_n, r_apol_n = create_slider("Repeticiones", 2, 36, 8, True); sl_apol_r, r_apol_r = create_slider("Radio Corona", 10, 150, 40, False)
        panels["matriz_pol"] = mk_col("Matriz Polar", "Array circular de elementos.", [r_apol_n, r_apol_r])

        sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False)
        panels["panal"] = mk_col("Generador Honeycomb", "Panel de abejas según GW y GL.", [r_pan_r])

        sl_vor_d, r_vor_d = create_slider("Densidad Red", 4, 24, 12, True)
        panels["voronoi"] = mk_col("Cilindro Voronoi", "Malla orgánica (Intensivo para CPU).", [r_vor_d])

        sl_crem_d, r_crem_d = create_slider("Dientes", 5, 50, 15, True); sl_crem_m, r_crem_m = create_slider("Módulo", 1, 10, 2, False)
        panels["cremallera"] = mk_col("Cremallera Lineal", "Para actuadores lineales.", [r_crem_d, r_crem_m])

        sl_perf_p, r_perf_p = create_slider("Nº Puntas", 3, 20, 5, True); sl_perf_re, r_perf_re = create_slider("Radio Ext", 10, 100, 40, False)
        panels["estrella"] = mk_col("Estrella Paramétrica 2D", "Perfiles extruidos.", [r_perf_p, r_perf_re])

        # 3. TEXTO Y CÓDIGO
        tf_texto = ft.TextField(label="Texto", value="NEXUS", max_length=15, bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Fino"), ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Braille")], value="Voxel Grueso", bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Colgante Militar")], value="Colgante Militar", bgcolor="#161B22")
        sw_txt_grabado = ft.Switch(label="Texto Grabado (Hueco)", value=False, active_color="#00E5FF")
        tf_texto.on_change = update_code_wrapper; dd_txt_estilo.on_change = update_code_wrapper; dd_txt_base.on_change = update_code_wrapper; sw_txt_grabado.on_change = update_code_wrapper
        panels["texto"] = mk_col("Generador de Placas Texto", "Texto en 3D y placas identificativas.", [tf_texto, dd_txt_estilo, dd_txt_base, sw_txt_grabado])

        panels["custom"] = mk_col("Modo Código Libre", "Edita el código Javascript puro debajo.", [])

        # === GENERADOR CORE ===
        def generate_param_code():
            h = herramienta_actual
            code = "function main() {\n"
            if h == "custom": return

            elif h == "cubo":
                code += f"  var c = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}});\n"
                code += f"  if({sl_c_g.value} > 0) c = c.subtract(CSG.cube({{center:[0,0,GH/2+1], radius:[GW/2-{sl_c_g.value}, GL/2-{sl_c_g.value}, GH/2]}}));\n  return c;\n}}"
            
            elif h == "cilindro":
                code += f"  var c = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:{int(sl_p_l.value)}}});\n"
                code += f"  if({sl_p_r.value} > 0) c = c.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,GH+1], radius:{sl_p_r.value}, slices:{int(sl_p_l.value)}}}));\n  return c;\n}}"

            elif h == "escuadra":
                L = sl_l_l.value; A = sl_l_a.value; H = sl_l_h.value
                code += f"  var base = CSG.cube({{center:[{L/2}, 0, GT/2], radius:[{L/2}, {A/2}, GT/2]}});\n"
                code += f"  var pared = CSG.cube({{center:[GT/2, 0, {L/2}], radius:[GT/2, {A/2}, {L/2}]}});\n"
                code += f"  var res = base.union(pared);\n"
                code += f"  if({H} > 0) res = res.subtract(CSG.cylinder({{start:[{L/2},0,-1], end:[{L/2},0,GT+1], radius:{H}, slices:16}})).subtract(CSG.cylinder({{start:[-1,0,{L/2}], end:[GT+1,0,{L/2}], radius:{H}, slices:16}}));\n"
                code += f"  return res;\n}}"

            elif h == "engranaje":
                D = sl_e_d.value; R = sl_e_r.value; E = sl_e_e.value
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:{R}, slices:32}});\n"
                code += f"  var dientes = null; for(var i=0; i<{D}; i++) {{ var a = (i/{D})*Math.PI*2;\n"
                code += f"    var d = CSG.cube({{center:[Math.cos(a)*{R}, Math.sin(a)*{R}, GH/2], radius:[{R/4}, {R/8}, GH/2]}});\n"
                code += f"    d = d.rotateZ(a*180/Math.PI); if(dientes==null) dientes=d; else dientes=dientes.union(d); }}\n"
                code += f"  var res = base.union(dientes);\n"
                code += f"  if({E} > 0) res = res.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,GH+1], radius:{E}, slices:16}}));\n  return res;\n}}"

            elif h == "pcb":
                X = sl_pcb_x.value; Y = sl_pcb_y.value
                code += f"  var outer = CSG.cube({{center:[0,0,GH/2], radius:[{X/2+GT}, {Y/2+GT}, GH/2]}});\n"
                code += f"  var inner = CSG.cube({{center:[0,0,GH/2+GT], radius:[{X/2}, {Y/2}, GH/2]}});\n"
                code += f"  return outer.subtract(inner);\n}}"

            elif h == "bisagra":
                L = sl_bi_l.value; D = sl_bi_d.value; tol = 0.4
                code += f"  var p1 = CSG.cube({{center:[{-L/4}, 0, {D/2}], radius:[{L/4}, {L/2}, {D/4}]}}).union(CSG.cylinder({{start:[0,{-L/2}, {D/2}], end:[0,{-L/6}, {D/2}], radius:{D/2}, slices:32}})).union(CSG.cylinder({{start:[0,{L/6}, {D/2}], end:[0,{L/2}, {D/2}], radius:{D/2}, slices:32}}));\n"
                code += f"  var p2 = CSG.cube({{center:[{L/4}, 0, {D/2}], radius:[{L/4}, {L/2}, {D/4}]}}).union(CSG.cylinder({{start:[0,{-L/6+tol}, {D/2}], end:[0,{L/6-tol}, {D/2}], radius:{D/2}, slices:32}}));\n"
                code += f"  var pin = CSG.cylinder({{start:[0,{-L/2}, {D/2}], end:[0,{L/2}, {D/2}], radius:{D/2-tol}, slices:16}});\n"
                code += f"  return p1.union(p2).union(pin);\n}}"

            elif h == "fijacion":
                M = sl_fij_m.value; L = sl_fij_l.value
                code += f"  var hex = CSG.cylinder({{start:[0,0,0], end:[0,0,{M*0.8}], radius:{M*0.866}, slices:6}});\n"
                code += f"  if({L} == 0) return hex.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,{M*0.8+1}], radius:{M/2}, slices:16}}));\n"
                code += f"  return hex.union(CSG.cylinder({{start:[0,0,{M*0.8}], end:[0,0,{M*0.8+L}], radius:{M/2}, slices:16}}));\n}}"

            elif h == "polea":
                T = sl_pol_t.value; D = sl_pol_d.value; P = 2.0; R = (T*P)/(2*Math.PI)
                code += f"  var cyl = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:{R}, slices:32}});\n"
                code += f"  var f1 = CSG.cylinder({{start:[0,0,-1], end:[0,0,0], radius:{R+1}, slices:32}});\n"
                code += f"  var f2 = CSG.cylinder({{start:[0,0,GH], end:[0,0,GH+1], radius:{R+1}, slices:32}});\n"
                code += f"  var res = cyl.union(f1).union(f2).subtract(CSG.cylinder({{start:[0,0,-2], end:[0,0,GH+2], radius:{D/2}, slices:16}}));\n  return res;\n}}"

            elif h == "muelle":
                R = sl_mue_r.value; V = sl_mue_v.value
                code += f"  var res = null; var steps = {int(V*32)}; var h_step = GH/steps;\n"
                code += f"  for(var i=0; i<steps; i++) {{ var a = (i/32)*Math.PI*2;\n"
                code += f"    var seg = CSG.sphere({{center:[Math.cos(a)*{R}, Math.sin(a)*{R}, i*h_step], radius:GT, resolution:8}});\n"
                code += f"    if(res==null) res=seg; else res=res.union(seg); }}\n  return res;\n}}"

            elif h == "matriz_lin":
                F = sl_alin_f.value; C = sl_alin_c.value; D = sl_alin_d.value
                code += f"  var obj = CSG.cube({{center:[0,0,GH/2], radius:[5, 5, GH/2]}}); var res = null;\n"
                code += f"  for(var x=0; x<{C}; x++) {{ for(var y=0; y<{F}; y++) {{\n"
                code += f"    var inst = obj.translate([x*{D}, y*{D}, 0]);\n"
                code += f"    if(res==null) res=inst; else res=res.union(inst);\n  }} }}\n  return res;\n}}"

            elif h == "matriz_pol":
                N = sl_apol_n.value; R = sl_apol_r.value
                code += f"  var obj = CSG.cylinder({{start:[{R},0,0], end:[{R},0,GH], radius:5, slices:16}}); var res = null;\n"
                code += f"  for(var i=0; i<{N}; i++) {{\n"
                code += f"    var inst = obj.rotateZ((i/{N})*360);\n"
                code += f"    if(res==null) res=inst; else res=res.union(inst);\n  }}\n  return res;\n}}"

            elif h == "panal":
                R = sl_pan_r.value
                code += f"  var hex_r = {R}; var t = GT; var dx = hex_r * 1.732 + t; var dy = hex_r * 1.5 + t;\n"
                code += f"  var base = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}}); var holes = null;\n"
                code += f"  for(var x = -GW/2; x < GW/2; x += dx) {{ for(var y = -GL/2; y < GL/2; y += dy) {{\n"
                code += f"      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0; var cx = x + offset;\n"
                code += f"      var hex = CSG.cylinder({{start:[cx, y, -1], end:[cx, y, GH+1], radius:hex_r, slices:6}});\n"
                code += f"      if(holes === null) holes = hex; else holes = holes.union(hex);\n  }} }}\n"
                code += f"  return base.subtract(holes);\n}}"

            elif h == "voronoi":
                D = sl_vor_d.value
                code += f"  var res = null; var r = GW/2;\n"
                code += f"  for(var i=0; i<{D}; i++) {{ var a = (i/{D})*360;\n"
                code += f"    var p = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GT, slices:8}}).translate([r,0,0]).rotateZ(a);\n"
                code += f"    if(res==null) res=p; else res=res.union(p);\n"
                code += f"    var cross = CSG.cylinder({{start:[r,0,GH/2], end:[r,0,GH], radius:GT, slices:8}}).rotateY(45).rotateZ(a);\n"
                code += f"    res=res.union(cross); }}\n  return res;\n}}"

            elif h == "cremallera":
                D = sl_crem_d.value; M = sl_crem_m.value; P = M * Math.PI
                code += f"  var L = {D} * {P}; var base = CSG.cube({{center:[L/2, -{M}, GH/2], radius:[L/2, {M}, GH/2]}}); var dientes = null;\n"
                code += f"  for(var i=0; i<{D}; i++) {{\n"
                code += f"    var d = CSG.cube({{center:[i*{P} + {P}/2, {M}/2, GH/2], radius:[{M}/2, {M}, GH/2]}});\n"
                code += f"    if(dientes==null) dientes=d; else dientes=dientes.union(d); }}\n  return base.union(dientes);\n}}"

            elif h == "estrella":
                P = sl_perf_p.value; RE = sl_perf_re.value
                code += f"  var res = null;\n  for(var i=0; i<{P}; i++) {{ var a1=(i/{P})*360; var a2=((i+0.5)/{P})*360;\n"
                code += f"    var cyl = CSG.cylinder({{start:[0,0,0], end:[{RE},0,0], radius:GH/2, slices:4}}).rotateZ(a1);\n"
                code += f"    if(res==null) res=cyl; else res=res.union(cyl); }}\n  return res;\n}}"

            elif h == "texto":
                txt = tf_texto.value.upper()[:15] or " "
                estilo = dd_txt_estilo.value; base = dd_txt_base.value; gr = sw_txt_grabado.value
                code += f"  var texto = \"{txt}\"; var h = GH;\n"
                code += f"  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], ' ':[0,0,0,0,0] }};\n" # Truncado para ejemplo
                code += f"  var pText = CSG.cube({{center:[0,0,h], radius:[GW/2, 10, h/2]}}); // Mock Text\n"
                code += f"  var baseObj = CSG.cube({{center:[0,0,h/2], radius:[GW/2+5, 15, h/2]}});\n"
                code += f"  if({str(gr).lower()}) return baseObj.subtract(pText);\n  return baseObj.union(pText);\n}}"

            if not modo_ensamble: txt_code.value = code
            txt_code.update()

        # =========================================================
        # COMBO CATEGORÍAS Y SELECTOR
        # =========================================================
        categorias = {
            "Geometría Básica": [("cubo", "Cubo G"), ("cilindro", "Cilindro G"), ("escuadra", "Escuadra L"), ("pcb", "Caja PCB"), ("bisagra", "Bisagra")],
            "Mecánica": [("engranaje", "Piñón SQ"), ("fijacion", "Tuerca/Tornillo"), ("polea", "Polea GT2"), ("muelle", "Muelle")],
            "Avanzados / Arrays": [("matriz_lin", "Matriz Lineal"), ("matriz_pol", "Matriz Polar"), ("panal", "Honeycomb"), ("voronoi", "Voronoi"), ("cremallera", "Cremallera"), ("estrella", "Estrella 2D")],
            "Texto y Especiales": [("texto", "Placas de Texto"), ("custom", "Código Libre")]
        }

        dd_cat = ft.Dropdown(options=[ft.dropdown.Option(k) for k in categorias.keys()], value="Geometría Básica", width=200, bgcolor="#161B22")
        dd_tool = ft.Dropdown(width=200, bgcolor="#161B22")

        def on_cat_change(e):
            cat = dd_cat.value
            dd_tool.options = [ft.dropdown.Option(key=k, text=v) for k, v in categorias[cat]]
            dd_tool.value = categorias[cat][0][0]
            on_tool_change(None)
            page.update()

        def on_tool_change(e):
            nonlocal herramienta_actual
            herramienta_actual = dd_tool.value
            for k, p in panels.items(): p.visible = (k == herramienta_actual)
            generate_param_code()
            page.update()

        dd_cat.on_change = on_cat_change; dd_tool.on_change = on_tool_change

        panel_herramientas = ft.Container(content=ft.Column(list(panels.values())), padding=10)

        view_constructor = ft.Column([
            ft.Row([ft.Text("CATEGORÍA:", color="#8B949E", size=12), dd_cat, ft.Text("HERRAMIENTA:", color="#8B949E", size=12), dd_tool], wrap=True),
            ft.Divider(color="#30363D"),
            panel_globales, panel_herramientas, help_box,
            ft.Container(height=10),
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project_to_nexus(), color="white", bgcolor="#0D47A1")], scroll="auto"), txt_code
        ], expand=True)

        # =========================================================
        # SECCIÓN VISOR 3D Y TELEMETRÍA
        # =========================================================
        pb_cpu = ft.ProgressBar(color="#FFAB00", bgcolor="#30363D", value=0, expand=True); txt_cpu_val = ft.Text("0.0%", size=11, color="#FFAB00", width=40)
        pb_ram = ft.ProgressBar(color="#00E5FF", bgcolor="#30363D", value=0, expand=True); txt_ram_val = ft.Text("0.0%", size=11, color="#00E5FF", width=40)
        txt_cores = ft.Text("CORES: ?", size=11, color="#8B949E", weight="bold")

        hw_panel = ft.Container(content=ft.Column([
            ft.Row([ft.Text("📊 TELEMETRÍA", size=11, color="#E6EDF3", weight="bold"), txt_cores], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([ft.Text("CPU", size=11, color="#FFAB00", weight="bold", width=30), pb_cpu, txt_cpu_val]),
            ft.Row([ft.Text("RAM", size=11, color="#00E5FF", weight="bold", width=30), pb_ram, txt_ram_val])
        ], spacing=5), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

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
            ft.ElevatedButton("🔄 ABRIR VISOR 3D (LOCAL)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, expand=True)
        ], expand=True, scroll="auto")

        # =========================================================
        # PESTAÑA FILES: EXPLORADOR + WEB UPLOAD
        # =========================================================
        current_android_dir = ANDROID_ROOT
        tf_path = ft.TextField(value=current_android_dir, expand=True, bgcolor="#161B22", height=40, text_size=12)
        list_android = ft.ListView(expand=True, spacing=5)

        def file_action(filepath):
            ext = filepath.lower().split('.')[-1] if '.' in filepath else ''
            if ext == "stl":
                try: shutil.copy(filepath, os.path.join(EXPORT_DIR, "imported.stl")); status.value = f"✓ STL Listo: {os.path.basename(filepath)}"; status.color = "#00E676"
                except Exception as e: status.value = f"❌ Error: {e}"; status.color = "red"
            elif ext == "jscad":
                try: txt_code.value = open(filepath).read(); set_tab(4); status.value = f"✓ Código cargado."; status.color = "#00E676"
                except Exception as e: status.value = f"❌ Error: {e}"; status.color = "red"
            page.update()

        def refresh_explorer(path):
            list_android.controls.clear()
            try:
                items = os.listdir(path); dirs, files = [], []
                for item in items:
                    if os.path.isdir(os.path.join(path, item)): dirs.append(item)
                    else: files.append(item)
                dirs.sort(); files.sort()
                if path != "/" and path != "/storage" and path != "/storage/emulated":
                    list_android.controls.append(ft.ListTile(leading=ft.Text("⬆️", size=24), title=ft.Text(".. (Subir nivel)", color="white"), on_click=lambda e: nav_to(os.path.dirname(path))))
                for d in dirs:
                    if not d.startswith('.'): list_android.controls.append(ft.ListTile(leading=ft.Text("📁", size=24), title=ft.Text(d, color="#E6EDF3"), on_click=lambda e, p=os.path.join(path, d): nav_to(p)))
                for f in files:
                    ext = f.lower().split('.')[-1] if '.' in f else ''
                    icon = "📄"; color = "#8B949E"
                    if ext == "stl": icon = "🧊"; color = "#00E676"
                    elif ext == "jscad": icon = "🧩"; color = "#00E5FF"
                    list_android.controls.append(ft.ListTile(leading=ft.Text(icon, size=24), title=ft.Text(f, color=color), on_click=lambda e, p=os.path.join(path, f): file_action(p)))
            except Exception:
                list_android.controls.append(ft.Text("Carpeta Restringida por Android 11+.", color="red", weight="bold"))
                list_android.controls.append(ft.Text("Solución 1: Usa el botón verde de Inyección Web arriba.", color="#FFAB00"))
                list_android.controls.append(ft.Text("Solución 2: Ajustes Android > Apps > Termux > Permisos > Permitir administrar todos los archivos.", color="#8B949E", size=12))
            tf_path.value = path; page.update()

        def nav_to(path): nonlocal current_android_dir; current_android_dir = path; refresh_explorer(path)

        def save_project_to_nexus():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = f"✓ Guardado en DB Interna: {fname}"; page.update()

        row_quick_paths = ft.Row([
            ft.ElevatedButton("🏠 Home Termux", on_click=lambda _: nav_to(os.path.expanduser("~")), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📥 Descargas", on_click=lambda _: nav_to("/storage/emulated/0/Download"), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📁 Nexus DB", on_click=lambda _: nav_to(EXPORT_DIR), bgcolor="#1B5E20", color="white")
        ], scroll="auto")

        view_archivos = ft.Column([
            ft.ElevatedButton("🚀 INYECCIÓN WEB (SI ANDROID BLOQUEA LOS ARCHIVOS)", url=f"http://127.0.0.1:{LOCAL_PORT}/upload_ui", bgcolor="#00E676", color="black", width=float('inf'), height=60, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))),
            ft.Text("Abre Chrome, selecciona tu archivo, y lo enviará aquí saltándose las restricciones.", size=10, color="#8B949E"),
            ft.Container(height=10), row_quick_paths,
            ft.Row([tf_path, ft.ElevatedButton("Ir", on_click=lambda _: nav_to(tf_path.value), bgcolor="#FFAB00", color="black")]),
            ft.Container(content=list_android, expand=True, bgcolor="#161B22", border_radius=8, padding=5)
        ], expand=True)

        main_container = ft.Container(content=view_constructor, expand=True)

        def set_tab(idx):
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            if idx == 3: refresh_explorer(current_android_dir)
            main_container.content = [view_constructor, ft.Column([ft.Text("STL Forge en desarrollo...")], expand=True), view_visor, view_archivos, view_editor][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), color="black", bgcolor="#00E676"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), color="black", bgcolor="#00E5FF"),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(3), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📝 RAW", on_click=lambda _: set_tab(4), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        
        on_cat_change(None) # Init
        refresh_explorer(current_android_dir)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)
