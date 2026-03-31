import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# CONFIGURACIÓN DE RUTAS BLINDADAS (Anti-Pantalla Negra)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Carpeta segura universal
try:
    EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)
except:
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

# =========================================================
# MOTOR SERVIDOR LOCAL HTTP
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
# APLICACIÓN PRINCIPAL NEXUS CAD (ESTRUCTURA PRIMITIVA)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v3.0 Final"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0

        status = ft.Text("Sistema Acorazado v3.0", size=10, color="grey")

        # --- SISTEMA DE PORTAPAPELES (Nivel Dios / Triple Capa) ---
        def copy_to_clipboard(text):
            success = False
            # Capa 1: Flet Moderno
            try:
                page.clipboard.set_text(text)
                success = True
            except: pass
            
            # Capa 2: Flet Clásico
            if not success:
                try:
                    page.set_clipboard(text)
                    success = True
                except: pass
                
            # Capa 3: Termux Nativo
            if not success:
                try:
                    subprocess.run(['termux-clipboard-set'], input=text.encode('utf-8'))
                    success = True
                except: pass
            
            if success:
                status.value = "✓ Código copiado."
            else:
                status.value = "❌ Error: API Portapapeles no soportada por el sistema."
            page.update()

        # --- PLANTILLAS JS-CSG MATEMÁTICAMENTE SEGURAS ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        T_ENGRARE = "function main() {\n  var b = CSG.cylinder({start:[0,0,0], end:[0,0,5], radius:20});\n  return b;\n}"
        T_PEANA = "function main() {\n  var base = CSG.cube({center: [0, 0, 5], radius: [60, 40, 5]});\n  var soporte = CSG.cube({center: [0, 10, 25], radius: [60, 5, 25]});\n  return base.union(soporte);\n}"
        T_BANDEJA = "function main() {\n  var solido = CSG.cube({center: [0,0,5], radius: [50, 50, 5]});\n  var hueco = CSG.cylinder({start: [0,0,2], end: [0,0,10], radius: 45, slices: 6});\n  return solido.subtract(hueco);\n}"

        # FIX: Eliminado todo atributo estético que pueda causar Crash
        txt_code = ft.TextField(
            label="Código JS-CSG", 
            multiline=True, 
            expand=True, 
            value=T_CARCASA
        )

        def on_template_change(e):
            val = e.control.value
            if val == "Carcasa": txt_code.value = T_CARCASA
            elif val == "Engranaje": txt_code.value = T_ENGRARE
            elif val == "Peana": txt_code.value = T_PEANA
            elif val == "Bandeja": txt_code.value = T_BANDEJA
            page.update()

        # FIX: Sustituido PopupMenu por un Dropdown estándar a prueba de balas
        dd_templates = ft.Dropdown(
            options=[
                ft.dropdown.Option("Carcasa"),
                ft.dropdown.Option("Engranaje"),
                ft.dropdown.Option("Peana"),
                ft.dropdown.Option("Bandeja"),
            ],
            on_change=on_template_change,
            width=180,
            label="Plantillas"
        )

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True, spacing=5)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: copy_file_content(name)
                def make_del(name): return lambda _: delete_file(name)

                # FIX: Iconos básicos sin parámetros extraños
                file_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(f[:15], expand=True),
                            ft.IconButton(ft.icons.PLAY_ARROW, on_click=make_load(f)),
                            ft.IconButton(ft.icons.COPY, on_click=make_copy(f)),
                            ft.IconButton(ft.icons.DELETE, on_click=make_del(f)),
                        ]), 
                        bgcolor="#1a1a1a", 
                        padding=5, 
                        border_radius=8
                    )
                )
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                tabs.selected_index = 0
                status.value = "✓ " + name + " cargado."
            except Exception as e:
                status.value = "❌ Error al leer."
            page.update()

        def copy_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: copy_to_clipboard(f.read())
            except Exception as e:
                status.value = "❌ Error al copiar."
                page.update()

        def delete_file(name):
            try:
                os.remove(os.path.join(EXPORT_DIR, name))
                status.value = "✓ Eliminado."
            except Exception as e:
                status.value = "❌ Error al borrar."
            update_files()

        # --- COMPILACIÓN Y GUARDADO ---
        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            tabs.selected_index = 1
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            try:
                with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
                status.value = "✓ Guardado: " + fname
            except Exception as e:
                status.value = "❌ Error de escritura."
            update_files()

        # --- INTERFAZ GLOBAL ---
        editor_tab = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), height=50, width=float('inf')),
            ft.Row([dd_templates, ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project())]),
            txt_code
        ], expand=True)

        prompts_tab = ft.Column([
            ft.Text("Prompts para enviar a tu IA:", weight="bold"),
            ft.TextField(label="Carcasa Técnica", value="Actúa como ingeniero CAD. Genera código Javascript para la librería CSG.js. Crea una carcasa de 90x60x30mm con vaciado interno de pared de 2mm. Usa center:[x,y,z] en los cubos. Devuelve la pieza final en la function main().", multiline=True),
            ft.TextField(label="Bandeja Organizadora", value="Genera el código JS (CSG.js) de una bandeja organizadora con patrón hexagonal. Usa cilindros con 'slices: 6' para crear los compartimentos hexagonales y réstalos de un cubo sólido principal.", multiline=True),
        ], expand=True, scroll="auto")

        tabs = ft.Tabs(selected_index=0, tabs=[
            ft.Tab(text="EDITOR", content=editor_tab),
            ft.Tab(text="VISOR", content=ft.Container(content=ft.ElevatedButton("ABRIR VISOR", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/"), alignment=ft.alignment.center)),
            ft.Tab(text="ARCHIVOS", content=ft.Column([ft.Text("Mis Proyectos"), file_list], expand=True)),
            ft.Tab(text="IA", content=prompts_tab)
        ], expand=True, on_change=lambda _: update_files())

        # FIX: Eliminado SafeArea para compatibilidad universal con versiones antiguas de Android/Flet
        page.add(ft.Container(content=ft.Column([tabs, status], expand=True), padding=10, expand=True))
        update_files()

    except Exception:
        page.clean()
        page.add(ft.Container(content=ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=10))
        page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)