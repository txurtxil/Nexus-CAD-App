import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, traceback, shutil
from urllib.parse import urlparse, unquote

try: import psutil; HAS_PSUTIL = True
except ImportError: HAS_PSUTIL = False

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# CONFIGURACIÓN DE RUTAS Y SERVIDOR (BASE 20.5)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_db")
os.makedirs(EXPORT_DIR, exist_ok=True)

def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL:
        cpu_p = psutil.cpu_percent(); ram_p = psutil.virtual_memory().percent
    return cpu_p, ram_p, cores

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0)); LOCAL_PORT = s.getsockname()[1]
except: LOCAL_PORT = 8556

LAN_IP = get_lan_ip()
LATEST_CODE_B64 = ""

# =========================================================
# SERVIDOR WEB (WEB INJECTION CORS FIX & STL FANTASMA)
# =========================================================
class NexusHandler(http.server.BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, File-Name")

    def do_OPTIONS(self):
        self.send_response(200); self._send_cors(); self.end_headers()

    def do_POST(self):
        if self.path == '/api/upload':
            cl = int(self.headers.get('Content-Length', 0))
            fn = unquote(self.headers.get('File-Name', 'uploaded_file.stl'))
            if cl > 0:
                try:
                    with open(os.path.join(EXPORT_DIR, fn), 'wb') as f:
                        f.write(self.rfile.read(cl))
                    self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(b'ok'); return
                except Exception as e: print(f"Error: {e}")
            self.send_response(500); self._send_cors(); self.end_headers()

    def do_GET(self):
        global LATEST_CODE_B64
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/get_code_b64.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self._send_cors(); self.end_headers()
            stl_path = os.path.join(EXPORT_DIR, "imported.stl")
            stl_hash = str(os.path.getmtime(stl_path)) if os.path.exists(stl_path) else "0"
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64, "stl_hash": stl_hash}).encode())
            LATEST_CODE_B64 = "" 

        elif parsed.path == '/imported.stl':
            filepath = os.path.join(EXPORT_DIR, "imported.stl")
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.send_response(200); self.send_header("Content-type", "application/sla"); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            else: 
                # FIX: STL Fantasma para evitar el error [object ProgressEvent] en el Visor 3D
                self.send_response(200); self.send_header("Content-type", "application/sla"); self._send_cors(); self.end_headers()
                self.wfile.write(b"solid dummy\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid dummy\n")

        elif parsed.path == '/upload_ui':
            html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta charset="UTF-8"></head>
            <body style="background:#0B0E14; color:#E6EDF3; font-family:sans-serif; text-align:center; padding:20px;">
                <h2 style="color:#00E676;">🚀 INYECCIÓN WEB NEXUS</h2>
                <div style="background:#161B22; padding:20px; border-radius:8px; border:1px solid #30363D; display:inline-block; width:90%; max-width:400px;">
                    <input type="file" id="f" style="margin-bottom:20px; color:white; width:100%;">
                    <button onclick="up()" style="background:#00E5FF; color:black; padding:15px; width:100%; font-weight:bold; border:none; border-radius:8px; cursor:pointer;">INYECTAR ARCHIVO</button>
                    <p id="s" style="margin-top:20px; font-weight:bold;"></p>
                </div>
                <script>function up(){var f=document.getElementById('f').files[0]; if(!f)return;
                document.getElementById('s').style.color='#FFAB00'; document.getElementById('s').innerText='Inyectando...';
                fetch('/api/upload', {method:'POST', headers:{'File-Name':encodeURIComponent(f.name)}, body:f})
                .then(r => { if(r.ok){ document.getElementById('s').style.color='#00E676'; document.getElementById('s').innerText='✓ ¡ÉXITO! Vuelve a la App y pulsa REFRESCAR.'; } else { throw 'Error'; } })
                .catch(e => { document.getElementById('s').style.color='red'; document.getElementById('s').innerText='❌ Error de red'; });}</script></body></html>"""
            self.send_response(200); self.send_header("Content-type", "text/html"); self._send_cors(); self.end_headers(); self.wfile.write(html.encode('utf-8'))
            
        elif parsed.path.startswith('/descargar/'):
            filename = unquote(parsed.path.replace('/descargar/', ''))
            filepath = os.path.join(EXPORT_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.send_response(200); self.send_header("Content-Disposition", f'attachment; filename="{filename}"'); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            else: self.send_response(404); self._send_cors(); self.end_headers()
            
        else:
            try:
                fn = self.path.strip("/") or "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, fn), "rb") as f: self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self._send_cors(); self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# LÓGICA DE LA APLICACIÓN FLET (ESTILO 20.5)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v26.3 PRO"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v26.3 PRO | Rollback Estable", color="#00E676", weight="bold")
        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n}"
        txt_code = ft.TextField(multiline=True, min_lines=10, max_lines=20, value=T_INICIAL, bgcolor="#0B0E14", color="#58A6FF", border_color="#30363D", text_size=12)

        herramienta_actual = "custom"
        dd_tool = None # Placeholder para el dropdown dinámico

        def update_code_wrapper(e=None):
            generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int=False):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=40, text_align="right", size=11, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int:
                sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                page.update()
                update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=90, size=11, color="#E6EDF3"), sl, txt_val])

        def mk_col(title, desc, controls, visible=False):
            return ft.Column([
                ft.Text(title, color="#00E676", weight="bold"), 
                ft.Text("ℹ️ "+desc, color="#FFD54F", size=10, italic=True), 
                ft.Container(content=ft.Column(controls, spacing=2), bgcolor="#161B22", padding=10, border_radius=8)
            ], visible=visible)

        # === GLOBALES ===
        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2)

        panel_globales = ft.Container(content=ft.Column([
            ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11),
            r_g_w, r_g_l, r_g_h, r_g_t
        ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        # =========================================================
        # CATEGORÍAS Y HERRAMIENTAS
        # =========================================================
        panels = {}

        # 1. BÁSICAS (Restauradas)
        sl_c_g, r_c_g = create_slider("Vaciado Pared", 0, 20, 0)
        panels["cubo"] = mk_col("Cubo Paramétrico", "Base sólida o hueca.", [r_c_g])
        sl_p_r, r_p_r = create_slider("Radio Hueco", 0, 95, 15)
        panels["cilindro"] = mk_col("Cilindro / Prisma", "Cuerpos de revolución.", [r_p_r])

        # 2. ULTIMATE STL FORGE (Las 10 herramientas pedidas)
        lbl_stl_status = ft.Text("No hay STL en memoria.", color="#8B949E", size=11)
        sl_stl_sc, r_stl_sc = create_slider("Escala (%)", 1, 500, 100, True)
        sl_stl_x, r_stl_x = create_slider("Mover X", -200, 200, 0)
        sl_stl_y, r_stl_y = create_slider("Mover Y", -200, 200, 0)
        sl_stl_z, r_stl_z = create_slider("Mover Z", -200, 200, 0)
        
        panel_stl_transform = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🔄 TRANSFORMACIÓN BASE STL", color="#00E676", weight="bold"), lbl_stl_status]),
            ft.ElevatedButton("📂 IR A FILES (IMPORTAR STL)", on_click=lambda _: set_tab(2), bgcolor="#00E5FF", color="black", width=float('inf')),
            r_stl_sc, r_stl_x, r_stl_y, r_stl_z
        ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"), visible=False)

        panels["stl"] = mk_col("Visor STL", "Muestra el archivo cargado tal cual.", [])
        
        sl_stlf_z, r_stlf_z = create_slider("Corte Z (mm)", 0, 50, 1)
        panels["stl_flatten"] = mk_col("Aplanar Base (Flatten)", "Corta la parte inferior para adherencia.", [r_stlf_z])
        
        dd_stls_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E")
        dd_stls_axis.on_change = update_code_wrapper
        sl_stls_pos, r_stls_pos = create_slider("Punto Corte", -150, 150, 0)
        panels["stl_split"] = mk_col("Cortador Avanzado (Split)", "Guillotina en cualquier eje.", [dd_stls_axis, r_stls_pos])
        
        sl_stlc_s, r_stlc_s = create_slider("Caja Tamaño", 10, 300, 50)
        panels["stl_crop"] = mk_col("Aislar (Crop Box)", "Elimina todo lo que quede fuera.", [r_stlc_s])
        
        dd_stld_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E")
        dd_stld_axis.on_change = update_code_wrapper
        sl_stld_r, r_stld_r = create_slider("Radio (M3=1.6)", 0.5, 20, 1.6)
        sl_stld_px, r_stld_px = create_slider("Pos 1", -150, 150, 0)
        sl_stld_py, r_stld_py = create_slider("Pos 2", -150, 150, 0)
        panels["stl_drill"] = mk_col("Taladro 3D Universal", "Perforación infinita.", [dd_stld_axis, r_stld_r, r_stld_px, r_stld_py])
        
        sl_stlm_w, r_stlm_w = create_slider("Ancho Orejeta", 10, 100, 40)
        sl_stlm_d, r_stlm_d = create_slider("Separación", 20, 200, 80)
        panels["stl_mount"] = mk_col("Orejetas Montaje (Screw Tabs)", "Anclajes laterales atornillables.", [r_stlm_w, r_stlm_d])
        
        sl_stle_r, r_stle_r = create_slider("Radio Disco", 5, 30, 15)
        sl_stle_d, r_stle_d = create_slider("Apertura XY", 10, 200, 50)
        panels["stl_ears"] = mk_col("Discos Anti-Warping", "Parches de 0.4mm en esquinas.", [r_stle_r, r_stle_d])
        
        sl_stlp_sx, r_stlp_sx = create_slider("Largo Parche", 5, 100, 20)
        sl_stlp_sy, r_stlp_sy = create_slider("Ancho Parche", 5, 100, 20)
        sl_stlp_sz, r_stlp_sz = create_slider("Alto Parche", 1, 50, 5)
        panels["stl_patch"] = mk_col("Parche de Refuerzo", "Fusiona un bloque sólido para reparar.", [r_stlp_sx, r_stlp_sy, r_stlp_sz])

        sl_stlh_r, r_stlh_r = create_slider("Tamaño Hex", 2, 20, 5)
        panels["stl_honeycomb"] = mk_col("Aligerado Honeycomb", "Resta panel de abejas al modelo.", [r_stlh_r])

        sl_stlp_r, r_stlp_r = create_slider("Radio Hélice", 10, 100, 40)
        sl_stlp_t, r_stlp_t = create_slider("Grosor Aro", 1, 10, 3)
        sl_stlp_x, r_stlp_rx = create_slider("Centro X", -100, 100, 0)
        sl_stlp_y, r_stlp_ry = create_slider("Centro Y", -100, 100, 0)
        panels["stl_propguard"] = mk_col("Protector de Hélice", "Fusiona un aro protector cilíndrico.", [r_stlp_r, r_stlp_t, r_stlp_rx, r_stlp_ry])

        # 3. TEXTO Y LLAVEROS (Añadido)
        tf_texto = ft.TextField(label="Contenido Texto", value="NEXUS", max_length=15, bgcolor="#1E1E1E")
        sw_txt_grabado = ft.Switch(label="Modo Hueco (Grabado)", value=False, active_color="#00E5FF")
        tf_texto.on_change = update_code_wrapper; sw_txt_grabado.on_change = update_code_wrapper
        panels["texto"] = mk_col("Generador de Texto 3D", "Llaveros y placas identificativas.", [tf_texto, sw_txt_grabado])

        panels["custom"] = mk_col("Código Libre RAW", "Edita el código fuente directamente.", [])

        # === GENERADOR JAVASCRIPT CON HÍBRIDO MULTI-BODY Y TEXTO ===
        def get_stl_base_js():
            sc = sl_stl_sc.value / 100.0; tx = sl_stl_x.value; ty = sl_stl_y.value; tz = sl_stl_z.value
            return f"""
  var sc = {sc}; var tx = {tx}; var ty = {ty}; var tz = {tz};
  var dron = null;
  if (typeof IMPORTED_STL !== 'undefined') {{
      // BYPASS HÍBRIDO AVANZADO (MULTI-BODY)
      if (Array.isArray(IMPORTED_STL) && IMPORTED_STL.length > 0) {{
          dron = IMPORTED_STL[0];
          for(var i = 1; i < IMPORTED_STL.length; i++) {{
              dron = dron.union(IMPORTED_STL[i]);
          }}
      }} else {{
          dron = IMPORTED_STL;
      }}
  }}
  if(!dron || !dron.polygons) {{ return CSG.cube({{radius:[0.1,0.1,0.1]}}); }}
  dron = dron.scale([sc, sc, sc]).translate([tx, ty, tz]);
"""

        def generate_param_code():
            h = herramienta_actual
            if h == "custom": return
            code = "function main() {\n"
            
            if h.startswith("stl"):
                code += get_stl_base_js()
                if h == "stl":
                    code += "  return dron;\n}"
                elif h == "stl_flatten":
                    code += f"  return dron.subtract(CSG.cube({{center:[0,0,-500+{sl_stlf_z.value}], radius:[1000,1000,500]}}));\n}}"
                elif h == "stl_split":
                    ax = dd_stls_axis.value; p = sl_stls_pos.value
                    cx = p-500 if ax=='X' else 0; cy = p-500 if ax=='Y' else 0; cz = p-500 if ax=='Z' else 0
                    code += f"  return dron.subtract(CSG.cube({{center:[{cx},{cy},{cz}], radius:[1000,1000,1000]}}));\n}}"
                elif h == "stl_crop":
                    S = sl_stlc_s.value / 2.0
                    code += f"  return dron.intersect(CSG.cube({{center:[0,0,0], radius:[{S},{S},{S}]}}));\n}}"
                elif h == "stl_drill":
                    ax = dd_stld_axis.value; R = sl_stld_r.value; p1 = sl_stld_px.value; p2 = sl_stld_py.value
                    st = f"[-500,{p1},{p2}]" if ax=='X' else (f"[{p1},-500,{p2}]" if ax=='Y' else f"[{p1},{p2},-500]")
                    en = f"[500,{p1},{p2}]" if ax=='X' else (f"[{p1},500,{p2}]" if ax=='Y' else f"[{p1},{p2},500]")
                    code += f"  return dron.subtract(CSG.cylinder({{start:{st}, end:{en}, radius:{R}}}));\n}}"
                elif h == "stl_mount":
                    w = sl_stlm_w.value; d = sl_stlm_d.value
                    code += f"  var m1 = CSG.cube({{center:[{d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{d/2},0,-5], end:[{d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  var m2 = CSG.cube({{center:[{-d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{-d/2},0,-5], end:[{-d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  return dron.union(m1).union(m2);\n}}"
                elif h == "stl_ears":
                    r = sl_stle_r.value; d = sl_stle_d.value
                    code += f"  var c1=CSG.cylinder({{start:[{d/2},{d/2},0], end:[{d/2},{d/2},0.4], radius:{r}}});\n"
                    code += f"  var c2=CSG.cylinder({{start:[{-d/2},{d/2},0], end:[{-d/2},{d/2},0.4], radius:{r}}});\n"
                    code += f"  var c3=CSG.cylinder({{start:[{d/2},{-d/2},0], end:[{d/2},{-d/2},0.4], radius:{r}}});\n"
                    code += f"  var c4=CSG.cylinder({{start:[{-d/2},{-d/2},0], end:[{-d/2},{-d/2},0.4], radius:{r}}});\n"
                    code += f"  return dron.union(c1).union(c2).union(c3).union(c4);\n}}"
                elif h == "stl_patch":
                    sx = sl_stlp_sx.value; sy = sl_stlp_sy.value; sz = sl_stlp_sz.value
                    code += f"  return dron.union(CSG.cube({{center:[0,0,0], radius:[{sx/2},{sy/2},{sz/2}]}}));\n}}"
                elif h == "stl_honeycomb":
                    hex_r = sl_stlh_r.value
                    code += f"  var dx = {hex_r}*1.732+2; var dy = {hex_r}*1.5+2; var holes = null;\n"
                    code += f"  for(var x = -100; x < 100; x += dx) {{ for(var y = -100; y < 100; y += dy) {{\n"
                    code += f"      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0;\n"
                    code += f"      var hex = CSG.cylinder({{start:[x+offset, y, -500], end:[x+offset, y, 500], radius:{hex_r}, slices:6}});\n"
                    code += f"      if(holes === null) holes = hex; else holes = holes.union(hex);\n"
                    code += f"  }} }}\n  return dron.subtract(holes);\n}}"
                elif h == "stl_propguard":
                    r = sl_stlp_r.value; t = sl_stlp_t.value; px = sl_stlp_x.value; py = sl_stlp_y.value
                    code += f"  var out = CSG.cylinder({{start:[{px},{py},0], end:[{px},{py},10], radius:{r+t}, slices:32}});\n"
                    code += f"  var inn = CSG.cylinder({{start:[{px},{py},-1], end:[{px},{py},11], radius:{r}, slices:32}});\n"
                    code += f"  return dron.union(out.subtract(inn));\n}}"
            else:
                if h == "cubo":
                    code += f"  return CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}});\n}}"
                elif h == "cilindro":
                    code += f"  return CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GW/2}});\n}}"
                elif h == "texto":
                    code += f"  var pText = CSG.cube({{center:[0,0,GH/2+2], radius:[GW/2-2, 10, 2]}});\n"
                    code += f"  var baseObj = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, 15, GH/2]}});\n"
                    code += f"  if({str(sw_txt_grabado.value).lower()}) return baseObj.subtract(pText.translate([0,0,-2]));\n  return baseObj.union(pText);\n}}"

            txt_code.value = code
            page.update()

        # =========================================================
        # FIX DEFINITIVO DE LOS COMBOS (DESTROZAR Y RECREAR)
        # =========================================================
        categorias = {
            "Ultimate STL Forge": [
                ("stl", "Ver STL Original"), 
                ("stl_flatten", "Aplanar Base"), 
                ("stl_split", "Cortador Split"), 
                ("stl_crop", "Aislar Crop"), 
                ("stl_drill", "Taladro 3D"), 
                ("stl_mount", "Orejetas de Montaje"), 
                ("stl_ears", "Discos Anti-Warp"),
                ("stl_patch", "Parche Refuerzo"),
                ("stl_honeycomb", "Honeycomb"),
                ("stl_propguard", "Protector de Hélice")
            ],
            "Geometría Básica": [("cubo", "Cubo G"), ("cilindro", "Cilindro / Hueco")],
            "Especiales": [("texto", "Llaveros y Carteles"), ("custom", "Código Libre RAW")]
        }

        dd_cat = ft.Dropdown(options=[ft.dropdown.Option(k) for k in categorias.keys()], value="Ultimate STL Forge", width=170, bgcolor="#161B22")
        
        # El contenedor que va a alojar el segundo combo para obligar a Flet a redibujarlo.
        container_tool = ft.Container()

        def on_tool_change(e):
            nonlocal herramienta_actual
            herramienta_actual = dd_tool.value
            for k, p in panels.items(): 
                p.visible = (k == herramienta_actual)
            
            panel_stl_transform.visible = herramienta_actual.startswith("stl")
            generate_param_code()
            page.update()

        def on_cat_change(e):
            nonlocal dd_tool
            cat = dd_cat.value
            
            # TRUCO MAESTRO: Destruimos el Dropdown y lo volvemos a crear en memoria. 
            # Esto evita el bug de la interfaz gráfica antigua de Termux donde no se actualizaban las opciones.
            dd_tool = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=v) for k, v in categorias[cat]],
                value=categorias[cat][0][0],
                width=170,
                bgcolor="#161B22",
                on_change=on_tool_change
            )
            container_tool.content = dd_tool
            page.update()
            on_tool_change(None)

        dd_cat.on_change = on_cat_change
        
        botones_raw = ft.Row([
            ft.ElevatedButton("💾 GUARDAR", bgcolor="#0D47A1", color="white")
        ], alignment="spaceBetween")

        editor_exp = ft.ExpansionTile(title=ft.Text("📝 CÓDIGO FUENTE RAW", color="#FFAB00", weight="bold"), controls=[botones_raw, txt_code], bgcolor="#0B0E14")

        view_constructor = ft.Column([
            ft.Row([ft.Text("Cat:", color="#8B949E", size=11), dd_cat, ft.Text("Tool:", color="#8B949E", size=11), container_tool], wrap=True),
            ft.Divider(color="#30363D"),
            panel_globales, panel_stl_transform, 
            ft.Column(list(panels.values())), 
            editor_exp,
            ft.ElevatedButton("▶ PROCESAR RENDER 3D", on_click=lambda _: [run_render()], color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        # =========================================================
        # VISOR Y VR
        # =========================================================
        def run_render():
            global LATEST_CODE_B64
            h = f"  var GW={sl_g_w.value}; var GL={sl_g_l.value}; var GH={sl_g_h.value}; var GT={sl_g_t.value};\n"
            c = txt_code.value
            final = c.replace("function main() {", "function main() {\n" + h, 1) if "function main() {" in c else h + "\n" + c
            LATEST_CODE_B64 = base64.b64encode(final.encode('utf-8')).decode()
            set_tab(1)

        view_visor = ft.Column([
            ft.Container(height=10),
            ft.Container(content=ft.Column([
                ft.Text("🥽 NEXUS VR GATEWAY", color="#00E5FF", weight="bold"),
                ft.Text("Conéctate desde tus gafas o PC en WiFi:", size=11, color="#8B949E"),
                ft.Text(f"http://{LAN_IP}:{LOCAL_PORT}/", size=16, color="#00E676", weight="bold", selectable=True)
            ]), bgcolor="#161B22", padding=15, border_radius=8, border=ft.border.all(1, "#00E5FF")),
            ft.Container(height=10),
            ft.ElevatedButton("🔄 ABRIR VISOR 3D LOCAL", url=f"http://127.0.0.1:{LOCAL_PORT}/", color="black", bgcolor="#00E676", height=60, expand=True)
        ], expand=True, scroll="auto")

        # =========================================================
        # ECOSISTEMA FILES (¡FIX ROBUSTO DE ICONOS Y TEXTO!)
        # =========================================================
        list_nexus_db = ft.ListView(expand=True, spacing=10)

        def refresh_nexus_db():
            list_nexus_db.controls.clear()
            try:
                files = [f for f in os.listdir(EXPORT_DIR) if not f.startswith('.') and f != "imported.stl"]
                if not files:
                    list_nexus_db.controls.append(ft.Text("La base de datos está vacía. Inyecta un archivo.", color="#8B949E", italic=True))
                for f in files:
                    ext = f.lower().split('.')[-1]
                    p = os.path.join(EXPORT_DIR, f)
                    
                    # FIX TOTAL: ft.TextButton con Emojis (sin keywords peligrosos)
                    list_nexus_db.controls.append(
                        ft.Container(content=ft.Row([
                            ft.Text("🧊" if ext=="stl" else "🧩", size=24),
                            ft.Text(f, color="white", weight="bold", expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.TextButton("▶️", on_click=lambda e, fp=p: load_file(fp), tooltip="Cargar a Forge"),
                            ft.TextButton("⬇️", on_click=lambda e, fn=f: page.launch_url(f"http://127.0.0.1:{LOCAL_PORT}/descargar/{fn}"), tooltip="Bajar"),
                            ft.TextButton("🗑️", on_click=lambda e, fp=p: [os.remove(fp), refresh_nexus_db()], tooltip="Borrar")
                        ]), bgcolor="#161B22", padding=10, border_radius=8)
                    )
            except Exception as e:
                list_nexus_db.controls.append(ft.Text(f"Error DB: {e}"))
            page.update()

        def load_file(filepath):
            fn = os.path.basename(filepath); ext = fn.lower().split('.')[-1]
            if ext == "stl":
                shutil.copy(filepath, os.path.join(EXPORT_DIR, "imported.stl"))
                lbl_stl_status.value = f"✓ Activo: {fn}"; lbl_stl_status.color = "#00E676"
                dd_cat.value = "Ultimate STL Forge"
                on_cat_change(None)
                dd_tool.value = "stl"
                on_tool_change(None)
                set_tab(0); status.value = "✓ STL Listo en Forge"
            elif ext == "jscad":
                txt_code.value = open(filepath).read()
                set_tab(0); status.value = "✓ Código Cargado"
            page.update()

        view_archivos = ft.Column([
            ft.ElevatedButton("🚀 INYECTAR ARCHIVO (WEB)", url=f"http://127.0.0.1:{LOCAL_PORT}/upload_ui", bgcolor="#00E676", color="black", width=float('inf'), height=60, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))),
            ft.Row([
                ft.Text("📁 NEXUS DB", color="white", weight="bold"), 
                ft.ElevatedButton("🔄 ACTUALIZAR", on_click=lambda _: refresh_nexus_db(), bgcolor="#1E1E1E", color="#00E5FF")
            ], alignment="spaceBetween"),
            ft.Divider(color="#30363D"),
            list_nexus_db
        ], expand=True)

        main_container = ft.Container(content=view_constructor, expand=True)

        def set_tab(idx):
            if idx == 2: refresh_nexus_db()
            main_container.content = [view_constructor, view_visor, view_archivos][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), color="black", bgcolor="#00E676", expand=True),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(1), color="black", bgcolor="#00E5FF", expand=True),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(2), bgcolor="#FFAB00", color="black", expand=True),
        ])

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        
        # Inicialización segura
        on_cat_change(None)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)