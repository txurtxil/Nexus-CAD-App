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

# Variable global que almacena ÚNICAMENTE los datos Base64 limpios
LATEST_CODE_B64 = ""

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global LATEST_CODE_B64
        parsed_url = urlparse(self.path)
        
        # RUTA API: Sirve los datos Base64 puros (JSON)
        if parsed_url.path == '/api/get_code_b64.json':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            response = json.dumps({"code_b64": LATEST_CODE_B64})
            self.wfile.write(response.encode('utf-8'))
            
        # RUTA WEB: Sirve el HTML Estático
        else:
            try:
                with open(os.path.join("assets", "openscad_engine.html"), "r", encoding="utf-8") as f:
                    template_html = f.read()
                
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(template_html.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error cargando motor: {e}".encode('utf-8'))
                
    def log_message(self, format, *args): pass 

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        home_dir = os.environ.get("HOME", os.getcwd())
        if home_dir == "/": home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS projects (name TEXT UNIQUE, code TEXT, created_at TEXT)")
        conn.commit()

        txt_name = ft.TextField(label="Proyecto", bgcolor="#121212", border_color="#333333")
        
        # El código OpenSCAD complejo 3D que mostraste en image_2.png
        txt_code = ft.TextField(
            label="Código OpenSCAD 3D", multiline=True, expand=True, 
            value="""module branch(length, thickness, angle, depth) {
  if (depth > 0) {
    cylinder(h=length, r1=thickness, r2=thickness*0.6, $fn=12);
    translate([0,0,length]) {
      rotate([angle,0,0]) branch(length*0.75, thickness*0.7, angle-0.3, depth-1);
      rotate([angle*0.6,0,120]) branch(length*0.7, thickness*0.7, angle+0.4, depth-1);
      rotate([-angle*0.5,0,-120]) branch(length*0.7, thickness*0.7, angle-0.2, depth-1);
    }
  }
}
module tree() {
  translate([0,0,-10]) branch(20, 3, 0.4, 8);
}
tree();
""", 
            color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        status_text = ft.Text("Listo", color="grey600")

        editor_container = ft.Container(
            content=ft.Column([txt_name, txt_code, ft.ElevatedButton("▶ COMPILAR Y VER", on_click=lambda e: run_render(), bgcolor="green900", color="white")], expand=True),
            padding=10, expand=True, bgcolor="#0a0a0a"
        )

        viewer_container = ft.Container(content=ft.Text("Visor inactivo."), alignment=ft.Alignment(0,0), expand=True, visible=False)

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        def run_render():
            global LATEST_CODE_B64
            status_text.value = "Generando malla por API segura..."
            status_text.color = "orange400"
            switch(1) 

            try:
                # 1. CODIFICAR Y GUARDAR EN MEMORIA limpia
                raw_b64 = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
                LATEST_CODE_B64 = raw_b64.replace('\n', '').replace('\r', '') # Base64 puro
                
                # 2. CARGAMOS EL HTML ESTÁTICO (SPA)
                final_url = f"http://127.0.0.1:{LOCAL_PORT}/?t={time.time()}"
                
                # Lanzamos en el navegador nativo delegando al Frontend (Flutter)
                viewer_container.content = ft.ElevatedButton(
                    "🚀 VER MODELO GENERADO (Navegador Nativo)", 
                    url=final_url,
                    bgcolor="blue900", 
                    color="white",
                    expand=True
                )
                
                status_text.value = f"✓ Listo. Renderizado por API HTTP"
                status_text.color = "blue400"
                page.update()
                
            except Exception as e:
                status_text.value = f"Error Python: {e}"
                status_text.color = "red900"
                page.update()

        page.add(
            ft.Container(content=ft.Row([ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)), ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1))], alignment="center"), bgcolor="#111111", padding=5),
            editor_container, viewer_container, status_text
        )

    except Exception:
        page.clean(); page.bgcolor = "#990000"; page.add(ft.Text("FALLO CRÍTICO", size=20, weight="bold", color="white"), ft.Text(traceback.format_exc(), color="white", selectable=True, size=12)); page.update()

if __name__ == "__main__":
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    if is_termux: ft.app(target=main, assets_dir="assets", view="web_browser", port=8555)
    else: ft.app(target=main, assets_dir="assets")
