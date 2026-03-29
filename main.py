import flet as ft
import os, base64, traceback, sqlite3, warnings
from datetime import datetime

warnings.simplefilter("ignore", DeprecationWarning)
try:
    import flet_webview as fwv
    HAS_WEBVIEW = True
except:
    HAS_WEBVIEW = False

def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        # 1. RUTAS SEGURAS EN ANDROID (Para DB y para el HTML renderizado)
        home_dir = os.environ.get("HOME", os.getcwd())
        if home_dir == "/": home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
        render_path = os.path.join(home_dir, "render.html") # AQUÍ GUARDAREMOS EL HTML
        
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS projects (name TEXT UNIQUE, code TEXT, created_at TEXT)")
        conn.commit()

        txt_name = ft.TextField(label="Nombre del Proyecto", bgcolor="#121212", border_color="#333333")
        txt_code = ft.TextField(
            label="Código OpenSCAD", multiline=True, expand=True, 
            value="module tree() {\n  // Tronco\n  cylinder(h=20, r=3);\n}\ntree();", 
            color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        
        status_text = ft.Text("Listo", color="grey600")

        editor_container = ft.Container(
            content=ft.Column([
                txt_name, txt_code, 
                ft.ElevatedButton("▶ COMPILAR", on_click=lambda e: run_render(), bgcolor="green900", color="white")
            ], expand=True),
            padding=10, expand=True, bgcolor="#0a0a0a"
        )

        # FIX CRÍTICO: Reemplazado ft.alignment.center por ft.Alignment(0, 0)
        viewer_container = ft.Container(
            content=ft.Text("Visor inactivo. Pulsa compilar.", color="grey500"), 
            alignment=ft.Alignment(0, 0), expand=True, visible=False
        )

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        # LA MAGIA: ESCRIBIR A DISCO PARA ENGAÑAR A ANDROID
        def run_render():
            status_text.value = "Horneando archivo local..."
            status_text.color = "orange400"
            switch(1) 

            try:
                # 1. Leemos la plantilla
                with open("assets/openscad_engine.html", "r", encoding="utf-8") as f:
                    template = f.read()
                
                # 2. Incrustamos tu código
                b64_code = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
                final_html = template.replace("__NEXUS_PAYLOAD__", b64_code)
                
                # 3. GUARDAMOS EL ARCHIVO FÍSICO EN EL MÓVIL
                with open(render_path, "w", encoding="utf-8") as f:
                    f.write(final_html)
                
                # 4. CARGAMOS EL ARCHIVO MEDIANTE file://
                if HAS_WEBVIEW and not page.web:
                    # Sobrescribimos el contenedor con un WebView totalmente nuevo apuntando al archivo
                    viewer_container.content = fwv.WebView(url=f"file://{render_path}", expand=True)
                    status_text.value = "✓ Renderizado (Motor Nativo Local)"
                    status_text.color = "blue400"
                else:
                    viewer_container.content = ft.Text("WebView no disponible", color="red")
            except Exception as e:
                status_text.value = f"Error al hornear: {e}"
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
            ft.Text("FALLO CRÍTICO EN SANDBOX ANDROID", size=20, weight="bold", color="white"),
            ft.Text(traceback.format_exc(), color="white", selectable=True, size=12)
        )
        page.update()

if __name__ == "__main__":
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    if is_termux:
        ft.app(target=main, assets_dir="assets", view="web_browser", port=8555)
    else:
        ft.app(target=main, assets_dir="assets")
