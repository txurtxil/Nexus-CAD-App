import flet as ft
import os, base64, traceback, sqlite3, warnings, json
import urllib.request
import http.server
import threading
import socket
import time
from urllib.parse import urlparse

warnings.simplefilter("ignore", DeprecationWarning)

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

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0)); LOCAL_PORT = s.getsockname()[1]
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
        page.title = "NEXUS CAD v2.5 (Industrial)"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        export_dir = os.path.join(os.environ.get("HOME", os.getcwd()), "nexus_proyectos")
        os.makedirs(export_dir, exist_ok=True)

        status_text = ft.Text("Sistema Online - v2.5 Industrial", color="grey600", size=11)

        # =========================================================
        # PLANTILLAS INDUSTRIALES
        # =========================================================
        code_bracket = """function main() {
    // Soporte Industrial en L (L-Bracket)
    var base = CSG.cube({center: [0, 0, 5], radius: [30, 20, 5]});
    var pared = CSG.cube({center: [-25, 0, 25], radius: [5, 20, 25]});
    var soporte = base.union(pared);
    
    // Taladros para tornillos
    var agujero_base = CSG.cylinder({start: [15, 0, -5], end: [15, 0, 15], radius: 4});
    var agujero_pared1 = CSG.cylinder({start: [-35, 10, 35], end: [-15, 10, 35], radius: 3});
    var agujero_pared2 = CSG.cylinder({start: [-35, -10, 35], end: [-15, -10, 35], radius: 3});
    
    // Redondeo de esquina
    var corte_esquina = CSG.cylinder({start: [25, 20, 5], end: [25, -20, 5], radius: 10}).rotateX(90);
    
    return soporte.subtract(agujero_base).subtract(agujero_pared1).subtract(agujero_pared2);
}"""

        code_stand = """function main() {
    var base = CSG.cube({center: [0, 0, 20], radius: [60, 40, 20]});
    var ranura = CSG.cube({center: [0, 5, 35], radius: [70, 15, 30]});
    var rebaje = CSG.cube({center: [0, -45, 45], radius: [70, 40, 30]});
    var tubo = CSG.cylinder({start: [0, -50, 15], end: [0, 50, 15], radius: 20});
    return base.subtract(ranura).subtract(rebaje).subtract(tubo);
}"""

        # =========================================================
        # 1. UI EDITOR Y SNIPPETS
        # =========================================================
        txt_code = ft.TextField(
            label="Código Javascript CSG", multiline=True, expand=True, 
            value=code_bracket, color="#00ff00", bgcolor="#050505", border_color="#333333", text_size=12
        )

        def save_project():
            filename = f"nexus_{int(time.time())}.jscad"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, "w") as f: f.write(txt_code.value)
            status_text.value = f"✓ Guardado: {filename}"; update_explorer(); page.update()

        def clear_code(): txt_code.value = "function main() {\n  return CSG.sphere({radius: 10});\n}"; page.update()
        def load_template(code): txt_code.value = code; page.update()
        
        # Inyección de Snippets
        def inject_snippet(code):
            txt_code.value += f"\n\n/* SNIPPET RAPIDO */\n{code}"
            status_text.value = "✓ Snippet inyectado al final del código."
            page.update()

        row_templates = ft.Row([
            ft.Text("Plantillas:", color="grey500", size=11),
            ft.ElevatedButton("🔧 Soporte L", on_click=lambda _: load_template(code_bracket), bgcolor="#222222", color="white"),
            ft.ElevatedButton("📱 Peana", on_click=lambda _: load_template(code_stand), bgcolor="#222222", color="white"),
            ft.ElevatedButton("💾 Guardar", on_click=lambda _: save_project(), bgcolor="#8e24aa", color="white"),
            ft.ElevatedButton("🗑️ Limpiar", on_click=lambda _: clear_code(), bgcolor="#e53935", color="white"),
        ], scroll=ft.ScrollMode.AUTO)
        
        row_snippets = ft.Row([
            ft.Text("Inyectar:", color="grey500", size=11),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("var cubo = CSG.cube({center: [0,0,0], radius: [10,10,10]});"), bgcolor="#1e88e5", color="white", height=30),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("var cil = CSG.cylinder({start: [0,0,0], end: [0,0,20], radius: 5, slices: 32});"), bgcolor="#1e88e5", color="white", height=30),
            ft.ElevatedButton("+ Esfera", on_click=lambda _: inject_snippet("var esf = CSG.sphere({center: [0,0,0], radius: 10, slices: 32});"), bgcolor="#1e88e5", color="white", height=30),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("var res = objeto1.subtract(objeto2);"), bgcolor="#d81b60", color="white", height=30),
        ], scroll=ft.ScrollMode.AUTO)

        btn_compile = ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda e: run_render(), bgcolor="green900", color="white", height=50, width=float('inf'))

        editor_container = ft.Container(
            content=ft.Column([
                btn_compile,
                row_templates,
                row_snippets,
                txt_code
            ], expand=True), padding=10, expand=True, bgcolor="#0a0a0a", visible=True
        )

        # =========================================================
        # 2. EXPLORADOR DE ARCHIVOS AVANZADO (Con Tamaños)
        # =========================================================
        lv_files = ft.ListView(expand=True, spacing=5)
        
        def load_file(filename):
            with open(os.path.join(export_dir, filename), "r") as f: txt_code.value = f.read()
            status_text.value = f"✓ Cargado: {filename}"; switch(0)

        def delete_file(filename):
            os.remove(os.path.join(export_dir, filename))
            status_text.value = f"🗑️ Eliminado: {filename}"; update_explorer()

        def export_file(filename):
            with open(os.path.join(export_dir, filename), "r") as f: page.set_clipboard(f.read())
            status_text.value = f"📤 Código copiado al portapapeles."; page.update()

        def rename_file(old_name, new_name, dlg):
            if new_name:
                os.rename(os.path.join(export_dir, old_name), os.path.join(export_dir, new_name + ".jscad"))
                status_text.value = f"✏️ Renombrado a {new_name}.jscad"
            dlg.open = False; update_explorer()

        def prompt_rename(filename):
            txt_new_name = ft.TextField(label="Nuevo nombre (sin extensión)")
            dlg = ft.AlertDialog(title=ft.Text("Renombrar"), content=txt_new_name, actions=[ft.TextButton("Guardar", on_click=lambda e: rename_file(filename, txt_new_name.value, dlg))])
            page.dialog = dlg; dlg.open = True; page.update()

        def update_explorer():
            lv_files.controls.clear()
            for f in reversed(os.listdir(export_dir)):
                filepath = os.path.join(export_dir, f)
                size_kb = os.path.getsize(filepath) / 1024
                row = ft.Row([
                    ft.Column([ft.Text("📄 " + f[:20], color="white", size=13), ft.Text(f"{size_kb:.1f} KB", color="grey500", size=10)], expand=True),
                    ft.TextButton("📂", on_click=lambda e, fname=f: load_file(fname), tooltip="Cargar"),
                    ft.TextButton("✏️", on_click=lambda e, fname=f: prompt_rename(fname), tooltip="Renombrar"),
                    ft.TextButton("📤", on_click=lambda e, fname=f: export_file(fname), tooltip="Copiar Código"),
                    ft.TextButton("🗑️", on_click=lambda e, fname=f: delete_file(fname), tooltip="Eliminar")
                ], alignment="spaceBetween")
                lv_files.controls.append(ft.Container(content=row, bgcolor="#1a1a1a", padding=5, border_radius=5))
            page.update()

        explorer_container = ft.Container(content=ft.Column([ft.Text("Gestor de Proyectos", color="white", weight="bold"), lv_files], expand=True), padding=10, expand=True, bgcolor="#0a0a0a", visible=False)

        # =========================================================
        # 3. NAVEGACIÓN
        # =========================================================
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
                ft.Row([ft.TextButton("💻 Editor", on_click=lambda _: switch(0)), ft.TextButton("👁️ Visor", on_click=lambda _: switch(1)), ft.TextButton("📁 Archivos", on_click=lambda _: switch(2))], alignment="center", scroll=ft.ScrollMode.AUTO),
                editor_container, viewer_container, explorer_container, status_text
            ], expand=True)
        )
        page.add(main_content); update_explorer()
        
    except Exception:
        page.clean(); page.add(ft.SafeArea(content=ft.Text(traceback.format_exc(), color="red", selectable=True))); page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets", view="web_browser", port=8555) if "com.termux" in os.environ.get("PREFIX", "") else ft.app(target=main, assets_dir="assets")
