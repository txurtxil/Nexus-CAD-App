import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback

# Desactivar advertencias de deprecación para mantener limpia la consola
warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# RUTAS Y DIRECTORIOS (ESTRUCTURA v4.3)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Intentar usar almacenamiento en memoria persistente si es posible
try:
    EXPORT_DIR = os.path.join(BASE_DIR, "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)
except:
    EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nexus_proyectos")
    os.makedirs(EXPORT_DIR, exist_ok=True)

# =========================================================
# MOTOR SERVIDOR LOCAL (ESTÁNDAR v4.3)
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
        if self.path == '/api/get_code_b64.json':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode())
        else:
            try:
                filename = self.path.strip("/")
                if not filename: filename = "openscad_engine.html"
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
# APLICACIÓN PRINCIPAL v4.3
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v4.3"
        page.theme_mode = "dark"
        page.padding = 0

        status = ft.Text("NEXUS v4.3 | Sistema Estable", color="green")

        # --- UTILIDADES ---
        def open_dialog(dialog):
            try: page.open(dialog)
            except: 
                if dialog not in page.overlay: page.overlay.append(dialog)
                dialog.open = True
                page.update()

        def close_dialog(dialog):
            try: page.close(dialog)
            except: dialog.open = False; page.update()

        def copy_to_clipboard(text_to_copy):
            try:
                page.set_clipboard(str(text_to_copy))
                status.value = "✓ Copiado al portapapeles."
                page.update()
            except:
                status.value = "⚠️ Error al copiar."
                page.update()

        # --- EDITOR CAD ---
        DEFAULT_CODE = "function main() {\n  return CSG.cube({center:[0,0,0], radius:[10,10,10]});\n}"
        txt_code = ft.TextField(
            label="Editor de Código JS-CSG",
            multiline=True,
            expand=True,
            value=DEFAULT_CODE,
            text_size=12,
            font_family="monospace"
        )

        def load_template(t):
            txt_code.value = t
            txt_code.update()
            set_tab(0)
            status.value = "✓ Plantilla cargada."
            page.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(1)
            page.update()

        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f:
                f.write(txt_code.value)
            update_files()
            status.value = f"✓ Guardado: {fname}"
            page.update()

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True, spacing=10)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_load(name): return lambda _: load_file_content(name)
                def make_del(name): return lambda _: (os.remove(os.path.join(EXPORT_DIR, name)), update_files())
                
                row = ft.Container(
                    content=ft.Column([
                        ft.Text(f, weight="bold", size=14),
                        ft.Row([
                            ft.ElevatedButton("▶ Cargar", on_click=make_load(f), bgcolor="green900"),
                            ft.ElevatedButton("🗑️", on_click=make_del(f), bgcolor="red900"),
                        ])
                    ]),
                    padding=10,
                    bgcolor="#1a1a1a",
                    border_radius=8
                )
                file_list.controls.append(row)
            page.update()

        def load_file_content(name):
            with open(os.path.join(EXPORT_DIR, name), "r") as f:
                txt_code.value = f.read()
            set_tab(0)
            page.update()

        # --- CATÁLOGO DE PROMPTS Y RECURSOS ---
        CODE_MAESTRO = """function main() {
  var base = CSG.cube({center: [0,0,12.5], radius: [80,60,12.5]});
  var agujeros = [];
  for(var x = -70; x <= -10; x += 22) {
    for(var y = -50; y <= 10; y += 22) {
      agujeros.push(CSG.cube({center: [x,y,14.5], radius: [9,9,12.5]}));
    }
  }
  var h_unidos = agujeros[0];
  for(var k = 1; k < agujeros.length; k++) h_unidos = h_unidos.union(agujeros[k]);
  return base.subtract(h_unidos);
}"""

        view_prompts = ft.Column([
            ft.Text("Catálogo de Recursos v4.3:", weight="bold", size=18, color="cyan"),
            ft.Divider(),
            ft.Text("Modelos Predefinidos:", weight="bold"),
            ft.ElevatedButton("💎 Estación Microsoldadura", on_click=lambda _: load_template(CODE_MAESTRO), width=400),
            ft.ElevatedButton("📦 Cubo Paramétrico", on_click=lambda _: load_template(DEFAULT_CODE), width=400),
            ft.Divider(),
            ft.Text("Prompts para mañana (Gemini Pro):", weight="bold"),
            ft.ListTile(title=ft.Text("Caja Raspberry Pi"), subtitle=ft.Text("Diseño paramétrico con huecos USB")),
            ft.ListTile(title=ft.Text("Engranaje Recto"), subtitle=ft.Text("Cálculo de dientes automático")),
        ], scroll="auto", expand=True)

        # --- ESTRUCTURA DE NAVEGACIÓN ---
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR Y VER EN 3D", on_click=lambda _: run_render(), bgcolor="teal900", height=60),
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project()),
                ft.ElevatedButton("🗑️ RESET", on_click=lambda _: (setattr(txt_code, "value", DEFAULT_CODE), txt_code.update())),
            ], alignment=ft.MainAxisAlignment.CENTER),
            txt_code
        ], expand=True)

        view_visor = ft.Column([
            ft.Container(height=100),
            ft.Row([
                ft.ElevatedButton(
                    "🚀 ABRIR VISOR 3D EXTERNO", 
                    url=f"http://127.0.0.1:{LOCAL_PORT}/", 
                    height=80, 
                    width=300,
                    bgcolor="blue900"
                )
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("El visor utiliza el motor WebGL local de la app.", text_align="center", color="grey")
        ], expand=True)

        view_archivos = ft.Column([
            ft.Text("Mis Proyectos Nexus:", weight="bold", size=18),
            file_list
        ], expand=True)

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_visor, view_archivos, view_prompts]
            main_container.content = tabs[idx]
            if idx == 2: update_files()
            page.update()

        nav_bar = ft.Row([
            ft.IconButton(ft.icons.CODE, on_click=lambda _: set_tab(0), tooltip="Editor"),
            ft.IconButton(ft.icons.VIEW_IN_AR_SHARP, on_click=lambda _: set_tab(1), tooltip="Visor 3D"),
            ft.IconButton(ft.icons.FOLDER_OPEN, on_click=lambda _: set_tab(2), tooltip="Archivos"),
            ft.IconButton(ft.icons.LIGHTBULB_OUTLINE, on_click=lambda _: set_tab(3), tooltip="Prompts"),
        ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, bgcolor="#111111")

        # --- COMPOSICIÓN FINAL ---
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Container(height=40), # Espacio para notch
                    nav_bar,
                    main_container,
                    status
                ], expand=True),
                padding=10,
                expand=True
            )
        )
        update_files()

    except Exception:
        page.add(ft.Text(traceback.format_exc(), color="red"))
        page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)