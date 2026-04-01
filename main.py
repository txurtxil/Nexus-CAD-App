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
# MOTOR SERVIDOR LOCAL (VISOR 3D)
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
# APLICACIÓN PRINCIPAL v11.2 (STABLE CORE)
# =========================================================
def main(page: ft.Page):
    try:
        page.title = "NEXUS CAD v11.2"
        page.theme_mode = "dark"
        page.padding = 0 
        
        status = ft.Text("NEXUS v11.2 | Todas las fases cargadas y estables", color="green")

        def copy_text(text_to_copy):
            try:
                page.set_clipboard(str(text_to_copy))
                status.value = "✓ Código copiado."
                status.color = "green"
            except:
                try:
                    subprocess.run(['termux-clipboard-set'], input=str(text_to_copy).encode('utf-8'))
                    status.value = "✓ Copiado (Termux)."
                    status.color = "green"
                except: pass
            page.update()

        T_INICIAL = "function main() {\n  var pieza = CSG.cube({center:[0,0,10], radius:[20,20,10]});\n  return pieza;\n}"
        txt_code = ft.TextField(label="Código Fuente (JS-CSG)", multiline=True, expand=True, value=T_INICIAL)

        def clear_editor():
            txt_code.value = "function main() {\n  var pieza = CSG.cube({center:[0,0,0], radius:[10,10,10]});\n  return pieza;\n}"
            txt_code.update()

        def inject_snippet(code_snippet):
            c = txt_code.value
            pos = c.rfind('return ')
            if pos != -1:
                txt_code.value = c[:pos] + code_snippet + "\n  " + c[pos:]
            else:
                txt_code.value = c + "\n" + code_snippet
            txt_code.update()

        def run_render():
            global LATEST_CODE_B64
            LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            set_tab(2)
            page.update()

        row_snippets = ft.Row([
            ft.Text("Primitivas:", color="grey", size=12),
            ft.ElevatedButton("+ Cubo", on_click=lambda _: inject_snippet("  var cubo = CSG.cube({center:[0,0,0], radius:[5,5,5]});")),
            ft.ElevatedButton("+ Cilindro", on_click=lambda _: inject_snippet("  var cil = CSG.cylinder({start:[0,0,0], end:[0,0,10], radius:5, slices:32});")),
            ft.ElevatedButton("- Restar", on_click=lambda _: inject_snippet("  pieza = pieza.subtract(pieza2);")),
        ], scroll="auto")

        herramienta_actual = "custom"

        def create_slider(label, min_v, max_v, val, is_int, on_change_fn):
            txt_val = ft.Text(f"{int(val) if is_int else val:.1f}", color="cyan", width=45, text_align="right", size=13)
            sl = ft.Slider(min=min_v, max=max_v, value=val, expand=True)
            if is_int: sl.divisions = int(max_v - min_v)
            def internal_change(e):
                txt_val.value = f"{int(sl.value) if is_int else sl.value:.1f}"
                txt_val.update()
                on_change_fn(e)
            sl.on_change = internal_change
            return sl, ft.Row([ft.Text(label, width=110, size=12, color="white"), sl, txt_val])

        # =========================================================
        # MOTOR PARAMÉTRICO - LÓGICA DE GENERACIÓN
        # =========================================================
        def generate_param_code(e=None):
            h = herramienta_actual
            
            if h == "custom": pass 

            elif h == "cubo":
                g = sl_c_grosor.value
                code = f"function main() {{\n  var pieza = CSG.cube({{center:[0,0,{sl_c_z.value/2}], radius:[{sl_c_x.value/2}, {sl_c_y.value/2}, {sl_c_z.value/2}]}});\n"
                if g > 0:
                    g = min(g, min(sl_c_x.value, sl_c_y.value) / 2.1)
                    code += f"  var int = CSG.cube({{center:[0,0,{sl_c_z.value/2 + g}], radius:[{sl_c_x.value/2 - g}, {sl_c_y.value/2 - g}, {sl_c_z.value/2}]}});\n  pieza = pieza.subtract(int);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code

            elif h == "cilindro":
                rint = min(sl_p_rint.value, sl_p_rext.value - 0.5)
                c = int(sl_p_lados.value)
                code = f"function main() {{\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,{sl_p_h.value}], radius:{sl_p_rext.value}, slices:{c}}});\n"
                if rint > 0:
                    code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,{sl_p_h.value+2}], radius:{rint}, slices:{c}}});\n  pieza = pieza.subtract(int);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code
            
            elif h == "escuadra":
                l, w, t, hr = sl_l_largo.value, sl_l_ancho.value, sl_l_grosor.value, sl_l_hueco.value
                code = f"function main() {{\n  var l = {l}; var w = {w}; var t = {t}; var r = {hr};\n"
                code += f"  var base = CSG.cube({{center:[l/2, w/2, t/2], radius:[l/2, w/2, t/2]}});\n"
                code += f"  var wall = CSG.cube({{center:[t/2, w/2, l/2], radius:[t/2, w/2, l/2]}});\n  var pieza = base.union(wall);\n"
                if hr > 0:
                    code += f"  var h1 = CSG.cylinder({{start:[l*0.7, w/2, -1], end:[l*0.7, w/2, t+1], radius:r, slices:32}});\n"
                    code += f"  var h2 = CSG.cylinder({{start:[-1, w/2, l*0.7], end:[t+1, w/2, l*0.7], radius:r, slices:32}});\n"
                    code += f"  pieza = pieza.subtract(h1).subtract(h2);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code
                
            elif h == "engranaje":
                d, r, ht, eje = int(sl_e_dientes.value), sl_e_radio.value, sl_e_grosor.value, sl_e_eje.value
                d_x, d_y = r * 0.15, r * 0.2
                code = f"function main() {{\n  var dientes = {d}; var r = {r}; var h = {ht};\n  var pieza = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r, slices:64}});\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n    var a = (i * Math.PI * 2) / dientes;\n"
                code += f"    var diente = CSG.cube({{center:[Math.cos(a)*r, Math.sin(a)*r, h/2], radius:[{d_x}, {d_y}, h/2]}});\n    pieza = pieza.union(diente);\n  }}\n"
                if eje > 0: code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{eje}, slices:32}});\n  pieza = pieza.subtract(hueco);\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code

            elif h == "fijacion":
                m, l_tornillo, tol = sl_fij_m.value, sl_fij_l.value, sl_fij_tol.value
                r_hex = (m * 1.8) / 2; h_cabeza = m * 0.8; r_eje = m / 2
                if l_tornillo == 0:
                    code = f"function main() {{\n  var m = {m}; var h = {h_cabeza};\n"
                    code += f"  var cuerpo = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:{r_hex}, slices:6}});\n"
                    code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:{r_eje + tol}, slices:32}});\n"
                    code += f"  return cuerpo.subtract(agujero);\n}}"
                else:
                    code = f"function main() {{\n"
                    code += f"  var m = {m}; var l_tornillo = {l_tornillo}; var r_eje = {r_eje - tol};\n"
                    code += f"  var h_cabeza = {h_cabeza}; var r_hex = {r_hex};\n"
                    code += f"  var cabeza = CSG.cylinder({{start:[0,0,0], end:[0,0,h_cabeza], radius:r_hex, slices:6}});\n"
                    code += f"  var eje = CSG.cylinder({{start:[0,0,h_cabeza - 0.1], end:[0,0,h_cabeza + l_tornillo], radius:r_eje - (m*0.08), slices:32}});\n"
                    code += f"  var pieza = cabeza.union(eje);\n"
                    code += f"  var paso = m * 0.15;\n"
                    code += f"  for(var z = h_cabeza + 1; z < h_cabeza + l_tornillo - 1; z += paso*1.5) {{\n"
                    code += f"      var anillo = CSG.cylinder({{start:[0,0,z], end:[0,0,z+paso], radius:r_eje, slices:16}});\n"
                    code += f"      pieza = pieza.union(anillo);\n"
                    code += f"  }}\n  return pieza;\n}}"
                txt_code.value = code

            elif h == "rodamiento":
                d_int, d_ext, ht = sl_rod_dint.value, sl_rod_dext.value, sl_rod_h.value
                code = f"function main() {{\n  var d_int = {d_int}; var d_ext = {d_ext}; var h = {ht};\n"
                code += f"  var pista_ext = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:d_ext/2, slices:64}})\n"
                code += f"       .subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:(d_ext/2)-2, slices:64}}) );\n"
                code += f"  var pista_int = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:(d_int/2)+2, slices:64}})\n"
                code += f"       .subtract( CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:d_int/2, slices:64}}) );\n"
                code += f"  var pieza = pista_ext.union(pista_int);\n\n"
                code += f"  var r_espacio = (((d_ext/2)-2) - ((d_int/2)+2)) / 2;\n"
                code += f"  var radio_centro = ((d_int/2)+2 + (d_ext/2)-2)/2;\n"
                code += f"  var n_bolas = Math.floor((Math.PI * 2 * radio_centro) / (r_espacio * 2.2));\n"
                code += f"  for(var i=0; i<n_bolas; i++) {{\n"
                code += f"      var a = (i * Math.PI * 2) / n_bolas;\n"
                code += f"      var bx = Math.cos(a) * radio_centro;\n"
                code += f"      var by = Math.sin(a) * radio_centro;\n"
                code += f"      var bola = CSG.sphere({{center:[bx, by, h/2], radius:r_espacio*0.95, resolution:16}});\n"
                code += f"      pieza = pieza.union(bola);\n  }}\n  return pieza;\n}}"
                txt_code.value = code

            elif h == "planetario":
                r_sol, r_planeta, ht = sl_plan_rs.value, sl_plan_rp.value, sl_plan_h.value
                code = f"function main() {{\n"
                code += f"  var r_sol = {r_sol}; var r_planeta = {r_planeta}; var h = {ht};\n"
                code += f"  var tol = 0.5; var r_anillo = r_sol + (r_planeta*2); var dist_centros = r_sol + r_planeta;\n"
                code += f"  var sol = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_sol - 1, slices:32}});\n"
                code += f"  var dientes_sol = Math.floor(r_sol * 1.5);\n"
                code += f"  for(var i=0; i<dientes_sol; i++) {{\n"
                code += f"      var a = (i * Math.PI * 2) / dientes_sol;\n"
                code += f"      var diente = CSG.cylinder({{start:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, 0], end:[Math.cos(a)*r_sol, Math.sin(a)*r_sol, h], radius:1.2, slices:12}});\n"
                code += f"      sol = sol.union(diente);\n  }}\n"
                code += f"  sol = sol.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:3, slices:16}}));\n"
                code += f"  var planetas = new CSG();\n"
                code += f"  var dientes_planeta = Math.floor(r_planeta * 1.5);\n"
                code += f"  for(var p=0; p<3; p++) {{\n"
                code += f"      var ap = (p * Math.PI * 2) / 3;\n"
                code += f"      var cx = Math.cos(ap) * dist_centros; var cy = Math.sin(ap) * dist_centros;\n"
                code += f"      var planeta = CSG.cylinder({{start:[cx, cy, 0], end:[cx, cy, h], radius:r_planeta - 1 - tol, slices:32}});\n"
                code += f"      for(var i=0; i<dientes_planeta; i++) {{\n"
                code += f"          var a = (i * Math.PI * 2) / dientes_planeta;\n"
                code += f"          var px = cx + Math.cos(a)*(r_planeta - tol);\n"
                code += f"          var py = cy + Math.sin(a)*(r_planeta - tol);\n"
                code += f"          var diente = CSG.cylinder({{start:[px, py, 0], end:[px, py, h], radius:1.2 - (tol/2), slices:12}});\n"
                code += f"          planeta = planeta.union(diente);\n      }}\n"
                code += f"      planeta = planeta.subtract(CSG.cylinder({{start:[cx, cy, -1], end:[cx, cy, h+1], radius:2, slices:12}}));\n"
                code += f"      planetas = planetas.union(planeta);\n  }}\n"
                code += f"  var corona = CSG.cylinder({{start:[0,0,0], end:[0,0,h], radius:r_anillo + 5, slices:64}});\n"
                code += f"  var hueco = CSG.cylinder({{start:[0,0,-1], end:[0,0,h+1], radius:r_anillo + tol, slices:64}});\n"
                code += f"  corona = corona.subtract(hueco);\n"
                code += f"  var dientes_corona = Math.floor(r_anillo * 1.5);\n"
                code += f"  var anillo_dientes = new CSG();\n"
                code += f"  for(var i=0; i<dientes_corona; i++) {{\n"
                code += f"      var a = (i * Math.PI * 2) / dientes_corona;\n"
                code += f"      var diente = CSG.cylinder({{start:[Math.cos(a)*(r_anillo + tol), Math.sin(a)*(r_anillo + tol), 0], end:[Math.cos(a)*(r_anillo + tol), Math.sin(a)*(r_anillo + tol), h], radius:1.2, slices:12}});\n"
                code += f"      anillo_dientes = anillo_dientes.union(diente);\n  }}\n"
                code += f"  corona = corona.union(anillo_dientes);\n"
                code += f"  return sol.union(planetas).union(corona);\n}}"
                txt_code.value = code

            elif h == "polea":
                dientes, ancho, d_eje = int(sl_pol_t.value), sl_pol_w.value, sl_pol_d.value
                code = f"function main() {{\n  var dientes = {dientes}; var ancho = {ancho}; var r_eje = {d_eje/2};\n"
                code += f"  var pitch = 2; var r_primitivo = (dientes * pitch) / (2 * Math.PI); var r_ext = r_primitivo - 0.25;\n"
                code += f"  var cuerpo = CSG.cylinder({{start:[0,0,1.5], end:[0,0,1.5+ancho], radius:r_ext, slices:64}});\n"
                code += f"  var matriz_dientes = new CSG();\n"
                code += f"  for(var i=0; i<dientes; i++) {{\n"
                code += f"      var a = (i * Math.PI * 2) / dientes;\n"
                code += f"      var d = CSG.cylinder({{start:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 1], end:[Math.cos(a)*r_ext, Math.sin(a)*r_ext, 2+ancho], radius:0.55, slices:8}});\n"
                code += f"      matriz_dientes = matriz_dientes.union(d);\n  }}\n"
                code += f"  cuerpo = cuerpo.subtract(matriz_dientes);\n"
                code += f"  var base = CSG.cylinder({{start:[0,0,0], end:[0,0,1.5], radius:r_ext + 1, slices:64}});\n"
                code += f"  var tapa = CSG.cylinder({{start:[0,0,1.5+ancho], end:[0,0,3+ancho], radius:r_ext + 1, slices:64}});\n"
                code += f"  var polea = base.union(cuerpo).union(tapa);\n"
                code += f"  polea = polea.subtract(CSG.cylinder({{start:[0,0,-1], end:[0,0,5+ancho], radius:r_eje, slices:32}}));\n"
                code += f"  return polea;\n}}"
                txt_code.value = code

            elif h == "helice":
                rad, n_aspas, pitch = sl_hel_r.value, int(sl_hel_n.value), sl_hel_p.value
                code = f"function main() {{\n  var rad = {rad}; var n = {n_aspas}; var pitch = {pitch};\n"
                code += f"  var hub = CSG.cylinder({{start:[0,0,0], end:[0,0,10], radius:8, slices:32}});\n"
                code += f"  var agujero = CSG.cylinder({{start:[0,0,-1], end:[0,0,11], radius:2.5, slices:16}});\n"
                code += f"  var aspas = new CSG();\n"
                code += f"  for(var i=0; i<n; i++) {{\n    var a = (i * Math.PI * 2) / n;\n"
                code += f"    var dx = Math.cos(a); var dy = Math.sin(a);\n"
                code += f"    var aspa = CSG.cylinder({{\n"
                code += f"        start: [6*dx, 6*dy, 5 - (pitch/10)],\n"
                code += f"        end: [rad*dx, rad*dy, 5 + (pitch/10)],\n"
                code += f"        radius: 3, slices: 4\n    }});\n"
                code += f"    aspas = aspas.union(aspa);\n  }}\n"
                code += f"  return hub.union(aspas).subtract(agujero);\n}}"
                txt_code.value = code

            elif h == "texto":
                txt_input = tf_texto.value.upper()[:12] 
                th = sl_txt_h.value
                code = f"""function main() {{
  var texto = "{txt_input}"; var grosor = {th};
  var font = {{ 'A':[14,17,31,17,17], 'B':[30,17,30,17,30], 'C':[14,17,16,17,14], 'D':[30,17,17,17,30], 'E':[31,16,30,16,31], 'F':[31,16,30,16,16], 'G':[14,17,23,17,14], 'H':[17,17,31,17,17], 'I':[14,4,4,4,14], 'J':[7,2,2,18,12], 'K':[17,18,28,18,17], 'L':[16,16,16,16,31], 'M':[17,27,21,17,17], 'N':[17,25,21,19,17], 'O':[14,17,17,17,14], 'P':[30,17,30,16,16], 'Q':[14,17,21,18,13], 'R':[30,17,30,18,17], 'S':[14,16,14,1,14], 'T':[31,4,4,4,4], 'U':[17,17,17,17,14], 'V':[17,17,17,10,4], 'W':[17,17,21,27,17], 'X':[17,10,4,10,17], 'Y':[17,10,4,4,4], 'Z':[31,2,4,8,31], ' ':[0,0,0,0,0], '0':[14,17,17,17,14], '1':[4,12,4,4,14], '2':[14,1,14,16,31], '3':[14,1,14,1,14], '4':[18,18,31,2,2], '5':[31,16,14,1,14], '6':[14,16,30,17,14], '7':[31,1,2,4,8], '8':[14,17,14,17,14], '9':[14,17,15,1,14] }};
  var piezaText = new CSG(); var voxelSize = 2; 
  for(var i=0; i<texto.length; i++) {{
    var charMatrix = font[texto[i]] || font[' '];
    var offsetX = i * (6 * voxelSize); 
    for(var fila=0; fila<5; fila++) {{
      var rowVal = charMatrix[fila];
      for(var col=0; col<5; col++) {{
        if ((rowVal >> (4 - col)) & 1) {{
           var x = offsetX + (col * voxelSize); var y = ( (4-fila) * voxelSize); 
           var voxel = CSG.cube({{center:[x, y, grosor/2], radius:[voxelSize/2, voxelSize/2, grosor/2]}});
           piezaText = piezaText.union(voxel);
        }}
      }}
    }}
  }}
  var largoBase = texto.length * (6 * voxelSize);
  var base = CSG.cube({{center:[(largoBase/2)-voxelSize, 4, -1], radius:[largoBase/2, 6, 1]}});
  return piezaText.union(base);
}}"""
                txt_code.value = code

            elif h == "abrazadera":
                diam, grosor, ancho = sl_clamp_d.value, sl_clamp_g.value, sl_clamp_w.value
                code = f"function main() {{\n  var diam = {diam}; var grosor = {grosor}; var ancho = {ancho};\n"
                code += f"  var ext = CSG.cylinder({{start:[0,0,0], end:[0,0,ancho], radius:(diam/2)+grosor, slices:64}});\n"
                code += f"  var int = CSG.cylinder({{start:[0,0,-1], end:[0,0,ancho+1], radius:diam/2, slices:64}});\n"
                code += f"  var corteInf = CSG.cube({{center:[0, -50, ancho/2], radius:[50, 50, ancho]}});\n"
                code += f"  var arco = ext.subtract(int).subtract(corteInf);\n"
                code += f"  var distPestana = (diam/2) + grosor + 5;\n"
                code += f"  var pestana = CSG.cube({{center:[ distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n"
                code += f"  var pestana2 = CSG.cube({{center:[ -distPestana, grosor/2, ancho/2 ], radius:[7.5, grosor/2, ancho/2]}});\n"
                code += f"  var m3 = CSG.cylinder({{start:[ distPestana, 10, ancho/2 ], end:[ distPestana, -10, ancho/2 ], radius:1.7, slices:16}});\n"
                code += f"  var m3_2 = CSG.cylinder({{start:[ -distPestana, 10, ancho/2 ], end:[ -distPestana, -10, ancho/2 ], radius:1.7, slices:16}});\n"
                code += f"  return arco.union(pestana).union(pestana2).subtract(m3).subtract(m3_2);\n}}"
                txt_code.value = code

            elif h == "bisagra":
                l, d, tol = sl_bi_l.value, sl_bi_d.value, sl_bi_tol.value
                code = f"function main() {{\n  var l = {l}; var d = {d}; var tol = {tol};\n"
                code += f"  var fix = CSG.cylinder({{start:[0,0,0], end:[0,0,l/3], radius:d/2, slices:32}});\n"
                code += f"  var fix2 = CSG.cylinder({{start:[0,0,2*l/3], end:[0,0,l], radius:d/2, slices:32}});\n"
                code += f"  var move = CSG.cylinder({{start:[0,0,l/3+tol], end:[0,0,2*l/3-tol], radius:d/2, slices:32}});\n"
                code += f"  var pin = CSG.cylinder({{start:[0,0,l/3-d/4], end:[0,0,2*l/3+d/4], radius:(d/4)-tol, slices:32}});\n"
                code += f"  var cut_pin = CSG.cylinder({{start:[0,0,l/3-d/2], end:[0,0,2*l/3+d/2], radius:d/4, slices:32}});\n"
                code += f"  var fijo = fix.union(fix2).subtract(cut_pin).union(pin);\n"
                code += f"  var movil = move.subtract(cut_pin);\n"
                code += f"  return fijo.union(movil.translate([0, d+2, 0]));\n}}"
                txt_code.value = code

            elif h == "vslot":
                l = sl_v_l.value
                code = f"function main() {{\n  var l = {l};\n  var pieza = CSG.cube({{center:[0,0,l/2], radius:[10,10,l/2]}});\n"
                code += f"  var ch = CSG.cylinder({{start:[0,0,-1], end:[0,0,l+1], radius:2.1, slices:32}});\n  pieza = pieza.subtract(ch);\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[0,-10,l/2], radius:[3,2,l/2+1]}})).subtract(CSG.cube({{center:[0,-8.5,l/2], radius:[5,1.5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  pieza = pieza.subtract(CSG.cube({{center:[-10,0,l/2], radius:[2,3,l/2+1]}})).subtract(CSG.cube({{center:[-8.5,0,l/2], radius:[1.5,5,l/2+1]}}));\n"
                code += f"  return pieza;\n}}"
                txt_code.value = code
                
            elif h == "pcb":
                px, py, ht, t = sl_pcb_x.value, sl_pcb_y.value, sl_pcb_h.value, sl_pcb_t.value
                code = f"function main() {{\n  var px = {px}; var py = {py}; var h = {ht}; var t = {t};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[px/2 + t, py/2 + t, h/2]}});\n"
                code += f"  var int = CSG.cube({{center:[0,0,h/2 + t], radius:[px/2, py/2, h/2]}});\n"
                code += f"  var pieza = ext.subtract(int);\n"
                code += f"  var dx = px/2 - 3.5; var dy = py/2 - 3.5;\n"
                code += f"  var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n"
                code += f"    var cyl = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 0], end:[m[i][0]*dx, m[i][1]*dy, h-2], radius: 3.5, slices:16}});\n"
                code += f"    var hole = CSG.cylinder({{start:[m[i][0]*dx, m[i][1]*dy, 2], end:[m[i][0]*dx, m[i][1]*dy, h], radius: 1.5, slices:16}});\n"
                code += f"    pieza = pieza.union(cyl).subtract(hole);\n  }}\n  return pieza;\n}}"
                txt_code.value = code

            elif h == "rotula":
                rb, tol = sl_rot_r.value, sl_rot_tol.value
                code = f"function main() {{\n  var r_bola = {rb}; var tol = {tol};\n"
                code += f"  var bola = CSG.sphere({{center:[0,0,0], radius:r_bola, resolution:32}});\n"
                code += f"  var eje_bola = CSG.cylinder({{start:[0,0,0], end:[0,0,-r_bola*2], radius:r_bola*0.6, slices:32}});\n"
                code += f"  var componente_bola = bola.union(eje_bola);\n"
                code += f"  var copa_ext = CSG.cylinder({{start:[0,0,-r_bola*0.2], end:[0,0,r_bola*1.5], radius:r_bola+4, slices:32}});\n"
                code += f"  var hueco_bola = CSG.sphere({{center:[0,0,0], radius:r_bola+tol, resolution:32}});\n"
                code += f"  var apertura = CSG.cylinder({{start:[0,0,r_bola*0.5], end:[0,0,r_bola*2], radius:r_bola*0.8, slices:32}});\n"
                code += f"  var componente_copa = copa_ext.subtract(hueco_bola).subtract(apertura);\n"
                code += f"  return componente_bola.union(componente_copa);\n}}"
                txt_code.value = code

            elif h == "carcasa":
                w, l, ht, t = sl_car_x.value, sl_car_y.value, sl_car_z.value, sl_car_t.value
                code = f"function main() {{\n  var w = {w}; var l = {l}; var h = {ht}; var t = {t};\n"
                code += f"  var ext = CSG.cube({{center:[0,0,h/2], radius:[w/2, l/2, h/2]}});\n"
                code += f"  var int = CSG.cube({{center:[0,0,(h/2)+t], radius:[(w/2)-t, (l/2)-t, h/2]}});\n"
                code += f"  var base = ext.subtract(int);\n"
                code += f"  var r_post = 3.5; var r_hole = 1.5; var h_post = 6;\n"
                code += f"  var m = [[1,1], [1,-1], [-1,1], [-1,-1]];\n"
                code += f"  for(var i=0; i<4; i++) {{\n"
                code += f"      var px = m[i][0] * ((w/2) - t - r_post - 1);\n"
                code += f"      var py = m[i][1] * ((l/2) - t - r_post - 1);\n"
                code += f"      var post = CSG.cylinder({{start:[px,py,t], end:[px,py,t+h_post], radius:r_post, slices:16}});\n"
                code += f"      var hole = CSG.cylinder({{start:[px,py,t], end:[px,py,t+h_post+1], radius:r_hole, slices:16}});\n"
                code += f"      base = base.union(post).subtract(hole);\n  }}\n"
                code += f"  var vents = new CSG();\n"
                code += f"  for(var vx=-(w/2)+15; vx < (w/2)-15; vx += 7) {{\n"
                code += f"      for(var vy=-(l/2)+15; vy < (l/2)-15; vy += 7) {{\n"
                code += f"          var agujero = CSG.cylinder({{start:[vx,vy,-1], end:[vx,vy,t+1], radius:2, slices:8}});\n"
                code += f"          vents = vents.union(agujero);\n"
                code += f"      }}\n  }}\n  return base.subtract(vents);\n}}"
                txt_code.value = code

            elif h == "muelle":
                r_res = sl_mue_r.value; r_hilo = sl_mue_h.value; vueltas = sl_mue_v.value; alt = sl_mue_alt.value
                code = f"function main() {{\n  var r_res = {r_res}; var r_hilo = {r_hilo}; var h = {alt}; var vueltas = {vueltas};\n"
                code += f"  var resorte = new CSG();\n"
                code += f"  var pasos = Math.floor(vueltas * 24);\n"
                code += f"  var paso_z = h / pasos; var a_step = (Math.PI * 2 * vueltas) / pasos;\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n"
                code += f"      var a1 = i * a_step; var a2 = (i+1) * a_step;\n"
                code += f"      var x1 = Math.cos(a1)*r_res; var y1 = Math.sin(a1)*r_res; var z1 = i*paso_z;\n"
                code += f"      var x2 = Math.cos(a2)*r_res; var y2 = Math.sin(a2)*r_res; var z2 = (i+1)*paso_z;\n"
                code += f"      var seg = CSG.cylinder({{start:[x1,y1,z1], end:[x2,y2,z2], radius:r_hilo, slices:8}});\n"
                code += f"      var esp = CSG.sphere({{center:[x2,y2,z2], radius:r_hilo, resolution:8}});\n"
                code += f"      resorte = resorte.union(seg).union(esp);\n  }}\n  return resorte;\n}}"
                txt_code.value = code

            elif h == "acme":
                d = sl_acme_d.value; pitch = sl_acme_p.value; length = sl_acme_l.value
                code = f"function main() {{\n  var r = {d/2}; var pitch = {pitch}; var len = {length};\n"
                code += f"  var r_core = r - (pitch * 0.4);\n"
                code += f"  var eje = CSG.cylinder({{start:[0,0,0], end:[0,0,len], radius:r_core, slices:32}});\n"
                code += f"  var thread = new CSG();\n"
                code += f"  var steps = Math.floor((len / pitch) * 24);\n"
                code += f"  var z_step = len / steps; var a_step = (Math.PI * 2 * (len/pitch)) / steps;\n"
                code += f"  var w = pitch * 0.35;\n"
                code += f"  for(var i=0; i<steps; i++) {{\n"
                code += f"      var a1 = i * a_step; var a2 = (i+1) * a_step;\n"
                code += f"      var z1 = i * z_step; var z2 = (i+1) * z_step;\n"
                code += f"      var seg = CSG.cylinder({{start:[Math.cos(a1)*r, Math.sin(a1)*r, z1], end:[Math.cos(a2)*r, Math.sin(a2)*r, z2], radius:w, slices:8}});\n"
                code += f"      thread = thread.union(seg);\n  }}\n  return eje.union(thread);\n}}"
                txt_code.value = code

            elif h == "codo":
                rt = sl_codo_r.value; rc = sl_codo_c.value; ang = sl_codo_a.value; gro = sl_codo_g.value
                code = f"function main() {{\n  var r_tubo = {rt}; var r_curva = {rc}; var angulo = {ang}; var grosor = {gro};\n"
                code += f"  var codo = new CSG();\n"
                code += f"  var pasos = Math.max(8, Math.floor(angulo / 5));\n"
                code += f"  for(var i=0; i<pasos; i++) {{\n"
                code += f"      var a1 = (i * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"      var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"      var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva;\n"
                code += f"      var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"      var ext = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo, slices:16}});\n"
                code += f"      var esf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo, resolution:16}});\n"
                code += f"      codo = codo.union(ext).union(esf);\n  }}\n"
                code += f"  if(grosor > 0) {{\n"
                code += f"     var hueco = new CSG();\n"
                code += f"     for(var i=0; i<pasos; i++) {{\n"
                code += f"         var a1 = (i * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"         var a2 = ((i+1) * (angulo/pasos)) * Math.PI / 180;\n"
                code += f"         var x1 = Math.cos(a1)*r_curva; var y1 = Math.sin(a1)*r_curva;\n"
                code += f"         var x2 = Math.cos(a2)*r_curva; var y2 = Math.sin(a2)*r_curva;\n"
                code += f"         var int = CSG.cylinder({{start:[x1,y1,0], end:[x2,y2,0], radius:r_tubo-grosor, slices:12}});\n"
                code += f"         var isf = CSG.sphere({{center:[x2,y2,0], radius:r_tubo-grosor, resolution:12}});\n"
                code += f"         hueco = hueco.union(int).union(isf);\n     }}\n"
                code += f"     codo = codo.subtract(hueco);\n  }}\n  return codo;\n}}"
                txt_code.value = code

            elif h == "naca":
                cuerda, grosor, envergadura = sl_naca_c.value, sl_naca_g.value, sl_naca_e.value
                code = f"function main() {{\n  var cuerda = {cuerda}; var grosor = {grosor}; var envergadura = {envergadura};\n"
                code += f"  var ala = new CSG();\n"
                code += f"  var num_pasos = 40;\n"
                code += f"  for(var i=0; i<=num_pasos; i++) {{\n"
                code += f"      var x = i/num_pasos;\n"
                code += f"      var yt = 5 * (grosor/100) * (0.2969*Math.sqrt(x) - 0.1260*x - 0.3516*(x*x) + 0.2843*Math.pow(x,3) - 0.1015*Math.pow(x,4));\n"
                code += f"      var x_real = x * cuerda;\n"
                code += f"      var yt_real = Math.max(yt * cuerda, 0.1);\n"
                code += f"      var cyl = CSG.cylinder({{start:[x_real, 0, 0], end:[x_real, 0, envergadura], radius: yt_real, slices: 16}});\n"
                code += f"      ala = ala.union(cyl);\n  }}\n  return ala;\n}}"
                txt_code.value = code

            txt_code.update()

        # =========================================================
        # SECCIÓN CRÍTICA: DEFINICIÓN DE INTERFACES ANTES DE USO
        # =========================================================
        # -- 1. CUSTOM --
        col_custom = ft.Column([
            ft.Text("Módulo Activo: Tu Código de IA", color="green", weight="bold"),
            ft.Text("Escribe tus propios algoritmos CSG.", color="grey", size=12),
            ft.Row([
                ft.ElevatedButton("🕳️ Vaciado", on_click=lambda _: inject_snippet("  var vaciado = pieza.scale([0.9, 0.9, 0.9]);\n  pieza = pieza.subtract(vaciado);"), bgcolor="#4e342e", color="white"),
                ft.ElevatedButton("🔄 Redondeo", on_click=lambda _: inject_snippet("  pieza = pieza.expand(2, 16);"), bgcolor="#1b5e20", color="white"),
            ], scroll="auto")
        ], visible=True)

        # -- 2. CUBO --
        sl_c_x, r_c_x = create_slider("Ancho X", 5, 200, 50, False, generate_param_code)
        sl_c_y, r_c_y = create_slider("Fondo Y", 5, 200, 30, False, generate_param_code)
        sl_c_z, r_c_z = create_slider("Alto Z", 5, 200, 20, False, generate_param_code)
        sl_c_grosor, r_c_g = create_slider("Grosor Pared", 0, 20, 0, False, generate_param_code)
        col_cubo = ft.Column([ft.Text("Cubo/Caja Hueca.", color="grey", size=12), ft.Container(content=ft.Column([r_c_x, r_c_y, r_c_z, r_c_g]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 3. CILINDRO --
        sl_p_rext, r_p_rext = create_slider("Radio Ext", 5, 100, 25, False, generate_param_code)
        sl_p_rint, r_p_rint = create_slider("Radio Int", 0, 95, 15, False, generate_param_code)
        sl_p_h, r_p_h = create_slider("Altura", 2, 200, 10, False, generate_param_code)
        sl_p_lados, r_p_lados = create_slider("Caras", 3, 64, 64, True, generate_param_code)
        col_cilindro = ft.Column([ft.Text("Cilindro/Tubo.", color="grey", size=12), ft.Container(content=ft.Column([r_p_rext, r_p_rint, r_p_h, r_p_lados]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 4. ESCUADRA --
        sl_l_largo, r_l_l = create_slider("Largo Brazos", 10, 100, 40, False, generate_param_code)
        sl_l_ancho, r_l_a = create_slider("Ancho Perfil", 5, 50, 15, False, generate_param_code)
        sl_l_grosor, r_l_g = create_slider("Grosor Chapa", 1, 20, 3, False, generate_param_code)
        sl_l_hueco, r_l_h = create_slider("Agujero", 0, 10, 2, False, generate_param_code)
        col_escuadra = ft.Column([ft.Text("Escuadra de refuerzo.", color="grey", size=12), ft.Container(content=ft.Column([r_l_l, r_l_a, r_l_g, r_l_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 5. ENGRANAJE --
        sl_e_dientes, r_e_d = create_slider("Dientes", 6, 40, 16, True, generate_param_code)
        sl_e_radio, r_e_r = create_slider("Radio Base", 10, 100, 30, False, generate_param_code)
        sl_e_grosor, r_e_g = create_slider("Grosor", 2, 50, 5, False, generate_param_code)
        sl_e_eje, r_e_e = create_slider("Hueco Eje", 0, 30, 5, False, generate_param_code)
        col_engranaje = ft.Column([ft.Text("Piñón Recto básico.", color="grey", size=12), ft.Container(content=ft.Column([r_e_d, r_e_r, r_e_g, r_e_e]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 6. PCB --
        sl_pcb_x, r_pcb_x = create_slider("Largo PCB", 20, 200, 70, False, generate_param_code)
        sl_pcb_y, r_pcb_y = create_slider("Ancho PCB", 20, 200, 50, False, generate_param_code)
        sl_pcb_h, r_pcb_h = create_slider("Altura Caja", 10, 100, 20, False, generate_param_code)
        sl_pcb_t, r_pcb_t = create_slider("Grosor Pared", 1, 10, 2, False, generate_param_code)
        col_pcb = ft.Column([ft.Text("Caja PCB.", color="grey", size=12), ft.Container(content=ft.Column([r_pcb_x, r_pcb_y, r_pcb_h, r_pcb_t]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 7. VSLOT --
        sl_v_l, r_v_l = create_slider("Longitud", 10, 300, 50, False, generate_param_code)
        col_vslot = ft.Column([ft.Text("V-Slot 2020.", color="grey", size=12), ft.Container(content=ft.Column([r_v_l]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 8. BISAGRA --
        sl_bi_l, r_bi_l = create_slider("Largo Total", 10, 100, 30, False, generate_param_code)
        sl_bi_d, r_bi_d = create_slider("Diámetro Eje", 5, 30, 10, False, generate_param_code)
        sl_bi_tol, r_bi_tol = create_slider("Tolerancia", 0.1, 1.0, 0.3, False, generate_param_code)
        col_bisagra = ft.Column([ft.Text("Bisagra Print-in-Place.", color="grey", size=12), ft.Container(content=ft.Column([r_bi_l, r_bi_d, r_bi_tol]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 9. ABRAZADERA --
        sl_clamp_d, r_clamp_d = create_slider("Ø Tubo", 10, 100, 25, False, generate_param_code)
        sl_clamp_g, r_clamp_g = create_slider("Grosor Arco", 2, 15, 5, False, generate_param_code)
        sl_clamp_w, r_clamp_w = create_slider("Ancho Pieza", 5, 50, 15, False, generate_param_code)
        col_abrazadera = ft.Column([ft.Text("Abrazadera media luna M3.", color="grey", size=12), ft.Container(content=ft.Column([r_clamp_d, r_clamp_g, r_clamp_w]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 10. FIJACIÓN (TORNILLOS) --
        sl_fij_m, r_fij_m = create_slider("Métrica (M)", 3, 20, 8, True, generate_param_code)
        sl_fij_l, r_fij_l = create_slider("Largo Tornillo", 0, 100, 30, False, generate_param_code)
        sl_fij_tol, r_fij_tol = create_slider("Tolerancia", 0, 1.0, 0.2, False, generate_param_code)
        col_fijacion = ft.Column([ft.Text("Tuerca (0) / Tornillo (>0).", color="amber", size=12), ft.Container(content=ft.Column([r_fij_m, r_fij_l, r_fij_tol]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 11. RODAMIENTO --
        sl_rod_dint, r_rod_dint = create_slider("Ø Eje Interno", 3, 50, 8, False, generate_param_code)
        sl_rod_dext, r_rod_dext = create_slider("Ø Externo", 10, 100, 22, False, generate_param_code)
        sl_rod_h, r_rod_h = create_slider("Altura", 3, 30, 7, False, generate_param_code)
        col_rodamiento = ft.Column([ft.Text("Ensamblaje Rodamiento.", color="amber", size=12), ft.Container(content=ft.Column([r_rod_dint, r_rod_dext, r_rod_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 12. PLANETARIO --
        sl_plan_rs, r_plan_rs = create_slider("Radio Sol", 5, 40, 10, False, generate_param_code)
        sl_plan_rp, r_plan_rp = create_slider("Radio Planetas", 4, 30, 8, False, generate_param_code)
        sl_plan_h, r_plan_h = create_slider("Grosor Total", 3, 30, 6, False, generate_param_code)
        col_planetario = ft.Column([ft.Text("Mecanismo Planetario.", color="amber", size=12), ft.Container(content=ft.Column([r_plan_rs, r_plan_rp, r_plan_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 13. POLEA --
        sl_pol_t, r_pol_t = create_slider("Nº Dientes", 10, 60, 20, True, generate_param_code)
        sl_pol_w, r_pol_w = create_slider("Ancho Correa", 4, 20, 6, False, generate_param_code)
        sl_pol_d, r_pol_d = create_slider("Ø Eje Motor", 2, 12, 5, False, generate_param_code)
        col_polea = ft.Column([ft.Text("Polea GT2 de Tracción.", color="cyan", size=12), ft.Container(content=ft.Column([r_pol_t, r_pol_w, r_pol_d]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 14. HÉLICE --
        sl_hel_r, r_hel_r = create_slider("Radio Total", 20, 150, 50, False, generate_param_code)
        sl_hel_n, r_hel_n = create_slider("Nº Aspas", 2, 12, 4, True, generate_param_code)
        sl_hel_p, r_hel_p = create_slider("Torsión (Pitch)", 10, 80, 45, False, generate_param_code)
        col_helice = ft.Column([ft.Text("Hélice Vectorial 3D.", color="cyan", size=12), ft.Container(content=ft.Column([r_hel_r, r_hel_n, r_hel_p]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 15. TEXTO --
        tf_texto = ft.TextField(label="Escribe tu Texto", value="AITOR", max_length=12, on_change=generate_param_code)
        sl_txt_h, r_txt_h = create_slider("Grosor Extrusión", 1, 20, 5, False, generate_param_code)
        col_texto = ft.Column([ft.Text("Letras Voxel 3D.", color="cyan", size=12), ft.Container(content=ft.Column([tf_texto, r_txt_h]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 16. RÓTULA --
        sl_rot_r, r_rot_r = create_slider("Radio Bola", 5, 30, 10, False, generate_param_code)
        sl_rot_tol, r_rot_tol = create_slider("Gap Tolerancia", 0.1, 1.0, 0.4, False, generate_param_code)
        col_rotula = ft.Column([ft.Text("Rótula Print-in-Place.", color="cyan", size=12), ft.Container(content=ft.Column([r_rot_r, r_rot_tol]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 17. CARCASA --
        sl_car_x, r_car_x = create_slider("Ancho (X)", 20, 200, 80, False, generate_param_code)
        sl_car_y, r_car_y = create_slider("Largo (Y)", 20, 200, 120, False, generate_param_code)
        sl_car_z, r_car_z = create_slider("Alto (Z)", 10, 100, 30, False, generate_param_code)
        sl_car_t, r_car_t = create_slider("Grosor Pared", 1, 5, 2, False, generate_param_code)
        col_carcasa = ft.Column([ft.Text("Carcasa Smart Electrónica.", color="cyan", size=12), ft.Container(content=ft.Column([r_car_x, r_car_y, r_car_z, r_car_t]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 18. MUELLE --
        sl_mue_r, r_mue_r = create_slider("Radio Resorte", 5, 50, 15, False, generate_param_code)
        sl_mue_h, r_mue_h = create_slider("Radio del Hilo", 1, 10, 2, False, generate_param_code)
        sl_mue_v, r_mue_v = create_slider("Nº Vueltas", 2, 20, 5, False, generate_param_code)
        sl_mue_alt, r_mue_alt = create_slider("Altura Total", 10, 200, 40, False, generate_param_code)
        col_muelle = ft.Column([ft.Text("Resorte Paramétrico Espiral.", color="amber", size=12), ft.Container(content=ft.Column([r_mue_r, r_mue_h, r_mue_v, r_mue_alt]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 19. ACME --
        sl_acme_d, r_acme_d = create_slider("Diámetro Eje", 4, 30, 8, False, generate_param_code)
        sl_acme_p, r_acme_p = create_slider("Paso (Pitch)", 1, 10, 2, False, generate_param_code)
        sl_acme_l, r_acme_l = create_slider("Longitud Eje", 10, 200, 50, False, generate_param_code)
        col_acme = ft.Column([ft.Text("Eje Trapezoidal (ACME).", color="amber", size=12), ft.Container(content=ft.Column([r_acme_d, r_acme_p, r_acme_l]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 20. CODO --
        sl_codo_r, r_codo_r = create_slider("Radio Tubo", 2, 50, 10, False, generate_param_code)
        sl_codo_c, r_codo_c = create_slider("Radio Curva", 10, 150, 30, False, generate_param_code)
        sl_codo_a, r_codo_a = create_slider("Ángulo Giroº", 10, 180, 90, False, generate_param_code)
        sl_codo_g, r_codo_g = create_slider("Grosor Hueco", 0, 10, 2, False, generate_param_code)
        col_codo = ft.Column([ft.Text("Tubo Curvo (Sweep).", color="cyan", size=12), ft.Container(content=ft.Column([r_codo_r, r_codo_c, r_codo_a, r_codo_g]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # -- 21. NACA --
        sl_naca_c, r_naca_c = create_slider("Cuerda (Largo)", 20, 200, 80, False, generate_param_code)
        sl_naca_g, r_naca_g = create_slider("Grosor Max %", 5, 30, 15, False, generate_param_code)
        sl_naca_e, r_naca_e = create_slider("Envergadura Z", 10, 300, 100, False, generate_param_code)
        col_naca = ft.Column([ft.Text("Perfil Alar NACA (NASA).", color="cyan", size=12), ft.Container(content=ft.Column([r_naca_c, r_naca_g, r_naca_e]), bgcolor="#1e1e1e", padding=10, border_radius=8)], visible=False)

        # =========================================================
        # FUNCIONES QUE DEPENDEN DE LAS INTERFACES (YA DEFINIDAS)
        # =========================================================
        def update_constructor_ui(e=None):
            paneles = [
                col_custom, col_cubo, col_cilindro, col_escuadra, col_engranaje, col_pcb, 
                col_vslot, col_bisagra, col_abrazadera, col_fijacion, col_rodamiento, 
                col_planetario, col_polea, col_helice, col_texto, col_rotula, col_carcasa,
                col_muelle, col_acme, col_codo, col_naca
            ]
            for p in paneles: p.visible = False
            
            v = herramienta_actual
            if v == "custom": col_custom.visible = True
            elif v == "cubo": col_cubo.visible = True
            elif v == "cilindro": col_cilindro.visible = True
            elif v == "escuadra": col_escuadra.visible = True
            elif v == "engranaje": col_engranaje.visible = True
            elif v == "pcb": col_pcb.visible = True
            elif v == "vslot": col_vslot.visible = True
            elif v == "bisagra": col_bisagra.visible = True
            elif v == "abrazadera": col_abrazadera.visible = True
            elif v == "fijacion": col_fijacion.visible = True
            elif v == "rodamiento": col_rodamiento.visible = True
            elif v == "planetario": col_planetario.visible = True
            elif v == "polea": col_polea.visible = True
            elif v == "helice": col_helice.visible = True
            elif v == "texto": col_texto.visible = True
            elif v == "rotula": col_rotula.visible = True
            elif v == "carcasa": col_carcasa.visible = True
            elif v == "muelle": col_muelle.visible = True
            elif v == "acme": col_acme.visible = True
            elif v == "codo": col_codo.visible = True
            elif v == "naca": col_naca.visible = True
            
            generate_param_code()
            page.update()

        def select_tool(nombre_herramienta):
            nonlocal herramienta_actual
            herramienta_actual = nombre_herramienta
            update_constructor_ui()

        def thumbnail(icon, title, tool_id, color):
            return ft.Container(
                content=ft.Column([ft.Text(icon, size=28), ft.Text(title, size=10, color="white", weight="bold")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=75, height=75, bgcolor=color, border_radius=8, on_click=lambda _: select_tool(tool_id), ink=True
            )

        # =========================================================
        # ENSAMBLAJE DE LA VISTA
        # =========================================================
        cat_especial = ft.Row([thumbnail("🧠", "Mi Código", "custom", "#000000"), thumbnail("🔠", "Texto 3D", "texto", "#c2185b")], scroll="auto")
        cat_aero = ft.Row([thumbnail("✈️", "Perfil NACA", "naca", "#0277bd"), thumbnail("🚁", "Hélice", "helice", "#00838f"), thumbnail("🚰", "Tubo Curvo", "codo", "#00695c")], scroll="auto")
        cat_mecanismos = ft.Row([thumbnail("🌀", "Muelle", "muelle", "#4e342e"), thumbnail("🦾", "Rótula", "rotula", "#d84315"), thumbnail("⚙️", "Planetario", "planetario", "#e65100"), thumbnail("🛼", "Polea", "polea", "#0277bd"), thumbnail("🛞", "Rodamiento", "rodamiento", "#5d4037")], scroll="auto")
        cat_ingenieria = ft.Row([thumbnail("🚧", "Eje ACME", "acme", "#424242"), thumbnail("🗃️", "Carcasa", "carcasa", "#2e7d32"), thumbnail("🔩", "Tornillos", "fijacion", "#c62828"), thumbnail("🗜️", "Abrazadera", "abrazadera", "#1565c0"), thumbnail("🔌", "Caja PCB", "pcb", "#004d40"), thumbnail("🚪", "Bisagra", "bisagra", "#4a148c"), thumbnail("🏗️", "V-Slot", "vslot", "#1a237e")], scroll="auto")
        cat_basico = ft.Row([thumbnail("📦", "Caja", "cubo", "#37474f"), thumbnail("🛢️", "Cilindro", "cilindro", "#37474f"), thumbnail("📐", "Escuadra", "escuadra", "#bf360c"), thumbnail("⚙️", "Piñón", "engranaje", "#ff6f00")], scroll="auto")

        view_constructor = ft.Column([
            ft.Text("💡 Especiales y Branding:", size=12, color="grey"), cat_especial,
            ft.Text("🛸 Aero y Orgánico (Fase 4):", size=12, color="cyan"), cat_aero,
            ft.Text("⚙️ Cinemática y Mecanismos:", size=12, color="amber"), cat_mecanismos,
            ft.Text("🛠️ Ingeniería (Fase 3):", size=12, color="orange"), cat_ingenieria,
            ft.Text("📦 Geometría Básica:", size=12, color="grey"), cat_basico,
            ft.Divider(),
            
            # LAS 21 COLUMNAS PERFECTAMENTE REFERENCIADAS
            col_custom, col_texto, col_naca, col_helice, col_codo,
            col_muelle, col_rotula, col_planetario, col_polea, col_rodamiento, 
            col_acme, col_carcasa, col_fijacion, col_abrazadera, col_pcb, col_bisagra, 
            col_vslot, col_cubo, col_cilindro, col_escuadra, col_engranaje,
            
            ft.Container(height=10),
            ft.ElevatedButton("▶ ACTUALIZAR MALLA (3D)", on_click=lambda _: run_render(), color="black", bgcolor="amber", height=60, width=float('inf'))
        ], expand=True, scroll="auto")

        view_editor = ft.Column([
            ft.Row([
                ft.ElevatedButton("💾 GUARDAR", on_click=lambda _: save_project(), color="white", bgcolor="#0d47a1"),
                ft.ElevatedButton("🗑️ RESET", on_click=lambda _: clear_editor(), color="white", bgcolor="#b71c1c"), 
            ], scroll="auto"),
            row_snippets, 
            txt_code
        ], expand=True)

        btn_visor = ft.ElevatedButton("🔄 RECARGAR VISOR 3D", url="http://127.0.0.1:" + str(LOCAL_PORT) + "/", color="black", bgcolor="amber", height=60, width=300)
        view_visor = ft.Column([
            ft.Container(height=40), 
            ft.Text("Visualizador 3D Compilado", text_align="center", color="cyan", weight="bold"),
            ft.Row([btn_visor], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
            ft.Text("📦 Usa el botón del visor Web para exportar a STL.", color="grey", text_align="center", size=12)
        ], expand=True)
        
        file_list = ft.ListView(expand=True, spacing=10)
        def update_files():
            file_list.controls.clear()
            for f in reversed(sorted(os.listdir(EXPORT_DIR))):
                if f == "nexus_config.json": continue
                def make_load(name): return lambda _: load_file_content(name)
                def make_del(name): return lambda _: delete_file(name)
                acciones = ft.Row([
                    ft.ElevatedButton("▶", on_click=make_load(f), color="white", bgcolor="#1b5e20"),
                    ft.ElevatedButton("🗑️", on_click=make_del(f), color="white", bgcolor="#b71c1c"),
                ], scroll="auto")
                file_list.controls.append(ft.Container(content=ft.Row([ft.Text(f, weight="bold", width=150), acciones]), padding=10, bgcolor="#1a1a1a", border_radius=8))
            page.update()

        def load_file_content(name):
            try:
                with open(os.path.join(EXPORT_DIR, name), "r") as f: txt_code.value = f.read()
                set_tab(0); status.value = f"✓ {name} cargado."
            except: pass
            page.update()

        def delete_file(name): os.remove(os.path.join(EXPORT_DIR, name)); update_files()
        def save_project():
            fname = f"nexus_{int(time.time())}.jscad"
            with open(os.path.join(EXPORT_DIR, fname), "w") as f: f.write(txt_code.value)
            update_files(); status.value = f"✓ Guardado: {fname}"; page.update()

        view_archivos = ft.Column([ft.Text("Mis Archivos", weight="bold"), file_list], expand=True)
        main_container = ft.Container(content=view_editor, expand=True)

        def set_tab(idx):
            tabs = [view_editor, view_constructor, view_visor, view_archivos]
            if idx == 2:
                global LATEST_CODE_B64
                LATEST_CODE_B64 = base64.b64encode(txt_code.value.encode()).decode()
            if idx == 3: update_files()
            main_container.content = tabs[idx]
            page.update()

        nav_bar = ft.Row([
            ft.ElevatedButton("💻 CODE", on_click=lambda _: set_tab(0)),
            ft.ElevatedButton("🛠️ BUILD", on_click=lambda _: set_tab(1), color="black", bgcolor="amber"),
            ft.ElevatedButton("👁️ 3D", on_click=lambda _: set_tab(2), color="white", bgcolor="#004d40"),
            ft.ElevatedButton("📁 FILES", on_click=lambda _: set_tab(3)),
        ], scroll="auto")

        root_container = ft.Container(content=ft.Column([nav_bar, main_container, status], expand=True), padding=ft.padding.only(top=45, left=5, right=5, bottom=5), expand=True)
        page.add(root_container)
        
        # INICIALIZACIÓN SEGURA:
        herramienta_actual = "custom"
        update_constructor_ui()
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