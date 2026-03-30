import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# CONFIGURACIÓN DE RUTAS UNIVERSAL (APK / TERMUX)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Determinar carpeta de proyectos segura
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
try:
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR, exist_ok=True)
except:
    # Fallback para APKs en carpetas restringidas
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

# =========================================================
# MOTOR SERVIDOR LOCAL HTTP (Puerto Dinámico)
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
# APLICACIÓN PRINCIPAL NEXUS CAD
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v2.8.5"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0

        status = ft.Text("Sistema Online v2.8.5", size=10, color="grey600")

        # --- SISTEMA DE PORTAPAPELES (Compatibilidad Máxima) ---
        def copy_to_clipboard(text):
            try:
                if hasattr(page, 'set_clipboard'):
                    page.set_clipboard(text)
                else:
                    # Fallback nativo Termux
                    subprocess.run(['termux-clipboard-set'], input=text.encode('utf-8'))
                status.value = "✓ Copiado correctamente."
            except:
                status.value = "❌ Error al acceder al portapapeles."
            page.update()

        # --- PLANTILLAS ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        T_ENGRARE = "function main() {\n  var b = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:20, slices:32});\n  return b;\n}"
        T_PEANA = "function main() {\n  var b = CSG.cube({center:[0,0,5], radius:[30,40,5]});\n  return b;\n}"

        txt_code = ft.TextField(
            label="Código JS-CSG", 
            multiline=True, 
            expand=True, 
            value=T_CARCASA, 
            text_size=12, 
            color="#00ff00"
        )

        def load_template(t):
            txt_code.value = t
            page.update()

        # === BOTÓN DE PLANTILLAS CORREGIDO ===
        btn_templates = ft.PopupMenuButton(
            items=[
                ft.PopupMenuItem(content=ft.Text("📦 Carcasa"), on_click=lambda _: load_template(T_CARCASA)),
                ft.PopupMenuItem(content=ft.Text("⚙️ Engranaje"), on_click=lambda _: load_template(T_ENGRARE)),
                ft.PopupMenuItem(content=ft.Text("📱 Peana"), on_click=lambda _: load_template(T_PEANA)),
            ],
            content=ft.Row([ft.Icon(ft.icons.BOOK), ft.Text("Plantillas")])   # ← AQUÍ ESTABA EL ERROR
        )

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True, spacing=5)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: copy_file_content(name)
                def make_del(name): return lambda _: delete_file(name)

                file_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(f[:15], size=12, expand=True),
                            ft.IconButton(ft.icons.PLAY_ARROW, on_click=make_load(f)),
                            ft.IconButton(ft.icons.COPY, on_click=make_copy(f), icon_color="blue"),
                            ft.IconButton(ft.icons.DELETE, on_click=make_del(f), icon_color="red"),
                        ]), bgcolor="#1a1a1a", padding=5, border_radius=8
                    )
                )
            page.update()

        def load_file_content(name):
            with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
            tabs.selected_index = 0
            page.update()

        def copy_file_content(name):
            with open(os.path.join(EXPORT_DIR, name), "r") as f: copy_to_clipboard(f.read())

        def delete_file(name):
            os.remove(os.path.join(EXPORT_DIR, name))
            update_files()

        # --- NAVEGACIÓN ---
        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            tabs.selected_index = 1
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = "✓ Guardado: " + fname
            update_files()

        editor_tab = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), height=50, width=float('inf'), bgcolor="green900", color="white"),
            ft.Row([btn_templates, ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), bgcolor="blue900")]),
            txt_code
        ], expand=True)

        prompts_tab = ft.Column([
            ft.Text("Prompts para IA:", weight="bold"),
            ft.TextField(label="Prompt CAD", value="Genera código CSG.js para una pieza técnica...", read_only=True),
        ], expand=True, scroll="auto")

        tabs = ft.Tabs(selected_index=0, tabs=[
            ft.Tab(text="EDITOR", content=editor_tab),
            ft.Tab(text="VISOR", content=ft.Container(content=ft.ElevatedButton("LANZAR VISOR", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/"), alignment=ft.alignment.center)),
            ft.Tab(text="ARCHIVOS", content=ft.Column([ft.Text("Mis Proyectos"), file_list], expand=True)),
            ft.Tab(text="IA", content=prompts_tab)
        ], expand=True, on_change=lambda _: update_files())

        page.add(ft.SafeArea(content=ft.Column([tabs, status], expand=True)))
        update_files()

    except Exception:
        page.clean()
        page.add(ft.SafeArea(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red", selectable=True)))
        page.update()

if __name__ == "__main__":
    # Detección de entorno para evitar bloqueos de red
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)