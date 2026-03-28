import flet as ft
import sqlite3
import os
import traceback
import base64
import warnings
import json # Necesario para parsear el mensaje de JavaScript
from datetime import datetime

warnings.simplefilter("ignore", DeprecationWarning)

try:
    import flet_webview as fwv
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

WASM_ENGINE_FILE = "openscad_engine.html"

# ==========================================
# GESTOR DE ESTADO GLOBAL (SENIOR TECH)
# ==========================================
# Variable de control de flujo. True cuando el WebView envía señal de "Listo"
IS_VIEWER_READY = False

def main(page: ft.Page):
    try:
        # Configuración blindada
        page.title = "NEXUS 3D Studio"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 10

        # RUTA DB ULTRA-BLINDADA PARA ANDROID Sandbox
        home_dir = os.environ.get("HOME")
        if not home_dir or home_dir == "/":
            home_dir = os.environ.get("TMPDIR", os.getcwd())
            
        db_path = os.path.join(home_dir, "nexus_cad.db")
        
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS projects
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                           name TEXT UNIQUE, 
                           code TEXT,
                           created_at TEXT)''')
        conn.commit()

        txt_name = ft.TextField(label="Nombre del Proyecto", bgcolor="#151515", border_color="#333333")
        txt_code = ft.TextField(
            label="Editor OpenSCAD",
            multiline=True, min_lines=10, expand=True,
            bgcolor="#000000", color="#00ff00",
            text_style=ft.TextStyle(font_family="monospace", size=12),
            value="cube([20,20,10], center=true);"
        )
        
        status_text = ft.Text("Sistema listo Offline.", color="grey600", size=12)
        projects_list = ft.ListView(expand=True, spacing=10, padding=10)

        # -------------------------------------------------------------------
        # EL MOTOR WASM (OPCIÓN B) CON HANDSHAKE
        # -------------------------------------------------------------------
        wasm_html_content = ""
        assets_path = os.path.join(os.getcwd(), "assets", WASM_ENGINE_FILE)
        
        if os.path.exists(assets_path):
            with open(assets_path, "r", encoding="utf-8") as f:
                wasm_html_content = f.read()
        else:
            wasm_html_content = "<html><body style='background:#111;color:#fff;'>Visor 3D no encontrado en assets.</body></html>"

        b64_html = base64.b64encode(wasm_html_content.encode('utf-8')).decode('utf-8')
        
        # === FUNCIÓN CLAVE: RECEPCIÓN DE MENSAJES JS -> PYTHON ===
        def on_webview_message(e):
            global IS_VIEWER_READY
            try:
                # Parseamos el mensaje JSON enviado por JavaScript (window.fletwebview.postMessage)
                data = json.loads(e.data)
                
                if data.get("type") == "ready":
                    # === FASE 1 DEL HANDSHAKE COMPLETADA ===
                    IS_VIEWER_READY = True
                    # Mostramos que ya estamos sincronizados
                    status_text.value = "✓ Visor 3D Sincronizado. Renderizando pieza..."
                    status_text.color = "blue400"
                    
                    # === FASE 2 DEL HANDSHAKE: INYECTAR EL CÓDIGO ===
                    # El visor está listo, ahora sí enviamos el código
                    render_in_wasm_confirmed()
            except Exception as ex:
                status_text.value = f"Error Handshake: {ex}"
                status_text.color = "red900"
            page.update()

        if HAS_WEBVIEW and not page.web:
            wasm_webview = fwv.WebView(
                url=f"data:text/html;base64,{b64_html}",
                expand=True, javascript_enabled=True, 
                # === ACTIVAR EL ESCUCHADOR DE MENSAJES ===
                on_message=on_webview_message # Llama a la función de handshake
            )
        else:
            wasm_webview = ft.Container(
                content=ft.Text("Visor 3D: Activo solo en APK (Modo Web local)", color="yellow"),
                alignment=ft.Alignment(0, 0), expand=True, bgcolor="#111111", border_radius=8
            )

        # FUNCIONES DB
        def load_history():
            projects_list.controls.clear()
            cursor.execute("SELECT name, created_at FROM projects ORDER BY created_at DESC")
            rows = cursor.fetchall()
            for row in rows:
                projects_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text("📦", size=16),
                            ft.Text(row[0], color="white", weight="bold", expand=True),
                            ft.TextButton("✏️ Cargar", on_click=lambda e, n=row[0]: load_project(n)),
                            ft.TextButton("🗑️ Borrar", on_click=lambda e, n=row[0]: delete_project(n)),
                        ]),
                        bgcolor="#151515", padding=10, border_radius=8
                    )
                )
            page.update()

        def load_project(name):
            cursor.execute("SELECT code FROM projects WHERE name=?", (name,))
            row = cursor.fetchone()
            if row:
                txt_name.value = name
                txt_code.value = row[0]
                switch_tab(0)

        def delete_project(name):
            cursor.execute("DELETE FROM projects WHERE name=?", (name,))
            conn.commit()
            load_history()

        def save_to_db(e):
            if not txt_name.value: return
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            cursor.execute("INSERT OR REPLACE INTO projects (name, code, created_at) VALUES (?, ?, ?)", 
                         (txt_name.value, txt_code.value, now))
            conn.commit()
            status_text.value = f"✓ Guardado: {txt_name.value}"
            status_text.color = "green400"
            load_history()
            page.update()

        def clear_editor(e):
            txt_name.value = ""
            txt_code.value = ""
            page.update()

        # FUNCIÓN DE COMPILACIÓN (INICIO DE FLUJO)
        def render_in_wasm():
            global IS_VIEWER_READY
            # Iniciamos el flujo: avisamos y cambiamos de pestaña
            status_text.value = "Abriendo visor offline..."
            status_text.color = "orange400"
            switch_tab(1) # Pestaña del visor
            
            # BLINDAJE: Si el visor ya estaba listo (ya hicimos handshake), renderizamos directo.
            if IS_VIEWER_READY:
                render_in_wasm_confirmed()
            # Si no está listo (primera vez), on_webview_message se encargará.

        # FUNCIÓN DE INYECCIÓN DE DATOS (FASE FINAL DEL HANDSHAKE)
        def render_in_wasm_confirmed():
            # Sanitizar código para enviarlo como JS string
            code = txt_code.value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            
            try:
                if HAS_WEBVIEW and not page.web:
                    # NUNCA inyectamos si el handshake no está completado
                    if IS_VIEWER_READY:
                        # Inyectar JavaScript en el WebView
                        wasm_webview.run_javascript(f"processOpenScad('{code}');")
                        status_text.value = f"✓ Objeto generado en WASM."
                        status_text.color = "green400"
                    else:
                        status_text.value = "Error: Intentando renderizar antes de sincronización."
                        status_text.color = "red900"
            except Exception as ex:
                status_text.value = f"WASM Error: {ex}"
                status_text.color = "red900"
            page.update()

        # VISTAS (Pestañas convertidas a Columnas independientes)
        editor_view = ft.Column([
            txt_name, txt_code,
            ft.Row([
                ft.FilledButton("💾 Guardar", on_click=save_to_db, style=ft.ButtonStyle(bgcolor="blue900")),
                # Botón de renderizado con Emoji
                ft.FilledButton("▶️ Compilar", on_click=lambda e: render_in_wasm(), style=ft.ButtonStyle(bgcolor="green900")),
                ft.FilledButton("🧹 Limpiar", on_click=clear_editor, style=ft.ButtonStyle(bgcolor="red900")),
            ], alignment="center", wrap=True),
            status_text,
        ], expand=True, visible=True) # Visible al inicio

        viewer_view = ft.Column([wasm_webview], expand=True, visible=False)
        history_view = ft.Column([
            ft.Text("Proyectos (Offline DB)", size=18, color="blue400", weight="bold"),
            projects_list,
        ], expand=True, visible=False)

        # NAVEGACIÓN PERSONALIZADA
        def get_btn_style(is_active):
            return ft.ButtonStyle(bgcolor="blue900" if is_active else "#222222", color="white")

        def switch_tab(index):
            editor_view.visible = (index == 0)
            viewer_view.visible = (index == 1)
            history_view.visible = (index == 2)
            btn_editor.style = get_btn_style(index == 0)
            btn_viewer.style = get_btn_style(index == 1)
            btn_history.style = get_btn_style(index == 2)
            if index == 2: load_history()
            page.update()

        # Botones de navegación personalizados con Emojis
        btn_editor = ft.FilledButton("💻 Editor", on_click=lambda e: switch_tab(0), style=get_btn_style(True))
        btn_viewer = ft.FilledButton("👁️ Visor 3D", on_click=lambda e: switch_tab(1), style=get_btn_style(False))
        btn_history = ft.FilledButton("📂 Historial", on_click=lambda e: switch_tab(2), style=get_btn_style(False))

        nav_row = ft.Row([btn_editor, btn_viewer, btn_history], alignment="center", wrap=True)

        # Inyectar todo en la página
        page.add(
            ft.Text("NEXUS STUDIO CAD", size=24, weight="bold", color="blue400"),
            nav_row,
            ft.Divider(color="#333333"),
            editor_view,
            viewer_view,
            history_view
        )
        load_history()

    # DIAGNÓSTICO ROJO
    except Exception:
        page.clean()
        page.bgcolor = "red900"
        page.scroll = "auto"
        page.add(
            ft.Text("FALLO CRÍTICO EN SANDBOX", size=24, weight="bold", color="white"),
            ft.Text(traceback.format_exc(), color="white", selectable=True, size=11)
        )
        page.update()

if __name__ == "__main__":
    if not os.path.exists("assets"): os.makedirs("assets")
        
    ft.app(
        target=main, 
        assets_dir="assets", 
        view="web_browser", 
        port=8555
    )
