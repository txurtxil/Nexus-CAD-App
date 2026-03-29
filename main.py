import flet as ft
import os, base64, traceback, sqlite3, warnings

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
        
        # Iniciar WebView vacío
        wv = fwv.WebView(url="about:blank", expand=True)

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

        # LA TÉCNICA DEFINITIVA: TEMPLATE BAKING
        def run_render():
            # 1. Leemos el archivo original
            with open("assets/openscad_engine.html", "r", encoding="utf-8") as f:
                template = f.read()
            
            # 2. Codificamos tu código en Base64
            b64_code = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
            
            # 3. Incrustamos el código DENTRO del HTML
            final_html = template.replace("__NEXUS_PAYLOAD__", b64_code)
            
            # 4. Convertimos todo el HTML nuevo a Base64 para la URL
            final_b64 = base64.b64encode(final_html.encode('utf-8')).decode('utf-8')
            
            # 5. Forzamos al WebView a cargar la nueva página
            if HAS_WEBVIEW and not page.web:
                wv.url = f"data:text/html;base64,{final_b64}"
            
            switch(1)

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
