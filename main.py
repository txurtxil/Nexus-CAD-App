import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS BLINDADAS 
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
# MOTOR SERVIDOR LOCAL (VISOR 3D)
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

# =========================================================
# APLICACIÓN PRINCIPAL v6.0 (SUITE PROFESIONAL)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v6.0"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("NEXUS v6.0 | Suite Profesional", color="green")

        def open_dialog(dialog):
            try: page.open(dialog)
            except: 
                if dialog not in page.overlay: page.overlay.append(dialog)
                dialog.open = True
                page.update()

        def close_dialog(dialog):
            try: page.close(dialog)
            except: dialog.open = False; page.update()

        def copy_text(text_to_copy):
            try:
                page.set_clipboard(str(text_to_copy))
                status.value = "✓ Código copiado."
                status.color = "green"
            except:
                try:
                    subprocess.run(['termux-clipboard-set'], input=str(text_to_copy).encode('utf-8'))
                    status.value = "✓ Copiado (Termux)."
                    status.color = "green"
                except: pass
            page.update()

        # --- EDITOR JS-CSG BASE ---
        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,10], radius:[20,20,10]});\n}"
        txt_code = ft.TextField(label="Código JS-CSG (Punto de Partida 0)", multiline=True, expand=True, value=T_INICIAL, text_size=12)

        def clear_editor():
            txt_code.value = "function main() {\n  return CSG.cube({center:[0,0,0], radius:[10,10,10]});\n}"
            txt_code.update()

        def inject_snippet(code_snippet):
            txt_code.value = txt_code.value + "\n" + code_snippet
            txt_code.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2)
            page.update()

        row_snippets = ft.Row([
            ft.Text("Snippets:", color="grey", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[5,5,5]});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5, slices:32});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("  var final = pieza1.subtract(pieza2);"), bgcolor="#4e342e", color="white"),
        ], scroll="auto")

        # =========================================================
        # CONSTRUCTOR PARAMÉTRICO Y GALERÍA (PESTAÑA BUILD)
        # =========================================================
        # Estado de herramienta seleccionada
        herramienta_actual = "cubo"

        def create_slider(label, min_v, max_v, val, is_int, on_change_fn):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="cyan", width=45, text_align="right", size=13)
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True)
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                txt_val.update()
                on_change_fn(e)
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="white"), sl, txt_val])

        def generate_param_code(e=None):
            h = herramienta_actual
            
            if h == "cubo":
                g = sl_c_grosor.value
                code = f"function main() {{\n  var ext = CSG.cube({{center:[0,0,{sl_c_z.value/2}], radius:[{sl_c_x.value/2}, {sl_c_y.value/2}, {sl_c_z.value/2}]}});\n"
                if g > 0:
                    g = min(g, min(sl_c_x.value, sl_c_y.value) / 2.1)
                    code += f"  var int = CSG.cube({{center:[0,0,{sl_c_z.value/2 + g}], radius:[{sl_c_x.value/2 - g}, {sl_c_y.value/2 - g}, {sl_c_z.value/2}]}});\n  return ext.subtract(int);\n}}"
                else: code += f"  return ext;\n}}"

            elif h == "cilindro":
                rint = min(sl_p_rint.value, sl_p_rext.value - 0.5)
                if rint < 0: rint = 0
                c = int(sl_p_lados.value)
                code = f"function main() {{\n  var ext = CSG.cylinder({{start:[0,0,0], end:[0,0,{sl_p_h.value}], radius:{sl_p_rext.value}, slices:{c}}});\n"
                if rint > 0:
                    code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,{sl_p_h.value+2}], radius:{rint}, slices:{c}}});\n  return ext.subtract(int);\n}}"
                else: code += f"  return ext;\n}}"
                    
            elif h == "engranaje":
                d, r, ht, eje = int(sl_e_dientes.value), sl_e_radio.value, sl_e_grosor.value, sl_e_eje.value
                d_x, d_y = r * 0.15, r * 0.2
                code = f"function main() {{\n  var dientes = {d}; var r = {r}; var h = {ht};\n  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var diente = CSG.cube({{center:[Math.cos(a)*r, Math.sin(a)*r, h/2], radius:[{d_x}, {d_y}, h/2]}});\n    base = base.union(diente);\n  }}\n"
                if eje > 0: code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{eje}, slices:32}});\n  return base.subtract(hueco);\n}}"
                else: code += f"  return base;\n}}"
            
            elif h == "escuadra":
                l, w, t, hr = sl_l_largo.value, sl_l_ancho.value, sl_l_grosor.value, sl_l_hueco.value
                code = f"function main() {{\n  var l = {l}; var w = {w}; var t = {t}; var r = {hr};\n"
                code += f"  var base = CSG.cube({{center:[l/2, w/2, t/2], radius:[l/2, w/2, t/2]}});\n"
                code += f"  var wall = CSG.cube({{center:[t/2, w/2, l/2], radius:[t/2, w/2, l/2]}});\n  var bracket = base.union(wall);\n"
                if hr > 0:
                    code += f"  var h1 = CSG.cylinder({{start:[l*0.7, w/2, -1], end:[l*0.7, w/2, t+1], radius:r, slices:32}});\n"
                    code += f"  var h2 = CSG.cylinder({{start:[-1, w/2, l*0.7], end:[t+1, w/2, l*0.7], radius:r, slices:32}});\n"
                    code += f"  bracket = bracket.subtract(h1).subtract(h2);\n"
                code += f"  return bracket;\n}}"

            elif h == "nema":
                t, tol = sl_n_grosor.value, sl_n_tol.value
                w, c_hole, m3, dist = 42.3, 11 + tol, 1.5 + tol, 15.5
                code = f"function main() {{\n  var t = {t};\n  var base = CSG.cube({{center:[0,0,t/2], radius:[{w/2}, {w/2}, t/2]}});\n"
                code += f"  var c_hole = CSG.cylinder({{start:[0,0,-1], end:[0,0,t+1], radius:{c_hole}, slices:64}});\n"
                code += f"  var h1 = CSG.cylinder({{start:[{dist}, {dist}, -1], end:[{dist}, {dist}, t+1], radius:{m3}, slices:32}});\n"
                code += f"  var h2 = CSG.cylinder({{start:[{-dist}, {dist}, -1], end:[{-dist}, {dist}, t+1], radius:{m3}, slices:32}});\n"
                code += f"  var h3 = CSG.cylinder({{start:[{dist}, {-dist}, -1], end:[{dist}, {-dist}, t+1], radius:{m3}, slices:32}});\n"
                code += f"  var h4 = CSG.cylinder({{start:[{-dist}, {-dist}, -1], end:[{-dist}, {-dist}, t+1], radius:{m3}, slices:32}});\n"
                code += f"  return base.subtract(c_hole).subtract(h1).subtract(h2).subtract(h3).subtract(h4);\n}}"

            elif h == "pcb":
                px, py, ht, t = sl_pcb_x.value, sl_pcb_y.value, sl_pcb_h.value, sl_pcb_t.value
                code = f"function main() {{\n  var px = {px}; var py = {py}; var h = {ht}; var t = {t};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[px/2 + t, py/2 + t, h/2]}});\n"
                code += f"  var int = CSG.cube({{center:[0,0,h/2 + t], radius:[px/2, py/2, h/2]}});\n"
                code += f"  var box = ext.subtract(int);\n"
                code += f"  var dx = px/2 - 3.5; var dy = py/2 - 3.5;\n"
                code += f"  var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n"
                code += f"    var cyl = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 0], end:[m[i][0]*dx, m[i][1]*dy, h-2], radius: 3.5, slices:16}});\n"
                code += f"    var hole = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 2], end:[m[i][0]*dx, m[i][1]*dy, h], radius: 1.5, slices:16}});\n"
                code += f"    box = box.union(cyl).subtract(hole);\n  }}\n  return box;\n}}"

            elif h == "acople":
                d1, d2, dext, ht = sl_a_d1.value, sl_a_d2.value, sl_a_dext.value, sl_a_h.value
                code = f"function main() {{\n  var d1 = {d1}; var d2 = {d2}; var dext = {dext}; var h = {ht};\n"
                code += f"  var body = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:dext/2, slices:64}});\n"
                code += f"  var h1 = CSG.cylinder({{start:[0,0,-1], end:[0,0,h/2 + 0.5], radius:d1/2, slices:32}});\n"
                code += f"  var h2 = CSG.cylinder({{start:[0,0,h/2 - 0.5], end:[0,0,h+1], radius:d2/2, slices:32}});\n"
                code += f"  var slit = CSG.cube({{center:[dext/2, 0, h/2], radius:[dext/2, 0.5, h/2 + 1]}});\n"
                code += f"  var scr1 = CSG.cylinder({{start:[0, -dext, h/4], end:[0, dext, h/4], radius:1.5, slices:16}});\n"
                code += f"  var scr2 = CSG.cylinder({{start:[0, -dext, 3*h/4], end:[0, dext, 3*h/4], radius:1.5, slices:16}});\n"
                code += f"  return body.subtract(h1).subtract(h2).subtract(slit).subtract(scr1).subtract(scr2);\n}}"

            elif h == "vslot":
                l = sl_v_l.value
                code = f"function main() {{\n  var l = {l};\n  var b = CSG.cube({{center:[0,0,l/2], radius:[10,10,l/2]}});\n"
                code += f"  var ch = CSG.cylinder({{start:[0,0,-1], end:[0,0,l+1], radius:2.1, slices:32}});\n  b = b.subtract(ch);\n"
                code += f"  b = b.subtract(CSG.cube({{center:[0,10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  b = b.subtract(CSG.cube({{center:[0,-10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,-8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  b = b.subtract(CSG.cube({{center:[10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  b = b.subtract(CSG.cube({{center:[-10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[-8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  return b;\n}}"

            txt_code.value = code
            txt_code.update()

        # UI Blocks Sliders
        sl_c_x, r_c_x = create_slider("Ancho X", 5, 200, 50, False, generate_param_code)
        sl_c_y, r_c_y = create_slider("Fondo Y", 5, 200, 30, False, generate_param_code)
        sl_c_z, r_c_z = create_slider("Alto Z", 5, 200, 20, False, generate_param_code)
        sl_c_grosor, r_c_g = create_slider("Grosor Pared", 0, 20, 0, False, generate_param_code)
        col_cubo = ft.Column([ft.Container(content=ft.Column([r_c_x, r_c_y, r_c_z, r_c_g]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=True)

        sl_p_rext, r_p_rext = create_slider("Radio Ext", 5, 100, 25, False, generate_param_code)
        sl_p_rint, r_p_rint = create_slider("Radio Int", 0, 95, 15, False, generate_param_code)
        sl_p_h, r_p_h = create_slider("Altura", 2, 200, 10, False, generate_param_code)
        sl_p_lados, r_p_lados = create_slider("Caras/Resol.", 3, 64, 64, True, generate_param_code)
        col_cilindro = ft.Column([ft.Container(content=ft.Column([r_p_rext, r_p_rint, r_p_h, r_p_lados]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_e_dientes, r_e_d = create_slider("Dientes", 6, 40, 16, True, generate_param_code)
        sl_e_radio, r_e_r = create_slider("Radio Base", 10, 100, 30, False, generate_param_code)
        sl_e_grosor, r_e_g = create_slider("Grosor", 2, 50, 5, False, generate_param_code)
        sl_e_eje, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False, generate_param_code)
        col_engranaje = ft.Column([ft.Container(content=ft.Column([r_e_d, r_e_r, r_e_g, r_e_e]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_l_largo, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False, generate_param_code)
        sl_l_ancho, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False, generate_param_code)
        sl_l_grosor, r_l_g = create_slider("Grosor Chapa", 1, 20, 3, False, generate_param_code)
        sl_l_hueco, r_l_h = create_slider("Radio Agujero", 0, 10, 2, False, generate_param_code)
        col_escuadra = ft.Column([ft.Container(content=ft.Column([r_l_l, r_l_a, r_l_g, r_l_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_n_grosor, r_n_g = create_slider("Grosor Placa", 2, 20, 5, False, generate_param_code)
        sl_n_tol, r_n_t = create_slider("Tolerancia", 0, 2, 0.4, False, generate_param_code)
        col_nema = ft.Column([ft.Container(content=ft.Column([r_n_g, r_n_t]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False, generate_param_code)
        sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False, generate_param_code)
        sl_pcb_h, r_pcb_h = create_slider("Altura Caja", 10, 100, 20, False, generate_param_code)
        sl_pcb_t, r_pcb_t = create_slider("Grosor Pared", 1, 10, 2, False, generate_param_code)
        col_pcb = ft.Column([ft.Container(content=ft.Column([r_pcb_x, r_pcb_y, r_pcb_h, r_pcb_t]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_a_d1, r_a_d1 = create_slider("Eje Motor (Ø)", 2, 20, 5, False, generate_param_code)
        sl_a_d2, r_a_d2 = create_slider("Varilla (Ø)", 2, 20, 8, False, generate_param_code)
        sl_a_dext, r_a_dext = create_slider("Ø Ext Acople", 10, 50, 20, False, generate_param_code)
        sl_a_h, r_a_h = create_slider("Largo Total", 10, 80, 25, False, generate_param_code)
        col_acople = ft.Column([ft.Container(content=ft.Column([r_a_d1, r_a_d2, r_a_dext, r_a_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_v_l, r_v_l = create_slider("Longitud", 10, 300, 50, False, generate_param_code)
        col_vslot = ft.Column([ft.Text("Perfil estructural 20x20 compatible con T-Nuts.", color="grey", size=12), ft.Container(content=ft.Column([r_v_l]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # Sistema de Miniaturas (Cards)
        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            for c in [col_cubo, col_cilindro, col_engranaje, col_escuadra, col_nema, col_pcb, col_acople, col_vslot]:
                c.visible = False
            if nombre_herramienta == "cubo": col_cubo.visible = True
            elif nombre_herramienta == "cilindro": col_cilindro.visible = True
            elif nombre_herramienta == "engranaje": col_engranaje.visible = True
            elif nombre_herramienta == "escuadra": col_escuadra.visible = True
            elif nombre_herramienta == "nema": col_nema.visible = True
            elif nombre_herramienta == "pcb": col_pcb.visible = True
            elif nombre_herramienta == "acople": col_acople.visible = True
            elif nombre_herramienta == "vslot": col_vslot.visible = True
            generate_param_code()
            page.update()

        def create_thumbnail(icon, title, tool_id, color):
            return ft.Container(
                content=ft.Column([ft.Text(icon, size=35), ft.Text(title, size=11, text_align="center", weight="bold")], alignment=ft.MainAxisAlignment.CENTER),
                width=90, height=90, bgcolor=color, border_radius=12, alignment=ft.alignment.center,
                on_click=lambda _: select_tool(tool_id), ink=True
            )

        row_miniaturas = ft.Row([
            create_thumbnail("📦", "Cubo / Caja", "cubo", "#37474f"),
            create_thumbnail("🔌", "Caja PCB", "pcb", "#004d40"),
            create_thumbnail("🏗️", "V-Slot 2020", "vslot", "#1a237e"),
            create_thumbnail("⚙️", "Engranaje", "engranaje", "#ff6f00"),
            create_thumbnail("🔗", "Acople Ejes", "acople", "#4a148c"),
            create_thumbnail("🛢️", "Cilindro", "cilindro", "#37474f"),
            create_thumbnail("📐", "Escuadra L", "escuadra", "#bf360c"),
            create_thumbnail("🔩", "NEMA 17", "nema", "#1b5e20"),
        ], scroll="auto")

        view_constructor = ft.Column([
            ft.Text("1. Selecciona Pieza Base:", weight="bold", color="amber"),
            row_miniaturas,
            ft.Divider(),
            ft.Text("2. Parámetros Exactos:", weight="bold", color="cyan"),
            col_cubo, col_cilindro, col_engranaje, col_escuadra, col_nema, col_pcb, col_acople, col_vslot,
            ft.Container(height=10),
            ft.ElevatedButton("▶ ACTUALIZAR Y VER MALLA", on_click=lambda _: run_render(), color="black", bgcolor="amber", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        # =========================================================
        # GESTOR DE ARCHIVOS Y RUTINAS BASE
        # =========================================================
        file_list = ft.ListView(expand=True, spacing=10)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                if f == "nexus_config.json": continue
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: export_manual(open(os.path.join(EXPORT_DIR, name), "r").read())
                def make_del(name): return lambda _: delete_file(name)

                acciones = ft.Row([
                    ft.ElevatedButton("▶ Cargar", on_click=make_load(f), color="white", bgcolor="#1b5e20"),
                    ft.ElevatedButton("📤 Exportar", on_click=make_copy(f), color="white", bgcolor="#0d47a1"),
                    ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#b71c1c"),
                ], scroll="auto")
                row = ft.Column([ft.Text(f, weight="bold"), acciones])
                file_list.controls.append(ft.Container(content=row, padding=10, bgcolor="#1a1a1a", border_radius=8))
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                set_tab(0) 
                status.value = f"✓ {name} cargado en Editor."
            except: pass
            page.update()

        def delete_file(name):
            os.remove(os.path.join(EXPORT_DIR, name)); update_files()

        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files()
            status.value = f"✓ Guardado: {fname}"
            page.update()

        # =========================================================
        # VISTAS INDEPENDIENTES 
        # =========================================================
        view_editor = ft.Column([
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR PIEZA", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            row_snippets,
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🚀 CARGAR MOTOR 3D (WebGL)", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="white", height=80, width=300)
        view_visor = ft.Column([
            ft.Container(height=40), 
            ft.Text("Visualizador 3D Local Activo", text_align="center", color="cyan", weight="bold"),
            ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER)
        ], expand=True)
        
        view_archivos = ft.Column([ft.Text("Mis Piezas Funcionales", weight="bold"), file_list], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_constructor, view_visor, view_archivos]
            main_container.content = tabs[idx]
            if idx == 3: update_files()
            page.update()

        # BARRA DE NAVEGACIÓN INFERIOR (Flujo: Code -> Build -> 3D)
        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("🛠️ BUILD / LIB", on_click=lambda _: set_tab(1), color="black", bgcolor="amber"),
            ft.ElevatedButton("👁️ VISOR 3D", on_click=lambda _: set_tab(2), color="white", bgcolor="#004d40"),
            ft.ElevatedButton("📁 FILES", on_click=lambda _: set_tab(3)),
        ], scroll="auto")

        # BOTÓN FLOTANTE (FAB) PARA SALTO RÁPIDO AL 3D
        page.floating_action_button = ft.FloatingActionButton(
            icon=ft.icons.VIEW_IN_AR_SHARP, on_click=lambda _: set_tab(2), bgcolor="amber"
        )

        root_container = ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True)
        page.add(root_container)
        
        # Iniciar backend visual
        generate_param_code()
        update_files()

    except Exception:
        page.clean()
        page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50))
        page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)