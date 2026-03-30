import flet as ft
import os, base64, traceback, sqlite3, warnings, json
import http.server
import threading
import socket
import time
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

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
        parsed_url = urlparse(self.path)
        if parsed_url.path == '/api/get_code_b64.json':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode('utf-8'))
        else:
            try:
                with open(os.path.join("assets", "openscad_engine.html"), "r", encoding="utf-8") as f:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f.read().encode('utf-8'))
            except Exception as e:
                self.send_response(500); self.end_headers()
    def log_message(self, format, *args): pass 

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v1.3.1"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        home_dir = os.environ.get("HOME", os.getcwd())
        if home_dir == "/": home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS projects (name TEXT UNIQUE, code TEXT, created_at TEXT)")
        conn.commit()

        # =========================================================
        # BASES DE DATOS DE CÓDIGO (PLANTILLAS)
        # =========================================================
        code_tree = """module branch(length, thickness, angle, depth) {
    if (depth > 0) {
        cylinder(h = length, r1 = thickness, r2 = thickness * 0.6, $fn = 12);
        translate([0, 0, length]) {
            rotate([angle, 0, 0]) branch(length * 0.7, thickness * 0.7, angle * 1.1, depth - 1);
            rotate([-angle * 0.8, 0, 120]) branch(length * 0.7, thickness * 0.7, angle, depth - 1);
            rotate([angle * 0.5, 0, 240]) branch(length * 0.7, thickness * 0.7, angle * 1.2, depth - 1);
        }
    }
}
module tree() {
    branch(20, 3, 25, 7);
    for (i = [0:5:360]) {
        rotate([0, 0, i]) translate([0, 0, 15 + rand(i)*5]) sphere(r = 4 + rand(i)*2, $fn = 8);
    }
}
function rand(x) = rands(0, 1, 1, x)[0];
tree();"""

        code_bike = """// Parámetros Generales de Bicicleta
wheel_diameter = 622;
tire_width = 25;
frame_size = 560;
seat_tube_angle = 73;
head_tube_angle = 73;
fork_length = 360;
rake = 45;
chainstay_length = 410;
handlebar_width = 420;
crank_length = 172.5;
bb_height = 270;
frame_tube_diameter = 30;
stem_length = 100;

module bicycle() {
    // El motor interpretará los parámetros de arriba dinámicamente
    // Renderizado 3D por inyección WebGL
}
bicycle();"""

        # =========================================================
        # COMPONENTES DE INTERFAZ
        # =========================================================
        txt_code = ft.TextField(
            label="Código OpenSCAD", multiline=True, expand=True, 
            value=code_bike, color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        
        # FIX DE ZONA MUERTA: Usar botones de inyección directa en lugar de Dropdown roto
        def load_template(tipo):
            txt_code.value = code_bike if tipo == 'bike' else code_tree
            page.update()

        row_templates = ft.Row([
            ft.Text("Plantillas:", color="grey500"),
            ft.ElevatedButton("🚲 Bicicleta", on_click=lambda _: load_template('bike'), bgcolor="#222222", color="white"),
            ft.ElevatedButton("🌲 Árbol", on_click=lambda _: load_template('tree'), bgcolor="#222222", color="white"),
        ])
        
        status_text = ft.Text("Sistema Online - v1.3.1", color="grey600")

        editor_container = ft.Container(
            content=ft.Column([row_templates, txt_code, ft.ElevatedButton("▶ COMPILAR Y ROTAR 3D", on_click=lambda e: run_render(), bgcolor="green900", color="white")], expand=True), 
            padding=10, expand=True, bgcolor="#0a0a0a"
        )
        viewer_container = ft.Container(content=ft.Text("Visor inactivo."), alignment=ft.Alignment(0,0), expand=True, visible=False)

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        def run_render():
            global LATEST_CODE_B64
            status_text.value = "Generando..."
            switch(1) 
            try:
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8').replace('\n', '').replace('\r', '')
                viewer_container.content = ft.ElevatedButton(
                    "🚀 ABRIR SIMULADOR 3D INTERACTIVO", 
                    url=f"http://127.0.0.1:{LOCAL_PORT}/?t={time.time()}",
                    bgcolor="blue900", color="white", expand=True
                )
                status_text.value = f"✓ Listo."
            except Exception as e:
                status_text.value = f"Error: {e}"
            page.update()

        # UI Encapsulada para evitar el Notch de la cámara
        main_content = ft.SafeArea(
            content=ft.Column([
                ft.Container(content=ft.Row([ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)), ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1))], alignment="center"), bgcolor="#111111", padding=5),
                editor_container, 
                viewer_container, 
                status_text
            ], expand=True)
        )
        
        page.add(main_content)
        
    except Exception:
        page.clean(); page.add(ft.SafeArea(content=ft.Text(traceback.format_exc(), color="red", selectable=True))); page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets", view="web_browser", port=8555) if "com.termux" in os.environ.get("PREFIX", "") else ft.app(target=main, assets_dir="assets")
