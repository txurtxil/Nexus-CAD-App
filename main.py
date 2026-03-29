import flet as ft
import os, base64, traceback, sqlite3, warnings
import http.server
import threading
import socket
import time

warnings.simplefilter("ignore", DeprecationWarning)

# ==========================================================
# MOTOR INTERNO: MICRO-SERVIDOR LOCAL
# ==========================================================
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        LOCAL_PORT = s.getsockname()[1]
except:
    LOCAL_PORT = 8556

LATEST_HTML = "<html><body style='background:#0a0a0a;color:#00ff00;font-family:monospace;padding:20px;'>NEXUS CAD: Esperando renderizado...</body></html>"

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global LATEST_HTML
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(LATEST_HTML.encode('utf-8'))
        
    def log_message(self, format, *args):
        pass 

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()
# ==========================================================

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
        txt_code = ft.TextField(
            label="Código OpenSCAD", multiline=True, expand=True, 
            value="module tree() {\n  // Tronco\n  cylinder(h=20, r=3);\n}\ntree();", 
            color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        status_text = ft.Text("Motor nativo listo", color="grey600")

        editor_container = ft.Container(
            content=ft.Column([
                txt_name, txt_code, 
                ft.ElevatedButton("▶ COMPILAR Y VER 3D", on_click=lambda e: run_render(), bgcolor="green900", color="white")
            ], expand=True),
            padding=10, expand=True, bgcolor="#0a0a0a"
        )

        # ==========================================================
        # UX DEFENSIVO: Botones con delegación nativa al Frontend
        # ==========================================================
        link_text = ft.Text("http://127.0.0.1", color="blue400", selectable=True, italic=True)
        
        # Este es el botón mágico. Usaremos su propiedad 'url' nativa más adelante.
        btn_open_browser = ft.ElevatedButton(
            "🚀 ABRIR EN NAVEGADOR NATIVO", 
            bgcolor="blue900", 
            color="white"
        )

        def copy_link():
            page.set_clipboard(link_text.value)
            status_text.value = "✓ Enlace copiado al portapapeles."
            status_text.color = "green400"
            page.update()

        viewer_container = ft.Container(
            content=ft.Column([
                ft.Text("🌐", size=80),
                ft.Text("Malla 3D Generada", color="white", size=20, weight="bold"),
                ft.Text("Servidor interno transmitiendo en:", text_align="center", color="grey500"),
                link_text,
                ft.Container(height=15),
                btn_open_browser,
                ft.Container(height=5),
                ft.ElevatedButton("📋 COPIAR ENLACE MANUALMENTE", on_click=lambda e: copy_link(), bgcolor="#333333", color="white")
            ], alignment="center", horizontal_alignment="center"), 
            expand=True, visible=False
        )

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        def run_render():
            global LATEST_HTML
            status_text.value = "Generando malla..."
            status_text.color = "orange400"
            page.update()

            try:
                with open(os.path.join("assets", "openscad_engine.html"), "r", encoding="utf-8") as f:
                    template = f.read()
                
                raw_b64 = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
                clean_b64 = raw_b64.replace('\n', '').replace('\r', '')
                
                LATEST_HTML = template.replace("__NEXUS_PAYLOAD__", clean_b64)
                
                # LA CLAVE: Actualizamos la URL nativa del botón
                current_url = f"http://127.0.0.1:{LOCAL_PORT}/?t={int(time.time())}"
                link_text.value = current_url
                btn_open_browser.url = current_url  # <-- Delegación a Flutter OS
                
                switch(1)
                status_text.value = f"✓ Listo. Pulsa el botón azul."
                status_text.color = "blue400"
                page.update()
                
            except Exception as e:
                status_text.value = f"Error Python: {e}"
                status_text.color = "red900"
                page.update()

        page.add(
            ft.Container(
                content=ft.Row([
                    ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)),
                    ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1)),
                ], alignment="center"),
                bgcolor="#111111", padding=5
            ),
            editor_container,
            viewer_container,
            status_text
        )

    except Exception:
        page.clean()
        page.bgcolor = "#990000" 
        page.add(
            ft.Text("FALLO CRÍTICO", size=20, weight="bold", color="white"),
            ft.Text(traceback.format_exc(), color="white", selectable=True, size=12)
        )
        page.update()

if __name__ == "__main__":
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    if is_termux: ft.app(target=main, assets_dir="assets", view="web_browser", port=8555)
    else: ft.app(target=main, assets_dir="assets")
