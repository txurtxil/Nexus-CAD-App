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

def start_server():
    try:
        http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever()
    except:
        pass
threading.Thread(target=start_server, daemon=True).start()

# =========================================================
# APLICACIÓN PRINCIPAL (SISTEMA DE NAVEGACIÓN PROPIO)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v3.4"
        page.theme_mode = "dark"
        page.padding = 10
        
        status = ft.Text("Navegacion Bare-Metal Activa", color="green")

        # --- PORTAPAPELES ---
        def copy_to_clipboard(text_to_copy):
            success = False
            try:
                page.clipboard.set_text(text_to_copy)
                success = True
            except: pass
            
            if not success:
                try:
                    page.set_clipboard(text_to_copy)
                    success = True
                except: pass
                
            if not success:
                try:
                    subprocess.run(['termux-clipboard-set'], input=text_to_copy.encode('utf-8'))
                    success = True
                except: pass
            
            if success:
                status.value = "✓ Codigo copiado."
            else:
                status.value = "❌ Error portapapeles."
            page.update()

        # --- PLANTILLAS ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        T_ENGRARE = "function main() {\n  var b = CSG.cylinder({start:[0,0,0], end:[0,0,5], radius:20});\n  return b;\n}"
        T_PEANA = "function main() {\n  var base = CSG.cube({center: [0, 0, 5], radius: [60, 40, 5]});\n  var soporte = CSG.cube({center: [0, 10, 25], radius: [60, 5, 25]});\n  return base.union(soporte);\n}"

        txt_code = ft.TextField(label="Codigo JS-CSG", multiline=True, expand=True, value=T_CARCASA)

        def load_template(t):
            txt_code.value = t
            page.update()

        btn_c = ft.ElevatedButton("📦 Carcasa", on_click=lambda _: load_template(T_CARCASA))
        btn_e = ft.ElevatedButton("⚙️ Engranaje", on_click=lambda _: load_template(T_ENGRARE))
        btn_p = ft.ElevatedButton("📱 Peana", on_click=lambda _: load_template(T_PEANA))
        
        row_templates = ft.Row([btn_c, btn_e, btn_p], wrap=True)

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: copy_file_content(name)
                def make_del(name): return lambda _: delete_file(name)

                btn_load = ft.ElevatedButton("▶", on_click=make_load(f))
                btn_copy = ft.ElevatedButton("📋", on_click=make_copy(f))
                btn_del = ft.ElevatedButton("🗑️", on_click=make_del(f))

                row = ft.Row([ft.Text(f[:15], expand=True), btn_load, btn_copy, btn_del])
                file_list.controls.append(ft.Container(content=row, padding=5))
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                set_tab(0) # Va al Editor
                status.value = "✓ " + name + " cargado."
            except:
                status.value = "❌ Error al leer."
            page.update()

        def copy_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: copy_to_clipboard(f.read())
            except:
                status.value = "❌ Error al copiar."
                page.update()

        def delete_file(name):
            try:
                os.remove(os.path.join(EXPORT_DIR, name))
                status.value = "✓ Eliminado."
            except:
                status.value = "❌ Error al borrar."
            update_files()

        # --- COMPILACIÓN Y GUARDADO ---
        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(1) # Va al Visor
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            try:
                with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
                status.value = "✓ Guardado: " + fname
            except:
                status.value = "❌ Error de escritura."
            update_files()

        # =========================================================
        # VISTAS INDEPENDIENTES (El nuevo sistema de Pestañas)
        # =========================================================
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render()),
            ft.Row([ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project()), ft.Text("Plantillas:")]),
            row_templates,
            txt_code
        ], expand=True)

        view_visor = ft.Container(content=ft.ElevatedButton("ABRIR VISOR NATIVO", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/"))
        
        view_archivos = ft.Column([ft.Text("Mis Proyectos"), file_list], expand=True)
        
        view_ia = ft.Column([
            ft.Text("Prompts para enviar a tu IA:"),
            ft.TextField(label="Carcasa Técnica", value="Genera codigo Javascript CSG.js para carcasa 90x60x30mm con vaciado pared 2mm. Usa center:[x,y,z].", multiline=True),
        ], expand=True)

        # =========================================================
        # MOTOR DE NAVEGACIÓN PERSONALIZADO (Cero Crashes)
        # =========================================================
        # Este contenedor cambiará su contenido dinámicamente según el botón que pulses
        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            if idx == 0: main_container.content = view_editor
            elif idx == 1: main_container.content = view_visor
            elif idx == 2: main_container.content = view_archivos
            elif idx == 3: main_container.content = view_ia
            page.update()

        # Nuestra barra de navegación fabricada a mano con botones
        nav_bar = ft.Row([
            ft.ElevatedButton("💻 EDITOR", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("👁️ VISOR", on_click=lambda _: set_tab(1)),
            ft.ElevatedButton("📁 ARCHIVOS", on_click=lambda _: (update_files(), set_tab(2))),
            ft.ElevatedButton("🧠 IA", on_click=lambda _: set_tab(3)),
        ])

        # Renderizado Final
        page.add(nav_bar, main_container, status)
        update_files()

    except Exception:
        page.clean()
        page.add(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"))
        page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)