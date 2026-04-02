import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, tempfile, traceback
from urllib.parse import urlparse
import urllib.request

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS
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
# SERVIDOR LOCAL WEBGL
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        LOCAL_PORT = s.getsockname()[1]
except:
    LOCAL_PORT = 8556

LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
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
        page.title = "NEXUS CAD v16.5 PRO"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v16.5 PRO | Motor Paramétrico y Cloud", color="#00E5FF", weight="bold")

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,10], radius:[20,20,10]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D")

        ensamble_stack = []
        herramienta_actual = "custom"
        modo_ensamble = False

        def clear_editor():
            nonlocal ensamble_stack
            ensamble_stack = []
            txt_code.value = "function main() {\n  var pieza = CSG.cube({center:[0,0,0], radius:[10,10,10]});\n  return pieza;\n}"
            status.value = "✓ Ensamble reseteado."
            status.color = "#B71C1C"
            txt_code.update(); page.update()

        def inject_snippet(code_snippet):
            c = txt_code.value
            pos = c.rfind('return ')
            if pos != -1: txt_code.value = c[:pos] + code_snippet + "\n  " + c[pos:]
            else: txt_code.value = c + "\n" + code_snippet
            txt_code.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2); page.update()

        row_snippets = ft.Row([
            ft.Text("Snippets:", color="#8B949E", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[GW/2, GL/2, GH/2]});"), bgcolor="#21262D", color="white"),
            ft.ElevatedButton("+ Cil", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,GH], radius:GW/2, slices:32});"), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        def update_code_wrapper(e=None): generate_param_code()

        def create_slider(label, min_v, max_v, val, is_int):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=45, text_align="right", size=13, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                txt_val.update()
                if not modo_ensamble: update_code_wrapper()
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="#E6EDF3"), sl, txt_val])

        # =========================================================
        # FASE 1: PARÁMETROS GLOBALES (MOTOR PARAMÉTRICO)
        # =========================================================
        sl_g_w, r_g_w = create_slider("Ancho (GW)", 1, 300, 50, False)
        sl_g_l, r_g_l = create_slider("Largo (GL)", 1, 300, 50, False)
        sl_g_h, r_g_h = create_slider("Alto (GH)", 1, 300, 20, False)
        sl_g_t, r_g_t = create_slider("Grosor (GT)", 0.5, 20, 2, False)
        
        sw_ensamble = ft.Switch(label="Activar Ensamblador (Stack)", value=False, active_color="#FFAB00")
        sw_ensamble.on_change = lambda e: (setattr(sw_ensamble, 'value', e.control.value), page.update())

        panel_globales = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("🌐 PARÁMETROS GLOBALES", color="#00E5FF", weight="bold", size=11), sw_ensamble]),
                r_g_w, r_g_l, r_g_h, r_g_t
            ]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333")
        )

        sl_g_tol, r_g_tol = create_slider("Tol. Global (mm)", 0.0, 1.0, 0.2, False)
        col_custom = ft.Column([ft.Text("Código Libre usando GW, GL, GH...", color="#00E676")], visible=True)

        # TEXTO MEJORADO
        tf_texto = ft.TextField(label="Escribe Texto", value="NEXUS", max_length=10, bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(options=[ft.dropdown.Option("Voxel"), ft.dropdown.Option("Braille")], value="Voxel", expand=True, bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(options=[ft.dropdown.Option("Texto Libre"), ft.dropdown.Option("Llavero (Anilla)"), ft.dropdown.Option("Placa Atornillable"), ft.dropdown.Option("Soporte de Mesa")], value="Placa Atornillable", expand=True, bgcolor="#161B22")
        
        col_texto = ft.Column([ft.Text("Tipografía y Placas", color="#880E4F"), ft.Container(content=ft.Column([tf_texto, ft.Row([dd_txt_estilo, dd_txt_base])]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        # OTRAS (Usan sliders locales o globales dependiendo de la lógica interna)
        sl_c_grosor, r_c_g = create_slider("Vaciado Pared", 0, 20, 0, False)
        col_cubo = ft.Column([ft.Text("Cubo Paramétrico (Usa Globales)", color="#8B949E", size=12), r_c_g], visible=False)

        sl_p_rint, r_p_rint = create_slider("Radio Hueco", 0, 95, 15, False)
        sl_p_lados, r_p_lados = create_slider("Caras (LowPoly)", 3, 64, 64, True)
        col_cilindro = ft.Column([ft.Text("Cilindro (Radio=GW/2, Alto=GH)", color="#8B949E"), r_p_rint, r_p_lados], visible=False)

        def generate_param_code():
            h = herramienta_actual
            tol_global = sl_g_tol.value 
            
            # INYECCIÓN DE VARIABLES GLOBALES
            code = f"function main() {{\n  var GW = {sl_g_w.value}; var GL = {sl_g_l.value}; var GH = {sl_g_h.value}; var GT = {sl_g_t.value};\n"
            
            if h == "custom" and not modo_ensamble: pass 

            elif h == "texto":
                txt_input = tf_texto.value.upper()[:10]
                estilo = dd_txt_estilo.value; base = dd_txt_base.value
                code += f"  var texto = \"{txt_input}\"; var h = GH;\n"
                
                if estilo == "Voxel":
                    code += f"""
  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0] }};
  var pText = null; var vSize = 2; var charWidth = 6 * vSize;
  for(var i=0; i<texto.length; i++) {{
    var cMat = font[texto[i]] || font[' '];
    var offX = i * charWidth; 
    for(var r=0; r<5; r++) {{
      for(var c=0; c<5; c++) {{
        if ((cMat[r] >> (4 - c)) & 1) {{
           var vox = CSG.cube({{center:[offX+(c*vSize), (4-r)*vSize, h/2], radius:[vSize/2.1, vSize/2.1, h/2]}});
           if(pText === null) pText = vox; else pText = pText.union(vox);
        }}
      }}
    }}
  }}
  var totalL = texto.length * charWidth;
"""
                elif estilo == "Braille":
                    code += f"""
  var braille = {{ 'A':[1], 'B':[1,2], 'C':[1,4], 'D':[1,4,5], 'E':[1,5], 'F':[1,2,4], ' ':[0] }};
  var pText = null; var rDomo = 1.2; var stepX = 3; var stepY = 3; var charWidth = 8;
  for(var i=0; i<texto.length; i++) {{
    var dots = braille[texto[i]] || [1];
    var offX = i * charWidth;
    for(var d=0; d<dots.length; d++) {{
        var p = dots[d]; if (p === 0) continue;
        var cx = (p>3) ? stepX : 0; var cy = ((p-1)%3 === 0) ? stepY*2 : (((p-1)%3 === 1) ? stepY : 0);
        var domo = CSG.sphere({{center:[offX+cx, cy, h/2], radius:rDomo, resolution:16}});
        if(pText === null) pText = domo; else pText = pText.union(domo);
    }}
  }}
  var totalL = texto.length * charWidth;
"""
                if base == "Llavero (Anilla)":
                    code += "  var baseC = CSG.cube({center:[(totalL/2)-3, 3, h/4], radius:[(totalL/2)+2, 8, h/4]});\n  var anclaje = CSG.cylinder({start:[totalL, 3, 0], end:[totalL, 3, h/2], radius:6, slices:32}).subtract(CSG.cylinder({start:[totalL, 3, -1], end:[totalL, 3, h/2+1], radius:3, slices:16}));\n  return baseC.union(anclaje).union(pText);\n}"
                elif base == "Placa Atornillable":
                    code += "  var baseC = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+10, 10, h/4]});\n  var h1 = CSG.cylinder({start:[-8, 3, -1], end:[-8, 3, h], radius:2, slices:16});\n  var h2 = CSG.cylinder({start:[totalL+2, 3, -1], end:[totalL+2, 3, h], radius:2, slices:16});\n  return baseC.subtract(h1).subtract(h2).union(pText);\n}"
                elif base == "Soporte de Mesa":
                    code += "  var baseC = CSG.cube({center:[totalL/2-3, 3, h/4], radius:[totalL/2+2, 5, h/4]});\n  var pata = CSG.cube({center:[totalL/2-3, -5, h/8], radius:[totalL/2+2, 10, h/8]});\n  return baseC.union(pata).union(pText);\n}"
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

            if not modo_ensamble: 
                if h in ["texto", "cubo", "cilindro"]: txt_code.value = code

            txt_code.update()

        tf_texto.on_change = update_code_wrapper
        dd_txt_estilo.on_change = update_code_wrapper
        dd_txt_base.on_change = update_code_wrapper

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            paneles = [col_custom, col_texto, col_cubo, col_cilindro]
            for p in paneles: p.visible = False
            if nombre_herramienta == "custom": col_custom.visible = True
            elif nombre_herramienta == "texto": col_texto.visible = True
            elif nombre_herramienta == "cubo": col_cubo.visible = True
            elif nombre_herramienta == "cilindro": col_cilindro.visible = True
            generate_param_code(); page.update()

        def thumbnail(icon, title, tool_id, color): return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_tools = ft.Row([thumbnail("🧠", "Código", "custom", "#000000"), thumbnail("🔠", "Placas Texto", "texto", "#880E4F"), thumbnail("📦", "Cubo G", "cubo", "#263238"), thumbnail("🛢️", "Cilindro G", "cilindro", "#263238")], scroll="auto")

        view_constructor = ft.Column([
            panel_globales, 
            ft.Text("Herramientas (Integradas a Parámetros Globales):", size=12, color="#8B949E"), cat_tools,
            ft.Divider(color="#30363D"),
            col_custom, col_texto, col_cubo, col_cilindro,
            ft.Container(height=10),
            ft.ElevatedButton("▶ ENVIAR AL WORKER (RENDER 3D)", on_click=lambda _: run_render(), color="black", bgcolor="#00E676", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0D47A1"), ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#B71C1C")], scroll="auto"),
            row_snippets, txt_code
        ], expand=True)

        view_visor = ft.Column([
            ft.Container(height=40), 
            ft.Text("Motor Web Worker / Multi-Hilo", text_align="center", color="#00E5FF", weight="bold"),
            ft.Row([ft.ElevatedButton("🔄 RECARGAR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, width=300)], alignment=ft.MainAxisAlignment.CENTER)
        ], expand=True)
        
        # =========================================================
        # FASE 2: SISTEMA DE ARCHIVOS EN LA NUBE (REST API)
        # =========================================================
        file_list = ft.ListView(expand=True, spacing=10)
        tf_fb_url = ft.TextField(label="URL Firebase Realtime DB (Ej: https://tudb.firebaseio.com)", bgcolor="#161B22", text_size=12)
        
        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                if f == "nexus_config.json": continue
                def make_load(name): return lambda _: (setattr(txt_code, 'value', open(os.path.join(EXPORT_DIR, name)).read()), set_tab(0), page.update())
                file_list.controls.append(ft.Container(content=ft.Row([ft.Text(f, weight="bold", color="#E6EDF3", width=150), ft.ElevatedButton("▶", on_click=make_load(f), color="white", bgcolor="#1B5E20")]), padding=10, bgcolor="#161B22", border_radius=8))
            page.update()

        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files(); status.value = f"✓ Guardado: {fname}"; page.update()

        def sync_cloud(e):
            url = tf_fb_url.value.strip().rstrip('/')
            if not url: status.value = "⚠️ Falta la URL de Firebase"; page.update(); return
            try:
                data = {}
                for f in os.listdir(EXPORT_DIR):
                    if f.endswith('.jscad'): data[f.replace('.jscad', '')] = open(os.path.join(EXPORT_DIR, f)).read()
                req = urllib.request.Request(f"{url}/nexus_sync.json", data=json.dumps(data).encode(), method='PUT', headers={'Content-Type': 'application/json'})
                urllib.request.urlopen(req)
                status.value = "☁️ ¡Subida a la Nube completada!"; status.color = "#00E676"
            except Exception as ex:
                status.value = f"❌ Error Nube: {str(ex)}"; status.color = "red"
            page.update()

        def download_cloud(e):
            url = tf_fb_url.value.strip().rstrip('/')
            if not url: return
            try:
                resp = urllib.request.urlopen(f"{url}/nexus_sync.json").read()
                data = json.loads(resp.decode())
                if data:
                    for k, v in data.items():
                        with open(os.path.join(EXPORT_DIR, f"{k}.jscad"), "w") as f: f.write(v)
                    update_files()
                    status.value = "☁️ ¡Descargado de la Nube!"; status.color = "#00B0FF"
            except: status.value = "❌ No hay datos o URL inválida"; status.color = "red"
            page.update()

        view_archivos = ft.Column([
            ft.Text("Almacenamiento Cloud (Firebase REST)", color="#FFAB00", weight="bold"),
            tf_fb_url,
            ft.Row([ft.ElevatedButton("⬆️ SUBIR", on_click=sync_cloud, bgcolor="#212121", color="#00E676", expand=True), ft.ElevatedButton("⬇️ BAJAR", on_click=download_cloud, bgcolor="#212121", color="#00B0FF", expand=True)]),
            ft.Divider(color="#30363D"),
            ft.Text("Almacenamiento Local (Dispositivo)", color="#00E5FF", weight="bold"), file_list
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
            ft.ElevatedButton("☁️ CLOUD", on_click=lambda _: set_tab(3), bgcolor="#21262D", color="white"),
        ], scroll="auto")

        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        select_tool("custom"); update_files()

    except Exception:
        page.clean(); page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)