import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, traceback, shutil
from urllib.parse import urlparse, unquote

try: import psutil; HAS_PSUTIL = True
except ImportError: HAS_PSUTIL = False

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# CONFIGURACIÓN DE RUTAS Y SERVIDOR
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
# SERVIDOR WEB (CON FIX CORS PARA ANDROID CHROME)
# =========================================================
class NexusHandler(http.server.BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, File-Name")

    def do_OPTIONS(self):
        # Vital para que Chrome Android no bloquee la subida
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/upload':
            cl = int(self.headers.get('Content-Length', 0))
            fn = unquote(self.headers.get('File-Name', 'uploaded_file.stl'))
            if cl > 0:
                try:
                    with open(os.path.join(EXPORT_DIR, fn), 'wb') as f:
                        f.write(self.rfile.read(cl))
                    self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(b'ok')
                    return
                except Exception as e:
                    print(f"Error guardando: {e}")
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
                    self.send_response(200); self.send_header("Content-type", "application/sla"); self._send_cors(); self.end_headers()
                    self.wfile.write(f.read())
            else: self.send_response(404); self._send_cors(); self.end_headers()

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
                .then(r => { if(r.ok){ document.getElementById('s').style.color='#00E676'; document.getElementById('s').innerText='✓ ¡ÉXITO! Vuelve a la App.'; } else { throw 'Error'; } })
                .catch(e => { document.getElementById('s').style.color='red'; document.getElementById('s').innerText='❌ Error de red'; });}</script></body></html>"""
            self.send_response(200); self.send_header("Content-type", "text/html"); self._send_cors(); self.end_headers(); self.wfile.write(html.encode('utf-8'))
            
        elif parsed.path.startswith('/descargar/'):
            filename = unquote(parsed.path.replace('/descargar/', ''))
            filepath = os.path.join(EXPORT_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.send_response(200); self.send_header("Content-Disposition", f'attachment; filename="{filename}"'); self._send_cors(); self.end_headers()
                    self.wfile.write(f.read())
            else: self.send_response(404); self._send_cors(); self.end_headers()
            
        else:
            try:
                fn = self.path.strip("/") or "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, fn), "rb") as f: 
                    self.send_response(200); self._send_cors(); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self._send_cors(); self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# LÓGICA DE LA APLICACIÓN FLET
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v25.1 Pro"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v25.1 Pro | Sistemas Online", color="#00E676", weight="bold")
        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n}"
        txt_code = ft.TextField(multiline=True, min_lines=10, max_lines=20, value=T_INICIAL, bgcolor="#0B0E14", color="#58A6FF", border_color="#30363D", text_size=12)

        herramienta_actual = "custom"
        modo_ensamble = False
        ensamble_stack = []

        def update_code_wrapper(e=None): generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=40, text_align="right", size=11, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"; page.update()
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

        sw_ensamble = ft.Switch(label="Ensamblador Pro", value=False, active_color="#FFAB00")
        def toggle_ensamble(e):
            nonlocal modo_ensamble; modo_ensamble = sw_ensamble.value
            panel_ensamble_ops.visible = modo_ensamble; page.update()
        sw_ensamble.on_change = toggle_ensamble

        def add_to_stack(op_type):
            nonlocal ensamble_stack
            lines = txt_code.value.split('\n'); vname = f"obj_{len(ensamble_stack)}"; body = []
            for l in lines[1:-1]:
                if l.strip().startswith("return "): body.append(f"  var {vname} = {l.replace('return','').replace(';','').strip()};")
                else: body.append(l)
            ensamble_stack.append({"body": "\n".join(body), "var": vname, "op": op_type if ensamble_stack else "base"})
            fc = "function main() {\n"; fv = ""
            for i, item in enumerate(ensamble_stack):
                fc += f"  // --- Módulo {i} ({item['op']}) ---\n{item['body']}\n"
                if item["op"] == "base": fv = item["var"]
                else: fc += f"  {fv} = {fv}.{item['op']}({item['var']});\n"
            txt_code.value = fc + f"  return {fv};\n}}"; page.update()

        def clear_editor():
            nonlocal ensamble_stack; ensamble_stack = []
            txt_code.value = T_INICIAL; status.value = "✓ Reset Realizado"; status.color="#B71C1C"; page.update()

        def save_project_to_nexus():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = f"✓ Guardado: {fname}"; status.color="#00E676"; page.update()

        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton("➕ UNIR", on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", color="white", expand=True),
            ft.ElevatedButton("➖ RESTAR", on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", color="white", expand=True),
        ], visible=False)

        panel_globales = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🌐 PARÁMETROS MAESTROS", color="#00E5FF", weight="bold", size=11), sw_ensamble], alignment="spaceBetween"),
            r_g_w, r_g_l, r_g_h, r_g_t, panel_ensamble_ops
        ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        # =========================================================
        # CATEGORÍAS Y HERRAMIENTAS (>30)
        # =========================================================
        panels = {}

        # 1. GEOMETRÍA BÁSICA
        sl_c_g, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        panels["cubo"] = mk_col("Cubo Paramétrico", "Base sólida o hueca.", [r_c_g])
        sl_p_r, r_p_r = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_l, r_p_l = create_slider("Caras", 3, 64, 64, True)
        panels["cilindro"] = mk_col("Cilindro / Prisma", "Cuerpos de revolución.", [r_p_r, r_p_l])
        sl_l_l, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False); sl_l_a, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False)
        panels["escuadra"] = mk_col("Escuadra Soporte", "Refuerzo estructural L.", [r_l_l, r_l_a])
        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False); sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False)
        panels["pcb"] = mk_col("Caja Electrónica", "Protección para placas.", [r_pcb_x, r_pcb_y])

        # 2. MECÁNICA
        sl_e_d, r_e_d = create_slider("Dientes", 6, 40, 16, True); sl_e_r, r_e_r = create_slider("Radio", 10, 100, 30, False)
        panels["engranaje"] = mk_col("Engranaje Recto", "Transmisión mecánica.", [r_e_d, r_e_r])
        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True)
        panels["fijacion"] = mk_col("Tuerca / Tornillo", "Fijaciones estándar.", [r_fij_m])
        sl_pol_t, r_pol_t = create_slider("Dientes", 10, 60, 20, True)
        panels["polea"] = mk_col("Polea GT2", "Para correas de precisión.", [r_pol_t])
        sl_mue_r, r_mue_r = create_slider("Radio", 5, 50, 15, False); sl_mue_v, r_mue_v = create_slider("Vueltas", 2, 20, 5, False)
        panels["muelle"] = mk_col("Resorte Helicoidal", "Amortiguación.", [r_mue_r, r_mue_v])

        # 3. AVANZADOS
        sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False)
        panels["panal"] = mk_col("Estructura Panal", "Aligerado Honeycomb.", [r_pan_r])
        sl_vor_d, r_vor_d = create_slider("Densidad", 4, 30, 12, True)
        panels["voronoi"] = mk_col("Patrón Voronoi", "Malla orgánica estructural.", [r_vor_d])
        sl_crem_d, r_crem_d = create_slider("Dientes", 5, 100, 20, True)
        panels["cremallera"] = mk_col("Cremallera Lineal", "Actuadores mecánicos.", [r_crem_d])

        # 4. TEXTO
        tf_texto = ft.TextField(label="Contenido Texto", value="NEXUS", max_length=15, bgcolor="#1E1E1E")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Grueso"), ft.dropdown.Option("Fino")], value="Grueso", bgcolor="#1E1E1E")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Llavero"), ft.dropdown.Option("Placa"), ft.dropdown.Option("Solo Texto")], value="Llavero", bgcolor="#1E1E1E")
        sw_txt_grabado = ft.Switch(label="Modo Grabado", value=False)
        tf_texto.on_change=update_code_wrapper; dd_txt_estilo.on_change=update_code_wrapper; dd_txt_base.on_change=update_code_wrapper; sw_txt_grabado.on_change=update_code_wrapper
        panels["texto"] = mk_col("Generador de Texto", "Cartelería y placas.", [tf_texto, dd_txt_estilo, dd_txt_base, sw_txt_grabado])

        # 5. ULTIMATE STL FORGE
        lbl_stl_status = ft.Text("No hay STL en memoria.", color="#8B949E", size=11)
        sl_stl_sc, r_stl_sc = create_slider("Escala (%)", 1, 500, 100, True)
        sl_stl_x, r_stl_x = create_slider("X", -200, 200, 0, False); sl_stl_y, r_stl_y = create_slider("Y", -200, 200, 0, False); sl_stl_z, r_stl_z = create_slider("Z", -200, 200, 0, False)
        
        panel_stl_transform = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🔄 TRANSFORMACIÓN BASE STL", color="#00E676", weight="bold"), lbl_stl_status]),
            ft.ElevatedButton("📂 IR A FILES (IMPORTAR STL)", on_click=lambda _: set_tab(2), bgcolor="#00E5FF", color="black", width=float('inf')),
            r_stl_sc, r_stl_x, r_stl_y, r_stl_z
        ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"), visible=False)

        panels["stl"] = mk_col("Visor STL", "Muestra el archivo cargado.", [])
        sl_stlf_z, r_stlf_z = create_slider("Corte Base Z", 0, 50, 1, False)
        panels["stl_flatten"] = mk_col("Aplanar Base", "Corte para adherencia a cama.", [r_stlf_z])
        dd_stls_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E"); dd_stls_axis.on_change=update_code_wrapper
        sl_stls_pos, r_stls_pos = create_slider("Punto Corte", -150, 150, 0, False)
        panels["stl_split"] = mk_col("Cortador Split", "División de pieza.", [dd_stls_axis, r_stls_pos])
        sl_stld_r, r_stld_r = create_slider("Radio Taladro", 0.5, 20, 1.6, False)
        panels["stl_drill"] = mk_col("Taladro 3D", "Perforación infinita.", [r_stld_r])

        panels["custom"] = mk_col("Código Libre RAW", "Edita el código fuente directamente.", [])

        # === GENERADOR CORE JAVASCRIPT ===
        def generate_param_code():
            h = herramienta_actual
            if h == "custom": return
            code = "function main() {\n"
            
            sc = sl_stl_sc.value / 100.0; tx = sl_stl_x.value; ty = sl_stl_y.value; tz = sl_stl_z.value

            if h.startswith("stl"):
                code += f"  var dron = (typeof IMPORTED_STL !== 'undefined') ? (Array.isArray(IMPORTED_STL)?IMPORTED_STL[0]:IMPORTED_STL) : null;\n"
                code += f"  if(!dron) return CSG.cube({{radius:0.1}});\n"
                code += f"  dron = dron.scale([{sc},{sc},{sc}]).translate([{tx},{ty},{tz}]);\n"
                
                if h == "stl": code += "  return dron;\n}"
                elif h == "stl_flatten": code += f"  return dron.subtract(CSG.cube({{center:[0,0,-500+{sl_stlf_z.value}], radius:[1000,1000,500]}}));\n}}"
                elif h == "stl_split":
                    ax = dd_stls_axis.value; p = sl_stls_pos.value
                    cx = p-500 if ax=='X' else 0; cy = p-500 if ax=='Y' else 0; cz = p-500 if ax=='Z' else 0
                    code += f"  return dron.subtract(CSG.cube({{center:[{cx},{cy},{cz}], radius:[1000,1000,1000]}}));\n}}"
                elif h == "stl_drill":
                    ax = dd_stld_axis.value; p = sl_stld_r.value
                    st = f"[-500,0,0]" if ax=='X' else (f"[0,-500,0]" if ax=='Y' else f"[0,0,-500]")
                    en = f"[500,0,0]" if ax=='X' else (f"[0,500,0]" if ax=='Y' else f"[0,0,500]")
                    code += f"  return dron.subtract(CSG.cylinder({{start:{st}, end:{en}, radius:{p}}}));\n}}"
            else:
                if h == "cubo": code += f"  return CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}});\n}}"
                elif h == "cilindro": code += f"  return CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:{int(sl_p_l.value)}}});\n}}"
                elif h == "pcb": code += f"  return CSG.cube({{radius:[GW/2+GT, GL/2+GT, GH/2]}}).subtract(CSG.cube({{radius:[GW/2, GL/2, GH/2+1]}}));\n}}"
                elif h == "engranaje": code += f"  return CSG.cylinder({{radius:{sl_e_r.value}, slices:{int(sl_e_d.value)}}});\n}}"
                elif h == "texto": code += f"  return CSG.cube({{radius:[GW/2, 10, GH/2]}}).union(CSG.cube({{radius:[GW/2+2, 12, 2]}}));\n}}"
                else: code += "  return CSG.sphere({radius:10});\n}"

            if not modo_ensamble:
                txt_code.value = code; page.update()

        # =========================================================
        # FIX CASCADA DE COMBOS
        # =========================================================
        categorias = {
            "Geometría Básica": [("cubo", "Cubo G"), ("cilindro", "Cilindro / Hueco"), ("escuadra", "Escuadra L"), ("pcb", "Caja Electrónica")],
            "Mecánica": [("engranaje", "Piñón Recto"), ("fijacion", "Tuerca / Tornillo"), ("polea", "Polea GT2"), ("muelle", "Resorte")],
            "Avanzados": [("panal", "HoneyComb"), ("voronoi", "Voronoi"), ("cremallera", "Cremallera")],
            "Ultimate STL Forge": [("stl", "Ver STL"), ("stl_flatten", "Aplanar"), ("stl_split", "Split"), ("stl_drill", "Taladro")],
            "Texto y Especiales": [("texto", "Placas Texto"), ("custom", "Código Libre RAW")]
        }

        dd_cat = ft.Dropdown(options=[ft.dropdown.Option(k) for k in categorias.keys()], value="Geometría Básica", width=170, bgcolor="#161B22")
        dd_tool = ft.Dropdown(width=170, bgcolor="#161B22")

        def on_cat_change(e):
            cat = dd_cat.value
            dd_tool.options = [ft.dropdown.Option(key=k, text=v) for k, v in categorias[cat]]
            dd_tool.value = categorias[cat][0][0]
            page.update() # Fix crucial para la UI
            on_tool_change(None)

        def on_tool_change(e):
            nonlocal herramienta_actual; herramienta_actual = dd_tool.value
            for k, p in panels.items(): p.visible = (k == herramienta_actual)
            panel_stl_transform.visible = herramienta_actual.startswith("stl")
            generate_param_code()
            page.update()

        dd_cat.on_change = on_cat_change; dd_tool.on_change = on_tool_change
        
        # RESTAURACIÓN BOTONES Y PLANTILLA IA
        def inject_snippet(code):
            c = txt_code.value; pos = c.rfind('return ')
            txt_code.value = (c[:pos] + code + "\n  " + c[pos:]) if pos != -1 else (c + "\n" + code)
            page.update()

        help_box = ft.ExpansionTile(title=ft.Text("💡 Ayuda IA / Plantillas", color="#00E5FF", size=12, weight="bold"), controls=[
            ft.Container(padding=10, bgcolor="#161B22", border_radius=8, content=ft.Column([
                ft.Text("Copia este Prompt para ChatGPT:", weight="bold", color="#8B949E", size=11),
                ft.TextField(value="Escribe código OpenJSCAD. Función main() obligatoria. Devuelve el objeto con 'return'. Usa GW, GL, GH.", read_only=True, text_size=10, multiline=True),
                ft.Row([ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("var c = CSG.cube({radius:[10,10,10]});")), ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5});"))])
            ]))
        ])

        botones_raw = ft.Row([
            ft.ElevatedButton("💾 GUARDAR JSCAD", on_click=lambda _: save_project_to_nexus(), bgcolor="#0D47A1", color="white"),
            ft.ElevatedButton("🗑️ LIMPIAR", on_click=lambda _: clear_editor(), bgcolor="#B71C1C", color="white")
        ], alignment="spaceBetween")

        editor_exp = ft.ExpansionTile(title=ft.Text("📝 CÓDIGO FUENTE RAW", color="#FFAB00", weight="bold"), controls=[botones_raw, txt_code], bgcolor="#0B0E14", initially_expanded=True)

        view_constructor = ft.Column([
            ft.Row([ft.Text("Cat:", color="#8B949E", size=11), dd_cat, ft.Text("Tool:", color="#8B949E", size=11), dd_tool], wrap=True),
            ft.Divider(color="#30363D"),
            panel_globales, panel_stl_transform, 
            ft.Column(list(panels.values())), 
            help_box,
            editor_exp,
            ft.ElevatedButton("▶ PROCESAR RENDER 3D", on_click=lambda _: [run_render()], color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        # =========================================================
        # VISOR Y VR
        # =========================================================
        pb_cpu = ft.ProgressBar(color="#FFAB00", bgcolor="#30363D", value=0, expand=True); txt_cpu_val = ft.Text("0.0%", size=11, color="#FFAB00", width=40)
        pb_ram = ft.ProgressBar(color="#00E5FF", bgcolor="#30363D", value=0, expand=True); txt_ram_val = ft.Text("0.0%", size=11, color="#00E5FF", width=40)
        
        hw_panel = ft.Container(content=ft.Column([
            ft.Row([ft.Text("📊 HARDWARE", size=11, color="#E6EDF3", weight="bold")]),
            ft.Row([ft.Text("CPU", size=11, color="#FFAB00", width=30), pb_cpu, txt_cpu_val]),
            ft.Row([ft.Text("RAM", size=11, color="#00E5FF", width=30), pb_ram, txt_ram_val])
        ], spacing=5), bgcolor="#1E1E1E", padding=10, border_radius=8)

        def hw_monitor_loop():
            while True:
                time.sleep(1.5)
                try:
                    if main_container.content == view_visor:
                        cpu, ram, cores = get_sys_info()
                        pb_cpu.value = cpu / 100.0; txt_cpu_val.value = f"{cpu:.1f}%"
                        pb_ram.value = ram / 100.0; txt_ram_val.value = f"{ram:.1f}%"
                        try: hw_panel.update()
                        except: pass
                except: pass
        threading.Thread(target=hw_monitor_loop, daemon=True).start()

        def run_render():
            global LATEST_CODE_B64
            h = f"  var GW={sl_g_w.value}; var GL={sl_g_l.value}; var GH={sl_g_h.value}; var GT={sl_g_t.value};\n"
            c = txt_code.value
            final = c.replace("function main() {", "function main() {\n" + h, 1) if "function main() {" in c else h + "\n" + c
            LATEST_CODE_B64 = base64.b64encode(final.encode('utf-8')).decode()
            set_tab(1)

        view_visor = ft.Column([
            ft.Container(height=5), hw_panel, ft.Container(height=5),
            ft.Container(content=ft.Column([
                ft.Text("🥽 NEXUS VR GATEWAY", color="#00E5FF", weight="bold"),
                ft.Text("Usa esta URL en tus Quest o PC:", size=11, color="#8B949E"),
                ft.Text(f"http://{LAN_IP}:{LOCAL_PORT}/", size=14, color="#00E676", weight="bold", selectable=True)
            ]), bgcolor="#161B22", padding=15, border_radius=8, border=ft.border.all(1, "#00E5FF")),
            ft.ElevatedButton("🔄 ABRIR VISOR 3D LOCAL", url=f"http://127.0.0.1:{LOCAL_PORT}/", color="black", bgcolor="#00E676", height=60, expand=True)
        ], expand=True, scroll="auto")

        # =========================================================
        # ECOSISTEMA FILES
        # =========================================================
        list_nexus_db = ft.ListView(expand=True, spacing=10)

        def refresh_nexus_db():
            list_nexus_db.controls.clear()
            try:
                files = [f for f in os.listdir(EXPORT_DIR) if not f.startswith('.') and f != "imported.stl"]
                if not files: list_nexus_db.controls.append(ft.Text("La base de datos está vacía. Inyecta un archivo.", color="#8B949E", italic=True))
                for f in files:
                    ext = f.lower().split('.')[-1]
                    p = os.path.join(EXPORT_DIR, f)
                    list_nexus_db.controls.append(
                        ft.Container(content=ft.Row([
                            ft.Text("🧊" if ext=="stl" else "🧩", size=24),
                            ft.Text(f, color="white", weight="bold", expand=True),
                            ft.IconButton(ft.icons.PLAY_CIRCLE, icon_color="#00E676", on_click=lambda e, fp=p: load_file(fp)),
                            ft.IconButton(ft.icons.DOWNLOAD, icon_color="#00E5FF", on_click=lambda e, fn=f: page.launch_url(f"http://127.0.0.1:{LOCAL_PORT}/descargar/{fn}")),
                            ft.IconButton(ft.icons.DELETE, icon_color="#B71C1C", on_click=lambda e, fp=p: [os.remove(fp), refresh_nexus_db()])
                        ]), bgcolor="#161B22", padding=10, border_radius=8)
                    )
            except Exception as e: list_nexus_db.controls.append(ft.Text(f"Error DB: {e}"))
            page.update()

        def load_file(filepath):
            fn = os.path.basename(filepath); ext = fn.lower().split('.')[-1]
            if ext == "stl":
                shutil.copy(filepath, os.path.join(EXPORT_DIR, "imported.stl"))
                lbl_stl_status.value = f"✓ Activo: {fn}"; lbl_stl_status.color = "#00E676"
                dd_cat.value = "Ultimate STL Forge"; on_cat_change(None); dd_tool.value = "stl"; on_tool_change(None)
                set_tab(0); status.value = "✓ STL Listo en Forge"
            elif ext == "jscad":
                txt_code.value = open(filepath).read(); set_tab(0); status.value = "✓ Código Cargado"
            page.update()

        view_archivos = ft.Column([
            ft.ElevatedButton("🚀 INYECTAR ARCHIVO (WEB)", url=f"http://127.0.0.1:{LOCAL_PORT}/upload_ui", bgcolor="#00E676", color="black", width=float('inf'), height=60, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))),
            ft.Row([ft.Text("📁 NEXUS DB", color="white", weight="bold"), ft.IconButton(ft.icons.REFRESH, on_click=lambda _: refresh_nexus_db(), icon_color="#00E5FF")], alignment="spaceBetween"),
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
        
        on_cat_change(None)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)