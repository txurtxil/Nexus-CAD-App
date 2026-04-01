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
# APLICACIÓN PRINCIPAL v8.0 (MECHANICAL PRO)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v8.0"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("NEXUS v8.0 | Mecánica Industrial Activa", color="green")

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
        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,10], radius:[20,20,10]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL)

        def clear_editor():
            txt_code.value = "function main() {\n  var pieza = CSG.cube({center:[0,0,0], radius:[10,10,10]});\n  return pieza;\n}"
            txt_code.update()

        def inject_snippet(code_snippet):
            c = txt_code.value
            pos = c.rfind('return ')
            if pos != -1:
                txt_code.value = c[:pos] + code_snippet + "\n  " + c[pos:]
            else:
                txt_code.value = c + "\n" + code_snippet
            txt_code.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2)
            page.update()

        row_snippets = ft.Row([
            ft.Text("Primitivas:", color="grey", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[5,5,5]});")),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5, slices:32});")),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("  pieza = pieza.subtract(pieza2);")),
        ], scroll="auto")

        # =========================================================
        # CONSTRUCTOR PARAMÉTRICO Y GALERÍA (PESTAÑA BUILD)
        # =========================================================
        herramienta_actual = "custom"

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
            
            if h == "custom":
                pass 

            elif h == "cubo":
                g = sl_c_grosor.value
                code = f"function main() {{\n  var pieza = CSG.cube({{center:[0,0,{sl_c_z.value/2}], radius:[{sl_c_x.value/2}, {sl_c_y.value/2}, {sl_c_z.value/2}]}});\n"
                if g > 0:
                    g = min(g, min(sl_c_x.value, sl_c_y.value) / 2.1)
                    code += f"  var int = CSG.cube({{center:[0,0,{sl_c_z.value/2 + g}], radius:[{sl_c_x.value/2 - g}, {sl_c_y.value/2 - g}, {sl_c_z.value/2}]}});\n  pieza = pieza.subtract(int);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code

            elif h == "cilindro":
                rint = min(sl_p_rint.value, sl_p_rext.value - 0.5)
                c = int(sl_p_lados.value)
                code = f"function main() {{\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,{sl_p_h.value}], radius:{sl_p_rext.value}, slices:{c}}});\n"
                if rint > 0:
                    code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,{sl_p_h.value+2}], radius:{rint}, slices:{c}}});\n  pieza = pieza.subtract(int);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code
                    
            elif h == "engranaje":
                d, r, ht, eje = int(sl_e_dientes.value), sl_e_radio.value, sl_e_grosor.value, sl_e_eje.value
                d_x, d_y = r * 0.15, r * 0.2
                code = f"function main() {{\n  var dientes = {d}; var r = {r}; var h = {ht};\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var diente = CSG.cube({{center:[Math.cos(a)*r, Math.sin(a)*r, h/2], radius:[{d_x}, {d_y}, h/2]}});\n    pieza = pieza.union(diente);\n  }}\n"
                if eje > 0: code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{eje}, slices:32}});\n  pieza = pieza.subtract(hueco);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code
            
            elif h == "escuadra":
                l, w, t, hr = sl_l_largo.value, sl_l_ancho.value, sl_l_grosor.value, sl_l_hueco.value
                code = f"function main() {{\n  var l = {l}; var w = {w}; var t = {t}; var r = {hr};\n"
                code += f"  var base = CSG.cube({{center:[l/2, w/2, t/2], radius:[l/2, w/2, t/2]}});\n"
                code += f"  var wall = CSG.cube({{center:[t/2, w/2, l/2], radius:[t/2, w/2, l/2]}});\n  var pieza = base.union(wall);\n"
                if hr > 0:
                    code += f"  var h1 = CSG.cylinder({{start:[l*0.7, w/2, -1], end:[l*0.7, w/2, t+1], radius:r, slices:32}});\n"
                    code += f"  var h2 = CSG.cylinder({{start:[-1, w/2, l*0.7], end:[t+1, w/2, l*0.7], radius:r, slices:32}});\n"
                    code += f"  pieza = pieza.subtract(h1).subtract(h2);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code

            elif h == "pcb":
                px, py, ht, t = sl_pcb_x.value, sl_pcb_y.value, sl_pcb_h.value, sl_pcb_t.value
                code = f"function main() {{\n  var px = {px}; var py = {py}; var h = {ht}; var t = {t};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[px/2 + t, py/2 + t, h/2]}});\n"
                code += f"  var int = CSG.cube({{center:[0,0,h/2 + t], radius:[px/2, py/2, h/2]}});\n"
                code += f"  var pieza = ext.subtract(int);\n"
                code += f"  var dx = px/2 - 3.5; var dy = py/2 - 3.5;\n"
                code += f"  var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n"
                code += f"    var cyl = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 0], end:[m[i][0]*dx, m[i][1]*dy, h-2], radius: 3.5, slices:16}});\n"
                code += f"    var hole = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 2], end:[m[i][0]*dx, m[i][1]*dy, h], radius: 1.5, slices:16}});\n"
                code += f"    pieza = pieza.union(cyl).subtract(hole);\n  }}\n  return pieza;\n}}"
                txt_code.value = code

            elif h == "vslot":
                l = sl_v_l.value
                code = f"function main() {{\n  var l = {l};\n  var pieza = CSG.cube({{center:[0,0,l/2], radius:[10,10,l/2]}});\n"
                code += f"  var ch = CSG.cylinder({{start:[0,0,-1], end:[0,0,l+1], radius:2.1, slices:32}});\n  pieza = pieza.subtract(ch);\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,-10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,-8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[-10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[-8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code

            elif h == "bisagra":
                l, d, tol = sl_bi_l.value, sl_bi_d.value, sl_bi_tol.value
                code = f"function main() {{\n  var l = {l}; var d = {d}; var tol = {tol};\n"
                code += f"  var fix = CSG.cylinder({{start:[0,0,0], end:[0,0,l/3], radius:d/2, slices:32}});\n"
                code += f"  var fix2 = CSG.cylinder({{start:[0,0,2*l/3], end:[0,0,l], radius:d/2, slices:32}});\n"
                code += f"  var move = CSG.cylinder({{start:[0,0,l/3+tol], end:[0,0,2*l/3-tol], radius:d/2, slices:32}});\n"
                code += f"  var pin = CSG.cylinder({{start:[0,0,l/3-d/4], end:[0,0,2*l/3+d/4], radius:(d/4)-tol, slices:32}});\n"
                code += f"  var cut_pin = CSG.cylinder({{start:[0,0,l/3-d/2], end:[0,0,2*l/3+d/2], radius:d/4, slices:32}});\n"
                code += f"  var fijo = fix.union(fix2).subtract(cut_pin).union(pin);\n"
                code += f"  var movil = move.subtract(cut_pin);\n"
                code += f"  var pieza = fijo.union(movil.translate([0, d+2, 0])); // Offset visual\n  return pieza;\n}}"
                txt_code.value = code

            # === NUEVAS FUNCIONES DE INGENIERÍA MECÁNICA v8.0 ===
            elif h == "tuerca":
                m, ht = sl_nut_m.value, sl_nut_h.value
                radio_hex = (m * 1.8) / 2  # Estándar aproximado ISO para cabeza hexagonal
                code = f"function main() {{\n  var m = {m}; var h = {ht};\n  var radioHex = {radio_hex};\n"
                code += f"  var cuerpo = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:radioHex, slices:6}});\n"
                code += f"  // Tolerancia de impresión 3D (+0.4mm al agujero)\n"
                code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:(m/2)+0.2, slices:32}});\n"
                code += f"  var pieza = cuerpo.subtract(agujero);\n  return pieza;\n}}"
                txt_code.value = code

            elif h == "abrazadera":
                diam, grosor, ancho = sl_clamp_d.value, sl_clamp_g.value, sl_clamp_w.value
                code = f"function main() {{\n  var diam = {diam}; var grosor = {grosor}; var ancho = {ancho};\n"
                code += f"  var ext = CSG.cylinder({{start:[0,0,0], end:[0,0,ancho], radius:(diam/2)+grosor, slices:64}});\n"
                code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,ancho+1], radius:diam/2, slices:64}});\n"
                code += f"  var corteInf = CSG.cube({{center:[0, -50, ancho/2], radius:[50, 50, ancho]}});\n"
                code += f"  var arco = ext.subtract(int).subtract(corteInf);\n\n"
                code += f"  var distPestana = (diam/2) + grosor + 5;\n"
                code += f"  var pestana = CSG.cube({{center:[ distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n"
                code += f"  var pestana2 = CSG.cube({{center:[ -distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n\n"
                code += f"  // Agujeros M3 para apretar (Avellanados)\n"
                code += f"  var m3 = CSG.cylinder({{start:[ distPestana, 10, ancho/2 ], end:[ distPestana, -10, ancho/2 ], radius:1.7, slices:16}});\n"
                code += f"  var m3_2 = CSG.cylinder({{start:[ -distPestana, 10, ancho/2 ], end:[ -distPestana, -10, ancho/2 ], radius:1.7, slices:16}});\n"
                code += f"  var pieza = arco.union(pestana).union(pestana2).subtract(m3).subtract(m3_2);\n  return pieza;\n}}"
                txt_code.value = code

            txt_code.update()

        def update_constructor_ui(e=None):
            for col in [col_custom, col_cubo, col_cilindro, col_engranaje, col_escuadra, col_pcb, col_vslot, col_bisagra, col_tuerca, col_abrazadera]: 
                col.visible = False
            v = herramienta_actual
            if v == "custom": col_custom.visible = True
            elif v == "cubo": col_cubo.visible = True
            elif v == "cilindro": col_cilindro.visible = True
            elif v == "engranaje": col_engranaje.visible = True
            elif v == "escuadra": col_escuadra.visible = True
            elif v == "pcb": col_pcb.visible = True
            elif v == "vslot": col_vslot.visible = True
            elif v == "bisagra": col_bisagra.visible = True
            elif v == "tuerca": col_tuerca.visible = True
            elif v == "abrazadera": col_abrazadera.visible = True
            generate_param_code()
            page.update()

        # UI Blocks Base
        col_custom = ft.Column([
            ft.Text("Módulo Activo: Tu Código de IA", color="green", weight="bold"),
            ft.Row([
                ft.ElevatedButton("🕳️ Vaciado", on_click=lambda _: inject_snippet("  var vaciado = pieza.scale([0.9, 0.9, 0.9]);\n  pieza = pieza.subtract(vaciado);"), bgcolor="#4e342e", color="white"),
                ft.ElevatedButton("🔄 Redondeo", on_click=lambda _: inject_snippet("  pieza = pieza.expand(2, 16);"), bgcolor="#1b5e20", color="white"),
            ], scroll="auto")
        ], visible=True)

        sl_c_x, r_c_x = create_slider("Ancho X", 5, 200, 50, False, generate_param_code)
        sl_c_y, r_c_y = create_slider("Fondo Y", 5, 200, 30, False, generate_param_code)
        sl_c_z, r_c_z = create_slider("Alto Z", 5, 200, 20, False, generate_param_code)
        sl_c_grosor, r_c_g = create_slider("Grosor Pared", 0, 20, 0, False, generate_param_code)
        col_cubo = ft.Column([ft.Container(content=ft.Column([r_c_x, r_c_y, r_c_z, r_c_g]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

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

        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False, generate_param_code)
        sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False, generate_param_code)
        sl_pcb_h, r_pcb_h = create_slider("Altura Caja", 10, 100, 20, False, generate_param_code)
        sl_pcb_t, r_pcb_t = create_slider("Grosor Pared", 1, 10, 2, False, generate_param_code)
        col_pcb = ft.Column([ft.Container(content=ft.Column([r_pcb_x, r_pcb_y, r_pcb_h, r_pcb_t]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_v_l, r_v_l = create_slider("Longitud", 10, 300, 50, False, generate_param_code)
        col_vslot = ft.Column([ft.Text("Perfil 2020 para CNC", color="grey", size=12), ft.Container(content=ft.Column([r_v_l]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False, generate_param_code)
        sl_bi_d, r_bi_d = create_slider("Diámetro", 5, 30, 10, False, generate_param_code)
        sl_bi_tol, r_bi_tol = create_slider("Tolerancia", 0.1, 1.0, 0.3, False, generate_param_code)
        col_bisagra = ft.Column([ft.Text("Despiece de bisagra Print-in-Place.", color="grey", size=12), ft.Container(content=ft.Column([r_bi_l, r_bi_d, r_bi_tol]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # UI Blocks Ingeniería Mecánica v8.0
        sl_nut_m, r_nut_m = create_slider("Métrica (M)", 3, 20, 8, True, generate_param_code)
        sl_nut_h, r_nut_h = create_slider("Altura (mm)", 2, 20, 6, False, generate_param_code)
        col_tuerca = ft.Column([ft.Text("Genera tuercas hexagonales estándar ISO con tolerancia de impresión (+0.2mm).", color="grey", size=12), ft.Container(content=ft.Column([r_nut_m, r_nut_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        sl_clamp_d, r_clamp_d = create_slider("Ø Tubo", 10, 100, 25, False, generate_param_code)
        sl_clamp_g, r_clamp_g = create_slider("Grosor Arco", 2, 15, 5, False, generate_param_code)
        sl_clamp_w, r_clamp_w = create_slider("Ancho Pieza", 5, 50, 15, False, generate_param_code)
        col_abrazadera = ft.Column([ft.Text("Soporte de media luna para tuberías, con aletas laterales preparadas para tornillos M3.", color="grey", size=12), ft.Container(content=ft.Column([r_clamp_d, r_clamp_g, r_clamp_w]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)


        # CARRUSEL
        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            update_constructor_ui()

        def create_thumbnail(icon, title, tool_id, color):
            return ft.Container(
                content=ft.Column([
                    ft.Text(icon, size=30), 
                    ft.Text(title, size=10, color="white", weight="bold")
                ]),
                width=80, height=80, bgcolor=color, border_radius=8, padding=10,
                on_click=lambda _: select_tool(tool_id)
            )

        row_miniaturas = ft.Row([
            create_thumbnail("🧠", "Mi Código", "custom", "#000000"),
            create_thumbnail("🔩", "Tuerca Hex", "tuerca", "#c62828"), # NUEVA HERRAMIENTA MECÁNICA
            create_thumbnail("🗜️", "Abrazadera", "abrazadera", "#1565c0"), # NUEVA HERRAMIENTA MECÁNICA
            create_thumbnail("📦", "Caja", "cubo", "#37474f"),
            create_thumbnail("🚪", "Bisagra", "bisagra", "#4a148c"),
            create_thumbnail("🏗️", "V-Slot", "vslot", "#1a237e"),
            create_thumbnail("🔌", "Caja PCB", "pcb", "#004d40"),
            create_thumbnail("⚙️", "Piñón", "engranaje", "#ff6f00"),
            create_thumbnail("🛢️", "Tubo", "cilindro", "#37474f"),
            create_thumbnail("📐", "Escuadra", "escuadra", "#bf360c"),
        ], scroll="auto")

        view_constructor = ft.Column([
            ft.Text("1. Galería Mecánica:", weight="bold", color="amber"),
            row_miniaturas,
            ft.Divider(),
            col_custom, col_tuerca, col_abrazadera, col_cubo, col_cilindro, col_engranaje, col_escuadra, col_pcb, col_vslot, col_bisagra,
            ft.Container(height=10),
            ft.ElevatedButton("▶ ACTUALIZAR MALLA (3D)", on_click=lambda _: run_render(), color="black", bgcolor="amber", height=60, width=float('inf'))
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
                    ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#b71c1c"),
                ], scroll="auto")
                row = ft.Column([ft.Text(f, weight="bold"), acciones])
                file_list.controls.append(ft.Container(content=row, padding=10, bgcolor="#1a1a1a", border_radius=8))
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                set_tab(0) 
                status.value = f"✓ {name} cargado."
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

        view_editor = ft.Column([
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            row_snippets,
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🔄 RECARGAR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="amber", height=60, width=300)
        view_visor = ft.Column([
            ft.Container(height=40), 
            ft.Text("Visualizador 3D Compilado", text_align="center", color="cyan", weight="bold"),
            ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
            ft.Text("📦 Usa el botón del visor Web para exportar a STL.", color="grey", text_align="center", size=12)
        ], expand=True)
        
        view_archivos = ft.Column([ft.Text("Mis Archivos", weight="bold"), file_list], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_constructor, view_visor, view_archivos]
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            if idx == 3: update_files()
            main_container.content = tabs[idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("🛠️ BUILD", on_click=lambda _: set_tab(1), color="black", bgcolor="amber"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), color="white", bgcolor="#004d40"),
            ft.ElevatedButton("📁 FILES", on_click=lambda _: set_tab(3)),
        ], scroll="auto")

        root_container = ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True)
        page.add(root_container)
        
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