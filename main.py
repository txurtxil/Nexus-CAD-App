import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# CONFIGURACIÓN DE RUTAS BLINDADAS (Anti-Pantalla Negra)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Lógica inteligente de almacenamiento para APK vs Termux
EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
try:
    os.makedirs(EXPORT_DIR, exist_ok=True)
except OSError:
    # Si falla (estamos dentro de una APK protegida de Android), usar carpeta interna segura.
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

# =========================================================
# MOTOR SERVIDOR LOCAL HTTP
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0)); LOCAL_PORT = s.getsockname()[1]
except: LOCAL_PORT = 8556

LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global LATEST_CODE_B64
        parsed = urlparse(self.path)
        if parsed.path == '/api/get_code_b64.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode())
        else:
            try:
                filename = self.path.strip("/")
                if not filename or filename == "": filename = "openscad_engine.html"
                fpath = os.path.join(ASSETS_DIR, filename)
                with open(fpath, "rb") as f:
                    self.send_response(200); self.end_headers(); self.wfile.write(f.read())
            except: self.send_response(404); self.end_headers()
    def log_message(self, *args): pass

# Arrancar el visor 3D de forma silenciosa para que no crashee la app si hay error
def start_server():
    try: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever()
    except: pass
threading.Thread(target=start_server, daemon=True).start()

# =========================================================
# APLICACIÓN PRINCIPAL NEXUS CAD
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v2.8.3"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0

        status = ft.Text(f"Memoria: ...{EXPORT_DIR[-25:]}", size=10, color="grey600")

        # --- SISTEMA DE PORTAPAPELES HÍBRIDO ---
        def copy_to_clipboard(text):
            try:
                if hasattr(page, 'set_clipboard'): page.set_clipboard(text)
                elif hasattr(page, 'clipboard'): page.clipboard.set_text(text)
                status.value = "✓ Código copiado."
            except:
                try:
                    subprocess.run(['termux-clipboard-set'], input=text.encode('utf-8'))
                    status.value = "✓ Código copiado (Nativo)."
                except:
                    status.value = "❌ Error al copiar."
            page.update()

        # --- PLANTILLAS INDUSTRIALES ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        T_ENGRARE = "function main() {\n  var b = CSG.cylinder({start:[0,0,0], end:[0,0,5], radius:20});\n  return b;\n} // Plantilla simplificada"
        T_PEANA = "function main() {\n  var base = CSG.cube({center: [0, 0, 5], radius: [60, 40, 5]});\n  var soporte = CSG.cube({center: [0, 10, 25], radius: [60, 5, 25]});\n  return base.union(soporte);\n}"
        T_BANDEJA = "function main() {\n  var solido = CSG.cube({center: [0,0,5], radius: [50, 50, 5]});\n  var hueco = CSG.cylinder({start: [0,0,2], end: [0,0,10], radius: 45, slices: 6});\n  return solido.subtract(hueco);\n}"

        txt_code = ft.TextField(label="Código JS-CSG", multiline=True, expand=True, value=T_CARCASA, text_size=12, color="#00ff00", font_family="monospace")

        def load_template(t):
            txt_code.value = t; page.update()

        btn_templates = ft.PopupMenuButton(
            items=[
                ft.PopupMenuItem(text="📦 Carcasa", on_click=lambda _: load_template(T_CARCASA)),
                ft.PopupMenuItem(text="⚙️ Engranaje", on_click=lambda _: load_template(T_ENGRARE)),
                ft.PopupMenuItem(text="📱 Peana", on_click=lambda _: load_template(T_PEANA)),
                ft.PopupMenuItem(text="📥 Bandeja", on_click=lambda _: load_template(T_BANDEJA)),
            ],
            content=ft.Row([ft.Icon(ft.icons.MENU_BOOK, size=18), ft.Text("Plantillas", weight="bold")])
        )

        # --- LÓGICA DE ARCHIVOS ---
        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_handler(fname): 
                    return lambda _: load_file_content(fname)
                def make_rename_handler(fname):
                    return lambda _: prompt_rename(fname)
                def make_copy_handler(fname):
                    return lambda _: copy_file_to_clipboard(fname)
                def make_delete_handler(fname):
                    return lambda _: delete_file(fname)

                file_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(f[:18], size=12, expand=True),
                            ft.IconButton(ft.icons.PLAY_ARROW, on_click=make_handler(f), icon_size=18),
                            ft.IconButton(ft.icons.EDIT, on_click=make_rename_handler(f), icon_color="amber", icon_size=18),
                            ft.IconButton(ft.icons.COPY, on_click=make_copy_handler(f), icon_color="blue", icon_size=18),
                            ft.IconButton(ft.icons.DELETE, on_click=make_delete_handler(f), icon_color="red", icon_size=18),
                        ]), bgcolor="#1a1a1a", padding=5, border_radius=8
                    )
                )
            page.update()

        def load_file_content(fname):
            with open(os.path.join(EXPORT_DIR, fname), "r") as f: txt_code.value = f.read()
            tabs.selected_index = 0; page.update()

        def copy_file_to_clipboard(fname):
            with open(os.path.join(EXPORT_DIR, fname), "r") as f: copy_to_clipboard(f.read())

        def delete_file(fname):
            os.remove(os.path.join(EXPORT_DIR, fname)); update_files()

        def prompt_rename(old_name):
            def do_rename(e):
                if txt_new.value:
                    os.rename(os.path.join(EXPORT_DIR, old_name), os.path.join(EXPORT_DIR, txt_new.value + ".jscad"))
                    if hasattr(page, 'close'): page.close(dlg)
                    else: dlg.open = False
                    update_files()
            txt_new = ft.TextField(label="Nuevo nombre")
            dlg = ft.AlertDialog(title=ft.Text("Renombrar"), content=txt_new, actions=[ft.TextButton("OK", on_click=do_rename)])
            if hasattr(page, 'open'): page.open(dlg)
            else: page.dialog = dlg; dlg.open = True; page.update()

        file_list = ft.ListView(expand=True, spacing=5)

        # --- PESTAÑAS ---
        editor_tab = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), height=50, width=float('inf'), bgcolor="green900", color="white"),
            ft.Row([
                ft.Container(content=btn_templates, bgcolor="#222", padding=5, border_radius=5),
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), bgcolor="blue900", color="white")
            ]),
            txt_code
        ], expand=True)

        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            status.value = f"✓ Guardado: {fname}"; update_files()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            tabs.selected_index = 1; page.update()

        prompts_tab = ft.Column([
            ft.Text("Prompts para IA:", weight="bold"),
            ft.TextField(label="Carcasa", value="Actúa como ingeniero CAD. Genera código JS (CSG.js) para una carcasa de 90x60x30mm con vaciado interno.", read_only=True),
            ft.TextField(label="Mecánico", value="Escribe código CSG.js para un engranaje de 12 dientes, radio 20mm y eje central de 5mm.", read_only=True),
        ], expand=True, scroll="auto")

        tabs = ft.Tabs(selected_index=0, tabs=[
            ft.Tab(text="EDITOR", content=editor_tab),
            ft.Tab(text="VISOR", content=ft.Container(content=ft.ElevatedButton("LANZAR VISOR", url=f"http://127.0.0.1:{LOCAL_PORT}/"), alignment=ft.alignment.center)),
            ft.Tab(text="ARCHIVOS", content=ft.Column([ft.Text("Mis Proyectos"), file_list], expand=True)),
            ft.Tab(text="IA", content=prompts_tab)
        ], expand=True, on_change=lambda _: update_files())

        page.add(ft.SafeArea(content=ft.Column([tabs, status], expand=True)))
        update_files()

    except Exception as e:
        # SISTEMA ANTI PANTALLA NEGRA
        page.clean()
        page.add(ft.SafeArea(ft.Text(f"CRASH FATAL:\n{traceback.format_exc()}", color="red", selectable=True)))
        page.update()

if __name__ == "__main__":
    # Si estamos en Termux usamos puerto dinamico y vista web.
    # Si estamos en APK Nativa (Github), no forzamos NADA para que Flet fluya libre.
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)