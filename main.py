import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

try:
    EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)
except:
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

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
            # Limpiamos el buffer para no re-renderizar infinitamente si recarga
            LATEST_CODE_B64 = "" 
        else:
            try:
                filename = self.path.strip("/")
                if not filename or filename == "": filename = "openscad_engine.html"
                fpath = os.path.join(ASSETS_DIR, filename)
                with open(fpath, "rb") as f:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f.read())
            except:
                self.send_response(404)
                self.end_headers()
    def log_message(self, *args): pass

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v16.5"
        page.theme_mode = "dark"
        page.bgcolor = "#0B0E14" 
        page.padding = 0 
        
        status = ft.Text("NEXUS v16.5 PRO | Maker Suite & Core Monitor activos.", color="#FFAB00", weight="bold")

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,10], radius:[20,20,10]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL, bgcolor="#161B22", color="#58A6FF", border_color="#30363D")

        ensamble_stack = []

        def clear_editor():
            nonlocal ensamble_stack
            ensamble_stack = []
            txt_code.value = "function main() {\n  var pieza = CSG.cube({center:[0,0,0], radius:[10,10,10]});\n  return pieza;\n}"
            status.value = "✓ Ensamble reseteado."
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
            status.value = "Enviando al Motor Multi-Core..."
            set_tab(2)
            page.update()

        # ENSAMBLADOR FASE 14
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
                final_code += f"  // --- Modificador {i} ({item['op']}) ---\n"
                final_code += item["body"] + "\n"
                if item["op"] == "base": final_var = item["var"]
                elif item["op"] == "union": final_code += f"  {final_var} = {final_var}.union({item['var']});\n"
                elif item["op"] == "subtract": final_code += f"  {final_var} = {final_var}.subtract({item['var']});\n"
            final_code += f"  return {final_var};\n}}"
            txt_code.value = final_code; txt_code.update(); page.update()

        herramienta_actual = "custom"
        modo_ensamble = False

        def create_slider(label, min_v, max_v, val, is_int, on_change_fn):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="#00E5FF", width=45, text_align="right", size=13, weight="bold")
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True, active_color="#00E5FF", inactive_color="#2A303C")
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                txt_val.update()
                if not modo_ensamble: on_change_fn(e)
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="#E6EDF3"), sl, txt_val])

        sl_g_tol, r_g_tol = create_slider("Tol. Global (mm)", 0.0, 1.0, 0.2, False, lambda e: generate_param_code())
        
        def toggle_ensamble(e):
            nonlocal modo_ensamble
            modo_ensamble = sw_ensamble.value
            panel_ensamble_ops.visible = modo_ensamble
            page.update()

        sw_ensamble = ft.Switch(label="Activar Ensamblador (Stack)", value=False, on_change=toggle_ensamble, active_color="#FFAB00")
        panel_ensamble_ops = ft.Row([
            ft.ElevatedButton("➕ UNIR AL ENSAMBLE", on_click=lambda _: add_to_stack("union"), bgcolor="#1B5E20", color="white", expand=True),
            ft.ElevatedButton("➖ RESTAR AL ENSAMBLE", on_click=lambda _: add_to_stack("subtract"), bgcolor="#B71C1C", color="white", expand=True)
        ], visible=False)

        panel_tolerancia = ft.Container(content=ft.Column([ft.Row([ft.Text("⚙️ CORE: Ajustes", color="#FFAB00", weight="bold", size=11), sw_ensamble]), panel_ensamble_ops, r_g_tol]), bgcolor="#1E1E1E", padding=10, border_radius=8, border=ft.border.all(1, "#333333"))

        # =========================================================
        # MAKER SUITE (TEXTO AVANZADO)
        # =========================================================
        tf_texto = ft.TextField(label="Escribe tu Texto (Max 10)", value="NEXUS", max_length=10, on_change=lambda e: generate_param_code(), bgcolor="#161B22")
        dd_txt_estilo = ft.Dropdown(label="Estilo/Fuente", options=[ft.dropdown.Option("Voxel"), ft.dropdown.Option("Braille")], value="Voxel", on_change=lambda e: generate_param_code(), expand=True, bgcolor="#161B22")
        dd_txt_base = ft.Dropdown(label="Formato de Base", options=[ft.dropdown.Option("Texto Libre"), ft.dropdown.Option("Llavero (Anilla)")], value="Texto Libre", on_change=lambda e: generate_param_code(), expand=True, bgcolor="#161B22")
        sl_txt_h, r_txt_h = create_slider("Grosor Z", 1, 20, 4, False, generate_param_code)
        
        col_texto = ft.Column([
            ft.Text("Maker Suite: Llaveros y Tipografía", color="#880E4F", size=12), 
            ft.Container(content=ft.Column([
                tf_texto, 
                ft.Row([dd_txt_estilo, dd_txt_base]), 
                r_txt_h
            ]), bgcolor="#161B22", padding=10, border_radius=8)
        ], visible=False)


        def generate_param_code(e=None):
            h = herramienta_actual
            tol_global = sl_g_tol.value 
            if h == "custom" and not modo_ensamble: pass 

            # NUEVO MÓDULO DE TEXTO MAKER
            elif h == "texto":
                txt_input = tf_texto.value.upper()[:10]
                grosor = sl_txt_h.value
                estilo = dd_txt_estilo.value
                base = dd_txt_base.value

                code = f"function main() {{\n  var texto = \"{txt_input}\"; var h = {grosor};\n"
                
                if estilo == "Voxel":
                    code += f"""
  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0], '0':[14,17,17,17,14], '1':[4,12,4,4,14], '2':[14,1,14,16,31] }};
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
  // Simplificacion Braille: 1=TL, 2=ML, 3=BL, 4=TR, 5=MR, 6=BR
  var braille = {{ 'A':[1], 'B':[1,2], 'C':[1,4], 'D':[1,4,5], 'E':[1,5], 'F':[1,2,4], 'G':[1,2,4,5], 'H':[1,2,5], 'I':[2,4], 'J':[2,4,5], 'N':[1,3,4,5], 'E':[1,5], 'X':[1,3,4,6], 'U':[1,3,6], 'S':[2,3,4] }};
  var pText = null; var rDomo = 1.2; var stepX = 3; var stepY = 3; var charWidth = 8;
  for(var i=0; i<texto.length; i++) {{
    var dots = braille[texto[i]] || [1];
    var offX = i * charWidth;
    for(var d=0; d<dots.length; d++) {{
        var p = dots[d];
        var cx = (p>3) ? stepX : 0;
        var cy = ((p-1)%3 === 0) ? stepY*2 : (((p-1)%3 === 1) ? stepY : 0);
        var domo = CSG.sphere({{center:[offX+cx, cy, 0], radius:rDomo, resolution:16}});
        if(pText === null) pText = domo; else pText = pText.union(domo);
    }}
  }}
  var totalL = texto.length * charWidth;
"""

                if base == "Llavero (Anilla)":
                    code += f"""
  var r_llavero = 6;
  var base = CSG.cube({{center:[(totalL/2)-3, 4, -1], radius:[(totalL/2)+2, 8, 1]}});
  var anclaje = CSG.cylinder({{start:[totalL, 4, -2], end:[totalL, 4, 0], radius:r_llavero, slices:32}});
  var agujero = CSG.cylinder({{start:[totalL, 4, -3], end:[totalL, 4, 1], radius:3, slices:16}});
  base = base.union(anclaje).subtract(agujero);
  if(pText !== null) return base.union(pText);
  return base;
}}"""
                else:
                    code += f"""
  if(pText !== null) return pText;
  return CSG.cube({{center:[0,0,0], radius:[1,1,1]}});
}}"""
                if not modo_ensamble: txt_code.value = code

            # RESTO DE HERRAMIENTAS SE MANTIENEN IGUAL QUE EN LA V16.0
            elif h == "cubo":
                g = sl_c_grosor.value
                code = f"function main() {{\n  var pieza = CSG.cube({{center:[0,0,{sl_c_z.value/2}], radius:[{sl_c_x.value/2}, {sl_c_y.value/2}, {sl_c_z.value/2}]}});\n"
                if g > 0: code += f"  var int_box = CSG.cube({{center:[0,0,{sl_c_z.value/2 + g}], radius:[{sl_c_x.value/2 - g}, {sl_c_y.value/2 - g}, {sl_c_z.value/2}]}});\n  pieza = pieza.subtract(int_box);\n"
                code += f"  return pieza;\n}}"
                if not modo_ensamble: txt_code.value = code

            txt_code.update()

        # DECLARACION MINIMA DE HERRAMIENTAS (Resumidas para el bloque)
        sl_c_x, r_c_x = create_slider("Ancho X", 5, 200, 50, False, generate_param_code)
        sl_c_y, r_c_y = create_slider("Fondo Y", 5, 200, 30, False, generate_param_code)
        sl_c_z, r_c_z = create_slider("Alto Z", 5, 200, 20, False, generate_param_code)
        sl_c_grosor, r_c_g = create_slider("Grosor Pared", 0, 20, 0, False, generate_param_code)
        col_cubo = ft.Column([ft.Text("Cubo/Caja Hueca.", color="#8B949E", size=12), ft.Container(content=ft.Column([r_c_x, r_c_y, r_c_z, r_c_g]), bgcolor="#161B22", padding=10, border_radius=8)], visible=False)

        def update_constructor_ui(e=None):
            for p in [col_custom, col_texto, col_cubo]: p.visible = False
            v = herramienta_actual
            if v == "custom": col_custom.visible = True
            elif v == "texto": col_texto.visible = True
            elif v == "cubo": col_cubo.visible = True
            generate_param_code()
            page.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            update_constructor_ui()

        def thumbnail(icon, title, tool_id, color):
            return ft.Container(content=ft.Column([ft.Text(icon, size=24), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=75, height=70, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True, border=ft.border.all(1, "#30363D"))

        cat_especial = ft.Row([thumbnail("🧠", "Mi Código", "custom", "#000000"), thumbnail("🔠", "Texto/Llavero", "texto", "#880E4F")], scroll="auto")
        cat_basico = ft.Row([thumbnail("📦", "Caja", "cubo", "#263238")], scroll="auto")

        col_custom = ft.Column([ft.Text("Tu Código de IA", color="#00E676")], visible=True)

        view_constructor = ft.Column([
            panel_tolerancia, 
            ft.Text("💡 Especiales y Branding:", size=12, color="#8B949E"), cat_especial,
            ft.Text("📦 Geometría Básica:", size=12, color="#8B949E"), cat_basico,
            ft.Divider(color="#30363D"),
            col_custom, col_texto, col_cubo,
            ft.Container(height=10),
            ft.ElevatedButton("▶ DELEGAR A NÚCLEOS JS", on_click=lambda _: run_render(), color="black", bgcolor="#FFAB00", height=60, width=float('inf')),
        ], expand=True, scroll="auto")

        view_editor = ft.Column([ft.Row([ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#B71C1C")]), txt_code], expand=True)
        view_visor = ft.Column([ft.Container(height=40), ft.ElevatedButton("🔄 RECARGAR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="#00E676", height=60, width=300)], expand=True)
        
        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_constructor, view_visor]
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            main_container.content = tabs[idx]
            page.update()

        nav_bar = ft.Row([ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0)), ft.ElevatedButton("🛠️ BUILD", on_click=lambda _: set_tab(1)), ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2))], scroll="auto")
        page.add(ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True))
        
        update_constructor_ui()

    except Exception:
        page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50)); page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ: ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else: ft.app(target=main)