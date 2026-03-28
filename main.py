import flet as ft
import sqlite3
import os
import traceback
import base64
import warnings
from datetime import datetime
import time

warnings.simplefilter("ignore", DeprecationWarning)

try:
    import flet_webview as fwv
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

WASM_ENGINE_FILE = "openscad_engine.html"

def main(page: ft.Page):
    try:
        page.title = "NEXUS 3D Studio"
        page.theme_mode = "dark"
        page.bgcolor = "#0a0a0a"
        page.padding = 10

        db_path = "nexus_cad.db"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS projects
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, code TEXT, created_at TEXT)''')
        conn.commit()

        txt_name = ft.TextField(label="Nombre", bgcolor="#151515", border_color="#333333")
        txt_code = ft.TextField(
            label="Editor OpenSCAD", multiline=True, min_lines=10, expand=True,
            bgcolor="#000000", color="#00ff00", text_style=ft.TextStyle(font_family="monospace", size=12),
            value="cube([20,20,10], center=true);"
        )
        
        status_text = ft.Text("Sistema listo.", color="grey600", size=12)
        projects_list = ft.ListView(expand=True, spacing=10, padding=10)

        viewer_view = ft.Column([
            ft.Text("Visor 3D inactivo.\nPulsa '▶️ Compilar'.", color="grey500", text_align="center")
        ], expand=True, visible=False, alignment="center")

        def load_history():
            projects_list.controls.clear()
            cursor.execute("SELECT name, created_at FROM projects ORDER BY created_at DESC")
            for row in cursor.fetchall():
                projects_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text("📦", size=16),
                            ft.Text(row[0], color="white", weight="bold", expand=True),
                            ft.TextButton("✏️", on_click=lambda e, n=row[0]: load_project(n)),
                            ft.TextButton("🗑️", on_click=lambda e, n=row[0]: delete_project(n)),
                        ]), bgcolor="#151515", padding=10, border_radius=8
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
            status_text.value = f"✓ Guardado"
            status_text.color = "green400"
            load_history()
            page.update()

        def clear_editor(e):
            txt_name.value = ""
            txt_code.value = ""
            page.update()

        def render_in_wasm():
            code = txt_code.value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            status_text.value = "Renderizando..."
            status_text.color = "orange400"
            switch_tab(1)
            
            try:
                if HAS_WEBVIEW and not page.web:
                    assets_path = os.path.join("assets", WASM_ENGINE_FILE)
                    with open(assets_path, "r", encoding="utf-8") as f:
                        html_data = f.read()
                    
                    # INYECCIÓN DIRECTA Y SEGURA: Obligamos a que pinte la pieza medio segundo después de cargar
                    html_data = html_data.replace("initCAD();", f"initCAD(); setTimeout(() => processOpenScad('{code}'), 500);")
                    b64 = base64.b64encode(html_data.encode('utf-8')).decode('utf-8')
                    
                    viewer_view.controls.clear()
                    viewer_view.controls.append(fwv.WebView(url=f"data:text/html;base64,{b64}", expand=True))
                    page.update()
                else:
                    viewer_view.controls.clear()
                    viewer_view.controls.append(ft.Text("Visor 3D: Activo solo en APK.", color="yellow"))
                    page.update()
            except Exception as ex:
                status_text.value = f"Error: {ex}"
                status_text.color = "red400"
                page.update()

        editor_view = ft.Column([
            txt_name, txt_code,
            ft.Row([
                ft.FilledButton("💾", on_click=save_to_db, style=ft.ButtonStyle(bgcolor="blue900")),
                ft.FilledButton("▶️ Compilar", on_click=lambda e: render_in_wasm(), style=ft.ButtonStyle(bgcolor="green900")),
                ft.FilledButton("🧹", on_click=clear_editor, style=ft.ButtonStyle(bgcolor="red900")),
            ], alignment="center", wrap=True),
            status_text,
        ], expand=True, visible=True)

        history_view = ft.Column([ft.Text("Proyectos", size=18, color="blue400", weight="bold"), projects_list], expand=True, visible=False)

        def switch_tab(index):
            editor_view.visible = (index == 0)
            viewer_view.visible = (index == 1)
            history_view.visible = (index == 2)
            btn_editor.style = ft.ButtonStyle(bgcolor="blue900" if index == 0 else "#222222", color="white")
            btn_viewer.style = ft.ButtonStyle(bgcolor="blue900" if index == 1 else "#222222", color="white")
            btn_history.style = ft.ButtonStyle(bgcolor="blue900" if index == 2 else "#222222", color="white")
            if index == 2: load_history()
            page.update()

        btn_editor = ft.FilledButton("💻 Editor", on_click=lambda e: switch_tab(0), style=ft.ButtonStyle(bgcolor="blue900", color="white"))
        btn_viewer = ft.FilledButton("👁️ Visor", on_click=lambda e: switch_tab(1), style=ft.ButtonStyle(bgcolor="#222222", color="white"))
        btn_history = ft.FilledButton("📂 Historial", on_click=lambda e: switch_tab(2), style=ft.ButtonStyle(bgcolor="#222222", color="white"))

        page.add(
            ft.Text("NEXUS STUDIO CAD", size=24, weight="bold", color="blue400"),
            ft.Row([btn_editor, btn_viewer, btn_history], alignment="center", wrap=True),
            ft.Divider(color="#333333"),
            editor_view, viewer_view, history_view
        )
        load_history()

    except Exception:
        page.clean()
        page.bgcolor = "#990000" 
        page.add(ft.Text("FALLO CRÍTICO", size=20, weight="bold", color="white"), ft.Text(traceback.format_exc(), color="white", size=12))
        page.update()

if __name__ == "__main__":
    if "com.termux" in os.environ.get("PREFIX", ""):
        ft.app(target=main, assets_dir="assets", view="web_browser", port=8555)
    else:
        ft.app(target=main, assets_dir="assets")
