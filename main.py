import flet as ft
import os, base64, traceback, sqlite3, warnings, threading
from datetime import datetime

warnings.simplefilter("ignore", DeprecationWarning)
try:
    import flet_webview as fwv
    HAS_WEBVIEW = True
except:
    HAS_WEBVIEW = False

def main(page: ft.Page):
    try:
        # Configuración blindada minúsculas/colores hex (image_2.png approved)
        page.title = "NEXUS CAD"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 0
        
        # RUTA DB ULTRA-BLINDADA PARA ANDROID Sandbox
        home_dir = os.environ.get("HOME")
        if not home_dir or home_dir == "/":
            home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS projects (name TEXT UNIQUE, code TEXT, created_at TEXT)")
        conn.commit()

        txt_name = ft.TextField(label="Nombre del Proyecto", bgcolor="#121212", border_color="#333333")
        txt_code = ft.TextField(
            label="Código OpenSCAD", multiline=True, expand=True, 
            # easter egg dedicado a tu código de image_1.png
            value="module tree() {\n  // Tronco\n  cylinder(h=20, r=3);\n}\ntree();", 
            color="#00ff00", bgcolor="#050505", border_color="#333333"
        )
        
        status_text = ft.Text("Listo", color="grey600")

        # Iniciar WebView vacío nativo. Ocupará el resto del espacio.
        wv = fwv.WebView(url="about:blank", expand=True)

        editor_container = ft.Container(
            content=ft.Column([
                txt_name, txt_code, 
                # Botón de renderizado con Emoji ▶
                ft.ElevatedButton("▶ COMPILAR", on_click=lambda e: run_render(), bgcolor="green900", color="white")
            ], expand=True),
            padding=10, expand=True, bgcolor="#0a0a0a"
        )

        viewer_container = ft.Container(content=wv, expand=True, visible=False)

        def switch(idx):
            editor_container.visible = (idx == 0)
            viewer_container.visible = (idx == 1)
            page.update()

        # LA TÉCNICA DEFINITIVA DE ANALISTA SENIOR: TEMPLATE BAKING
        # Python "hornea" el código DENTRO del HTML antes de cargarlo
        def run_render():
            status_text.value = "Abriendo visor offline..."
            status_text.color = "orange400"
            switch(1) # Cambiar instantáneamente a la pestaña del Visor

            # 1. Leemos el archivo original
            with open("assets/openscad_engine.html", "r", encoding="utf-8") as f:
                template = f.read()
            
            # 2. Codificamos tu código en Base64 para inyección segura
            b64_code = base64.b64encode(txt_code.value.encode('utf-8')).decode('utf-8')
            
            # 3. Incrustamos el código DENTRO del HTML, reemplazando el placeholder
            final_html = template.replace("__NEXUS_PAYLOAD__", b64_code)
            
            # 4. Convertimos todo el HTML nuevo a Base64 para la URL
            final_b64 = base64.b64encode(final_html.encode('utf-8')).decode('utf-8')
            
            # 5. Forzamos al WebView nativo a cargar la nueva página
            if HAS_WEBVIEW and not page.web:
                wv.url = f"data:text/html;base64,{final_b64}"
                status_text.value = f"✓ Objeto generado nativamente."
                status_text.color = "blue400"
            else:
                # Placeholder para cuando pruebes localmente en localhost:8555
                wv.url = f"data:text/html,<html><body style='background:#111;color:#fff;'>Visor 3D: Activo solo en APK (Modo Web local)</body></html>"

        page.add(
            # Navegación personalizada con Emojis (approved)
            ft.Container(
                content=ft.Row([
                    ft.TextButton("💻 EDITOR", on_click=lambda _: switch(0)),
                    ft.TextButton("👁️ VISOR", on_click=lambda _: switch(1)),
                ], alignment="center"),
                bgcolor="#111111", padding=5
            ),
            editor_container,
            viewer_container,
            status_text # El estatus en el footer de image_0.png
        )

    # BLINDAJE: Diagnóstico rojo ante fallos de Sandbox
    except Exception:
        page.clean()
        page.bgcolor = "#990000" 
        page.scroll = "auto"
        page.add(
            ft.Text("FALLO CRÍTICO EN SANDBOX", size=24, weight="bold", color="white"),
            ft.Text(traceback.format_exc(), color="white", selectable=True, size=11)
        )
        page.update()

if __name__ == "__main__":
    # FIX CRÍTICO: Eliminado el 'os.makedirs("assets")' que crasheaba el APK
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    if is_termux:
        ft.app(target=main, assets_dir="assets", view="web_browser", port=8555)
    else:
        ft.app(target=main, assets_dir="assets")
