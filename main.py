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
# MOTOR SERVIDOR LOCAL
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
# APLICACIÓN PRINCIPAL v5.1 (CONSTRUCTOR PRO)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v5.1"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("NEXUS v5.1 | Constructor PRO Activo", color="green")

        def open_dialog(dialog):
            try: page.open(dialog)
            except: 
                if dialog not in page.overlay: page.overlay.append(dialog)
                dialog.open = True
                page.update()

        def close_dialog(dialog):
            try: page.close(dialog)
            except: dialog.open = False; page.update()

        def export_manual(texto, titulo="Exportar Código"):
            txt_copy = ft.TextField(value=texto, multiline=True, read_only=True, expand=True)
            dlg_copy = ft.AlertDialog(
                title=ft.Text(titulo),
                content=ft.Column([
                    ft.Text("Mantén pulsado en el texto para COPIAR:", color="grey"),
                    ft.Container(content=txt_copy, height=300)
                ]),
                actions=[ft.ElevatedButton("CERRAR", on_click=lambda _: close_dialog(dlg_copy))]
            )
            open_dialog(dlg_copy)

        def copy_text(text_to_copy):
            try:
                page.set_clipboard(str(text_to_copy))
                status.value = "✓ Código copiado."
                status.color = "green"
                page.update()
            except:
                try:
                    subprocess.run(['termux-clipboard-set'], input=str(text_to_copy).encode('utf-8'))
                    status.value = "✓ Copiado (Termux)."
                    status.color = "green"
                    page.update()
                except:
                    export_manual(str(text_to_copy), "Copiar Prompt Manualmente")
                    status.value = "⚠️ Usa copia manual."
                    status.color = "amber"
                    page.update()

        # --- EDITOR JS-CSG BASE ---
        T_INICIAL = "function main() {\n  return CSG.cube({center:[0,0,10], radius:[20,20,10]});\n}"
        txt_code = ft.TextField(label="Código JS-CSG", multiline=True, expand=True, value=T_INICIAL)

        def load_template(t):
            txt_code.value = t
            txt_code.update() 
            set_tab(0) 
            status.value = "✓ Código cargado."
            status.color = "green"
            status.update()

        def clear_editor():
            txt_code.value = "function main() {\n  return CSG.cube({center:[0,0,0], radius:[10,10,10]});\n}"
            txt_code.update()

        def inject_snippet(code_snippet):
            txt_code.value = txt_code.value + "\n" + code_snippet
            txt_code.update()

        row_snippets = ft.Row([
            ft.Text("Inyectar:", color="grey", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[5,5,5]});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5, slices:32});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("  var final = pieza1.subtract(pieza2);"), bgcolor="#4e342e", color="white"),
        ], scroll="auto")

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2)
            page.update()

        # =========================================================
        # CONSTRUCTOR PARAMÉTRICO PRO (FASE 1.5)
        # =========================================================
        def generate_param_code(e=None):
            shape = param_shape_dd.value
            
            # 1. CUBO / CAJA HUECA
            if shape == "📦 Cubo / Caja":
                g = sl_c_grosor.value
                code = f"function main() {{\n  var ext = CSG.cube({{center:[0,0,{sl_c_z.value/2}], radius:[{sl_c_x.value/2}, {sl_c_y.value/2}, {sl_c_z.value/2}]}});\n"
                if g > 0:
                    g = min(g, min(sl_c_x.value, sl_c_y.value) / 2.1) # Evitar que el grosor supere el tamaño
                    code += f"  var int = CSG.cube({{center:[0,0,{sl_c_z.value/2 + g}], radius:[{sl_c_x.value/2 - g}, {sl_c_y.value/2 - g}, {sl_c_z.value/2}]}});\n  return ext.subtract(int);\n}}"
                else:
                    code += f"  return ext;\n}}"

            # 2. CILINDRO / POLÍGONO (Tuercas)
            elif shape == "🛢️ Cilindro / Polígono":
                rint = min(sl_p_rint.value, sl_p_rext.value - 0.5)
                if rint < 0: rint = 0
                caras = int(sl_p_lados.value)
                code = f"function main() {{\n  var ext = CSG.cylinder({{start:[0,0,0], end:[0,0,{sl_p_h.value}], radius:{sl_p_rext.value}, slices:{caras}}});\n"
                if rint > 0:
                    code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,{sl_p_h.value+2}], radius:{rint}, slices:{caras}});\n  return ext.subtract(int);\n}}"
                else:
                    code += f"  return ext;\n}}"
                    
            # 3. ENGRANAJE DINÁMICO
            elif shape == "⚙️ Engranaje":
                d = int(sl_e_dientes.value)
                r = sl_e_radio.value
                h = sl_e_grosor.value
                eje = sl_e_eje.value
                
                # Tamaño proporcional del diente
                d_x = r * 0.15
                d_y = r * 0.2
                
                code = f"function main() {{\n  var dientes = {d}; var r = {r}; var h = {h};\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n"
                code += f"    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var x = Math.cos(a) * r;\n    var y = Math.sin(a) * r;\n"
                code += f"    var diente = CSG.cube({{center:[x,y,h/2], radius:[{d_x}, {d_y}, h/2]}});\n"
                code += f"    base = base.union(diente);\n  }}\n"
                if eje > 0:
                    code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{eje}, slices:32}});\n  return base.subtract(hueco);\n}}"
                else:
                    code += f"  return base;\n}}"
            
            # 4. ESFERA
            elif shape == "⚽ Esfera":
                r = sl_s_radio.value
                res = int(sl_s_res.value)
                code = f"function main() {{\n  return CSG.sphere({{center:[0,0,{r}], radius:{r}, resolution:{res}}});\n}}"

            txt_code.value = code
            txt_code.update()
            status.value = f"✓ {shape} generado."
            status.color = "amber"
            status.update()

        def update_constructor_ui(e=None):
            col_cubo.visible = param_shape_dd.value == "📦 Cubo / Caja"
            col_prisma.visible = param_shape_dd.value == "🛢️ Cilindro / Polígono"
            col_engranaje.visible = param_shape_dd.value == "⚙️ Engranaje"
            col_esfera.visible = param_shape_dd.value == "⚽ Esfera"
            generate_param_code()
            page.update()

        # Instanciación segura sin on_change
        param_shape_dd = ft.Dropdown(
            options=[
                ft.dropdown.Option("📦 Cubo / Caja"), 
                ft.dropdown.Option("🛢️ Cilindro / Polígono"), 
                ft.dropdown.Option("⚙️ Engranaje"),
                ft.dropdown.Option("⚽ Esfera")
            ],
            value="📦 Cubo / Caja",
            label="1. Primitiva Avanzada",
            bgcolor="#212121"
        )
        param_shape_dd.on_change = update_constructor_ui

        # 1. UI Cubo / Caja
        sl_c_x = ft.Slider(min=5, max=200, value=50, label="Ancho (X): {value}mm")
        sl_c_y = ft.Slider(min=5, max=200, value=30, label="Profundidad (Y): {value}mm")
        sl_c_z = ft.Slider(min=5, max=200, value=20, label="Alto (Z): {value}mm")
        sl_c_grosor = ft.Slider(min=0, max=20, value=0, label="Grosor Pared (0=Macizo): {value}mm")
        for sl in [sl_c_x, sl_c_y, sl_c_z, sl_c_grosor]: sl.on_change = generate_param_code
        col_cubo = ft.Column([ft.Text("Dimensiones Base:", color="cyan"), sl_c_x, sl_c_y, sl_c_z, sl_c_grosor], visible=True)

        # 2. UI Prisma / Tubo
        sl_p_rext = ft.Slider(min=5, max=100, value=25, label="Radio Exterior: {value}mm")
        sl_p_rint = ft.Slider(min=0, max=95, value=15, label="Radio Interior (0=Macizo): {value}mm")
        sl_p_h = ft.Slider(min=2, max=200, value=10, label="Altura: {value}mm")
        sl_p_lados = ft.Slider(min=3, max=64, value=6, divisions=61, label="Caras (3=Tri, 6=Hex, 64=Círculo): {value}")
        for sl in [sl_p_rext, sl_p_rint, sl_p_h, sl_p_lados]: sl.on_change = generate_param_code
        col_prisma = ft.Column([ft.Text("Ajustes de Revolución (¡Prueba a poner 6 caras!):", color="cyan"), sl_p_rext, sl_p_rint, sl_p_h, sl_p_lados], visible=False)

        # 3. UI Engranaje
        sl_e_dientes = ft.Slider(min=6, max=40, value=16, divisions=34, label="Número Dientes: {value}")
        sl_e_radio = ft.Slider(min=10, max=100, value=30, label="Radio Base: {value}mm")
        sl_e_grosor = ft.Slider(min=2, max=50, value=5, label="Grosor: {value}mm")
        sl_e_eje = ft.Slider(min=0, max=30, value=5, label="Hueco Eje (0=Macizo): {value}mm")
        for sl in [sl_e_dientes, sl_e_radio, sl_e_grosor, sl_e_eje]: sl.on_change = generate_param_code
        col_engranaje = ft.Column([ft.Text("Parámetros de Engranaje Recto:", color="cyan"), sl_e_dientes, sl_e_radio, sl_e_grosor, sl_e_eje], visible=False)

        # 4. UI Esfera
        sl_s_radio = ft.Slider(min=5, max=100, value=30, label="Radio: {value}mm")
        sl_s_res = ft.Slider(min=8, max=64, value=32, divisions=56, label="Resolución de malla: {value}")
        for sl in [sl_s_radio, sl_s_res]: sl.on_change = generate_param_code
        col_esfera = ft.Column([ft.Text("Parámetros de Esfera:", color="cyan"), sl_s_radio, sl_s_res], visible=False)

        view_constructor = ft.Column([
            ft.Text("🛠️ Motor Paramétrico Avanzado", weight="bold", color="amber", size=18),
            ft.Text("Diseña piezas complejas sin tocar una línea de código.", color="grey", size=12),
            param_shape_dd,
            ft.Divider(),
            col_cubo,
            col_prisma,
            col_engranaje,
            col_esfera,
            ft.Divider(),
            ft.ElevatedButton("▶ GENERAR MALLA 3D", on_click=lambda _: run_render(), color="black", bgcolor="amber", height=60, width=float('inf'))
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

        # =========================================================
        # LIBRERÍA DE INGENIERÍA
        # =========================================================
        def create_gallery(icon, title, examples):
            controls = []
            for name, code in examples:
                controls.append(ft.Text(name, color="green", weight="bold"))
                controls.append(ft.ElevatedButton("▶ Cargar Código", on_click=lambda e, c=code: load_template(c), bgcolor="#1b5e20", color="white"))
                controls.append(ft.Container(height=15))
            col = ft.Column(controls, visible=False)
            btn = ft.ElevatedButton(icon + " " + title, on_click=lambda _: (setattr(col, "visible", not col.visible), page.update()), width=float('inf'), color="black", bgcolor="cyan")
            return ft.Column([btn, col])

        CODE_ESTACION = "function main() {\n  var base = CSG.cube({center: [0,0,12.5], radius: [80,60,12.5]});\n  for(var x = -70; x <= -10; x += 22) {\n    for(var y = -50; y <= 10; y += 22) {\n      base = base.subtract(CSG.cube({center: [x,y,14.5], radius: [9,9,12.5]}));\n    }\n  }\n  return base;\n}"

        view_ia = ft.Column([
            ft.Text("Plantillas Industriales:", weight="bold", color="cyan"),
            create_gallery("📚", "ESTACIÓN DE SOLDADURA", [("Base Multi-Huecos SMD", CODE_ESTACION)]),
            ft.Container(height=20),
            ft.Text("💡 Tip Pro:", color="amber", weight="bold"),
            ft.Text("Ve a la pestaña BUILD. Selecciona 'Cilindro / Polígono'. Ajusta las 'Caras' a 6 y ponle Radio Interior. Acabas de crear una tuerca hexagonal para impresión 3D.", color="grey", size=13)
        ], expand=True, scroll="auto")

        # =========================================================
        # VISTAS INDEPENDIENTES 
        # =========================================================
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), color="white", bgcolor="#004d40", height=50),
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ LIMPIAR", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            row_snippets,
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🚀 ABRIR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="white", height=60)
        view_visor = ft.Column([ft.Container(height=80), ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER)], expand=True)
        
        view_archivos = ft.Column([ft.Text("Mis Proyectos", weight="bold"), file_list], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_constructor, view_visor, view_archivos, view_ia]
            main_container.content = tabs[idx]
            if idx == 3: update_files()
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("🛠️ BUILD", on_click=lambda _: set_tab(1), color="black", bgcolor="amber"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2)),
            ft.ElevatedButton("📁 FILE", on_click=lambda _: set_tab(3)),
            ft.ElevatedButton("📚 LIB", on_click=lambda _: set_tab(4), color="black", bgcolor="cyan"),
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