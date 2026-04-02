import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, tempfile, traceback

# Intentar usar psutil si existe, si no, usar lecturas nativas de Android/Linux
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from urllib.parse import urlparse
import urllib.request

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS DE ALMACENAMIENTO
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

try:
    EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)
except:
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

# =========================================================
# LECTOR DE HARDWARE (ANDROID / LINUX NATIVO)
# =========================================================
def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL:
        cpu_p = psutil.cpu_percent()
        ram_p = psutil.virtual_memory().percent
    else:
        try:
            # Lectura en Termux/Android puro sin dependencias
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
        except:
            pass # Si falla (ej. en Windows sin psutil) devuelve 0
    return cpu_p, ram_p, cores

# =========================================================
# SERVIDOR LOCAL WEBGL & DATA HANDLER
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        LOCAL_PORT = s.getsockname()[1]
except:
    LOCAL_PORT = 8556

LATEST_CODE_B64 = ""

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
                except Exception as e: pass
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
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode())
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

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APP FLET MAIN
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v18.0 PRO"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v18.0 PRO | Texto Avanzado & HW Mon", color="#00E5FF", weight="bold")

        T_INICIAL = "function main() {\n  var GW = 50; var GL = 50; var GH = 20; var GT = 2;\n  var pieza = CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

        ensamble_stack = []
        herramienta_actual = "custom"
        modo_ensamble = False

        def clear_editor():
            nonlocal ensamble_stack
            ensamble_stack = []
            txt_code.value = "function main() {\n  var GW = 50; var GL = 50; var GH = 20; var GT = 2;\n  // Plantilla limpia\n  return CSG.cube({radius:[0,0,0]});\n}"
            status.value = "✓ Código borrado."
            status.color = "#B71C1C"
            txt_code.update(); page.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2); page.update()

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
        sl_g_tol, r_g_tol = create_slider("Tol. Global (mm)", 0.0, 1.0, 0.2, False)

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
            for line in code_lines[2:-1]: 
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
            final_code = f"function main() {{\n  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value};\n"
            final_var = ""
            for i, item in enumerate(ensamble_stack):
                final_code += f"  // --- Modificador {i} ({item['op']}) ---\n"
                final_code += item["body"] + "\n"
                if item["op"] == "base": final_var = item["var"]
                elif item["op"] == "union": final_code += f"  {final_var} = {final_var}.union({item['var']});\n"
                elif item["op"] == "subtract": final_code += f"  {final_var} = {final_var}.subtract({item['var']});\n"
            final_code += f"  return {final_var};\n}}"
            txt_code.value = final_code; txt_code.update(); page.update()

        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton("➕ UNIR", on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", color="white", expand=True),
            ft.ElevatedButton("➖ RESTAR", on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", color="white", expand=True)
        ], visible=False)

        panel_globales = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11), sw_ensamble], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                r_g_w, r_g_l, r_g_h, r_g_t, r_g_tol, panel_ensamble_ops
            ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333")
        )

        col_custom = ft.Column([ft.Text("Código Libre", color="#00E676")], visible=True)

        def inst(texto): return ft.Text("ℹ️ " + texto, color="#FFD54F", size=11, italic=True)

        # =========================================================
        # MEJORA: MOTOR DE TEXTO AVANZADO
        # =========================================================
        tf_texto = ft.TextField(label="Escribe Texto", value="NEXUS", max_length=15, bgcolor="#161B22", on_change=update_code_wrapper)
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Fino"), ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Braille")], value="Voxel Grueso", expand=True, bgcolor="#161B22", on_change=update_code_wrapper)
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Solo Texto"), ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Soporte de Mesa"), ft.dropdown.Option("Colgante Militar"), ft.dropdown.Option("Placa Ovalada")], value="Colgante Militar", expand=True, bgcolor="#161B22", on_change=update_code_wrapper)
        sw_txt_grabado = ft.Switch(label="Texto Grabado (Hueco)", value=False, active_color="#00E5FF", on_change=update_code_wrapper)
        
        col_texto = ft.Column([
            ft.Text("Tipografía y Placas (V2)", color="#880E4F", weight="bold"), 
            inst("GH define el grosor de la placa. 'Grabado' hunde las letras en el material."), 
            ft.Container(content=ft.Column([
                tf_texto, 
                ft.Row([dd_txt_estilo, dd_txt_base]),
                sw_txt_grabado
            ]), bgcolor="#161B22", padding=10, border_radius=8)
        ], visible=False)

        # OTRAS HERRAMIENTAS (Resumidas para ahorrar espacio en este bloque, mantienen tu código exacto)
        sl_las_x, r_las_x = create_slider("Ancho Objeto", 10, 200, 50, False)
        sl_las_y, r_las_y = create_slider("Largo Objeto", 10, 200, 50, False)
        sl_las_z, r_las_z = create_slider("Altura Z Corte", 0, 100, 5, False)
        col_laser = ft.Column([ft.Text("Perfil Láser", color="#D50000"), r_las_x, r_las_y, r_las_z], visible=False)

        sl_alin_f, r_alin_f = create_slider("Filas (Y)", 1, 10, 3, True)
        sl_alin_c, r_alin_c = create_slider("Columnas (X)", 1, 10, 3, True)
        sl_alin_dx, r_alin_dx = create_slider("Distancia X", 5, 100, 20, False)
        sl_alin_dy, r_alin_dy = create_slider("Distancia Y", 5, 100, 20, False)
        sl_alin_h, r_alin_h = create_slider("Altura Base", 2, 50, 10, False)
        col_array_lin = ft.Column([ft.Text("Matriz Lineal Grid", color="#00B0FF"), r_alin_f, r_alin_c, r_alin_dx, r_alin_dy, r_alin_h], visible=False)

        sl_apol_n, r_apol_n = create_slider("Repeticiones", 2, 36, 8, True)
        sl_apol_r, r_apol_r = create_slider("Radio Corona", 10, 150, 40, False)
        sl_apol_rp, r_apol_rp = create_slider("Radio Pieza", 2, 20, 5, False)
        sl_apol_h, r_apol_h = create_slider("Grosor (Z)", 2, 50, 5, False)
        col_array_pol = ft.Column([ft.Text("Matriz Polar Circular", color="#00B0FF"), r_apol_n, r_apol_r, r_apol_rp, r_apol_h], visible=False)

        sl_c_grosor, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        col_cubo = ft.Column([ft.Text("Cubo Paramétrico", color="#8B949E"), r_c_g], visible=False)
        
        sl_p_rint, r_p_rint = create_slider("Radio Hueco", 0, 95, 15, False)
        sl_p_lados, r_p_lados = create_slider("Caras (LowPoly)", 3, 64, 64, True)
        col_cilindro = ft.Column([ft.Text("Cilindro / Prisma", color="#8B949E"), r_p_rint, r_p_lados], visible=False)

        def generate_param_code():
            h = herramienta_actual; tol_global = sl_g_tol.value 
            code = f"function main() {{\n  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value};\n"
            
            if h == "custom":
                pass
                
            elif h == "texto":
                txt_input = tf_texto.value.upper()[:15]; estilo = dd_txt_estilo.value; base = dd_txt_base.value; grabado = sw_txt_grabado.value
                code += f"  var texto = \"{txt_input}\"; var h = GH;\n"
                code += f"  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0], '0':[14,17,17,17,14], '1':[4,12,4,4,14], '2':[14,1,14,16,31], '3':[14,1,14,1,14], '4':[18,18,31,2,2], '5':[31,16,14,1,14], '6':[14,16,30,17,14], '7':[31,1,2,4,8], '8':[14,17,14,17,14], '9':[14,17,15,1,14] }};\n"
                
                # Z y Altura de las letras según si es grabado o relieve
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
                # Generación de la Base
                code += "  var baseObj = null;\n"
                
                if base == "Llavero (Anilla)": 
                    code += "  var bc = CSG.cube({center:[(totalL/2)-3, 3, h/4], radius:[(totalL/2)+2, 8, h/4]});\n  var anclaje = CSG.cylinder({start:[totalL, 3, 0], end:[totalL, 3, h/2], radius:6, slices:32}).subtract(CSG.cylinder({start:[totalL, 3, -1], end:[totalL, 3, h/2+1], radius:3, slices:16}));\n  baseObj = bc.union(anclaje);\n"
                elif base == "Placa Atornillable": 
                    code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+10, 10, h/4]});\n  var h1 = CSG.cylinder({start:[-8, 3, -1], end:[-8, 3, h], radius:2.5, slices:16});\n  var h2 = CSG.cylinder({start:[totalL+2, 3, -1], end:[totalL+2, 3, h], radius:2.5, slices:16});\n  baseObj = bc.subtract(h1).subtract(h2);\n"
                elif base == "Soporte de Mesa": 
                    code += "  var bc = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+2, 5, h/4]});\n  var pata = CSG.cube({center:[totalL/2-3, -5, h/8], radius:[totalL/2+2, 10, h/8]});\n  baseObj = bc.union(pata);\n"
                elif base == "Colgante Militar":
                    code += "  var b_cen = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 10, h/4]});\n"
                    code += "  var b_izq = CSG.cylinder({start:[-4, 4, 0], end:[-4, 4, h/2], radius:10, slices:32});\n"
                    code += "  var b_der = CSG.cylinder({start:[totalL-2, 4, 0], end:[totalL-2, 4, h/2], radius:10, slices:32});\n"
                    code += "  var agujero = CSG.cylinder({start:[-8, 4, -1], end:[-8, 4, h], radius:2.5, slices:16});\n"
                    code += "  baseObj = b_cen.union(b_izq).union(b_der).subtract(agujero);\n"
                elif base == "Placa Ovalada":
                    code += "  var c1 = CSG.cylinder({start:[-2, 4, 0], end:[-2, 4, h/2], radius:12, slices:64});\n"
                    code += "  var c2 = CSG.cylinder({start:[totalL-4, 4, 0], end:[totalL-4, 4, h/2], radius:12, slices:64});\n"
                    code += "  var p_med = CSG.cube({center:[totalL/2-3, 4, h/4], radius:[totalL/2-1, 12, h/4]});\n"
                    code += "  baseObj = p_med.union(c1).union(c2);\n"
                else: 
                    baseObj = None

                # Operación Booleana final según Modo
                if baseObj:
                    if grabado: code += "  return baseObj.subtract(pText);\n}"
                    else: code += "  return baseObj.union(pText);\n}"
                else:
                    code += "  return pText || CSG.cube({radius:[1,1,1]});\n}"

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
                code += f"  var w = {sl_las_x.value}; var l = {sl_las_y.value}; var z_cut = {sl_las_z.value};\n  var base_obj = CSG.cube({{center:[0,0,10], radius:[w/2, l/2, 10]}}).subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,21], radius:5, slices:16}}));\n  var cut_plane = CSG.cube({{center:[0,0,z_cut], radius:[w, l, 0.1]}});\n  return base_obj.intersect(cut_plane).scale([1,1,10]);\n}}"

            if not modo_ensamble and h != "custom": 
                txt_code.value = code
            txt_code.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            paneles = [col_custom, col_texto, col_cubo, col_cilindro, col_laser, col_array_lin, col_array_pol]
            for p in paneles: p.visible = False
            
            if nombre_herramienta == "custom": col_custom.visible = True
            elif nombre_herramienta == "texto": col_texto.visible = True
            elif nombre_herramienta == "cubo": col_cubo.visible = True
            elif nombre_herramienta == "cilindro": col_cilindro.visible = True
            elif nombre_herramienta == "laser": col_laser.visible = True
            elif nombre_herramienta == "array_lin": col_array_lin.visible = True
            elif nombre_herramienta == "array_pol": col_array_pol.visible = True
            generate_param_code(); page.update()

        def thumbnail(icon, title, tool_id, color): return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_especial = ft.Row([thumbnail("🧠", "Código Libre", "custom", "#000000"), thumbnail("🔠", "Texto Placas", "texto", "#880E4F")], scroll="auto")
        cat_produccion = ft.Row([thumbnail("🔪", "Perfil Láser", "laser", "#D50000"), thumbnail("🔲", "Matriz Grid", "array_lin", "#0091EA"), thumbnail("🎡", "Matriz Polar", "array_pol", "#00B0FF")], scroll="auto")
        cat_basico = ft.Row([thumbnail("📦", "Cubo G", "cubo", "#263238"), thumbnail("🛢️", "Cilindro G", "cilindro", "#263238")], scroll="auto")

        view_constructor = ft.Column([
            panel_globales, 
            ft.Text("💡 Especiales y Letras (V2):", size=12, color="#8B949E"), cat_especial,
            ft.Text("🏭 Producción y Láser:", size=12, color="#00B0FF"), cat_produccion,
            ft.Text("📦 Geometría Básica:", size=12, color="#8B949E"), cat_basico,
            ft.Divider(color="#30363D"),
            
            col_custom, col_texto, col_cubo, col_cilindro, col_laser, col_array_lin, col_array_pol,
            
            ft.Container(height=10),
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0D47A1"), ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#B71C1C")], scroll="auto"),
            txt_code
        ], expand=True)

        # =========================================================
        # MEJORA: PANEL DE TELEMETRÍA EN PESTAÑA VISOR 3D
        # =========================================================
        txt_hw = ft.Text("Recabando datos de hardware...", color="#00E5FF", weight="bold", size=12, text_align="center")
        hw_panel = ft.Container(content=txt_hw, bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#30363D"), width=float('inf'))

        def hw_monitor_loop():
            while True:
                time.sleep(1.5)
                # Solo actualizamos el panel si estamos en la pestaña del visor 3D (índice 2)
                try:
                    if main_container.content == view_visor:
                        cpu, ram, cores = get_sys_info()
                        txt_hw.value = f"⚙️ CORES: {cores}   |   🧠 CPU: {cpu:.1f}%   |   📊 RAM: {ram:.1f}%"
                        txt_hw.update()
                except: pass

        threading.Thread(target=hw_monitor_loop, daemon=True).start()

        view_visor = ft.Column([
            hw_panel,
            ft.Container(height=20), 
            ft.Text("Motor Web Worker / Multi-Hilo", text_align="center", color="#E6EDF3", weight="bold"),
            ft.Row([ft.ElevatedButton("🔄 RECARGAR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, width=300)], alignment=ft.MainAxisAlignment.CENTER)
        ], expand=True)
        
        # =========================================================
        # PESTAÑA DB: GESTOR DE ARCHIVOS
        # =========================================================
        file_list = ft.ListView(expand=True, spacing=10)
        tf_fb_url = ft.TextField(label="URL Firebase Realtime DB", bgcolor="#161B22", text_size=12)
        
        current_rename_file = ""
        rename_tf = ft.TextField(label="Renombrar Archivo", expand=True, bgcolor="#161B22", text_size=13)

        def confirm_rename(e):
            nonlocal current_rename_file
            if rename_tf.value and current_rename_file:
                old_path = os.path.join(EXPORT_DIR, current_rename_file)
                new_path = os.path.join(EXPORT_DIR, rename_tf.value)
                if not new_path.endswith(os.path.splitext(current_rename_file)[1]): new_path += os.path.splitext(current_rename_file)[1]
                try: 
                    os.rename(old_path, new_path)
                    status.value = f"✓ Renombrado a {os.path.basename(new_path)}"; status.color = "#00E676"
                except Exception as ex: 
                    status.value = f"❌ Error: {str(ex)}"; status.color = "red"
            rename_panel.visible = False; current_rename_file = ""
            update_files()

        def cancel_rename(e): rename_panel.visible = False; page.update()

        rename_panel = ft.Container(content=ft.Row([rename_tf, ft.ElevatedButton("💾", on_click=confirm_rename, bgcolor="#00E676", color="black"), ft.ElevatedButton("❌", on_click=cancel_rename, bgcolor="#B71C1C", color="white")]), visible=False, padding=10, bgcolor="#1E1E1E", border_radius=8, border=ft.border.all(1, "#FFAB00"))

        def open_rename(name):
            nonlocal current_rename_file
            current_rename_file = name; rename_tf.value = name; rename_panel.visible = True; page.update()

        def update_files():
            file_list.controls.clear()
            if not os.path.exists(EXPORT_DIR): return
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                if f == "nexus_config.json": continue
                
                def make_del(name): return lambda _: (os.remove(os.path.join(EXPORT_DIR, name)), update_files())
                def make_ren(name): return lambda _: open_rename(name)
                def make_down(name): return lambda _: page.launch_url(f"http://127.0.0.1:{LOCAL_PORT}/exports/{name}")
                
                btn_del = ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#B71C1C", width=60)
                btn_ren = ft.ElevatedButton("✏️", on_click=make_ren(f), color="black", bgcolor="#FFAB00", width=60)
                
                if f.endswith('.jscad'):
                    def make_load(name): return lambda _: (setattr(txt_code, 'value', open(os.path.join(EXPORT_DIR, name)).read()), set_tab(0), page.update())
                    acciones = ft.Row([ft.ElevatedButton("▶ CARGAR", on_click=make_load(f), color="white", bgcolor="#1B5E20"), btn_ren, btn_del])
                    icon = "🧩"; tipo = "Código Fuente"
                elif f.endswith('.stl'):
                    acciones = ft.Row([ft.ElevatedButton("⬇️ BAJAR STL", on_click=make_down(f), color="black", bgcolor="#00E5FF"), btn_ren, btn_del])
                    icon = "🧊"; tipo = "Modelo 3D"
                elif f.endswith('.obj'):
                    acciones = ft.Row([ft.ElevatedButton("⬇️ BAJAR OBJ", on_click=make_down(f), color="white", bgcolor="#C51162"), btn_ren, btn_del])
                    icon = "📦"; tipo = "Unity/Blender"
                else: continue

                file_list.controls.append(ft.Container(content=ft.Column([ft.Text(f"{icon} {f}", weight="bold", color="#E6EDF3", size=13), ft.Text(tipo, color="#8B949E", size=10), acciones]), padding=10, bgcolor="#161B22", border_radius=8))
            page.update()

        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files(); status.value = f"✓ Guardado: {fname}"; page.update()

        view_archivos = ft.Column([
            ft.Text("Cloud Sync", color="#FFAB00", weight="bold"), tf_fb_url,
            rename_panel, file_list
        ], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            if idx == 3: update_files()
            main_container.content = [view_editor, view_constructor, view_visor, view_archivos][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("🌐 PARAM", on_click=lambda _: set_tab(1), color="black", bgcolor="#FFAB00"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), color="black", bgcolor="#00E5FF"),
            ft.ElevatedButton("☁️ DB", on_click=lambda _: set_tab(3), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        select_tool("custom"); update_files()

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)