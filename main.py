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

threading.Thread(target=lambda: http.server.HTTPServer(("127.0.0.1", LOCAL_PORT), NexusHandler).serve_forever(), daemon=True).start()

# =========================================================
# APLICACIÓN PRINCIPAL v4.3
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v4.3"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("Sistema ToolKit v4.3 Activo", color="green")

        def open_dialog(dialog):
            try: page.open(dialog)
            except: 
                if dialog not in page.overlay: page.overlay.append(dialog)
                dialog.open = True
                page.update()

        def close_dialog(dialog):
            try: page.close(dialog)
            except: dialog.open = False; page.update()

        def export_manual(texto, titulo="Exportar Código"):
            txt_copy = ft.TextField(value=texto, multiline=True, read_only=True, expand=True)
            dlg_copy = ft.AlertDialog(
                title=ft.Text(titulo),
                content=ft.Column([
                    ft.Text("Mantén pulsado en el texto para COPIAR:", color="grey"),
                    ft.Container(content=txt_copy, height=300)
                ]),
                actions=[ft.ElevatedButton("CERRAR", on_click=lambda _: close_dialog(dlg_copy))]
            )
            open_dialog(dlg_copy)

        # FIX SUPREMO DEL PORTAPAPELES: Fallback automático a modo visual
        def copy_text(text_to_copy):
            try:
                page.set_clipboard(str(text_to_copy))
                status.value = "✓ Código copiado."
                status.color = "green"
                page.update()
            except:
                try:
                    subprocess.run(['termux-clipboard-set'], input=str(text_to_copy).encode('utf-8'))
                    status.value = "✓ Copiado (Termux)."
                    status.color = "green"
                    page.update()
                except:
                    # Si falla la seguridad de Android, abrimos el código para copia manual garantizada
                    export_manual(str(text_to_copy), "Copiar Prompt Manualmente")
                    status.value = "⚠️ Portapapeles bloqueado. Usa copia manual."
                    status.color = "amber"
                    page.update()

        # --- PLANTILLAS BÁSICAS ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        txt_code = ft.TextField(label="Código JS-CSG", multiline=True, expand=True, value=T_CARCASA)

        def load_template(t):
            txt_code.value = t
            txt_code.update() 
            set_tab(0) # Salta al editor
            status.value = "✓ Código cargado en el Editor."
            status.color = "green"
            status.update()

        def clear_editor():
            txt_code.value = "function main() {\n  // Inicia tu diseño aquí\n  \n  return CSG.cube({center:[0,0,0], radius:[10,10,10]});\n}"
            txt_code.update()
            status.value = "✓ Editor vaciado."
            status.color = "green"
            status.update()

        def inject_snippet(code_snippet):
            txt_code.value = txt_code.value + "\n" + code_snippet
            txt_code.update()

        row_snippets = ft.Row([
            ft.Text("Inyectar:", color="grey", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[5,5,5]});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5, slices:32});"), bgcolor="#263238", color="white"),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("  var final = pieza1.subtract(pieza2);"), bgcolor="#4e342e", color="white"),
        ], scroll="auto")

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True, spacing=10)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: export_manual(open(os.path.join(EXPORT_DIR, name), "r").read())
                def make_del(name): return lambda _: delete_file(name)
                def make_ren(name): return lambda _: prompt_rename(name)

                acciones = ft.Row([
                    ft.ElevatedButton("▶ Abrir", on_click=make_load(f), color="white", bgcolor="#1b5e20"),
                    ft.ElevatedButton("✏️ Editar", on_click=make_ren(f)),
                    ft.ElevatedButton("📤 Exportar", on_click=make_copy(f), color="white", bgcolor="#0d47a1"),
                    ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#b71c1c"),
                ], scroll="auto")
                row = ft.Column([ft.Text(f, weight="bold"), acciones])
                file_list.controls.append(ft.Container(content=row, padding=10, bgcolor="#1a1a1a", border_radius=8))
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                set_tab(0) 
                status.value = "✓ " + name + " cargado."
                status.color = "green"
            except:
                status.value = "❌ Error al leer."
                status.color = "red"
            page.update()

        def delete_file(name):
            os.remove(os.path.join(EXPORT_DIR, name)); update_files()

        def prompt_rename(old_name):
            txt_new = ft.TextField(label="Nuevo nombre (sin .jscad)")
            def do_rename(e):
                if txt_new.value:
                    os.rename(os.path.join(EXPORT_DIR, old_name), os.path.join(EXPORT_DIR, txt_new.value + ".jscad"))
                close_dialog(dlg)
                update_files()
            dlg = ft.AlertDialog(title=ft.Text("Renombrar Proyecto"), content=txt_new, actions=[ft.ElevatedButton("GUARDAR", on_click=do_rename, bgcolor="#0d47a1", color="white")])
            open_dialog(dlg)

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(1) 
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files()

        # =========================================================
        # MÓDULOS DE IA Y GALERÍA (ACCORDIONS)
        # =========================================================
        AI_RULE = " REGLA CRÍTICA: Escribe en Javascript puro para CSG.js. NUNCA uses cylinder() o translate() sueltos. Usa primitivas absolutas: CSG.cube({center:[x,y,z], radius:[x,y,z]}) y CSG.cylinder({start:[x,y,z], end:[x,y,z], radius:R, slices:N}). Devuelve la pieza final en 'function main() { ... return pieza; }'."

        def create_folder(icon, title, prompts):
            controls = []
            for name, text in prompts:
                controls.append(ft.Text(name, color="amber", weight="bold"))
                full_prompt = text + AI_RULE
                controls.append(ft.TextField(value=full_prompt, multiline=True, read_only=True, text_size=12))
                controls.append(ft.ElevatedButton("📋 Copiar", on_click=lambda e, txt=full_prompt: copy_text(txt)))
                controls.append(ft.Container(height=15))
            content_col = ft.Column(controls, visible=False)
            def toggle(e):
                content_col.visible = not content_col.visible
                page.update()
            btn = ft.ElevatedButton(icon + " " + title, on_click=toggle, width=float('inf'), color="white", bgcolor="#424242")
            return ft.Column([btn, content_col])

        def create_gallery(icon, title, examples):
            controls = []
            for name, code in examples:
                controls.append(ft.Text(name, color="green", weight="bold"))
                controls.append(ft.Text("Código CAD industrial prefabricado.", color="grey", size=10))
                controls.append(ft.ElevatedButton("▶ Cargar en Editor", on_click=lambda e, c=code: load_template(c), bgcolor="#1b5e20", color="white"))
                controls.append(ft.Container(height=15))
            content_col = ft.Column(controls, visible=False)
            def toggle(e):
                content_col.visible = not content_col.visible
                page.update()
            btn = ft.ElevatedButton(icon + " " + title, on_click=toggle, width=float('inf'), color="black", bgcolor="amber")
            return ft.Column([btn, content_col])

        ia_electronica = [("Caja Raspberry Pi", "Actúa como ingeniero CAD. Haz una caja de 90x60x30mm. Añade agujeros laterales para USB.")]
        ia_mecanismos = [("Rejilla Paramétrica", "Crea un cubo de 100x100x5mm. Usa dos bucles 'for' anidados para restar cilindros cada 10mm.")]

        # GALERÍA DE CÓDIGO MAESTRO
        CODE_ESTACION = """function main() {
  var base = CSG.cube({center: [0,0,12.5], radius: [80,60,12.5]});
  var agujeros = [];
  for(var x = -70; x <= -10; x += 22) {
    for(var y = -50; y <= 10; y += 22) {
      agujeros.push(CSG.cube({center: [x,y,14.5], radius: [9,9,12.5]}));
    }
  }
  agujeros.push(CSG.cylinder({start: [-85,40,16], end: [85,40,16], radius: 8, slices: 64}));
  agujeros.push(CSG.cube({center: [50,40,18], radius: [25,6,12]}));
  for(var i = 0; i < 3; i++) {
    agujeros.push(CSG.cylinder({start: [60,-40+(i*25),5], end: [60,-40+(i*25),30], radius: 9.5, slices: 64}));
  }
  var h_unidos = agujeros[0];
  for(var k = 1; k < agujeros.length; k++) h_unidos = h_unidos.union(agujeros[k]);
  return base.subtract(h_unidos).union(CSG.cylinder({start: [35,-35,25], end: [35,-35,60], radius: 4, slices: 32}));
}"""

        CODE_ENGRANAJE = """function main() {
  var dientes = 12; var radio = 20;
  var base = CSG.cylinder({start:[0,0,0], end:[0,0,5], radius:radio, slices:64});
  var diente_base = CSG.cube({center:[0,0,2.5], radius:[2,4,2.5]});
  for(var i=0; i<dientes; i++) {
    var angulo = (i * Math.PI * 2) / dientes;
    var x = Math.cos(angulo) * radio;
    var y = Math.sin(angulo) * radio;
    var d = CSG.cube({center:[x,y,2.5], radius:[2,4,2.5]});
    base = base.union(d);
  }
  var eje = CSG.cylinder({start:[0,0,-1], end:[0,0,6], radius:4, slices:32});
  return base.subtract(eje);
}"""

        galeria_ejemplos = [
            ("Estación Microsoldadura SMD", CODE_ESTACION),
            ("Engranaje Recto Matemático", CODE_ENGRANAJE)
        ]

        # =========================================================
        # VISTAS INDEPENDIENTES 
        # =========================================================
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), color="white", bgcolor="#004d40", height=50),
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ LIMPIAR", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            row_snippets,
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🚀 ABRIR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="white", bgcolor="#4a148c", height=60)
        view_visor = ft.Column([ft.Container(height=60), ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER)], expand=True)
        
        view_archivos = ft.Column([ft.Text("Proyectos", weight="bold"), file_list], expand=True)
        
        view_ia = ft.Column([
            ft.Text("Ingeniería Asistida:", weight="bold", color="cyan"),
            create_gallery("📚", "LIBRERÍA CAD (Ejemplos Listos)", galeria_ejemplos),
            ft.Container(height=10),
            ft.Text("Catálogo de Prompts IA:", weight="bold", color="grey"),
            create_folder("⚡", "Electrónica y PCB", ia_electronica),
            create_folder("⚙️", "Mecanismos Paramétricos", ia_mecanismos),
        ], expand=True, scroll="auto")

        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            if idx == 0: main_container.content = view_editor
            elif idx == 1: main_container.content = view_visor
            elif idx == 2: main_container.content = view_archivos
            elif idx == 3: main_container.content = view_ia
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 EDITOR", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("👁️ VISOR", on_click=lambda _: set_tab(1)),
            ft.ElevatedButton("📁 ARCHIVOS", on_click=lambda _: (update_files(), set_tab(2))),
            ft.ElevatedButton("🧠 IA & LIBRERÍA", on_click=lambda _: set_tab(3), color="black", bgcolor="cyan"),
        ], scroll="auto")

        root_container = ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True)
        page.add(root_container)
        update_files()

    except Exception:
        page.clean()
        page.add(ft.Container(ft.Text("CRASH FATAL:\n" + traceback.format_exc(), color="red"), padding=50))
        page.update()

if __name__ == "__main__":
    if "TERMUX_VERSION" in os.environ:
        ft.app(target=main, port=0, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)
