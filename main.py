import flet as ft
import os, base64, traceback, sqlite3, warnings, json
import urllib.request
import http.server
import threading
import socket
import time
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

# =========================================================
# GESTOR OFFLINE (Descarga librerías JS locales)
# =========================================================
assets_dir = os.path.join(os.getcwd(), "assets")
os.makedirs(assets_dir, exist_ok=True)
libs = {
    "three.min.js": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
    "csg.js": "https://raw.githubusercontent.com/evanw/csg.js/master/csg.js"
}
for name, url in libs.items():
    path = os.path.join(assets_dir, name)
    if not os.path.exists(path):
        try: urllib.request.urlretrieve(url, path)
        except: pass

# =========================================================
# MOTOR API LOCAL
# =========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        LOCAL_PORT = s.getsockname()[1]
except: LOCAL_PORT = 8556

LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global LATEST_CODE_B64
        parsed_url = urlparse(self.path)
        if parsed_url.path == '/api/get_code_b64.json':
            self.send_response(200); self.send_header("Content-type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode('utf-8'))
        elif self.path == '/three.min.js' or self.path == '/csg.js':
            try:
                with open(os.path.join(assets_dir, self.path.replace('/', '')), "r", encoding="utf-8") as f:
                    self.send_response(200); self.send_header("Content-type", "application/javascript"); self.end_headers(); self.wfile.write(f.read().encode('utf-8'))
            except: self.send_response(404); self.end_headers()
        else:
            try:
                with open(os.path.join(assets_dir, "openscad_engine.html"), "r", encoding="utf-8") as f:
                    self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(f.read().encode('utf-8'))
            except: self.send_response(500); self.end_headers()
    def log_message(self, format, *args): pass 

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD AI Core (v1.7.1)"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        export_dir = os.path.join(os.environ.get("HOME", os.getcwd()), "nexus_proyectos")
        os.makedirs(export_dir, exist_ok=True)

        # =========================================================
        # PLANTILLAS JS-CSG
        # =========================================================
        code_gear = """function main() {
    var base = CSG.cylinder({start: [0,-2,0], end: [0,2,0], radius: 15, slices: 32});
    var hole = CSG.cylinder({start: [0,-3,0], end: [0,3,0], radius: 5, slices: 16});
    var gear = base.subtract(hole);
    for(var i=0; i<8; i++) {
        var a = (i * 45) * Math.PI / 180;
        var tooth = CSG.cube({center: [Math.cos(a)*15, 0, Math.sin(a)*15], radius: [2, 2, 2]});
        gear = gear.union(tooth);
    }
    return gear;
}"""

        code_box = """function main() {
    var exterior = CSG.cube({center: [0,0,0], radius: [20, 10, 15]});
    var interior = CSG.cube({center: [0,2,0], radius: [18, 10, 13]}); 
    return exterior.subtract(interior);
}"""

        # =========================================================
        # UI EDITOR (LAYOUT CORREGIDO)
        # =========================================================
        txt_code = ft.TextField(
            label="Código IA (Javascript CSG)", multiline=True, expand=True, 
            value=code_gear, color="#00ff00", bgcolor="#050505", border_color="#333333", text_size=12
        )
        status_text = ft.Text("Sistema AI Online - v1.7.1", color="grey600", size=11)

        def save_project():
            filename = f"ai_model_{int(time.time())}.jscad"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, "w") as f: f.write(txt_code.value)
            status_text.value = f"✓ Guardado: {filename}"; update_explorer(); page.update()

        def clear_code(): txt_code.value = "function main() {\n  // Pega aquí el código de la IA\n  return CSG.sphere({radius: 10});\n}"; page.update()
        def load_template(code): txt_code.value = code; page.update()

        row_actions = ft.Row([
            ft.ElevatedButton("⚙️", on_click=lambda _: load_template(code_gear), bgcolor="#222222", color="white", tooltip="Engranaje"),
            ft.ElevatedButton("📦", on_click=lambda _: load_template(code_box), bgcolor="#222222", color="white", tooltip="Caja"),
            ft.ElevatedButton("💾 Guardar", on_click=lambda _: save_project(), bgcolor="#8e24aa", color="white"),
            ft.ElevatedButton("🗑️", on_click=lambda _: clear_code(), bgcolor="#e53935", color="white"),
        ], scroll=ft.ScrollMode.AUTO)
        
        btn_compile = ft.ElevatedButton("▶ COMPILAR MALLA BOOLEANA", on_click=lambda e: run_render(), bgcolor="green900", color="white", height=50, width=float('inf'))

        # NUEVO ORDEN DE INTERFAZ: Botón Compilar ARRIBA, luego acciones, luego la caja de texto infinita
        editor_container = ft.Container(
            content=ft.Column([
                btn_compile,
                row_actions,
                txt_code
            ], expand=True), 
            padding=10, expand=True, bgcolor="#0a0a0a", visible=True
        )
        
        # =========================================================
        # UI EXPLORADOR DE ARCHIVOS (FIX ICONO)
        # =========================================================
        lv_files = ft.ListView(expand=True, spacing=5)
        
        def load_file(filename):
            with open(os.path.join(export_dir, filename), "r") as f: txt_code.value = f.read()
            status_text.value = f"✓ Archivo cargado: {filename}"; switch(0)

        def update_explorer():
            lv_files.controls.clear()
            for f in reversed(os.listdir(export_dir)):
                # FIX: Sustituido el icono problemático por un emoji de texto plano "📄"
                lv_files.controls.append(
                    ft.Container(content=ft.Row([ft.Text("📄", size=20), ft.Text(f, color="white")]), 
                                 bgcolor="#1a1a1a", padding=10, border_radius=5, on_click=lambda e, fname=f: load_file(fname))
                )
            page.update()

        explorer_container = ft.Container(content=ft.Column([ft.Text("Proyectos Locales (Termux)", color="white", weight="bold"), lv_files], expand=True), padding=10, expand=True, bgcolor="#0a0a0a", visible=False)
        viewer_container = ft.Container(content=ft.Text("Visor inactivo."), alignment=ft.Alignment(0,0), expand=True, visible=False)

        def switch(idx):
            editor_container.visible = (idx == 0); viewer_container.visible = (idx == 1); explorer_container.visible = (idx == 2)
            if idx == 2: update_explorer()
            page.update()

        def run_render():
            global LATEST_CODE_B64
            status_text.value = "Compilando operaciones booleanas..."
            switch(1) 
            try:
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8').replace('\n', '').replace('\r', '')
                viewer_container.content = ft.ElevatedButton("🚀 ABRIR RENDERIZADOR HARDWARE", url=f"http://127.0.0.1:{LOCAL_PORT}/?t={time.time()}", bgcolor="blue900", color="white", expand=True)
                status_text.value = f"✓ Listo."
            except Exception as e: status_text.value = f"Error: {e}"
            page.update()

        main_content = ft.SafeArea(
            content=ft.Column([
                ft.Container(content=ft.Row([ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)), ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1)), ft.TextButton("📁 ARCHIVOS", on_click=lambda _: switch(2))], alignment="center"), bgcolor="#111111", padding=5),
                editor_container, viewer_container, explorer_container, status_text
            ], expand=True)
        )
        page.add(main_content); update_explorer()
        
    except Exception:
        page.clean(); page.add(ft.SafeArea(content=ft.Text(traceback.format_exc(), color="red", selectable=True))); page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets", view="web_browser", port=8555) if "com.termux" in os.environ.get("PREFIX", "") else ft.app(target=main, assets_dir="assets")
