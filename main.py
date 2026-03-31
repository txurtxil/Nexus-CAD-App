import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, tempfile, traceback
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
# APLICACIÓN PRINCIPAL v4.1
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v4.1"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("Sistema Acorazado v4.1 Activo", color="green")

        def open_dialog(dialog):
            try: page.open(dialog)
            except: 
                if dialog not in page.overlay: page.overlay.append(dialog)
                dialog.open = True
                page.update()

        def close_dialog(dialog):
            try: page.close(dialog)
            except: dialog.open = False; page.update()

        def export_manual(texto):
            txt_copy = ft.TextField(value=texto, multiline=True, read_only=True, expand=True)
            dlg_copy = ft.AlertDialog(
                title=ft.Text("Exportar Código"),
                content=ft.Column([
                    ft.Text("Mantén pulsado dentro del cuadro azul para COPIAR TODO:", color="grey"),
                    ft.Container(content=txt_copy, height=300)
                ]),
                actions=[ft.ElevatedButton("CERRAR", on_click=lambda _: close_dialog(dlg_copy))]
            )
            open_dialog(dlg_copy)

        # --- PLANTILLAS JS-CSG RÁPIDAS ---
        T_CARCASA = "function main() {\n  var ext = CSG.cube({center:[0,0,10], radius:[40,25,10]});\n  var int = CSG.cube({center:[0,0,12], radius:[38,23,10]});\n  return ext.subtract(int);\n}"
        T_ENGRARE = "function main() {\n  var b = CSG.cylinder({start:[0,0,0], end:[0,0,5], radius:20, slices:32});\n  var h = CSG.cylinder({start:[0,0,-1], end:[0,0,6], radius:5, slices:16});\n  return b.subtract(h);\n}"
        T_PEANA = "function main() {\n  var base = CSG.cube({center: [0, 0, 5], radius: [60, 40, 5]});\n  var soporte = CSG.cube({center: [0, 10, 25], radius: [60, 5, 25]});\n  return base.union(soporte);\n}"

        txt_code = ft.TextField(label="Código JS-CSG", multiline=True, expand=True, value=T_CARCASA)

        # FIX: Función explícita de carga de plantillas
        def load_template(t):
            txt_code.value = t
            txt_code.update() # Forzar refresco UI específico
            status.value = "✓ Plantilla cargada."
            status.update()

        btn_c = ft.ElevatedButton("📦 Carcasa", on_click=lambda _: load_template(T_CARCASA))
        btn_e = ft.ElevatedButton("⚙️ Engranaje", on_click=lambda _: load_template(T_ENGRARE))
        btn_p = ft.ElevatedButton("📱 Peana", on_click=lambda _: load_template(T_PEANA))
        
        row_templates = ft.Row([btn_c, btn_e, btn_p], scroll="auto")

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
            try:
                os.remove(os.path.join(EXPORT_DIR, name))
                status.value = "✓ Eliminado."
                status.color = "green"
            except:
                status.value = "❌ Error al borrar."
                status.color = "red"
            update_files()

        def prompt_rename(old_name):
            txt_new = ft.TextField(label="Nuevo nombre (sin .jscad)")
            
            def do_rename(e):
                if txt_new.value:
                    try:
                        nuevo = txt_new.value + ".jscad"
                        os.rename(os.path.join(EXPORT_DIR, old_name), os.path.join(EXPORT_DIR, nuevo))
                        status.value = "✓ Renombrado"
                        status.color = "green"
                    except Exception as ex:
                        status.value = "❌ Error: " + str(ex)
                        status.color = "red"
                close_dialog(dlg)
                update_files()

            dlg = ft.AlertDialog(
                title=ft.Text("Renombrar Proyecto"),
                content=txt_new,
                actions=[ft.ElevatedButton("GUARDAR", on_click=do_rename, bgcolor="#0d47a1", color="white")]
            )
            open_dialog(dlg)

        # --- COMPILACIÓN Y GUARDADO ---
        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(1) 
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            try:
                with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
                status.value = "✓ Guardado: " + fname
                status.color = "green"
            except:
                status.value = "❌ Error de escritura."
                status.color = "red"
            update_files()

        # =========================================================
        # CARPETAS DE IA (SISTEMA ACCORDION ANTI-ALUCINACIONES)
        # =========================================================
        # REGLA MAESTRA PARA LA IA:
        AI_RULE = " REGLA CRÍTICA: Escribe en Javascript puro para la librería CSG.js. NUNCA uses comandos como cylinder() o translate() sueltos. Usa SIEMPRE primitivas absolutas: CSG.cube({center:[x,y,z], radius:[x,y,z]}) y CSG.cylinder({start:[x,y,z], end:[x,y,z], radius:R, slices:N}). Devuelve la pieza en 'function main() { ... return pieza; }'. "

        def create_folder(icon, title, prompts):
            controls = []
            for name, text in prompts:
                controls.append(ft.Text(name, color="amber", weight="bold"))
                # Inyectamos la regla maestra en cada prompt
                full_prompt = text + AI_RULE
                controls.append(ft.TextField(value=full_prompt, multiline=True, read_only=True, text_size=12))
                controls.append(ft.Container(height=15))

            content_col = ft.Column(controls, visible=False)

            def toggle(e):
                content_col.visible = not content_col.visible
                page.update()

            btn = ft.ElevatedButton(icon + " " + title, on_click=toggle, width=float('inf'), color="white", bgcolor="#424242")
            return ft.Column([btn, content_col])

        ia_electronica = [
            ("Caja Raspberry Pi", "Actúa como ingeniero CAD. Haz una caja de 90x60x30mm. Añade agujeros laterales para USB restando cubos."),
            ("Pasacables de Escritorio", "Genera un cilindro hueco paramétrico (radio ext 30mm, int 25mm, alto 20mm) con una ranura lateral para cables."),
        ]
        
        ia_hogar = [
            ("Posavasos de Panal", "Diseña un posavasos redondo de radio 45mm y grosor 5mm. Usa un bucle 'for' en JS para generar hexágonos (CSG.cylinder con slices:6) y únelos todos en una variable antes de restarlos a la base."),
            ("Soporte para Móvil Inclinado", "Crea un soporte de smartphone. Usa un cubo inclinado (matemáticamente con restas) o varios bloques unidos para formar un respaldo a 60 grados."),
        ]
        
        ia_deportes = [
            ("Silbato Paramétrico", "Diseña un silbato deportivo. Mezcla un cilindro hueco como cámara de aire y un rectángulo como boquilla."),
        ]
        
        ia_herramientas = [
            ("Soporte L con Refuerzo", "Crea un soporte en forma de L de 50x50x50mm. Añade un bloque oblicuo como refuerzo interno. Incluye 2 agujeros pasantes."),
            ("Organizador de Brocas", "Haz un bloque sólido de 100x30x20mm. Usa un bucle for para restar cilindros a lo largo del bloque (radios de 2 a 6mm)."),
        ]

        # =========================================================
        # VISTAS INDEPENDIENTES 
        # =========================================================
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), color="white", bgcolor="#004d40", height=50),
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
            ], scroll="auto"),
            ft.Text("Plantillas rápidas:", color="grey"),
            # FIX: Restaurada la fila de plantillas al editor visible
            row_templates,
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🚀 ABRIR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="white", bgcolor="#4a148c", height=60)
        view_visor = ft.Column([
            ft.Container(height=60), 
            ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("Haz clic para abrir el motor 3D interactivo WebGL.", text_align=ft.TextAlign.CENTER, color="grey")
        ], expand=True)
        
        view_archivos = ft.Column([ft.Text("Proyectos", weight="bold"), file_list], expand=True)
        
        view_ia = ft.Column([
            ft.Text("Catálogo de Prompts IA:", weight="bold", color="cyan"),
            ft.Text("Manten pulsado para copiar. Llevan una regla oculta anti-errores.", color="grey", size=11),
            create_folder("⚡", "Electrónica y PCB", ia_electronica),
            create_folder("🏠", "Hogar y Decoración", ia_hogar),
            create_folder("🔧", "Herramientas y Taller", ia_herramientas),
            create_folder("🚴", "Deportes y Outdoors", ia_deportes),
        ], expand=True, scroll="auto")

        # =========================================================
        # MOTOR DE NAVEGACIÓN Y DISTRIBUCIÓN 
        # =========================================================
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
            ft.ElevatedButton("🧠 PROMPTS IA", on_click=lambda _: set_tab(3), color="black", bgcolor="cyan"),
        ], scroll="auto")

        root_container = ft.Container(
            content=ft.Column([nav_bar, main_container, status], expand=True),
            padding=ft.padding.only(top=45, left=5, right=5, bottom=5),
            expand=True
        )

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