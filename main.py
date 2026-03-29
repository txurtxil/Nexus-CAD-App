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
        
        home_dir = os.environ.get("HOME", os.getcwd())
        if home_dir == "/": home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
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

        # Iniciar WebView con about:blank. ¡OJO! Sin on_message ni javascript_enabled.
        if HAS_WEBVIEW and not page.web:
            wv = fwv.WebView(url="about:blank", expand=True)
        else:
            wv = ft.Container(content=ft.Text("Visor 3D: Activo en APK"), expand=True, bgcolor="#111")

        editor_container = ft.Container(
            content=ft.Column([
                txt_name, txt_code, 
                ft.ElevatedButton("▶ COMPILAR", on_click=lambda e: run_render(), bgcolor="green900", color="white")
            ], expand=True),
            padding=10, expand=True, bgcolor="#0a0a0a"
        )

        viewer_container = ft.Container(content=wv, expand=True, visible=False)

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        def run_render():
            status_text.value = "Generando..."
            status_text.color = "orange400"
            switch(1) 

            # LEEMOS EL HTML
            with open("assets/openscad_engine.html", "r", encoding="utf-8") as f:
                template = f.read()
            
            # CIFRAMOS EL CÓDIGO A BASE64
            b64_code = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
            
            # INYECTAMOS EN EL HTML Y CODIFICAMOS LA PÁGINA COMPLETA
            final_html = template.replace("__NEXUS_PAYLOAD__", b64_code)
            final_b64 = base64.b64encode(final_html.encode('utf-8')).decode('utf-8')
            
            # RECARGAMOS LA URL DEL WEBVIEW
            if HAS_WEBVIEW and not page.web:
                wv.url = f"data:text/html;base64,{final_b64}"
                status_text.value = "✓ Objeto generado."
                status_text.color = "blue400"
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
