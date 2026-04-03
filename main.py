import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, traceback, shutil

try:
    import psutil; HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS, PERMISOS Y SERVIDOR
# =========================================================
try: os.system("termux-setup-storage")
except: pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
os.makedirs(EXPORT_DIR, exist_ok=True)

def get_android_root():
    for p in ["/storage/emulated/0", os.path.expanduser("~/storage/shared"), BASE_DIR]:
        try: os.listdir(p); return p
        except: pass
    return BASE_DIR

ANDROID_ROOT = get_android_root()

def get_sys_info():
    cores = os.cpu_count() or 1
    cpu_p, ram_p = 0.0, 0.0
    if HAS_PSUTIL: cpu_p = psutil.cpu_percent(); ram_p = psutil.virtual_memory().percent
    return cpu_p, ram_p, cores

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0)); LOCAL_PORT = s.getsockname()[1]
except: LOCAL_PORT = 8556

LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/upload_stl':
            cl = int(self.headers.get('Content-Length', 0))
            fn = self.headers.get('File-Name', 'uploaded_file.stl')
            if cl > 0:
                try:
                    with open(os.path.join(EXPORT_DIR, fn), 'wb') as f: f.write(self.rfile.read(cl))
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
                <div style="background:#161B22; padding:20px; border-radius:8px; border:1px solid #30363D; display:inline-block; width:90%; max-width:400px;">
                    <input type="file" id="f" style="margin-bottom:20px; color:white; width:100%;">
                    <button onclick="up()" style="background:#00E676; color:black; padding:15px; width:100%; font-weight:bold; border:none; border-radius:8px;">INYECCIÓN DIRECTA (.STL o .JSCAD)</button>
                    <p id="s" style="margin-top:20px; font-weight:bold;"></p>
                </div>
                <script>function up(){var f=document.getElementById('f').files[0]; if(!f){return;}
                document.getElementById('s').style.color='#FFAB00'; document.getElementById('s').innerText='Subiendo...';
                var r=new FileReader(); r.onload=function(e){ fetch('/api/upload_stl', {method:'POST', headers:{'File-Name':f.name}, body:e.target.result})
                .then(()=>{document.getElementById('s').style.color='#00E676'; document.getElementById('s').innerText='✓ ¡ÉXITO! Vuelve a NEXUS.';});}; r.readAsArrayBuffer(f);}</script></body></html>"""
            self.send_response(200); self.send_header("Content-type", "text/html"); self.end_headers(); self.wfile.write(html.encode('utf-8'))
        else:
            try:
                fn = self.path.strip("/") or "openscad_engine.html"
                with open(os.path.join(ASSETS_DIR, fn), "rb") as f: self.send_response(200); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APP FLET MAIN
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v24.0 MASTER"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v24.0 MASTER | All-in-One Activo", color="#00E676", weight="bold")
        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]});\n}"
        txt_code = ft.TextField(label="Código JS-CSG (Editable en RAW)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D", text_size=12)

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

        # === GLOBALES Y ENSAMBLADOR (EL FIX DEL CRASH) ===
        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False)
        sl_g_tol, r_g_tol = create_slider("Tol. (G_TOL)", 0.0, 2.0, 0.2, False)

        sw_ensamble = ft.Switch(label="Activar Ensamblador", value=False, active_color="#FFAB00")
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
                fc += f"  // --- Mod {i} ({item['op']}) ---\n{item['body']}\n"
                if item["op"] == "base": fv = item["var"]
                else: fc += f"  {fv} = {fv}.{item['op']}({item['var']});\n"
            txt_code.value = fc + f"  return {fv};\n}}"; txt_code.update(); page.update()

        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton("➕ UNIR", on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", color="white", expand=True),
            ft.ElevatedButton("➖ RESTAR", on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", color="white", expand=True)
        ], visible=False)

        panel_globales = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11), sw_ensamble], alignment="spaceBetween"),
            r_g_w, r_g_l, r_g_h, r_g_t, r_g_tol, panel_ensamble_ops
        ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        def prepare_js_payload():
            h = f"  var GW={sl_g_w.value}; var GL={sl_g_l.value}; var GH={sl_g_h.value}; var GT={sl_g_t.value}; var G_TOL={sl_g_tol.value};\n"
            c = txt_code.value
            return c.replace("function main() {", "function main() {\n" + h, 1) if "function main() {" in c else h + "\n" + c

        def run_render():
            global LATEST_CODE_B64; LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            set_tab(2)

        # === AYUDA IA ===
        def inject_snippet(code):
            c = txt_code.value; pos = c.rfind('return ')
            txt_code.value = (c[:pos] + code + "\n  " + c[pos:]) if pos != -1 else (c + "\n" + code); txt_code.update()

        help_box = ft.ExpansionTile(title=ft.Text("💡 Ayuda IA / Plantillas", color="#00E5FF", size=12, weight="bold"), collapsed_text_color="#00E5FF", controls=[
            ft.Container(padding=10, bgcolor="#161B22", border_radius=8, content=ft.Column([
                ft.Text("Copia este Prompt para ChatGPT/Gemini:", weight="bold", color="#8B949E", size=11),
                ft.TextField(value="Escribe código para OpenJSCAD. Función main() obligatoria. Devuelve el objeto final con 'return'. Usa las variables globales GW (ancho), GL (largo), GH (alto). Operaciones booleanas válidas: obj.union(b), obj.subtract(b), obj.intersect(b).", read_only=True, text_size=10, multiline=True),
                ft.Row([ft.ElevatedButton("+ Cubo Test", on_click=lambda _: inject_snippet("var c = CSG.cube({center:[0,0,0], radius:[10,10,10]});")), ft.ElevatedButton("+ Cilindro Test", on_click=lambda _: inject_snippet("var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5});"))])
            ]))
        ])

        # =========================================================
        # PANELES DE HERRAMIENTAS (>30) + STL FORGE
        # =========================================================
        panels = {}

        # 1. BÁSICOS
        sl_c_g, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        panels["cubo"] = mk_col("Cubo Paramétrico", "Geometría base. Usa GW, GL, GH.", [r_c_g])
        sl_p_r, r_p_r = create_slider("Radio Hueco", 0, 95, 15, False); sl_p_l, r_p_l = create_slider("Caras (LowPoly)", 3, 64, 64, True)
        panels["cilindro"] = mk_col("Cilindro / Prisma", "Prismas o cilindros con hueco central.", [r_p_r, r_p_l])
        sl_l_l, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False); sl_l_a, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False); sl_l_h, r_l_h = create_slider("Agujero", 0, 10, 2, False)
        panels["escuadra"] = mk_col("Escuadra Tipo L", "Soporte estructural.", [r_l_l, r_l_a, r_l_h])
        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False); sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False)
        panels["pcb"] = mk_col("Caja Electrónica", "Caja hueca según GT.", [r_pcb_x, r_pcb_y])
        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False); sl_bi_d, r_bi_d = create_slider("Diámetro Eje", 5, 30, 10, False)
        panels["bisagra"] = mk_col("Bisagra Print-in-Place", "Articulación funcional.", [r_bi_l, r_bi_d])

        # 2. MECÁNICA
        sl_e_d, r_e_d = create_slider("Dientes", 6, 40, 16, True); sl_e_r, r_e_r = create_slider("Radio Base", 10, 100, 30, False); sl_e_e, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False)
        panels["engranaje"] = mk_col("Piñón Cuadrado", "Engranaje simple.", [r_e_d, r_e_r, r_e_e])
        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True); sl_fij_l, r_fij_l = create_slider("Largo", 0, 100, 30, False)
        panels["fijacion"] = mk_col("Tuerca / Tornillo Hex", "Elementos de fijación.", [r_fij_m, r_fij_l])
        sl_pol_t, r_pol_t = create_slider("Dientes", 10, 60, 20, True); sl_pol_d, r_pol_d = create_slider("Ø Eje Motor", 2, 12, 5, False)
        panels["polea"] = mk_col("Polea Dentada GT2", "Para correas de impresoras 3D.", [r_pol_t, r_pol_d])
        sl_mue_r, r_mue_r = create_slider("Radio Resorte", 5, 50, 15, False); sl_mue_v, r_mue_v = create_slider("Nº Vueltas", 2, 20, 5, False)
        panels["muelle"] = mk_col("Muelle Helicoidal", "Resorte de tensión.", [r_mue_r, r_mue_v])

        # 3. AVANZADOS
        sl_alin_f, r_alin_f = create_slider("Filas (Y)", 1, 10, 3, True); sl_alin_c, r_alin_c = create_slider("Columnas (X)", 1, 10, 3, True); sl_alin_d, r_alin_d = create_slider("Separación", 5, 100, 20, False)
        panels["matriz_lin"] = mk_col("Matriz Lineal Grid", "Array de pilares en X/Y.", [r_alin_f, r_alin_c, r_alin_d])
        sl_apol_n, r_apol_n = create_slider("Repeticiones", 2, 36, 8, True); sl_apol_r, r_apol_r = create_slider("Radio Corona", 10, 150, 40, False)
        panels["matriz_pol"] = mk_col("Matriz Polar", "Array circular.", [r_apol_n, r_apol_r])
        sl_pan_r, r_pan_r = create_slider("Radio Hex", 2, 20, 5, False)
        panels["panal"] = mk_col("Generador Honeycomb", "Panel de abejas paramétrico.", [r_pan_r])
        sl_crem_d, r_crem_d = create_slider("Dientes", 5, 50, 15, True); sl_crem_m, r_crem_m = create_slider("Módulo", 1, 10, 2, False)
        panels["cremallera"] = mk_col("Cremallera Lineal", "Actuadores.", [r_crem_d, r_crem_m])
        sl_perf_p, r_perf_p = create_slider("Nº Puntas", 3, 20, 5, True); sl_perf_re, r_perf_re = create_slider("Radio Ext", 10, 100, 40, False)
        panels["estrella"] = mk_col("Estrella Paramétrica 2D", "Perfiles extruidos.", [r_perf_p, r_perf_re])

        # 4. TEXTO Y CUSTOM
        tf_texto = ft.TextField(label="Texto", value="NEXUS", max_length=15, bgcolor="#1E1E1E")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel Grueso"), ft.dropdown.Option("Voxel Fino")], value="Voxel Grueso", bgcolor="#1E1E1E")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Solo Texto")], value="Llavero (Anilla)", bgcolor="#1E1E1E")
        sw_txt_grabado = ft.Switch(label="Grabado (Hueco)", value=False, active_color="#00E5FF")
        tf_texto.on_change=update_code_wrapper; dd_txt_estilo.on_change=update_code_wrapper; dd_txt_base.on_change=update_code_wrapper; sw_txt_grabado.on_change=update_code_wrapper
        panels["texto"] = mk_col("Placas de Texto", "Genera texto 3D o placas identificativas.", [tf_texto, dd_txt_estilo, dd_txt_base, sw_txt_grabado])
        panels["custom"] = mk_col("Modo Código Libre", "Programa Javascript CSG en la pestaña RAW.", [])

        # 5. ULTIMATE STL FORGE
        lbl_stl_status = ft.Text("Ningún STL cargado aún.", color="#8B949E", size=11)
        sl_stl_sc, r_stl_sc = create_slider("Escala (%)", 1, 500, 100, True)
        sl_stl_x, r_stl_x = create_slider("Mover X", -200, 200, 0, False)
        sl_stl_y, r_stl_y = create_slider("Mover Y", -200, 200, 0, False)
        sl_stl_z, r_stl_z = create_slider("Mover Z", -200, 200, 0, False)
        panel_stl_transform = ft.Container(content=ft.Column([
            ft.Row([ft.Text("🔄 Transformación Base STL", color="#00E676", weight="bold"), lbl_stl_status]),
            ft.ElevatedButton("📂 ABRIR EXPLORADOR (FILES)", on_click=lambda _: set_tab(3), bgcolor="#00E5FF", color="black", width=float('inf'), height=35),
            r_stl_sc, r_stl_x, r_stl_y, r_stl_z
        ]), bgcolor="#161B22", padding=10, border_radius=8, border=ft.border.all(1, "#00E676"), visible=False)

        panels["stl"] = mk_col("Visor Híbrido", "Muestra el STL para aplicar ensamblajes.", [])
        sl_stlf_z, r_stlf_z = create_slider("Corte Inf (Z)", 0, 50, 1, False)
        panels["stl_flatten"] = mk_col("Aplanar Base", "Corta la base para dejarla perfectamente plana.", [r_stlf_z])
        dd_stls_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E"); dd_stls_axis.on_change=update_code_wrapper
        sl_stls_pos, r_stls_pos = create_slider("Posición Corte", -150, 150, 0, False)
        sw_stls_inv = ft.Switch(label="Invertir", value=False, active_color="#FFAB00"); sw_stls_inv.on_change=update_code_wrapper
        panels["stl_split"] = mk_col("Cortador Avanzado", "Guillotina el modelo.", [ft.Row([ft.Text("Eje:"), dd_stls_axis]), r_stls_pos, sw_stls_inv])
        sl_stlc_s, r_stlc_s = create_slider("Tamaño Caja", 10, 300, 50, False)
        panels["stl_crop"] = mk_col("Aislamiento (Crop)", "Elimina todo lo que quede fuera de la caja central.", [r_stlc_s])
        dd_stld_axis = ft.Dropdown(options=[ft.dropdown.Option("X"), ft.dropdown.Option("Y"), ft.dropdown.Option("Z")], value="Z", bgcolor="#1E1E1E"); dd_stld_axis.on_change=update_code_wrapper
        sl_stld_r, r_stld_r = create_slider("Radio Agujero", 0.5, 20, 1.6, False)
        sl_stld_p1, r_stld_p1 = create_slider("Coord 1", -150, 150, 0, False); sl_stld_p2, r_stld_p2 = create_slider("Coord 2", -150, 150, 0, False)
        panels["stl_drill"] = mk_col("Taladro 3D", "Perfora infinitamente.", [ft.Row([ft.Text("Eje:"), dd_stld_axis]), r_stld_r, r_stld_p1, r_stld_p2])
        sl_stlm_w, r_stlm_w = create_slider("Ancho Orejetas", 10, 100, 40, False); sl_stlm_d, r_stlm_d = create_slider("Separación Ext.", 20, 200, 80, False)
        panels["stl_mount"] = mk_col("Orejetas Montaje", "Añade pestañas atornillables.", [r_stlm_w, r_stlm_d])
        sl_stle_r, r_stle_r = create_slider("Radio Discos", 5, 30, 15, False); sl_stle_d, r_stle_d = create_slider("Apertura XY", 10, 200, 50, False)
        panels["stl_ears"] = mk_col("Discos Anti-Warp", "Parches de 0.4mm en esquinas.", [r_stle_r, r_stle_d])

        # === GENERADOR CORE JAVASCRIPT ===
        def get_stl_base_js():
            return f"""
  var sc = {sl_stl_sc.value / 100.0}; var tx = {sl_stl_x.value}; var ty = {sl_stl_y.value}; var tz = {sl_stl_z.value};
  var stlParts = Array.isArray(IMPORTED_STL) ? IMPORTED_STL : [IMPORTED_STL]; var finalPolys = [];
  stlParts.forEach(function(part) {{ var polys = part.polygons || (part.toPolygons ? part.toPolygons() : []);
      polys.forEach(function(p) {{ var newVerts = p.vertices.map(function(v) {{
              var VecClass = (typeof CSG.Vector3D !== 'undefined') ? CSG.Vector3D : ((typeof CSG.Vector !== 'undefined') ? CSG.Vector : null);
              return new CSG.Vertex(new VecClass(v.pos.x*sc+tx, v.pos.y*sc+ty, v.pos.z*sc+tz), new VecClass(v.normal.x, v.normal.y, v.normal.z)); }});
          finalPolys.push(new CSG.Polygon(newVerts, p.shared)); }}); }});
  var dron = CSG.fromPolygons(finalPolys); if(!dron.polygons || dron.polygons.length === 0) return CSG.cube({{radius:[0.1,0.1,0.1]}});
"""

        def generate_param_code():
            h = herramienta_actual
            if h == "custom": return
            code = "function main() {\n"
            
            if h.startswith("stl"):
                code += get_stl_base_js()
                if h == "stl": code += "  return dron;\n}"
                elif h == "stl_flatten": code += f"  return dron.subtract(CSG.cube({{center:[0, 0, -500 + {sl_stlf_z.value}], radius:[1000, 1000, 500]}}));\n}}"
                elif h == "stl_split":
                    ax = dd_stls_axis.value; p = sl_stls_pos.value; off = 500 if sw_stls_inv.value else -500
                    cx = p+off if ax=='X' else 0; cy = p+off if ax=='Y' else 0; cz = p+off if ax=='Z' else 0
                    rx = 500 if ax=='X' else 1000; ry = 500 if ax=='Y' else 1000; rz = 500 if ax=='Z' else 1000
                    code += f"  return dron.subtract(CSG.cube({{center:[{cx},{cy},{cz}], radius:[{rx},{ry},{rz}]}}));\n}}"
                elif h == "stl_crop": code += f"  return dron.intersect(CSG.cube({{center:[0,0,0], radius:[{sl_stlc_s.value/2},{sl_stlc_s.value/2},{sl_stlc_s.value/2}]}}));\n}}"
                elif h == "stl_drill":
                    ax = dd_stld_axis.value; rad = sl_stld_r.value; p1 = sl_stld_p1.value; p2 = sl_stld_p2.value
                    st = f"[-500,{p1},{p2}]" if ax=='X' else (f"[{p1},-500,{p2}]" if ax=='Y' else f"[{p1},{p2},-500]")
                    en = f"[500,{p1},{p2}]" if ax=='X' else (f"[{p1},500,{p2}]" if ax=='Y' else f"[{p1},{p2},500]")
                    code += f"  return dron.subtract(CSG.cylinder({{start:{st}, end:{en}, radius:{rad}, slices:32}}));\n}}"
                elif h == "stl_mount":
                    w = sl_stlm_w.value; d = sl_stlm_d.value
                    code += f"  var m1 = CSG.cube({{center:[{d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{d/2},0,-5], end:[{d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  var m2 = CSG.cube({{center:[{-d/2},0,0], radius:[{w/2},15,3]}}).subtract(CSG.cylinder({{start:[{-d/2},0,-5], end:[{-d/2},0,5], radius:2.2, slices:16}}));\n"
                    code += f"  return dron.union(m1).union(m2);\n}}"
                elif h == "stl_ears":
                    r = sl_stle_r.value; d = sl_stle_d.value
                    code += f"  var c1=CSG.cylinder({{start:[{d/2},{d/2},0], end:[{d/2},{d/2},0.4], radius:{r}, slices:32}});\n"
                    code += f"  var c2=CSG.cylinder({{start:[{-d/2},{d/2},0], end:[{-d/2},{d/2},0.4], radius:{r}, slices:32}});\n"
                    code += f"  var c3=CSG.cylinder({{start:[{d/2},{-d/2},0], end:[{d/2},{-d/2},0.4], radius:{r}, slices:32}});\n"
                    code += f"  var c4=CSG.cylinder({{start:[{-d/2},{-d/2},0], end:[{-d/2},{-d/2},0.4], radius:{r}, slices:32}});\n"
                    code += f"  return dron.union(c1).union(c2).union(c3).union(c4);\n}}"
            else:
                # Resto de herramientas... (Cubo, Cilindro, etc)
                if h == "cubo":
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
                    code += f"  if({H} > 0) res = res.subtract(CSG.cylinder({{start:[{L/2},0,-1], end:[{L/2},0,GT+1], radius:{H}, slices:16}})).subtract(CSG.cylinder({{start:[-1,0,{L/2}], end:[GT+1,0,{L/2}], radius:{H}, slices:16}}));\n  return res;\n}}"
                elif h == "engranaje":
                    D = sl_e_d.value; R = sl_e_r.value; E = sl_e_e.value
                    code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:{R}, slices:32}});\n"
                    code += f"  var dientes = null; for(var i=0; i<{D}; i++) {{ var a = (i/{D})*Math.PI*2;\n"
                    code += f"    var d = CSG.cube({{center:[Math.cos(a)*{R}, Math.sin(a)*{R}, GH/2], radius:[{R/4}, {R/8}, GH/2]}});\n"
                    code += f"    d = d.rotateZ(a*180/Math.PI); if(dientes==null) dientes=d; else dientes=dientes.union(d); }}\n"
                    code += f"  var res = base.union(dientes);\n  if({E} > 0) res = res.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,GH+1], radius:{E}, slices:16}}));\n  return res;\n}}"
                elif h == "pcb":
                    X = sl_pcb_x.value; Y = sl_pcb_y.value
                    code += f"  return CSG.cube({{center:[0,0,GH/2], radius:[{X/2+GT}, {Y/2+GT}, GH/2]}}).subtract(CSG.cube({{center:[0,0,GH/2+GT], radius:[{X/2}, {Y/2}, GH/2]}}));\n}}"
                elif h == "bisagra":
                    L = sl_bi_l.value; D = sl_bi_d.value; tol = 0.4
                    code += f"  var p1 = CSG.cube({{center:[{-L/4}, 0, {D/2}], radius:[{L/4}, {L/2}, {D/4}]}}).union(CSG.cylinder({{start:[0,{-L/2}, {D/2}], end:[0,{-L/6}, {D/2}], radius:{D/2}, slices:32}})).union(CSG.cylinder({{start:[0,{L/6}, {D/2}], end:[0,{L/2}, {D/2}], radius:{D/2}, slices:32}}));\n"
                    code += f"  var p2 = CSG.cube({{center:[{L/4}, 0, {D/2}], radius:[{L/4}, {L/2}, {D/4}]}}).union(CSG.cylinder({{start:[0,{-L/6+tol}, {D/2}], end:[0,{L/6-tol}, {D/2}], radius:{D/2}, slices:32}}));\n"
                    code += f"  return p1.union(p2).union(CSG.cylinder({{start:[0,{-L/2}, {D/2}], end:[0,{L/2}, {D/2}], radius:{D/2-tol}, slices:16}}));\n}}"
                elif h == "fijacion":
                    M = sl_fij_m.value; L = sl_fij_l.value
                    code += f"  var hex = CSG.cylinder({{start:[0,0,0], end:[0,0,{M*0.8}], radius:{M*0.866}, slices:6}});\n"
                    code += f"  if({L} == 0) return hex.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,{M*0.8+1}], radius:{M/2}, slices:16}}));\n"
                    code += f"  return hex.union(CSG.cylinder({{start:[0,0,{M*0.8}], end:[0,0,{M*0.8+L}], radius:{M/2}, slices:16}}));\n}}"
                elif h == "polea":
                    T = sl_pol_t.value; D = sl_pol_d.value; R = (T*2.0)/(2*Math.PI)
                    code += f"  return CSG.cylinder({{start:[0,0,0], end:[0,0,GH], radius:{R}, slices:32}}).union(CSG.cylinder({{start:[0,0,-1], end:[0,0,0], radius:{R+1}, slices:32}})).union(CSG.cylinder({{start:[0,0,GH], end:[0,0,GH+1], radius:{R+1}, slices:32}})).subtract(CSG.cylinder({{start:[0,0,-2], end:[0,0,GH+2], radius:{D/2}, slices:16}}));\n}}"
                elif h == "muelle":
                    code += f"  var res = null; var steps = {int(sl_mue_v.value*32)};\n"
                    code += f"  for(var i=0; i<steps; i++) {{ var a = (i/32)*Math.PI*2;\n"
                    code += f"    var seg = CSG.sphere({{center:[Math.cos(a)*{sl_mue_r.value}, Math.sin(a)*{sl_mue_r.value}, i*(GH/steps)], radius:GT, resolution:8}});\n"
                    code += f"    if(res==null) res=seg; else res=res.union(seg); }}\n  return res;\n}}"
                elif h == "matriz_lin":
                    F = sl_alin_f.value; C = sl_alin_c.value; D = sl_alin_d.value
                    code += f"  var obj = CSG.cube({{center:[0,0,GH/2], radius:[5, 5, GH/2]}}); var res = null;\n"
                    code += f"  for(var x=0; x<{C}; x++) {{ for(var y=0; y<{F}; y++) {{\n"
                    code += f"    var inst = obj.translate([x*{D}, y*{D}, 0]); if(res==null) res=inst; else res=res.union(inst);\n  }} }}\n  return res;\n}}"
                elif h == "matriz_pol":
                    N = sl_apol_n.value; R = sl_apol_r.value
                    code += f"  var obj = CSG.cylinder({{start:[{R},0,0], end:[{R},0,GH], radius:5, slices:16}}); var res = null;\n"
                    code += f"  for(var i=0; i<{N}; i++) {{ var inst = obj.rotateZ((i/{N})*360); if(res==null) res=inst; else res=res.union(inst); }}\n  return res;\n}}"
                elif h == "panal":
                    code += f"  var hex_r = {sl_pan_r.value}; var dx = hex_r*1.732+GT; var dy = hex_r*1.5+GT;\n"
                    code += f"  var base = CSG.cube({{center:[0,0,GH/2], radius:[GW/2, GL/2, GH/2]}}); var holes = null;\n"
                    code += f"  for(var x = -GW/2; x < GW/2; x += dx) {{ for(var y = -GL/2; y < GL/2; y += dy) {{\n"
                    code += f"      var offset = (Math.abs(Math.round(y/dy)) % 2 === 1) ? dx/2 : 0;\n"
                    code += f"      var hex = CSG.cylinder({{start:[x+offset, y, -1], end:[x+offset, y, GH+1], radius:hex_r, slices:6}});\n"
                    code += f"      if(holes === null) holes = hex; else holes = holes.union(hex);\n  }} }}\n  return base.subtract(holes);\n}}"
                elif h == "cremallera":
                    D = sl_crem_d.value; M = sl_crem_m.value; P = M * Math.PI; L = D * P
                    code += f"  var base = CSG.cube({{center:[{L/2}, -{M}, GH/2], radius:[{L/2}, {M}, GH/2]}}); var dientes = null;\n"
                    code += f"  for(var i=0; i<{D}; i++) {{ var d = CSG.cube({{center:[i*{P}+{P/2}, {M/2}, GH/2], radius:[{M/2}, {M}, GH/2]}});\n"
                    code += f"    if(dientes==null) dientes=d; else dientes=dientes.union(d); }}\n  return base.union(dientes);\n}}"
                elif h == "estrella":
                    P = sl_perf_p.value; RE = sl_perf_re.value
                    code += f"  var res = null;\n  for(var i=0; i<{P}; i++) {{ var a1=(i/{P})*360;\n"
                    code += f"    var cyl = CSG.cylinder({{start:[0,0,0], end:[{RE},0,0], radius:GH/2, slices:4}}).rotateZ(a1);\n"
                    code += f"    if(res==null) res=cyl; else res=res.union(cyl); }}\n  return res;\n}}"
                elif h == "texto":
                    txt = tf_texto.value.upper()[:15] or " "
                    code += f"  var font = {{ 'A':[14,17,31,17,17], ' ':[0,0,0,0,0] }};\n"
                    code += f"  var pText = CSG.cube({{center:[0,0,GH/2+2], radius:[GW/2, 10, GH/2]}});\n"
                    code += f"  var baseObj = CSG.cube({{center:[0,0,GH/2], radius:[GW/2+5, 15, GH/2]}});\n"
                    code += f"  if({str(sw_txt_grabado.value).lower()}) return baseObj.subtract(pText.translate([0,0,-2]));\n  return baseObj.union(pText);\n}}"

            if not modo_ensamble: txt_code.value = code; txt_code.update()

        # =========================================================
        # COMBOS Y CATEGORÍAS UI
        # =========================================================
        categorias = {
            "Geometría Básica": [("cubo", "Cubo Paramétrico"), ("cilindro", "Cilindro / Hueco"), ("escuadra", "Escuadra Tipo L"), ("pcb", "Caja PCB"), ("bisagra", "Bisagra PIP")],
            "Mecánica": [("engranaje", "Engranaje SQ"), ("fijacion", "Tuerca / Tornillo"), ("polea", "Polea GT2"), ("muelle", "Muelle")],
            "Avanzados / Arrays": [("matriz_lin", "Matriz Lineal"), ("matriz_pol", "Matriz Polar"), ("panal", "Honeycomb"), ("cremallera", "Cremallera"), ("estrella", "Estrella 2D")],
            "Ultimate STL Forge": [("stl", "Ver STL Original"), ("stl_flatten", "Aplanar Base"), ("stl_split", "Cortador (Split)"), ("stl_crop", "Aislar (Crop Box)"), ("stl_drill", "Taladro 3D"), ("stl_mount", "Orejetas Montaje"), ("stl_ears", "Discos Anti-Warp")],
            "Texto y Especiales": [("texto", "Placas Texto"), ("custom", "Código Libre RAW")]
        }

        dd_cat = ft.Dropdown(options=[ft.dropdown.Option(k) for k in categorias.keys()], value="Geometría Básica", width=180, bgcolor="#161B22")
        dd_tool = ft.Dropdown(width=180, bgcolor="#161B22")

        def on_cat_change(e):
            dd_tool.options = [ft.dropdown.Option(key=k, text=v) for k, v in categorias[dd_cat.value]]
            dd_tool.value = categorias[dd_cat.value][0][0]
            on_tool_change(None)
            page.update()

        def on_tool_change(e):
            nonlocal herramienta_actual; herramienta_actual = dd_tool.value
            for k, p in panels.items(): p.visible = (k == herramienta_actual)
            panel_stl_transform.visible = herramienta_actual.startswith("stl")
            generate_param_code()
            page.update()

        dd_cat.on_change = on_cat_change; dd_tool.on_change = on_tool_change
        panel_herramientas = ft.Container(content=ft.Column(list(panels.values())), padding=0)

        view_constructor = ft.Column([
            ft.Row([ft.Text("Categoría:", color="#8B949E", size=11), dd_cat, ft.Text("Tool:", color="#8B949E", size=11), dd_tool], wrap=True),
            ft.Divider(color="#30363D"),
            panel_globales, panel_stl_transform, panel_herramientas, help_box,
            ft.Container(height=5),
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project_to_nexus(), color="white", bgcolor="#0D47A1")], scroll="auto"), txt_code
        ], expand=True)

        # =========================================================
        # VISOR Y EXPLORADOR FILES
        # =========================================================
        pb_cpu = ft.ProgressBar(color="#FFAB00", bgcolor="#30363D", value=0, expand=True); txt_cpu_val = ft.Text("0.0%", size=11, color="#FFAB00", width=40)
        pb_ram = ft.ProgressBar(color="#00E5FF", bgcolor="#30363D", value=0, expand=True); txt_ram_val = ft.Text("0.0%", size=11, color="#00E5FF", width=40)
        
        hw_panel = ft.Container(content=ft.Column([
            ft.Text("📊 TELEMETRÍA", size=11, color="#E6EDF3", weight="bold"),
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
                        hw_panel.update()
                except: pass
        threading.Thread(target=hw_monitor_loop, daemon=True).start()

        view_visor = ft.Column([
            ft.Container(height=5), hw_panel, ft.Container(height=5),
            ft.ElevatedButton("🔄 ABRIR VISOR 3D (LOCAL)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, expand=True)
        ], expand=True, scroll="auto")

        current_android_dir = ANDROID_ROOT
        tf_path = ft.TextField(value=current_android_dir, expand=True, bgcolor="#161B22", height=40, text_size=12)
        list_android = ft.ListView(expand=True, spacing=5)

        def file_action(filepath):
            ext = filepath.lower().split('.')[-1] if '.' in filepath else ''
            if ext == "stl":
                try: 
                    shutil.copy(filepath, os.path.join(EXPORT_DIR, "imported.stl"))
                    lbl_stl_status.value = f"✓ STL Listo: {os.path.basename(filepath)}"
                    lbl_stl_status.color = "#00E676"
                    
                    # MAGIA: Saltar automáticamente a la herramienta STL!
                    dd_cat.value = "Ultimate STL Forge"; on_cat_change(None)
                    dd_tool.value = "stl"; on_tool_change(None)
                    set_tab(0) 
                    status.value = "✓ STL Cargado. Listo para modificar."
                except Exception as e: status.value = f"❌ Error: {e}"; status.color = "red"
            elif ext == "jscad":
                try: txt_code.value = open(filepath).read(); set_tab(3); status.value = f"✓ Código cargado."; status.color = "#00E676"
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
                if path not in ["/", "/storage", "/storage/emulated"]:
                    list_android.controls.append(ft.ListTile(leading=ft.Text("⬆️", size=24), title=ft.Text(".. (Subir nivel)", color="white"), on_click=lambda e: nav_to(os.path.dirname(path))))
                for d in dirs:
                    if not d.startswith('.'): list_android.controls.append(ft.ListTile(leading=ft.Text("📁", size=24), title=ft.Text(d, color="#E6EDF3"), on_click=lambda e, p=os.path.join(path, d): nav_to(p)))
                for f in files:
                    ext = f.lower().split('.')[-1] if '.' in f else ''
                    icon = "🧊" if ext=="stl" else ("🧩" if ext=="jscad" else "📄"); color = "#00E676" if ext=="stl" else ("#00E5FF" if ext=="jscad" else "#8B949E")
                    list_android.controls.append(ft.ListTile(leading=ft.Text(icon, size=24), title=ft.Text(f, color=color), on_click=lambda e, p=os.path.join(path, f): file_action(p)))
            except Exception:
                list_android.controls.append(ft.Text("Carpeta Restringida (Android 11+).", color="red", weight="bold"))
                list_android.controls.append(ft.Text("Usa la Inyección Web de arriba.", color="#FFAB00"))
            tf_path.value = path; page.update()

        def nav_to(path): nonlocal current_android_dir; current_android_dir = path; refresh_explorer(path)

        def save_project_to_nexus():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = f"✓ Guardado en: {fname}"; page.update()

        view_archivos = ft.Column([
            ft.ElevatedButton("🚀 INYECCIÓN WEB (SI ANDROID BLOQUEA ARCHIVOS)", url=f"http://127.0.0.1:{LOCAL_PORT}/upload_ui", bgcolor="#00E676", color="black", width=float('inf'), height=60, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))),
            ft.Row([
                ft.ElevatedButton("🏠 Android", on_click=lambda _: nav_to("/storage/emulated/0"), bgcolor="#21262D", color="white"),
                ft.ElevatedButton("📥 Descargas", on_click=lambda _: nav_to("/storage/emulated/0/Download"), bgcolor="#21262D", color="white"),
                ft.ElevatedButton("📁 Nexus DB", on_click=lambda _: nav_to(EXPORT_DIR), bgcolor="#1B5E20", color="white")
            ], scroll="auto"),
            ft.Row([tf_path, ft.ElevatedButton("Ir", on_click=lambda _: nav_to(tf_path.value), bgcolor="#FFAB00", color="black")]),
            ft.Container(content=list_android, expand=True, bgcolor="#161B22", border_radius=8, padding=5)
        ], expand=True)

        main_container = ft.Container(content=view_constructor, expand=True)

        def set_tab(idx):
            if idx == 1:
                global LATEST_CODE_B64; LATEST_CODE_B64 = base64.b64encode(prepare_js_payload().encode('utf-8')).decode()
            if idx == 2: refresh_explorer(current_android_dir)
            main_container.content = [view_constructor, view_visor, view_archivos, view_editor][idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0), color="black", bgcolor="#00E676"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(1), color="black", bgcolor="#00E5FF"),
            ft.ElevatedButton("📂 FILES", on_click=lambda _: set_tab(2), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("📝 RAW", on_click=lambda _: set_tab(3), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        
        on_cat_change(None); refresh_explorer(current_android_dir)

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)