import flet as ft
import os, base64, traceback, sqlite3, warnings, time, threading

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
        
        db_path = "nexus_cad.db"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS p (name TEXT UNIQUE, code TEXT)")

        txt_name = ft.TextField(label="Proyecto", bgcolor="#121212", border_color="#333333")
        txt_code = ft.TextField(
            label="Código OpenSCAD", multiline=True, expand=True, 
            value="module tree() {\n  // Tronco\n  cylinder(h=20, r=3);\n}\ntree();", 
            color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        
        # Cargar motor HTML local
        html_b64 = ""
        if os.path.exists("assets/openscad_engine.html"):
            with open("assets/openscad_engine.html", "r") as f:
                html_b64 = base64.b64encode(f.read().encode()).decode()

        # WebView nativo
        wv = fwv.WebView(url=f"data:text/html;base64,{html_b64}", expand=True)

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

        # LA SOLUCIÓN DEFINITIVA: Base64 + Hilo de fondo
        def inject_code():
            time.sleep(0.5) # Espera técnica a que Android despliegue el WebView
            raw_code = txt_code.value
            b64_code = base64.b64encode(raw_code.encode('utf-8')).decode('utf-8')
            try:
                wv.run_javascript(f"window.processOpenScad('{b64_code}')")
            except Exception as ex:
                print("Error de puente JS:", ex)

        def run_render():
            switch(1)
            # Iniciar la inyección sin congelar la UI de Flet
            threading.Thread(target=inject_code, daemon=True).start()

        page.add(
            ft.Container(
                content=ft.Row([
                    ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)),
                    ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1)),
                ], alignment="center"),
                bgcolor="#111111", padding=5
            ),
            editor_container,
            viewer_container
        )

    except Exception:
        page.add(ft.Text(f"ERROR FATAL:\n{traceback.format_exc()}", color="red"))
        page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
