import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, traceback, shutil

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from urllib.parse import urlparse
import urllib.request

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS DEL SISTEMA Y ANDROID
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
os.makedirs(EXPORT_DIR, exist_ok=True)

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
# TELEMETRÍA Y RED LOCAL
# =========================================================
def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL:
        cpu_p = psutil.cpu_percent()
        ram_p = psutil.virtual_memory().percent
    else:
        try:
            with open('/proc/meminfo', 'r') as f: lines = f.readlines()
            total = free = buffers = cached = 0
            for line in lines:
                if 'MemTotal:' in line: total = int(line.split()[1])
                elif 'MemFree:' in line: free = int(line.split()[1])
                elif 'Buffers:' in line: buffers = int(line.split()[1])
                elif 'Cached:' in line: cached = int(line.split()[1])
            if total > 0:
                used = total - free - buffers - cached
                ram_p = (used / total) * 100.0
            with open('/proc/loadavg', 'r') as f:
                load = float(f.read().split()[0])
            cpu_p = min((load / cores) * 100.0, 100.0)
        except: pass
    return cpu_p, ram_p, cores

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: return "127.0.0.1"

# =========================================================
# SERVIDOR LOCAL WEBGL (INTACTO v20.7)
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        LOCAL_PORT = s.getsockname()[1]
except:
    LOCAL_PORT = 8556

LAN_IP = get_lan_ip()
LATEST_CODE_B64 = ""

def get_stl_hash():
    path = os.path.join(EXPORT_DIR, "imported.stl")
    if os.path.exists(path): return str(os.path.getmtime(path))
    return ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/save_export':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data.decode('utf-8'))
                    filepath = os.path.join(EXPORT_DIR, data['filename'])
                    with open(filepath, 'w') as f: f.write(data['data'])
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b'{"status": "ok"}')
                    return
                except Exception: pass
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        global LATEST_CODE_B64
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/get_code_b64.json':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = json.dumps({"code_b64": LATEST_CODE_B64, "stl_hash": get_stl_hash()})
            self.wfile.write(payload.encode())
            LATEST_CODE_B64 = "" 
            
        elif parsed.path.startswith('/exports/'):
            filename = parsed.path.replace('/exports/', '')
            filepath = os.path.join(EXPORT_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.end_headers()
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            try:
                filename = self.path.strip("/")
                if not filename: filename = "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, filename), "rb") as f:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f.read())
            except:
                self.send_response(404)
                self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APP FLET MAIN
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v20.8 TITAN"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v20.8 TITAN | Explorador Nativo + Híbrido", color="#00E676", weight="bold")

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

        ensamble_stack = []
        herramienta_actual = "custom"
        modo_ensamble = False

        def clear_editor():
            nonlocal ensamble_stack
            ensamble_stack = []
            txt_code.value = "function main() {\n  // Plantilla limpia\n  return CSG.cube({radius:[0,0,0]});\n}"
            status.value = "✓ Código borrado por completo."
            status.color = "#B71C1C"
            txt_code.update(); page.update()

        def inject_snippet(code_snippet):
            c = txt_code.value
            pos = c.rfind('return ')
            if pos != -1: txt_code.value = c[:pos] + code_snippet + "\n  " + c[pos:]
            else: txt_code.value = c + "\n" + code_snippet
            txt_code.update()

        def update_code_wrapper(e=None): generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=45, text_align="right", size=13, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                txt_val.update(); 
                if not modo_ensamble: update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="#E6EDF3"), sl, txt_val])

        # === PARAMETROS GLOBALES ===
        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False)
        sl_g_tol, r_g_tol = create_slider("Tol. Global (G_TOL)", 0.0, 2.0, 0.2, False)

        def prepare_js_payload():
            header = f"  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value}; var G_TOL = {sl_g_tol.value};\n"
            c = txt_code.value
            if "function main() {" in c: c = c.replace("function main() {", "function main() {\n" + header, 1)
            else: c = header + "\n" + c
            return c

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            set_tab(2); page.update()

        help_box = ft.ExpansionTile(title=ft.Text("💡 Ayuda Rápida y Plantilla para IA", color="#00E5FF", weight="bold", size=12), collapsed_text_color="#00E5FF", text_color="#00E5FF", icon_color="#00E5FF", controls=[ft.Container(padding=10, bgcolor="#161B22", border_radius=8, content=ft.Column([ft.Text("📝 REGLAS DEL MOTOR:", weight="bold", color="#8B949E", size=11), ft.Text("1. Tu función principal siempre debe ser 'function main() { ... }'.\n2. Para devolver la pieza final, usa 'return objeto;'.\n3. Operaciones booleanas: pieza.union(b), pieza.subtract(b), pieza.intersect(b).\n4. Globals automáticos: GW (ancho), GL (largo), GH (alto), GT (grosor), G_TOL (tolerancia).", size=11, color="#E6EDF3")]))])

        row_snippets = ft.Row([ft.Text("Snippets:", color="#8B949E", size=12), ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[GW/2, GL/2, GH/2]});"), bgcolor="#21262D", color="white"), ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:32});"), bgcolor="#21262D", color="white")], scroll="auto")

        sw_ensamble = ft.Switch(label="Activar Ensamblador", value=False, active_color="#FFAB00")
        def toggle_ensamble(e):
            nonlocal modo_ensamble
            modo_ensamble = sw_ensamble.value
            panel_ensamble_ops.visible = modo_ensamble; page.update()
        sw_ensamble.on_change = toggle_ensamble

        def parse_current_tool_to_stack_var():
            code_lines = txt_code.value.split('\n')
            var_name = f"obj_{len(ensamble_stack)}"
            body = []
            for line in code_lines[1:-1]:
                if line.strip().startswith("return "):
                    ret_val = line.replace("return", "").replace(";", "").strip()
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
            final_code += f"  return {final_var};\n}}"
            txt_code.value = final_code; txt_code.update(); page.update()

        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton("➕ UNIR", on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", color="white", expand=True),
            ft.ElevatedButton("➖ RESTAR", on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", color="white", expand=True)
        ], visible=False)

        panel_globales = ft.Container(content=ft.Column([ft.Row([ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11), sw_ensamble], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), r_g_w, r_g_l, r_g_h, r_g_t, r_g_tol, panel_ensamble_ops]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        col_custom = ft.Column([ft.Text("Modo Código Libre (Edita en la pestaña CODE)", color="#00E676")], visible=True)
        def inst(texto): return ft.Text("ℹ️ " + texto, color="#FFD54F", size=11, italic=True)

        # =========================================================
        # HERRAMIENTA ESPECIAL: EXPLORADOR STL INTERNO Y HERRAMIENTAS FORGE
        # =========================================================
        lbl_stl_status = ft.Text("Ningún STL cargado aún en memoria.", color="#8B949E", size=11)

        sl_stl_sc, r_stl_sc = create_slider("Escala (%)", 1, 500, 100, True)
        sl_stl_x, r_stl_x = create_slider("Mover X", -150, 150, 0, False)
        sl_stl_y, r_stl_y = create_slider("Mover Y", -150, 150, 0, False)
        sl_stl_z, r_stl_z = create_slider("Mover Z", -150, 150, 0, False)

        panel_stl_transform = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🔄 TRANSFORMACIÓN BASE STL", color="#00E676", weight="bold"), lbl_stl_status]),
            ft.ElevatedButton("📂 BUSCAR STL EN ANDROID", on_click=lambda _: set_tab(3), bgcolor="#00E5FF", color="black", width=float('inf')),
            inst("El Motor Híbrido soldará automáticamente piezas multi-body."),
            r_stl_sc, r_stl_x, r_stl_y, r_stl_z
        ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"), visible=False)

        col_stl = ft.Column([ft.Text("Visor STL Original", color="#00E676", weight="bold")], visible=False)
        
        # --- ULTIMATE STL FORGE PANELS ---
        sl_stlf_z, r_stlf_z = create_slider("Corte Z (mm)", 0, 50, 1, False)
        col_stl_flatten = ft.Column([ft.Text("Aplanar Base (Flatten)", color="#00E676", weight="bold"), r_stlf_z], visible=False)

        dd_stls_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E")
        dd_stls_axis.on_change = update_code_wrapper
        sl_stls_pos, r_stls_pos = create_slider("Punto Corte", -150, 150, 0, False)
        col_stl_split = ft.Column([ft.Text("Cortador Avanzado (Split XYZ)", color="#00E676", weight="bold"), dd_stls_axis, r_stls_pos], visible=False)

        sl_stlc_s, r_stlc_s = create_slider("Caja Tamaño", 10, 300, 50, False)
        col_stl_crop = ft.Column([ft.Text("Aislar Objeto (Crop Box)", color="#00E676", weight="bold"), r_stlc_s], visible=False)

        dd_stld_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E")
        dd_stld_axis.on_change = update_code_wrapper
        sl_stld_r, r_stld_r = create_slider("Radio Perfo. (M3=1.6)", 0.5, 20, 1.6, False)
        sl_stld_px, r_stld_px = create_slider("Coord 1", -150, 150, 0, False)
        sl_stld_py, r_stld_py = create_slider("Coord 2", -150, 150, 0, False)
        col_stl_drill = ft.Column([ft.Text("Taladro 3D Universal", color="#00E676", weight="bold"), dd_stld_axis, r_stld_r, r_stld_px, r_stld_py], visible=False)

        sl_stlm_w, r_stlm_w = create_slider("Ancho Orejeta", 10, 100, 40, False)
        sl_stlm_d, r_stlm_d = create_slider("Separación Ext.", 20, 200, 80, False)
        col_stl_mount = ft.Column([ft.Text("Orejetas de Montaje (Screw Tabs)", color="#00E676", weight="bold"), r_stlm_w, r_stlm_d], visible=False)

        sl_stle_r, r_stle_r = create_slider("Radio Disco", 5, 30, 15, False)
        sl_stle_d, r_stle_d = create_slider("Apertura XY", 10, 200, 50, False)
        col_stl_ears = ft.Column([ft.Text("Discos Anti-Warping (Mouse Ears)", color="#00E676", weight="bold"), r_stle_r, r_stle_d], visible=False)

        sl_stlp_sx, r_stlp_sx = create_slider("Largo Parche X", 5, 100, 20, False)
        sl_stlp_sy, r_stlp_sy = create_slider("Ancho Parche Y", 5, 100, 20, False)
        sl_stlp_sz, r_stlp_sz = create_slider("Alto Parche Z", 1, 50, 5, False)
        col_stl_patch = ft.Column([ft.Text("Parche de Refuerzo de Bloque", color="#00E676", weight="bold"), r_stlp_sx, r_stlp_sy, r_stlp_sz], visible=False)

        sl_stlh_r, r_stlh_r = create_slider("Tamaño Hexágono", 2, 20, 5, False)
        col_stl_honeycomb = ft.Column([ft.Text("Aligerado Honeycomb Paramétrico", color="#00E676", weight="bold"), r_stlh_r], visible=False)

        sl_stlpg_r, r_stlpg_r = create_slider("Radio Hélice", 10, 100, 40, False)
        sl_stlpg_t, r_stlpg_t = create_slider("Grosor Aro", 1, 10, 3, False)
        sl_stlpg_x, r_stlpg_x = create_slider("Centro Aro X", -100, 100, 0, False)
        sl_stlpg_y, r_stlpg_y = create_slider("Centro Aro Y", -100, 100, 0, False)
        col_stl_propguard = ft.Column([ft.Text("Protector de Hélice (Prop-Guard)", color="#00E676", weight="bold"), r_stlpg_r, r_stlpg_t, r_stlpg_x, r_stlpg_y], visible=False)


        # =========================================================
        # HERRAMIENTAS Y PANELES (INTACTOS V20.7)
        # =========================================================
        tf_texto = ft.TextField(label="Escribe Texto", value="NEXUS", max_length=15, bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Fino"), ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Braille")], value="Voxel Grueso", expand=True, bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Solo Texto"), ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Soporte de Mesa"), ft.dropdown.Option("Colgante Militar"), ft.dropdown.Option("Placa Ovalada")], value="Colgante Militar", expand=True, bgcolor="#161B22")
        sw_txt_grabado = ft.Switch(label="Texto Grabado (Hueco)", value=False, active_color="#00E5FF")
        
        tf_texto.on_change = update_code_wrapper; dd_txt_estilo.on_change = update_code_wrapper; dd_txt_base.on_change = update_code_wrapper; sw_txt_grabado.on_change = update_code_wrapper

        col_texto = ft.Column([ft.Text("Tipografía y Placas Especiales", color="#880E4F", weight="bold"), inst("GH define el grosor de la placa. 'Grabado' hunde el texto en el material."), ft.Container(content=ft.Column([tf_texto, ft.Row([dd_txt_estilo, dd_txt_base]), sw_txt_grabado]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_las_x, r_las_x = create_slider("Ancho Objeto", 10, 200, 50, False); sl_las_y, r_las_y = create_slider("Largo Objeto", 10, 200, 50, False); sl_las_z, r_las_z = create_slider("Altura Z Corte", 0, 100, 5, False)
        col_laser = ft.Column([ft.Text("Perfil Láser", color="#D50000"), inst("Secciona cualquier modelo 3D en Z. Obten un perfil plano."), ft.Container(content=ft.Column([r_las_x, r_las_y, r_las_z]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_alin_f, r_alin_f = create_slider("Filas (Y)", 1, 10, 3, True); sl_alin_c, r_alin_c = create_slider("Columnas (X)", 1, 10, 3, True); sl_alin_dx, r_alin_dx = create_slider("Distancia X", 5, 100, 20, False); sl_alin_dy, r_alin_dy = create_slider("Distancia Y", 5, 100, 20, False); sl_alin_h, r_alin_h = create_slider("Altura Base", 2, 50, 10, False)
        col_array_lin = ft.Column([ft.Text("Matriz Lineal Grid", color="#00B0FF"), ft.Container(content=ft.Column([r_alin_f, r_alin_c, r_alin_dx, r_alin_dy, r_alin_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_apol_n, r_apol_n = create_slider("Repeticiones", 2, 36, 8, True); sl_apol_r, r_apol_r = create_slider("Radio Corona", 10, 150, 40, False); sl_apol_rp, r_apol_rp = create_slider("Radio Pieza", 2, 20, 5, False); sl_apol_h, r_apol_h = create_slider("Grosor (Z)", 2, 50, 5, False)
        col_array_pol = ft.Column([ft.Text("Matriz Polar Circular", color="#00B0FF"), ft.Container(content=ft.Column([r_apol_n, r_apol_r, r_apol_rp, r_apol_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_loft_w, r_loft_w = create_slider("Ancho Base SQ", 10, 150, 60, False); sl_loft_r, r_loft_r = create_slider("Radio Top", 5, 100, 20, False); sl_loft_h, r_loft_h = create_slider("Altura Z", 10, 200, 80, False); sl_loft_g, r_loft_g = create_slider("Grosor Pared", 1, 10, 2, False)
        col_loft = ft.Column([ft.Text("Lofting Adaptador", color="#D50000"), ft.Container(content=ft.Column([r_loft_w, r_loft_r, r_loft_h, r_loft_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_pan_x, r_pan_x = create_slider("Ancho X", 20, 200, 80, False); sl_pan_y, r_pan_y = create_slider("Largo Y", 20, 200, 80, False); sl_pan_z, r_pan_z = create_slider("Alto Z", 2, 50, 10, False); sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False)
        col_panal = ft.Column([ft.Text("Panal Honeycomb", color="#FBC02D"), ft.Container(content=ft.Column([r_pan_x, r_pan_y, r_pan_z, r_pan_r]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_vor_ro, r_vor_ro = create_slider("Radio Ext", 10, 100, 40, False); sl_vor_ri, r_vor_ri = create_slider("Radio Int", 5, 95, 35, False); sl_vor_h, r_vor_h = create_slider("Altura Tubo", 20, 200, 100, False); sl_vor_d, r_vor_d = create_slider("Densidad Red", 4, 24, 12, True)
        col_voronoi = ft.Column([ft.Text("Carcasa Voronoi", color="#FBC02D"), ft.Container(content=ft.Column([r_vor_ro, r_vor_ri, r_vor_h, r_vor_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_evo_d, r_evo_d = create_slider("Nº Dientes", 8, 60, 20, True); sl_evo_m, r_evo_m = create_slider("Módulo", 1, 10, 2, False); sl_evo_h, r_evo_h = create_slider("Grosor (Z)", 2, 50, 10, False)
        col_evolvente = ft.Column([ft.Text("Engranaje Evolvente", color="#FFAB00"), ft.Container(content=ft.Column([r_evo_d, r_evo_m, r_evo_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_crem_d, r_crem_d = create_slider("Nº Dientes", 5, 50, 15, True); sl_crem_m, r_crem_m = create_slider("Módulo", 1, 10, 2, False); sl_crem_h, r_crem_h = create_slider("Grosor (Z)", 2, 50, 10, False); sl_crem_w, r_crem_w = create_slider("Ancho Base", 2, 50, 8, False)
        col_cremallera = ft.Column([ft.Text("Cremallera", color="#FFAB00"), ft.Container(content=ft.Column([r_crem_d, r_crem_m, r_crem_h, r_crem_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_con_d, r_con_d = create_slider("Nº Dientes", 8, 40, 16, True); sl_con_rb, r_con_rb = create_slider("Radio Base", 10, 100, 30, False); sl_con_rt, r_con_rt = create_slider("Radio Top", 5, 80, 15, False); sl_con_h, r_con_h = create_slider("Altura Cono", 5, 100, 20, False)
        col_conico = ft.Column([ft.Text("Engranaje Cónico", color="#FFAB00"), ft.Container(content=ft.Column([r_con_d, r_con_rb, r_con_rt, r_con_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_mc_x, r_mc_x = create_slider("Ancho X", 20, 200, 60, False); sl_mc_y, r_mc_y = create_slider("Largo Y", 20, 200, 40, False); sl_mc_z, r_mc_z = create_slider("Alto Z", 10, 100, 30, False); sl_mc_tol, r_mc_tol = create_slider("Tol. Encaje", 0.0, 2.0, 0.4, False); sl_mc_sep, r_mc_sep = create_slider("Sep. Visual", 0, 50, 15, False)
        col_multicaja = ft.Column([ft.Text("Caja+Tapa (Multicuerpo)", color="#7CB342"), ft.Container(content=ft.Column([r_mc_x, r_mc_y, r_mc_z, r_mc_tol, r_mc_sep]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_perf_p, r_perf_p = create_slider("Nº Puntas", 3, 20, 5, True); sl_perf_re, r_perf_re = create_slider("Radio Ext", 10, 100, 40, False); sl_perf_ri, r_perf_ri = create_slider("Radio Int", 5, 80, 15, False); sl_perf_h, r_perf_h = create_slider("Grosor (Z)", 2, 50, 10, False)
        col_perfil = ft.Column([ft.Text("Estrella Paramétrica 2D", color="#AB47BC"), ft.Container(content=ft.Column([r_perf_p, r_perf_re, r_perf_ri, r_perf_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_rev_h, r_rev_h = create_slider("Altura Total", 20, 200, 80, False); sl_rev_r1, r_rev_r1 = create_slider("Radio Base", 10, 100, 30, False); sl_rev_r2, r_rev_r2 = create_slider("Radio Cuello", 5, 80, 15, False); sl_rev_g, r_rev_g = create_slider("Grosor Pared", 0, 15, 2, False)
        col_revolucion = ft.Column([ft.Text("Sólido de Revolución", color="#AB47BC"), ft.Container(content=ft.Column([r_rev_h, r_rev_r1, r_rev_r2, r_rev_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_c_grosor, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        col_cubo = ft.Column([ft.Text("Cubo Paramétrico", color="#8B949E"), r_c_g], visible=False)

        sl_p_rint, r_p_rint = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_lados, r_p_lados = create_slider("Caras (LowPoly)", 3, 64, 64, True)
        col_cilindro = ft.Column([ft.Text("Cilindro / Prisma", color="#8B949E"), r_p_rint, r_p_lados], visible=False)

        sl_l_largo, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False); sl_l_ancho, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False); sl_l_grosor, r_l_g = create_slider("Grosor Chapa", 1, 20, 3, False); sl_l_hueco, r_l_h = create_slider("Agujero", 0, 10, 2, False); sl_l_chaf, r_l_chaf = create_slider("Refuerzo Int", 0, 20, 5, False)
        col_escuadra = ft.Column([ft.Text("Escuadra Tipo L", color="#8B949E"), ft.Container(content=ft.Column([r_l_l, r_l_a, r_l_g, r_l_h, r_l_chaf]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_e_dientes, r_e_d = create_slider("Dientes", 6, 40, 16, True); sl_e_radio, r_e_r = create_slider("Radio Base", 10, 100, 30, False); sl_e_grosor, r_e_g = create_slider("Grosor", 2, 50, 5, False); sl_e_eje, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False)
        col_engranaje = ft.Column([ft.Text("Piñón Cuadrado Básico", color="#8B949E"), ft.Container(content=ft.Column([r_e_d, r_e_r, r_e_g, r_e_e]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False); sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False); sl_pcb_h, r_pcb_h = create_slider("Altura Caja", 10, 100, 20, False); sl_pcb_t, r_pcb_t = create_slider("Grosor Pared", 1, 10, 2, False)
        col_pcb = ft.Column([ft.Text("Caja para Electrónica", color="#8B949E"), ft.Container(content=ft.Column([r_pcb_x, r_pcb_y, r_pcb_h, r_pcb_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_v_l, r_v_l = create_slider("Longitud", 10, 300, 50, False)
        col_vslot = ft.Column([ft.Text("Perfil V-Slot 2020", color="#8B949E"), ft.Container(content=ft.Column([r_v_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False); sl_bi_d, r_bi_d = create_slider("Diámetro Eje", 5, 30, 10, False)
        col_bisagra = ft.Column([ft.Text("Bisagra Print-in-Place", color="#8B949E"), ft.Container(content=ft.Column([r_bi_l, r_bi_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_clamp_d, r_clamp_d = create_slider("Ø Tubo", 10, 100, 25, False); sl_clamp_g, r_clamp_g = create_slider("Grosor Arco", 2, 15, 5, False); sl_clamp_w, r_clamp_w = create_slider("Ancho Pieza", 5, 50, 15, False)
        col_abrazadera = ft.Column([ft.Text("Abrazadera de Tubo", color="#8B949E"), ft.Container(content=ft.Column([r_clamp_d, r_clamp_g, r_clamp_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True); sl_fij_l, r_fij_l = create_slider("Largo Tornillo", 0, 100, 30, False)
        col_fijacion = ft.Column([ft.Text("Tuerca / Tornillo Hex", color="#FFAB00"), ft.Container(content=ft.Column([r_fij_m, r_fij_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_rod_dint, r_rod_dint = create_slider("Ø Eje Interno", 3, 50, 8, False); sl_rod_dext, r_rod_dext = create_slider("Ø Externo", 10, 100, 22, False); sl_rod_h, r_rod_h = create_slider("Altura", 3, 30, 7, False)
        col_rodamiento = ft.Column([ft.Text("Rodamiento de Bolas", color="#FFAB00"), ft.Container(content=ft.Column([r_rod_dint, r_rod_dext, r_rod_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_plan_rs, r_plan_rs = create_slider("Radio Sol", 5, 40, 10, False); sl_plan_rp, r_plan_rp = create_slider("Radio Planetas", 4, 30, 8, False); sl_plan_h, r_plan_h = create_slider("Grosor Total", 3, 30, 6, False)
        col_planetario = ft.Column([ft.Text("Mecanismo Planetario", color="#FFAB00"), ft.Container(content=ft.Column([r_plan_rs, r_plan_rp, r_plan_h]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_pol_t, r_pol_t = create_slider("Nº Dientes", 10, 60, 20, True); sl_pol_w, r_pol_w = create_slider("Ancho Correa", 4, 20, 6, False); sl_pol_d, r_pol_d = create_slider("Ø Eje Motor", 2, 12, 5, False)
        col_polea = ft.Column([ft.Text("Polea Dentada GT2", color="#00E5FF"), ft.Container(content=ft.Column([r_pol_t, r_pol_w, r_pol_d]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_hel_r, r_hel_r = create_slider("Radio Total", 20, 150, 50, False); sl_hel_n, r_hel_n = create_slider("Nº Aspas", 2, 12, 4, True); sl_hel_p, r_hel_p = create_slider("Torsión", 10, 80, 45, False)
        col_helice = ft.Column([ft.Text("Hélice Paramétrica", color="#00E5FF"), ft.Container(content=ft.Column([r_hel_r, r_hel_n, r_hel_p]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_rot_r, r_rot_r = create_slider("Radio Bola", 5, 30, 10, False)
        col_rotula = ft.Column([ft.Text("Rótula Articulada", color="#00E5FF"), ft.Container(content=ft.Column([r_rot_r]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_car_x, r_car_x = create_slider("Ancho (X)", 20, 200, 80, False); sl_car_y, r_car_y = create_slider("Largo (Y)", 20, 200, 120, False); sl_car_z, r_car_z = create_slider("Alto (Z)", 10, 100, 30, False); sl_car_t, r_car_t = create_slider("Grosor Pared", 1, 5, 2, False)
        col_carcasa = ft.Column([ft.Text("Carcasa Smart con Ventilación", color="#00E5FF"), ft.Container(content=ft.Column([r_car_x, r_car_y, r_car_z, r_car_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_mue_r, r_mue_r = create_slider("Radio Resorte", 5, 50, 15, False); sl_mue_h, r_mue_h = create_slider("Radio Hilo", 1, 10, 2, False); sl_mue_v, r_mue_v = create_slider("Nº Vueltas", 2, 20, 5, False); sl_mue_alt, r_mue_alt = create_slider("Altura Total", 10, 200, 40, False)
        col_muelle = ft.Column([ft.Text("Muelle Helicoidal", color="#FFAB00"), ft.Container(content=ft.Column([r_mue_r, r_mue_h, r_mue_v, r_mue_alt]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_acme_d, r_acme_d = create_slider("Diámetro Eje", 4, 30, 8, False); sl_acme_p, r_acme_p = create_slider("Paso (Pitch)", 1, 10, 2, False); sl_acme_l, r_acme_l = create_slider("Longitud", 10, 200, 50, False)
        col_acme = ft.Column([ft.Text("Eje Roscado (ACME)", color="#FFAB00"), ft.Container(content=ft.Column([r_acme_d, r_acme_p, r_acme_l]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_codo_r, r_codo_r = create_slider("Radio Tubo", 2, 50, 10, False); sl_codo_c, r_codo_c = create_slider("Radio Curva", 10, 150, 30, False); sl_codo_a, r_codo_a = create_slider("Ángulo Giroº", 10, 180, 90, False); sl_codo_g, r_codo_g = create_slider("Grosor Hueco", 0, 10, 2, False)
        col_codo = ft.Column([ft.Text("Tubería y Codos", color="#00E5FF"), ft.Container(content=ft.Column([r_codo_r, r_codo_c, r_codo_a, r_codo_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_naca_c, r_naca_c = create_slider("Cuerda", 20, 200, 80, False); sl_naca_g, r_naca_g = create_slider("Grosor Max %", 5, 30, 15, False); sl_naca_e, r_naca_e = create_slider("Envergadura Z", 10, 300, 100, False)
        col_naca = ft.Column([ft.Text("Perfil Alar NACA", color="#00E5FF"), ft.Container(content=ft.Column([r_naca_c, r_naca_g, r_naca_e]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_st_ang, r_st_ang = create_slider("Inclinación º", 5, 45, 15, False); sl_st_w, r_st_w = create_slider("Ancho Base", 40, 120, 70, False); sl_st_t, r_st_t = create_slider("Grosor Dispo.", 6, 20, 12, False)
        col_stand_movil = ft.Column([ft.Text("Soporte para Móvil/Tablet", color="#00E676"), inst("Soporte de escritorio rígido con labio de sujeción frontal."), ft.Container(content=ft.Column([r_st_ang, r_st_w, r_st_t]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_clip_d, r_clip_d = create_slider("Ø Cable", 3, 15, 6, False); sl_clip_w, r_clip_w = create_slider("Ancho Adhesivo", 10, 40, 20, False)
        col_clip_cable = ft.Column([ft.Text("Clip de Cables (Desk)", color="#00E676"), inst("Organizador de cables. Imprime boca abajo. Añade cinta de doble cara en la base plana."), ft.Container(content=ft.Column([r_clip_d, r_clip_w]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        sl_vr_s, r_vr_s = create_slider("Tamaño Base", 50, 500, 200, False)
        col_vr_pedestal = ft.Column([ft.Text("Pedestal de Exhibición (Modo VR)", color="#B388FF"), inst("Usa esto como base en el Ensamblador antes de colocar tu modelo encima para verlo en Realidad Virtual."), ft.Container(content=ft.Column([r_vr_s]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)


        # === GENERADOR DE CÓDIGO JS CON HÍBRIDO MÚLTIPLE INYECTADO ===
        def get_stl_base_js():
            sc = sl_stl_sc.value / 100.0; tx = sl_stl_x.value; ty = sl_stl_y.value; tz = sl_stl_z.value
            return f"""  var sc = {sc}; var tx = {tx}; var ty = {ty}; var tz = {tz};
  var dron = null;
  if (typeof IMPORTED_STL !== 'undefined') {{
      if (Array.isArray(IMPORTED_STL) && IMPORTED_STL.length > 0) {{
          dron = IMPORTED_STL[0];
          for(var i = 1; i < IMPORTED_STL.length; i++) {{ dron = dron.union(IMPORTED_STL[i]); }}
      }} else {{ dron = IMPORTED_STL; }}
  }}
  if(!dron || !dron.polygons) {{ return CSG.cube({{radius:[0.1,0.1,0.1]}}); }}
  dron = dron.scale([sc, sc, sc]).translate([tx, ty, tz]);
"""

        def generate_param_code():
            h = herramienta_actual
            code = "function main() {\n"
            
            if h == "custom": pass
            
            elif h.startswith("stl"):
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
                    r = sl_stlpg_r.value; t = sl_stlpg_t.value; px = sl_stlpg_x.value; py = sl_stlpg_y.value
                    code += f"  var out = CSG.cylinder({{start:[{px},{py},0], end:[{px},{py},10], radius:{r+t}, slices:32}});\n"
                    code += f"  var inn = CSG.cylinder({{start:[{px},{py},-1], end:[{px},{py},11], radius:{r}, slices:32}});\n"
                    code += f"  return dron.union(out.subtract(inn));\n}}"

            elif h == "texto":
                txt_input = tf_texto.value.upper()[:15]; estilo = dd_txt_estilo.value; base = dd_txt_base.value; grabado = sw_txt_grabado.value
                if not txt_input: txt_input = " "
                code += f"  var texto = \"{txt_input}\"; var h = GH;\n"
                code += f"  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0], '0':[14,17,17,17,14], '1':[4,12,4,4,14], '2':[14,1,14,16,31], '3':[14,1,14,1,14], '4':[18,18,31,2,2], '5':[31,16,14,1,14], '6':[14,16,30,17,14], '7':[31,1,2,4,8], '8':[14,17,14,17,14], '9':[14,17,15,1,14] }};\n"
                z_start = "h/2" if not grabado else "h - 1"
                h_letra = "h/2" if not grabado else "h+2"

                if "Voxel" in estilo:
                    es_grueso = "1.1" if "Grueso" in estilo else "2.1"
                    code += f"""
  var pText = null; var vSize = 2; var charWidth = 6 * vSize;
  for(var i=0; i<texto.length; i++) {{
    var cMat = font[texto[i]] || font[' ']; var offX = i * charWidth; 
    for(var r=0; r<5; r++) {{ for(var c=0; c<5; c++) {{
        if ((cMat[r] >> (4 - c)) & 1) {{
           var vox = CSG.cube({{center:[offX+(c*vSize), (4-r)*vSize, {z_start}], radius:[vSize/{es_grueso}, vSize/{es_grueso}, {h_letra}/2]}});
           if(pText === null) pText = vox; else pText = pText.union(vox);
        }}
    }} }}
  }}
  var totalL = Math.max(texto.length * charWidth, 10);
"""
                elif estilo == "Braille":
                    rad_braille = "1.5" if not grabado else "1.8"
                    code += f"""
  var braille = {{ 'A':[1], 'B':[1,2], 'C':[1,4], 'D':[1,4,5], 'E':[1,5], 'F':[1,2,4], 'G':[1,2,4,5], 'H':[1,2,5], 'I':[2,4], 'J':[2,4,5], 'K':[1,3], 'L':[1,2,3], 'M':[1,3,4], 'N':[1,3,4,5], 'O':[1,3,5], 'P':[1,2,3,4], 'Q':[1,2,3,4,5], 'R':[1,2,3,5], 'S':[2,3,4], 'T':[2,3,4,5], 'U':[1,3,6], 'V':[1,2,3,6], 'W':[2,4,5,6], 'X':[1,3,4,6], 'Y':[1,3,4,5,6], 'Z':[1,3,5,6], ' ':[0] }};
  var pText = null; var stepX = 4; var stepY = 4; var charWidth = 10;
  for(var i=0; i<texto.length; i++) {{
    var dots = braille[texto[i]] || [1]; var offX = i * charWidth;
    for(var d=0; d<dots.length; d++) {{
        var p = dots[d]; if (p === 0) continue;
        var cx = (p>3) ? stepX : 0; var cy = ((p-1)%3 === 0) ? stepY*2 : (((p-1)%3 === 1) ? stepY : 0);
        var domo = CSG.sphere({{center:[offX+cx, cy, {z_start}], radius:{rad_braille}, resolution:16}});
        if(pText === null) pText = domo; else pText = pText.union(domo);
    }}
  }}
  var totalL = Math.max(texto.length * charWidth, 10);
"""
                code += "  if (pText === null) pText = CSG.cube({center:[0,0,0], radius:[0.01, 0.01, 0.01]});\n  var baseObj = null;\n"
                if base == "Llavero (Anilla)": 
                    code += "  var bc = CSG.cube({center:[(totalL/2)-3, 3, h/4], radius:[(totalL/2)+2, 8, h/4]});\n  var anclaje = CSG.cylinder({start:[totalL, 3, 0], end:[totalL, 3, h/2], radius:6, slices:32}).subtract(CSG.cylinder({start:[totalL, 3, -1], end:[totalL, 3, h/2+1], radius:3, slices:16}));\n  baseObj = bc.union(anclaje);\n"
                elif base == "Placa Atornillable": 
                    code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+10, 10, h/4]});\n  var h1 = CSG.cylinder({start:[-8, 3, -1], end:[-8, 3, h], radius:2.5, slices:16});\n  var h2 = CSG.cylinder({start:[totalL+2, 3, -1], end:[totalL+2, 3, h], radius:2.5, slices:16});\n  baseObj = bc.subtract(h1).subtract(h2);\n"
                elif base == "Soporte de Mesa": 
                    code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+2, 5, h/4]});\n  var pata = CSG.cube({center:[totalL/2-3, -5, h/8], radius:[totalL/2+2, 10, h/8]});\n  baseObj = bc.union(pata);\n"
                elif base == "Colgante Militar":
                    code += "  var b_cen = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 10, h/4]});\n  var b_izq = CSG.cylinder({start:[-4, 4, 0], end:[-4, 4, h/2], radius:10, slices:32});\n  var b_der = CSG.cylinder({start:[totalL-2, 4, 0], end:[totalL-2, 4, h/2], radius:10, slices:32});\n  var agujero = CSG.cylinder({start:[-8, 4, -1], end:[-8, 4, h], radius:2.5, slices:16});\n  baseObj = b_cen.union(b_izq).union(b_der).subtract(agujero);\n"
                elif base == "Placa Ovalada":
                    code += "  var c1 = CSG.cylinder({start:[-2, 4, 0], end:[-2, 4, h/2], radius:12, slices:64});\n  var c2 = CSG.cylinder({start:[totalL-4, 4, 0], end:[totalL-4, 4, h/2], radius:12, slices:64});\n  var p_med = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 12, h/4]});\n  baseObj = p_med.union(c1).union(c2);\n"

                code += "  if(baseObj !== null) {\n"
                if grabado: code += "      return baseObj.subtract(pText);\n  } else {\n      return pText;\n  }\n}"
                else: code += "      return baseObj.union(pText);\n  } else {\n      return pText;\n  }\n}"

            elif h == "cubo":
                g = sl_c_grosor.value
                code += f"  var pieza = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}});\n"
                if g > 0: code += f"  var int_box = CSG.cube({{center:[0,0,GH/2 + {g}], radius:[GW/2 - {g}, GL/2 - {g}, GH/2]}});\n  pieza = pieza.subtract(int_box);\n"
                code += f"  return pieza;\n}}"

            elif h == "cilindro":
                rint = sl_p_rint.value; c = int(sl_p_lados.value)
                code += f"  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:{c}}});\n"
                if rint > 0: code += f"  var int_cyl = CSG.cylinder({{start:[0,0,-1], end:[0,0,GH+2], radius:{rint}, slices:{c}}});\n  pieza = pieza.subtract(int_cyl);\n"
                code += f"  return pieza;\n}}"

            elif h == "laser":
                code += f"  var w = {sl_las_x.value}; var l = {sl_las_y.value}; var z_cut = {sl_las_z.value};\n"
                code += f"  var base_obj = CSG.cube({{center:[0,0,10], radius:[w/2, l/2, 10]}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,21], radius:5, slices:16}}));\n"
                code += f"  var cut_plane = CSG.cube({{center:[0,0,z_cut], radius:[w, l, 0.5]}});\n  return base_obj.intersect(cut_plane);\n}}"

            elif h == "array_lin":
                code += f"  var filas = {int(sl_alin_f.value)}; var columnas = {int(sl_alin_c.value)}; var dx = {sl_alin_dx.value}; var dy = {sl_alin_dy.value}; var h = {sl_alin_h.value};\n"
                code += f"  var array_obj = null; var start_x = -((columnas - 1) * dx) / 2; var start_y = -((filas - 1) * dy) / 2;\n"
                code += f"  for(var i=0; i<filas; i++) {{ for(var j=0; j<columnas; j++) {{\n"
                code += f"      var px = start_x + (j * dx); var py = start_y + (i * dy);\n"
                code += f"      var pieza = CSG.cylinder({{start:[px,py,0], end:[px,py,h], radius:5, slices:16}});\n"
                code += f"      if(array_obj === null) array_obj = pieza; else array_obj = array_obj.union(pieza);\n"
                code += f"  }} }}\n  return array_obj || CSG.cube({{radius:[1,1,1]}});\n}}"

            elif h == "array_pol":
                code += f"  var n = {int(sl_apol_n.value)}; var radio_corona = {sl_apol_r.value}; var r_pieza = {sl_apol_rp.value}; var h = {sl_apol_h.value};\n"
                code += f"  var array_obj = null;\n"
                code += f"  for(var i=0; i<n; i++) {{\n      var a = (i * Math.PI * 2) / n; var px = Math.cos(a) * radio_corona; var py = Math.sin(a) * radio_corona;\n"
                code += f"      var pieza = CSG.cylinder({{start:[px,py,0], end:[px,py,h], radius:r_pieza, slices:16}});\n"
                code += f"      if(array_obj === null) array_obj = pieza; else array_obj = array_obj.union(pieza);\n  }}\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,h/2], radius:radio_corona + r_pieza + 2, slices:32}});\n"
                code += f"  if(array_obj !== null) base = base.subtract(array_obj);\n  return base;\n}}"

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
                code += f"          if(loft_obj === null) loft_obj = p_ext; else loft_obj = loft_obj.union(p_ext);\n"
                code += f"          if(hueco === null) hueco = p_int; else hueco = hueco.union(p_int);\n      }}\n  }}\n"
                code += f"  return loft_obj || CSG.cube({{radius:[1,1,1]}});\n}}"

            elif h == "panal":
                code += f"  var w = {sl_pan_x.value}; var l = {sl_pan_y.value}; var h = {sl_pan_z.value}; var r_hex = {sl_pan_r.value}; var t = 1.5;\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}}); var int_box = CSG.cube({{center:[0,0,h/2], radius:[w/2-t, l/2-t, h/2+1]}});\n"
                code += f"  var frame = ext.subtract(int_box); var core_vol = CSG.cube({{center:[0,0,h/2], radius:[w/2-t, l/2-t, h/2]}});\n"
                code += f"  var holes = null; var dx = r_hex * 1.732 + t; var dy = r_hex * 1.5 + t;\n"
                code += f"  for(var x = -w/2 + r_hex; x < w/2; x += dx) {{ for(var y = -l/2 + r_hex; y < l/2; y += dy) {{\n"
                code += f"      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0; var cx = x + offset;\n"
                code += f"      if(cx < w/2 - r_hex && cx > -w/2 + r_hex) {{\n"
                code += f"          var hex = CSG.cylinder({{start:[cx, y, -1], end:[cx, y, h+1], radius:r_hex, slices:6}});\n"
                code += f"          if(holes === null) holes = hex; else holes = holes.union(hex);\n      }}\n  }} }}\n"
                code += f"  if(holes !== null) core_vol = core_vol.subtract(holes);\n  return frame.union(core_vol);\n}}"

            elif h == "voronoi":
                code += f"  var r_out = {sl_vor_ro.value}; var r_in = {sl_vor_ri.value}; var h = {sl_vor_h.value}; var d = {int(sl_vor_d.value)};\n"
                code += f"  var pipe = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_out, slices:32}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:r_in, slices:32}}));\n"
                code += f"  var holes = null; var z_step = (r_out - r_in) * 2.5; var r_esfera = (r_out - r_in) * 1.8; var t = 0;\n"
                code += f"  for(var z = z_step; z < h - z_step; z += z_step) {{\n      var offset_a = (t % 2 === 1) ? Math.PI/d : 0;\n"
                code += f"      for(var i=0; i<d; i++) {{\n          var a = (i * Math.PI * 2 / d) + offset_a;\n"
                code += f"          var cx = Math.cos(a) * (r_out - (r_out-r_in)/2); var cy = Math.sin(a) * (r_out - (r_out-r_in)/2);\n"
                code += f"          var hole = CSG.sphere({{center:[cx, cy, z], radius:r_esfera, resolution:8}});\n"
                code += f"          if(holes === null) holes = hole; else holes = holes.union(hole);\n      }}\n      t++;\n  }}\n"
                code += f"  if(holes !== null) return pipe.subtract(holes);\n  return pipe;\n}}"

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
                code += f"  var hole = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius: r_root * 0.3, slices:32}});\n  return gear.subtract(hole);\n}}"

            elif h == "cremallera":
                code += f"  var dientes = {int(sl_crem_d.value)}; var m = {sl_crem_m.value}; var h = {sl_crem_h.value}; var w = {sl_crem_w.value};\n"
                code += f"  var pitch = Math.PI * m; var len = dientes * pitch;\n"
                code += f"  var rack = CSG.cube({{center:[len/2, w/2, h/2], radius:[len/2, w/2, h/2]}}); var t_w = pitch / 2;\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n      var px = i * pitch + pitch/2;\n"
                code += f"      var t1 = CSG.cube({{center:[px, w + m*0.2, h/2], radius:[t_w*0.4, m*0.3, h/2]}});\n"
                code += f"      var t2 = CSG.cube({{center:[px, w + m*0.7, h/2], radius:[t_w*0.2, m*0.4, h/2]}});\n"
                code += f"      rack = rack.union(t1).union(t2);\n  }}\n  return rack;\n}}"

            elif h == "conico":
                code += f"  var dientes = {int(sl_con_d.value)}; var rb = {sl_con_rb.value}; var rt = {sl_con_rt.value}; var h = {sl_con_h.value};\n"
                code += f"  var res = 20; var dz = h / res; var gear = null; var m = rb / (dientes/2);\n"
                code += f"  for(var z=0; z<res; z++) {{\n      var z_pos = z * dz; var r_curr = rb - (rb - rt)*(z/res); var r_root = Math.max(0.1, r_curr - m);\n"
                code += f"      var core = CSG.cylinder({{start:[0,0,z_pos], end:[0,0,z_pos+dz], radius:r_root, slices:32}});\n"
                code += f"      if(gear === null) gear = core; else gear = gear.union(core);\n"
                code += f"      var t_w = (Math.PI * r_curr / dientes) * 0.8;\n"
                code += f"      for(var i=0; i<dientes; i++) {{\n          var a = (i * Math.PI * 2) / dientes;\n"
                code += f"          var cx1 = Math.cos(a)*(r_root + m*0.3); var cy1 = Math.sin(a)*(r_root + m*0.3);\n"
                code += f"          var cx2 = Math.cos(a)*r_curr;           var cy2 = Math.sin(a)*r_curr;\n"
                code += f"          var t1 = CSG.cylinder({{start:[cx1,cy1,z_pos], end:[cx1,cy1,z_pos+dz], radius:t_w*0.6, slices:8}});\n"
                code += f"          var t2 = CSG.cylinder({{start:[cx2,cy2,z_pos], end:[cx2,cy2,z_pos+dz], radius:t_w*0.3, slices:8}});\n"
                code += f"          gear = gear.union(t1).union(t2);\n      }}\n  }}\n"
                code += f"  var hole = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius: rt * 0.3, slices:16}});\n"
                code += f"  if(gear !== null) return gear.subtract(hole);\n  return CSG.cube({{radius:[1,1,1]}});\n}}"

            elif h == "multicaja":
                code += f"  var w = {sl_mc_x.value}; var l = {sl_mc_y.value}; var h = {sl_mc_z.value}; var tol = {sl_mc_tol.value}; var sep = {sl_mc_sep.value};\n"
                code += f"  var t = 2; var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}});\n"
                code += f"  var int_box = CSG.cube({{center:[0,0,h/2+t], radius:[w/2-t, l/2-t, h/2]}}); var caja = ext.subtract(int_box);\n"
                code += f"  var offsetZ = h + sep; var tapa_b = CSG.cube({{center:[0,0, offsetZ + t/2], radius:[w/2, l/2, t/2]}});\n"
                code += f"  var tapa_i = CSG.cube({{center:[0,0, offsetZ - t/2], radius:[w/2-t-tol, l/2-t-tol, t/2]}}); var tapa = tapa_b.union(tapa_i);\n"
                code += f"  return caja.union(tapa);\n}}"

            elif h == "perfil":
                code += f"  var puntas = {int(sl_perf_p.value)}; var rext = {sl_perf_re.value}; var rint = {sl_perf_ri.value}; var h = {sl_perf_h.value};\n"
                code += f"  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:rint, slices:32}});\n"
                code += f"  var d_theta = (Math.PI * 2) / puntas; var r_punta = (rext - rint) / 1.5;\n"
                code += f"  for(var i=0; i<puntas; i++) {{\n     var a = i * d_theta; var px = Math.cos(a) * (rint + r_punta*0.8); var py = Math.sin(a) * (rint + r_punta*0.8);\n"
                code += f"     var punta = CSG.cylinder({{start:[px, py, 0], end:[px, py, h], radius:r_punta, slices:16}});\n"
                code += f"     pieza = pieza.union(punta);\n  }}\n  return pieza;\n}}"

            elif h == "revolucion":
                code += f"  var h = {sl_rev_h.value}; var r1 = {sl_rev_r1.value}; var r2 = {sl_rev_r2.value}; var grosor = {sl_rev_g.value};\n"
                code += f"  var res = 60; var dz = h / res; var solido = null; var hueco = null;\n"
                code += f"  for(var i=0; i<res; i++) {{\n      var z = i * dz; var f = Math.sin((z/h) * Math.PI); var rad = r1 + (r2 - r1)*(z/h) + (f * 15);\n"
                code += f"      var capa = CSG.cylinder({{start:[0,0,z], end:[0,0,z+dz], radius:rad, slices:32}});\n"
                code += f"      if(solido === null) solido = capa; else solido = solido.union(capa);\n"
                code += f"      if (grosor > 0 && z > grosor) {{\n         var r_int = Math.max(0.1, rad - grosor);\n"
                code += f"         var capa_h = CSG.cylinder({{start:[0,0,z], end:[0,0,z+dz+0.1], radius:r_int, slices:32}});\n"
                code += f"         if(hueco === null) hueco = capa_h; else hueco = hueco.union(capa_h);\n      }}\n  }}\n"
                code += f"  if(grosor > 0 && hueco !== null) solido = solido.subtract(hueco);\n  return solido;\n}}"

            elif h == "escuadra":
                code += f"  var l = {sl_l_largo.value}; var w = {sl_l_ancho.value}; var t = {sl_l_grosor.value}; var r = {sl_l_hueco.value}; var chaf = {sl_l_chaf.value};\n"
                code += f"  var base = CSG.cube({{center:[l/2, w/2, t/2], radius:[l/2, w/2, t/2]}}); var wall = CSG.cube({{center:[t/2, w/2, l/2], radius:[t/2, w/2, l/2]}}); var pieza = base.union(wall);\n"
                if sl_l_chaf.value > 0: code += f"  var fillet = CSG.cylinder({{start:[t, 0, t], end:[t, w, t], radius:chaf, slices:16}}); pieza = pieza.union(fillet);\n"
                if sl_l_hueco.value > 0: code += f"  var h1 = CSG.cylinder({{start:[l*0.7, w/2, -1], end:[l*0.7, w/2, t+1], radius:r, slices:32}});\n  var h2 = CSG.cylinder({{start:[-1, w/2, l*0.7], end:[t+1, w/2, l*0.7], radius:r, slices:32}});\n  pieza = pieza.subtract(h1).subtract(h2);\n"
                code += f"  return pieza;\n}}"
                
            elif h == "engranaje":
                code += f"  var dientes = {int(sl_e_dientes.value)}; var r = {sl_e_radio.value}; var h = {sl_e_grosor.value};\n"
                code += f"  var d_x = r*0.15; var d_y = r*0.2;\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var diente = CSG.cube({{center:[Math.cos(a)*r, Math.sin(a)*r, h/2], radius:[d_x, d_y, h/2]}}); pieza = pieza.union(diente);\n  }}\n"
                if sl_e_eje.value > 0: code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{sl_e_eje.value} + G_TOL, slices:32}}); pieza = pieza.subtract(hueco);\n"
                code += f"  return pieza;\n}}"

            elif h == "pcb":
                code += f"  var px = {sl_pcb_x.value}; var py = {sl_pcb_y.value}; var h = {sl_pcb_h.value}; var t = {sl_pcb_t.value};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[px/2 + t, py/2 + t, h/2]}});\n"
                code += f"  var int_box = CSG.cube({{center:[0,0,h/2 + t], radius:[px/2, py/2, h/2]}}); var pieza = ext.subtract(int_box);\n"
                code += f"  var dx = px/2 - 3.5; var dy = py/2 - 3.5; var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n    var cyl = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 0], end:[m[i][0]*dx, m[i][1]*dy, h-2], radius: 3.5, slices:16}});\n"
                code += f"    var hole = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 2], end:[m[i][0]*dx, m[i][1]*dy, h], radius: 1.5 + (G_TOL/2), slices:16}});\n"
                code += f"    pieza = pieza.union(cyl).subtract(hole);\n  }}\n  return pieza;\n}}"

            elif h == "vslot":
                code += f"  var l = {sl_v_l.value};\n  var pieza = CSG.cube({{center:[0,0,l/2], radius:[10,10,l/2]}});\n"
                code += f"  var ch = CSG.cylinder({{start:[0,0,-1], end:[0,0,l+1], radius:2.1 + (G_TOL/2), slices:32}}); pieza = pieza.subtract(ch);\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,-10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,-8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[-10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[-8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  return pieza;\n}}"

            elif h == "bisagra":
                code += f"  var l = {sl_bi_l.value}; var d = {sl_bi_d.value};\n"
                code += f"  var fix = CSG.cylinder({{start:[0,0,0], end:[0,0,l/3], radius:d/2, slices:32}});\n"
                code += f"  var fix2 = CSG.cylinder({{start:[0,0,2*l/3], end:[0,0,l], radius:d/2, slices:32}});\n"
                code += f"  var move = CSG.cylinder({{start:[0,0,l/3+G_TOL], end:[0,0,2*l/3-G_TOL], radius:d/2, slices:32}});\n"
                code += f"  var pin = CSG.cylinder({{start:[0,0,l/3-d/4], end:[0,0,2*l/3+d/4], radius:(d/4)-G_TOL, slices:32}});\n"
                code += f"  var cut_pin = CSG.cylinder({{start:[0,0,l/3-d/2], end:[0,0,2*l/3+d/2], radius:d/4, slices:32}});\n"
                code += f"  var fijo = fix.union(fix2).subtract(cut_pin).union(pin);\n  var movil = move.subtract(cut_pin);\n  return fijo.union(movil);\n}}"

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
                code += f"  return arco.union(pestana).union(pestana2).subtract(m3).subtract(m3_2);\n}}"

            elif h == "fijacion":
                m, l_tornillo = sl_fij_m.value, sl_fij_l.value
                r_hex = (m * 1.8) / 2; h_cabeza = m * 0.8; r_eje = m / 2
                if l_tornillo == 0: 
                    code += f"  var m = {m}; var h = {h_cabeza};\n"
                    code += f"  var cuerpo = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:{r_hex}, slices:6}});\n"
                    code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:({r_eje} + G_TOL), slices:32}});\n  return cuerpo.subtract(agujero);\n}}"
                else: 
                    code += f"  var m = {m}; var l_tornillo = {l_tornillo}; var h_cabeza = {h_cabeza}; var r_hex = {r_hex};\n"
                    code += f"  var cabeza = CSG.cylinder({{start:[0,0,0], end:[0,0,h_cabeza], radius:r_hex, slices:6}});\n"
                    code += f"  var eje = CSG.cylinder({{start:[0,0,h_cabeza - 0.1], end:[0,0,h_cabeza + l_tornillo], radius:({r_eje} - G_TOL) - (m*0.08), slices:32}});\n"
                    code += f"  var pieza = cabeza.union(eje); var paso = m * 0.15;\n"
                    code += f"  for(var z = h_cabeza + 1; z < h_cabeza + l_tornillo - 1; z += paso*1.5) {{\n"
                    code += f"      var anillo = CSG.cylinder({{start:[0,0,z], end:[0,0,z+paso], radius:({r_eje} - G_TOL), slices:16}});\n"
                    code += f"      pieza = pieza.union(anillo);\n  }}\n  return pieza;\n}}"

            elif h == "rodamiento":
                code += f"  var d_int = {sl_rod_dint.value}; var d_ext = {sl_rod_dext.value}; var h = {sl_rod_h.value};\n"
                code += f"  var pista_ext = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:d_ext/2, slices:64}}).subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:(d_ext/2)-2 + G_TOL, slices:64}}) );\n"
                code += f"  var pista_int = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:(d_int/2)+2 - G_TOL, slices:64}}).subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:d_int/2, slices:64}}) );\n"
                code += f"  var pieza = pista_ext.union(pista_int);\n"
                code += f"  var r_espacio = (((d_ext/2)-2) - ((d_int/2)+2)) / 2; var radio_centro = ((d_int/2)+2 + (d_ext/2)-2)/2;\n"
                code += f"  var n_bolas = Math.floor((Math.PI * 2 * radio_centro) / (r_espacio * 2.2));\n"
                code += f"  for(var i=0; i<n_bolas; i++) {{\n      var a = (i * Math.PI * 2) / n_bolas; var bx = Math.cos(a) * radio_centro; var by = Math.sin(a) * radio_centro;\n"
                code += f"      var bola = CSG.sphere({{center:[bx, by, h/2], radius:(r_espacio*0.95) - (G_TOL/2), resolution:16}});\n"
                code += f"      pieza = pieza.union(bola);\n  }}\n  return pieza;\n}}"

            elif h == "planetario":
                code += f"  var r_sol = {sl_plan_rs.value}; var r_planeta = {sl_plan_rp.value}; var h = {sl_plan_h.value};\n"
                code += f"  var r_anillo = r_sol + (r_planeta*2); var dist_centros = r_sol + r_planeta;\n"
                code += f"  var sol = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_sol - 1, slices:32}});\n"
                code += f"  var dientes_sol = Math.floor(r_sol * 1.5);\n"
                code += f"  for(var i=0; i<dientes_sol; i++) {{\n      var a = (i * Math.PI * 2) / dientes_sol;\n"
                code += f"      var diente = CSG.cylinder({{start:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, 0], end:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, h], radius:1.2, slices:12}});\n"
                code += f"      sol = sol.union(diente);\n  }}\n"
                code += f"  sol = sol.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:3, slices:16}}));\n"
                code += f"  var planetas = null; var dientes_planeta = Math.floor(r_planeta * 1.5);\n"
                code += f"  for(var p=0; p<3; p++) {{\n      var ap = (p * Math.PI * 2) / 3; var cx = Math.cos(ap) * dist_centros; var cy = Math.sin(ap) * dist_centros;\n"
                code += f"      var planeta = CSG.cylinder({{start:[cx, cy, 0], end:[cx, cy, h], radius:r_planeta - 1 - G_TOL, slices:32}});\n"
                code += f"      for(var i=0; i<dientes_planeta; i++) {{\n          var a = (i * Math.PI * 2) / dientes_planeta;\n"
                code += f"          var px = cx + Math.cos(a)*(r_planeta - G_TOL); var py = cy + Math.sin(a)*(r_planeta - G_TOL);\n"
                code += f"          var diente_p = CSG.cylinder({{start:[px, py, 0], end:[px, py, h], radius:1.2 - (G_TOL/2), slices:12}});\n"
                code += f"          planeta = planeta.union(diente_p);\n      }}\n"
                code += f"      planeta = planeta.subtract(CSG.cylinder({{start:[cx, cy, -1], end:[cx, cy, h+1], radius:2, slices:12}}));\n"
                code += f"      if(planetas === null) planetas = planeta; else planetas = planetas.union(planeta);\n  }}\n"
                code += f"  var corona = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_anillo + 5, slices:64}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:r_anillo + G_TOL, slices:64}}));\n"
                code += f"  var dientes_corona = Math.floor(r_anillo * 1.5); var anillo_dientes = null;\n"
                code += f"  for(var i=0; i<dientes_corona; i++) {{\n      var a = (i * Math.PI * 2) / dientes_corona;\n"
                code += f"      var diente_c = CSG.cylinder({{start:[Math.cos(a)*(r_anillo + G_TOL), Math.sin(a)*(r_anillo + G_TOL), 0], end:[Math.cos(a)*(r_anillo + G_TOL), Math.sin(a)*(r_anillo + G_TOL), h], radius:1.2, slices:12}});\n"
                code += f"      if(anillo_dientes === null) anillo_dientes = diente_c; else anillo_dientes = anillo_dientes.union(diente_c);\n  }}\n"
                code += f"  if(anillo_dientes !== null) corona = corona.union(anillo_dientes);\n"
                code += f"  var obj = sol.union(corona);\n  if(planetas !== null) obj = obj.union(planetas);\n  return obj;\n}}"

            elif h == "polea":
                code += f"  var dientes = {int(sl_pol_t.value)}; var ancho = {sl_pol_w.value}; var r_eje = {sl_pol_d.value/2};\n"
                code += f"  var pitch = 2; var r_primitivo = (dientes * pitch) / (2 * Math.PI); var r_ext = r_primitivo - 0.25;\n"
                code += f"  var cuerpo = CSG.cylinder({{start:[0,0,1.5], end:[0,0,1.5+ancho], radius:r_ext, slices:64}});\n"
                code += f"  var matriz_dientes = null;\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n      var a = (i * Math.PI * 2) / dientes;\n"
                code += f"      var d = CSG.cylinder({{start:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 1], end:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 2+ancho], radius:0.55, slices:8}});\n"
                code += f"      if(matriz_dientes === null) matriz_dientes = d; else matriz_dientes = matriz_dientes.union(d);\n  }}\n"
                code += f"  if(matriz_dientes !== null) cuerpo = cuerpo.subtract(matriz_dientes);\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,1.5], radius:r_ext + 1, slices:64}});\n"
                code += f"  var tapa = CSG.cylinder({{start:[0,0,1.5+ancho], end:[0,0,3+ancho], radius:r_ext + 1, slices:64}});\n"
                code += f"  var polea = base.union(cuerpo).union(tapa);\n"
                code += f"  polea = polea.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,5+ancho], radius:r_eje + (G_TOL/2), slices:32}}));\n  return polea;\n}}"

            elif h == "helice":
                code += f"  var rad = {sl_hel_r.value}; var n = {int(sl_hel_n.value)}; var pitch = {sl_hel_p.value};\n"
                code += f"  var hub = CSG.cylinder({{start:[0,0,0], end:[0,0,10], radius:8, slices:32}});\n"
                code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,11], radius:2.5 + G_TOL, slices:16}});\n"
                code += f"  var aspas = null;\n"
                code += f"  for(var i=0; i<n; i++) {{\n    var a = (i * Math.PI * 2) / n; var dx = Math.cos(a); var dy = Math.sin(a);\n"
                code += f"    var aspa = CSG.cylinder({{start:[6*dx, 6*dy, 5 - (pitch/10)], end:[rad*dx, rad*dy, 5 + (pitch/10)], radius: 3, slices: 4}});\n"
                code += f"    if(aspas === null) aspas = aspa; else aspas = aspas.union(aspa);\n  }}\n"
                code += f"  if(aspas !== null) hub = hub.union(aspas);\n  return hub.subtract(agujero);\n}}"

            elif h == "rotula":
                code += f"  var r_bola = {sl_rot_r.value};\n"
                code += f"  var bola = CSG.sphere({{center:[0,0,0], radius:r_bola, resolution:32}}); var eje_bola = CSG.cylinder({{start:[0,0,0], end:[0,0,-r_bola*2], radius:r_bola*0.6, slices:32}});\n"
                code += f"  var componente_bola = bola.union(eje_bola);\n"
                code += f"  var copa_ext = CSG.cylinder({{start:[0,0,-r_bola*0.2], end:[0,0,r_bola*1.5], radius:r_bola+4, slices:32}});\n"
                code += f"  var hueco_bola = CSG.sphere({{center:[0,0,0], radius:r_bola+G_TOL, resolution:32}}); var apertura = CSG.cylinder({{start:[0,0,r_bola*0.5], end:[0,0,r_bola*2], radius:r_bola*0.8, slices:32}});\n"
                code += f"  var componente_copa = copa_ext.subtract(hueco_bola).subtract(apertura);\n  return componente_bola.union(componente_copa);\n}}"

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
                code += f"          if(vents === null) vents = agujero; else vents = vents.union(agujero);\n      }}\n  }}\n"
                code += f"  if(vents !== null) base = base.subtract(vents);\n  return base;\n}}"

            elif h == "muelle":
                code += f"  var r_res = {sl_mue_r.value}; var r_hilo = {sl_mue_h.value}; var h = {sl_mue_alt.value}; var vueltas = {sl_mue_v.value};\n"
                code += f"  var resorte = null; var pasos = Math.floor(vueltas * 24); var paso_z = h / pasos; var a_step = (Math.PI * 2 * vueltas) / pasos;\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n      var a1 = i * a_step; var a2 = (i+1) * a_step;\n"
                code += f"      var x1 = Math.cos(a1)*r_res; var y1 = Math.sin(a1)*r_res; var z1 = i*paso_z;\n"
                code += f"      var x2 = Math.cos(a2)*r_res; var y2 = Math.sin(a2)*r_res; var z2 = (i+1)*paso_z;\n"
                code += f"      var seg = CSG.cylinder({{start:[x1,y1,z1], end:[x2,y2,z2], radius:r_hilo, slices:8}});\n"
                code += f"      var esp = CSG.sphere({{center:[x2,y2,z2], radius:r_hilo, resolution:8}});\n"
                code += f"      if(resorte === null) resorte = seg.union(esp); else resorte = resorte.union(seg).union(esp);\n  }}\n  return resorte;\n}}"

            elif h == "acme":
                code += f"  var r = {sl_acme_d.value/2}; var pitch = {sl_acme_p.value}; var len = {sl_acme_l.value};\n"
                code += f"  var r_core = r - (pitch * 0.4); var eje = CSG.cylinder({{start:[0,0,0], end:[0,0,len], radius:r_core, slices:32}});\n"
                code += f"  var thread = null; var steps = Math.floor((len / pitch) * 24); var z_step = len / steps; var a_step = (Math.PI * 2 * (len/pitch)) / steps; var w = pitch * 0.35;\n"
                code += f"  for(var i=0; i<steps; i++) {{\n      var a1 = i * a_step; var a2 = (i+1) * a_step; var z1 = i * z_step; var z2 = (i+1) * z_step;\n"
                code += f"      var seg = CSG.cylinder({{start:[Math.cos(a1)*r, Math.sin(a1)*r, z1], end:[Math.cos(a2)*r, Math.sin(a2)*r, z2], radius:w, slices:8}});\n"
                code += f"      if(thread === null) thread = seg; else thread = thread.union(seg);\n  }}\n"
                code += f"  if(thread !== null) eje = eje.union(thread);\n  return eje;\n}}"

            elif h == "codo":
                code += f"  var r_tubo = {sl_codo_r.value}; var r_curva = {sl_codo_c.value}; var angulo = {sl_codo_a.value}; var grosor = {sl_codo_g.value};\n"
                code += f"  var codo = null; var pasos = Math.max(8, Math.floor(angulo / 5));\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n      var a1 = (i * (angulo/pasos)) * Math.PI / 180; var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"      var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva; var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"      var ext = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo, slices:16}});\n"
                code += f"      var esf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo, resolution:16}});\n"
                code += f"      var sol = ext.union(esf);\n      if(codo === null) codo = sol; else codo = codo.union(sol);\n  }}\n"
                code += f"  if(grosor > 0) {{\n     var hueco = null;\n     for(var i=0; i<pasos; i++) {{\n"
                code += f"         var a1 = (i * (angulo/pasos)) * Math.PI / 180; var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"         var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva; var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"         var int_c = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo-grosor, slices:12}});\n"
                code += f"         var isf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo-grosor, resolution:12}});\n"
                code += f"         var hol = int_c.union(isf); if(hueco === null) hueco = hol; else hueco = hueco.union(hol);\n"
                code += f"     }}\n     if(hueco !== null) codo = codo.subtract(hueco);\n  }}\n  return codo;\n}}"

            elif h == "naca":
                code += f"  var cuerda = {sl_naca_c.value}; var grosor = {sl_naca_g.value}; var envergadura = {sl_naca_e.value};\n"
                code += f"  var ala = null; var num_pasos = 40;\n"
                code += f"  for(var i=0; i<=num_pasos; i++) {{\n      var x = i/num_pasos;\n"
                code += f"      var yt = 5 * (grosor/100) * (0.2969*Math.sqrt(x) - 0.1260*x - 0.3516*(x*x) + 0.2843*Math.pow(x,3) - 0.1015*Math.pow(x,4));\n"
                code += f"      var x_real = x * cuerda; var yt_real = Math.max(yt * cuerda, 0.1);\n"
                code += f"      var cyl = CSG.cylinder({{start:[x_real, 0, 0], end:[x_real, 0, envergadura], radius: yt_real, slices: 16}});\n"
                code += f"      if(ala === null) ala = cyl; else ala = ala.union(cyl);\n  }}\n  return ala;\n}}"

            elif h == "stand_movil":
                code += f"  var ang = {sl_st_ang.value} * Math.PI / 180; var w = {sl_st_w.value}; var t = {sl_st_t.value};\n"
                code += f"  var base = CSG.cube({{center:[0, -20, t/2], radius:[w/2, 40, t/2]}});\n"
                code += f"  var h_back = 80; var dx = Math.sin(ang)*h_back; var dy = Math.cos(ang)*h_back;\n"
                code += f"  var back = CSG.cube({{center:[0, dy/2, dx/2], radius:[w/2, dy/2, dx/2]}});\n"
                code += f"  var lip = CSG.cube({{center:[0, -50, t + 5], radius:[w/2, t/2, 5]}});\n"
                code += f"  return base.union(back).union(lip);\n}}"

            elif h == "clip_cable":
                code += f"  var d = {sl_clip_d.value}; var w = {sl_clip_w.value}; var t = 3;\n"
                code += f"  var base = CSG.cube({{center:[0, 0, t/2], radius:[w/2, w/2, t/2]}});\n"
                code += f"  var anillo = CSG.cylinder({{start:[0,0,t], end:[0,0,t+w], radius:(d/2)+t, slices:32}});\n"
                code += f"  var hueco = CSG.cylinder({{start:[0,0,t-1], end:[0,0,t+w+1], radius:(d/2), slices:32}});\n"
                code += f"  var slot = CSG.cube({{center:[0, d, t+(w/2)], radius:[(d/2)-0.5, d, w/2+1]}});\n"
                code += f"  return base.union(anillo).subtract(hueco).subtract(slot);\n}}"

            elif h == "vr_pedestal":
                code += f"  var s = {sl_vr_s.value};\n"
                code += f"  var base1 = CSG.cube({{center:[0, 0, 10], radius:[s/2, s/2, 10]}});\n"
                code += f"  var base2 = CSG.cube({{center:[0, 0, 30], radius:[(s/2)-20, (s/2)-20, 10]}});\n"
                code += f"  var pillar = CSG.cylinder({{start:[0,0,40], end:[0,0,150], radius: s/4, slices:32}});\n"
                code += f"  var top = CSG.cylinder({{start:[0,0,150], end:[0,0,160], radius: (s/4)+10, slices:32}});\n"
                code += f"  return base1.union(base2).union(pillar).union(top);\n}}"

            if not modo_ensamble and h != "custom": 
                txt_code.value = code
            txt_code.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            
            tool_panels = {
                "custom": col_custom, "stl": col_stl, "stl_flatten": col_stl_flatten, "stl_split": col_stl_split,
                "stl_crop": col_stl_crop, "stl_drill": col_stl_drill, "stl_mount": col_stl_mount, "stl_ears": col_stl_ears,
                "stl_patch": col_stl_patch, "stl_honeycomb": col_stl_honeycomb, "stl_propguard": col_stl_propguard,
                "texto": col_texto, "cubo": col_cubo, "cilindro": col_cilindro, "laser": col_laser,
                "array_lin": col_array_lin, "array_pol": col_array_pol, "loft": col_loft, "panal": col_panal,
                "voronoi": col_voronoi, "evolvente": col_evolvente, "cremallera": col_cremallera, "conico": col_conico,
                "multicaja": col_multicaja, "perfil": col_perfil, "revolucion": col_revolucion, "escuadra": col_escuadra,
                "engranaje": col_engranaje, "pcb": col_pcb, "vslot": col_vslot, "bisagra": col_bisagra,
                "abrazadera": col_abrazadera, "fijacion": col_fijacion, "rodamiento": col_rodamiento,
                "planetario": col_planetario, "polea": col_polea, "helice": col_helice, "rotula": col_rotula,
                "carcasa": col_carcasa, "muelle": col_muelle, "acme": col_acme, "codo": col_codo, "naca": col_naca,
                "stand_movil": col_stand_movil, "clip_cable": col_clip_cable, "vr_pedestal": col_vr_pedestal
            }
            
            for k, p in tool_panels.items():
                p.visible = (k == nombre_herramienta)
                
            panel_stl_transform.visible = nombre_herramienta.startswith("stl")
            generate_param_code(); page.update()

        def thumbnail(icon, title, tool_id, color): return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_especial = ft.Row([thumbnail("🧠", "Código Libre", "custom", "#000000"), thumbnail("🔠", "Placas Texto", "texto", "#880E4F"), thumbnail("🥽", "Pedestal VR", "vr_pedestal", "#B388FF")], scroll="auto")
        cat_stl_forge = ft.Row([
            thumbnail("🧊", "Híbrido Base", "stl", "#00C853"),
            thumbnail("📏", "Flatten", "stl_flatten", "#00C853"),
            thumbnail("✂️", "Split XYZ", "stl_split", "#00C853"),
            thumbnail("📦", "Crop Box", "stl_crop", "#00C853"),
            thumbnail("🕳️", "Taladro 3D", "stl_drill", "#00C853"),
            thumbnail("🔩", "Orejetas", "stl_mount", "#00C853"),
            thumbnail("🖱️", "Mouse Ears", "stl_ears", "#00C853"),
            thumbnail("🧱", "Bloque Ref", "stl_patch", "#00C853"),
            thumbnail("🐝", "Honeycomb", "stl_honeycomb", "#00C853"),
            thumbnail("🛡️", "Prop Guard", "stl_propguard", "#00C853")
        ], scroll="auto")
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
            ft.Divider(color="#30363D"),
            
            panel_stl_transform,
            col_custom, col_stl, col_stl_flatten, col_stl_split, col_stl_crop, col_stl_drill, col_stl_mount, col_stl_ears, col_stl_patch, col_stl_honeycomb, col_stl_propguard,
            col_texto, col_cubo, col_cilindro, col_laser, col_array_lin, col_array_pol, col_loft, col_panal, col_voronoi, col_evolvente, col_cremallera, col_conico, col_multicaja, col_perfil, col_revolucion, col_escuadra, col_engranaje, col_pcb, col_vslot, col_bisagra, col_abrazadera, col_fijacion, col_rodamiento, col_planetario, col_polea, col_helice, col_rotula, col_carcasa, col_muelle, col_acme, col_codo, col_naca, col_stand_movil, col_clip_cable, col_vr_pedestal,
            
            ft.Container(height=10),
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project_to_nexus(), color="white", bgcolor="#0D47A1"), ft.ElevatedButton("🗑️ RESET TOTAL", on_click=lambda _: clear_editor(), color="white", bgcolor="#B71C1C")], scroll="auto"),
            help_box, row_snippets, txt_code
        ], expand=True)

        # =========================================================
        # SECCIÓN VISOR 3D + TELEMETRÍA GRÁFICA + ENLACE VR
        # =========================================================
        pb_cpu = ft.ProgressBar(width=100, color="#FFAB00", bgcolor="#30363D", value=0, expand=True)
        txt_cpu_val = ft.Text("0.0%", size=11, color="#FFAB00", width=40, text_align="right")
        
        pb_ram = ft.ProgressBar(width=100, color="#00E5FF", bgcolor="#30363D", value=0, expand=True)
        txt_ram_val = ft.Text("0.0%", size=11, color="#00E5FF", width=40, text_align="right")
        
        txt_cores = ft.Text("CORES: ?", size=11, color="#8B949E", weight="bold")

        hw_panel = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("📊 TELEMETRÍA HARDWARE", size=11, color="#E6EDF3", weight="bold"), txt_cores], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([ft.Text("CPU", size=11, color="#FFAB00", weight="bold", width=30), pb_cpu, txt_cpu_val]),
                ft.Row([ft.Text("RAM", size=11, color="#00E5FF", weight="bold", width=30), pb_ram, txt_ram_val])
            ], spacing=5),
            bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333")
        )

        vr_url = f"http://{LAN_IP}:{LOCAL_PORT}/"
        warning_msg = ft.Text("⚠️ NOTA: Usas datos móviles. Conecta al Wi-Fi para gafas VR.", color="#FF5252", size=10, italic=True) if LAN_IP.startswith("10.") and not (LAN_IP.startswith("10.0.") or LAN_IP.startswith("10.1.")) else ft.Container()

        panel_vr = ft.Container(
            content=ft.Column([
                ft.Text("🥽 MODO GAFAS VR O PC EXTERNO", color="#B388FF", weight="bold", size=11),
                ft.TextField(value=vr_url, read_only=True, text_size=16, text_align="center", bgcolor="#161B22", color="#00E676"),
                warning_msg
            ], spacing=5),
            bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#B388FF")
        )

        def hw_monitor_loop():
            while True:
                time.sleep(1.5)
                try:
                    if main_container.content == view_visor:
                        cpu, ram, cores = get_sys_info()
                        pb_cpu.value = cpu / 100.0
                        txt_cpu_val.value = f"{cpu:.1f}%"
                        pb_ram.value = ram / 100.0
                        txt_ram_val.value = f"{ram:.1f}%"
                        txt_cores.value = f"CORES: {cores}"
                        hw_panel.update()
                except: pass

        threading.Thread(target=hw_monitor_loop, daemon=True).start()

        view_visor = ft.Column([
            ft.Container(height=5), hw_panel, ft.Container(height=5), panel_vr, ft.Container(height=5),
            ft.Text("Motor Web Worker / Multi-Hilo", text_align="center", color="#00E5FF", weight="bold"),
            ft.Row([ft.ElevatedButton("🔄 ABRIR VISOR 3D (LOCAL)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, expand=True)], alignment=ft.MainAxisAlignment.CENTER)
        ], expand=True, scroll="auto")
        
        # =========================================================
        # PESTAÑA FILES: EXPLORADOR ANDROID NATIVO (MODO EMOJI SEGURO)
        # =========================================================
        current_android_dir = ANDROID_ROOT
        tf_path = ft.TextField(value=current_android_dir, expand=True, bgcolor="#161B22", height=40, text_size=12)
        list_android = ft.ListView(expand=True, spacing=5)

        def file_action(filepath):
            ext = filepath.lower().split('.')[-1] if '.' in filepath else ''
            if ext == "stl":
                dest = os.path.join(EXPORT_DIR, "imported.stl")
                try:
                    shutil.copy(filepath, dest)
                    lbl_stl_status.value = f"✓ STL Android: {os.path.basename(filepath)}"
                    lbl_stl_status.color = "#00E676"
                    select_tool("stl")
                    set_tab(1)
                    update_code_wrapper()
                except Exception as e:
                    status.value = f"❌ Error leyendo STL: {e}"; status.color = "red"
            elif ext == "jscad":
                try:
                    txt_code.value = open(filepath).read()
                    set_tab(0)
                    status.value = f"✓ Código {os.path.basename(filepath)} cargado."; status.color = "#00E676"
                except Exception as e:
                    status.value = f"❌ Error leyendo JSCAD: {e}"; status.color = "red"
            else:
                status.value = f"⚠️ Formato .{ext} no soportado para importación directa."; status.color = "#FFAB00"
            page.update()

        def refresh_explorer(path):
            list_android.controls.clear()
            try:
                items = os.listdir(path)
                dirs = [d for d in items if os.path.isdir(os.path.join(path, d))]
                files = [f for f in items if os.path.isfile(os.path.join(path, f))]
                dirs.sort(); files.sort()
                
                if path != "/" and path != "/storage" and path != "/storage/emulated":
                    list_android.controls.append(
                        ft.ListTile(leading=ft.Text("⬆️", size=24), title=ft.Text(".. (Subir nivel)", color="white"), on_click=lambda e: nav_to(os.path.dirname(path)))
                    )
                    
                for d in dirs:
                    if d.startswith('.'): continue
                    list_android.controls.append(
                        ft.ListTile(leading=ft.Text("📁", size=24), title=ft.Text(d, color="#E6EDF3"), on_click=lambda e, p=os.path.join(path, d): nav_to(p))
                    )
                    
                for f in files:
                    ext = f.lower().split('.')[-1] if '.' in f else ''
                    icon = "📄"; color = "#8B949E"
                    if ext == "stl": icon = "🧊"; color = "#00E676"
                    elif ext == "jscad": icon = "🧩"; color = "#00E5FF"
                    
                    list_android.controls.append(
                        ft.ListTile(leading=ft.Text(icon, size=24), title=ft.Text(f, color=color), subtitle=ft.Text(f"{os.path.getsize(os.path.join(path, f)) // 1024} KB", size=10), on_click=lambda e, p=os.path.join(path, f): file_action(p))
                    )
            except PermissionError:
                list_android.controls.append(ft.Text("❌ Permiso Denegado por Android. Ve a Termux y escribe 'termux-setup-storage' y dale permisos.", color="red", weight="bold"))
            except Exception as ex:
                list_android.controls.append(ft.Text(f"Error accediendo a carpeta: {ex}", color="red"))
                
            tf_path.value = path
            page.update()

        def nav_to(path):
            nonlocal current_android_dir
            current_android_dir = path
            refresh_explorer(path)

        def save_to_android(e):
            if not os.path.isdir(current_android_dir): return
            fname = f"nexus_{int(time.time())}.jscad"
            dest = os.path.join(current_android_dir, fname)
            try:
                with open(dest, "w") as f: f.write(txt_code.value)
                status.value = f"✓ Guardado en Android: {fname}"; status.color = "#00E676"
                refresh_explorer(current_android_dir)
            except Exception as ex:
                status.value = f"❌ Error guardando: {ex}"; status.color = "red"
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
            ft.Text("Explorador de Dispositivo (Android Native)", color="#00E5FF", weight="bold"),
            ft.Text("Navega por tu móvil. Toca un .stl para el Híbrido, o .jscad para Editar.", size=10, color="#8B949E"),
            row_quick_paths,
            ft.Row([tf_path, ft.ElevatedButton("Ir", on_click=lambda _: nav_to(tf_path.value), bgcolor="#FFAB00", color="black")]),
            ft.ElevatedButton("💾 GUARDAR CÓDIGO EN ESTA CARPETA", on_click=save_to_android, bgcolor="#00E676", color="black", width=float('inf')),
            ft.Container(content=list_android, expand=True, bgcolor="#161B22", border_radius=8, padding=5)
        ], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            if idx == 3: refresh_explorer(current_android_dir)
            main_container.content = [view_editor, view_constructor, view_visor, view_archivos][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🌐 PARAM", on_click=lambda _: set_tab(1), color="black", bgcolor="#FFAB00"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), color="black", bgcolor="#00E5FF"),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(3), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        select_tool("custom"); refresh_explorer(current_android_dir)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)