import flet as ft
import os, base64, json, threading, http.server, socket, time, warnings, subprocess, tempfile, traceback
import urllib.request

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

CONFIG_FILE = os.path.join(EXPORT_DIR, "nexus_config.json")

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
        if self.path == '/api/get_code_b64.json':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"code_b64": LATEST_CODE_B64}).encode())
        else:
            try:
                filename = self.path.strip("/")
                if not filename: filename = "openscad_engine.html"
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
# APLICACIÓN PRINCIPAL v5.0.2 (HOTFIX STORAGE)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v5.0.2"
        page.theme_mode = "dark"
        page.padding = 0

        status = ft.Text("NEXUS v5.0.2 | Módulo IA Activo", color="green")

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
                    export_manual(str(text_to_copy), "Copiar Manualmente")
                    status.value = "⚠️ Usa copia manual."
                    status.color = "amber"
                    page.update()

        # --- EDITOR CAD ---
        DEFAULT_CODE = "function main() {\n  return CSG.cube({center:[0,0,0], radius:[10,10,10]});\n}"
        txt_code = ft.TextField(label="Código JS-CSG", multiline=True, expand=True, value=DEFAULT_CODE)

        def load_template(t):
            txt_code.value = t
            txt_code.update()
            set_tab(0)
            status.value = "✓ Código cargado."
            status.color = "green"
            status.update()

        def clear_editor():
            txt_code.value = DEFAULT_CODE
            txt_code.update()
            status.value = "✓ Editor vaciado."
            status.color = "green"
            status.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(1)
            page.update()

        def save_project():
            fname = "nexus_" + str(int(time.time())) + ".jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files()
            status.value = f"✓ Guardado: {fname}"
            status.update()

        # --- GESTOR DE ARCHIVOS ---
        file_list = ft.ListView(expand=True, spacing=10)

        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                if f == "nexus_config.json": continue # Ignoramos el archivo de configuración
                
                def make_load(name): return lambda _: load_file_content(name)
                def make_copy(name): return lambda _: export_manual(open(os.path.join(EXPORT_DIR, name), "r").read())
                def make_del(name): return lambda _: (os.remove(os.path.join(EXPORT_DIR, name)), update_files())

                acciones = ft.Row([
                    ft.ElevatedButton("▶ Abrir", on_click=make_load(f), color="white", bgcolor="#1b5e20"),
                    ft.ElevatedButton("📤 Exportar", on_click=make_copy(f), color="white", bgcolor="#0d47a1"),
                    ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#b71c1c"),
                ], scroll="auto")
                row = ft.Column([ft.Text(f, weight="bold"), acciones])
                file_list.controls.append(ft.Container(content=row, padding=10, bgcolor="#1a1a1a", border_radius=8))
            page.update()

        def load_file_content(name):
            with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
            set_tab(0)
            page.update()

        # =========================================================
        # MÓDULO: AGENTE IA (SISTEMA DE GUARDADO NATIVO REPARADO)
        # =========================================================
        def load_config():
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, "r") as f: return json.load(f)
            except: pass
            return {"ai_api_key": "", "ai_provider": "Groq"}

        config_data = load_config()
        saved_key = config_data.get("ai_api_key", "")
        saved_prov = config_data.get("ai_provider", "Groq")

        api_key_input = ft.TextField(label="API Key", value=saved_key, password=True, can_reveal_password=True, expand=True)
        provider_dd = ft.Dropdown(options=[ft.dropdown.Option("Groq"), ft.dropdown.Option("OpenRouter")], value=saved_prov, width=120)
        
        def save_config(e):
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump({"ai_api_key": api_key_input.value, "ai_provider": provider_dd.value}, f)
                status.value = "✓ Configuración IA Guardada localmente."
                status.color = "green"
            except Exception as ex:
                status.value = f"❌ Error guardando config: {str(ex)}"
                status.color = "red"
            status.update()

        btn_save_config = ft.ElevatedButton("💾 Guardar", on_click=save_config)
        config_row = ft.Row([provider_dd, api_key_input, btn_save_config])

        chat_history = ft.ListView(expand=True, spacing=10)
        user_prompt = ft.TextField(label="Ej: Crea una peana paramétrica...", multiline=True, expand=True)
        loading_ring = ft.ProgressRing(visible=False, width=20, height=20)

        SYS_PROMPT = """Eres un ingeniero experto en CAD paramétrico. Genera código en Javascript PURO para la librería CSG.js. 
REGLAS ESTRICTAS:
1. NUNCA uses comandos como cylinder() o translate() sueltos.
2. Usa SIEMPRE primitivas absolutas: CSG.cube({center:[x,y,z], radius:[x,y,z]}), CSG.cylinder({start:[x,y,z], end:[x,y,z], radius:R, slices:N}), CSG.sphere({center:[x,y,z], radius:R}).
3. Usa pieza1.union(pieza2) y pieza1.subtract(pieza2).
4. Devuelve SOLO el código dentro de una 'function main() { ... return pieza_final; }'. No añadas explicaciones largas, solo el código dentro de un bloque ```javascript """

        def send_to_ai(e):
            if not api_key_input.value:
                status.value = "❌ Falta la API Key."
                status.color = "red"; status.update()
                return
            if not user_prompt.value: return

            prompt_text = user_prompt.value
            user_prompt.value = ""
            loading_ring.visible = True
            
            chat_history.controls.append(ft.Container(
                content=ft.Text(prompt_text, color="white"),
                bgcolor="#0d47a1", padding=10, border_radius=8, alignment=ft.alignment.center_right
            ))
            page.update()

            def fetch_ai():
                try:
                    key = api_key_input.value
                    prov = provider_dd.value
                    
                    if prov == "Groq":
                        url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
                        model = "llama3-70b-8192"
                    else:
                        url = "[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)"
                        model = "google/gemini-pro"

                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    data = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYS_PROMPT},
                            {"role": "user", "content": prompt_text}
                        ]
                    }
                    
                    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
                    with urllib.request.urlopen(req, timeout=40) as response:
                        res_data = json.loads(response.read().decode('utf-8'))
                        ai_text = res_data['choices'][0]['message']['content']
                    
                    extracted_code = ""
                    if "```javascript" in ai_text:
                        extracted_code = ai_text.split("```javascript")[1].split("```")[0].strip()
                    elif "```js" in ai_text:
                        extracted_code = ai_text.split("```js")[1].split("```")[0].strip()
                    elif "function main()" in ai_text:
                        extracted_code = ai_text[ai_text.find("function main()"):].strip()

                    bot_controls = [ft.Text(ai_text, color="#e0e0e0", selectable=True)]
                    if extracted_code:
                        bot_controls.append(ft.ElevatedButton(
                            "▶ INYECTAR AL EDITOR Y COMPILAR", 
                            on_click=lambda _, c=extracted_code: (load_template(c), run_render()),
                            bgcolor="green900", color="white"
                        ))

                    chat_history.controls.append(ft.Container(
                        content=ft.Column(bot_controls),
                        bgcolor="#212121", padding=10, border_radius=8
                    ))

                except Exception as ex:
                    chat_history.controls.append(ft.Text(f"❌ Error API: {str(ex)}", color="red"))
                
                loading_ring.visible = False
                page.update()

            threading.Thread(target=fetch_ai, daemon=True).start()

        btn_send = ft.IconButton(ft.icons.SEND, on_click=send_to_ai, icon_color="cyan")

        view_ia = ft.Column([
            ft.Text("Configuración de Motor LLM", weight="bold", color="grey"),
            config_row,
            ft.Divider(),
            chat_history,
            ft.Row([user_prompt, loading_ring, btn_send], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        ], expand=True)

        # =========================================================
        # VISTAS INDEPENDIENTES Y NAVEGACIÓN
        # =========================================================
        view_editor = ft.Column([
            ft.ElevatedButton("▶ COMPILAR MALLA 3D", on_click=lambda _: run_render(), color="white", bgcolor="#004d40", height=50),
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ LIMPIAR", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🚀 ABRIR VISOR 3D", url="[http://127.0.0.1](http://127.0.0.1):" + str(LOCAL_PORT) + "/", color="white", bgcolor="#4a148c", height=60)
        view_visor = ft.Column([ft.Container(height=60), ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER)], expand=True)
        view_archivos = ft.Column([ft.Text("Proyectos Guardados", weight="bold"), file_list], expand=True)
        
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
            ft.ElevatedButton("🤖 ASISTENTE IA", on_click=lambda _: set_tab(3), color="black", bgcolor="cyan"),
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
