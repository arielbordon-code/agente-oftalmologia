"""
Módulo para registrar leads calificados en Google Sheets.
"""

import gspread
from gspread_formatting import CellFormat, Color, TextFormat, set_frozen, format_cell_range
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

from dashboard_utils import obtener_iniciales, asignar_color

SHEET_ID = os.getenv("SHEET_ID", "1hyPscn6LOKnJQYGmYruhGB7983ONRej7DUm9YSuP0n4")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google-credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Fecha",
    "Teléfono",
    "Nombre",
    "Qué quiere resolver por WhatsApp",
    "Negocio / Rubro",
    "Horario preferido (llamada)",
    "Score IA",
    "Estado",
    "Notas",
]

ESTADO_A_TEXTO = {
    "pending": "Pendiente confirmar",
    "confirmed": "Confirmado",
    "attended": "Atendido",
}
TEXTO_A_ESTADO = {texto: clave for clave, texto in ESTADO_A_TEXTO.items()}

# Turquesa Centro de Ojos
COLOR_VERDE = Color(0.10, 0.60, 0.65)
COLOR_TITULO = Color(0.05, 0.40, 0.45)
COLOR_FILA_PAR = Color(0.88, 0.96, 0.97)
COLOR_BLANCO = Color(1, 1, 1)


def get_client():
    google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet():
    return get_client().open_by_key(SHEET_ID).sheet1


def calcular_score(tratamiento: str) -> str:
    """Todo lead que llega hasta acá completó la demo entera (consulta + calificación
    + dejó nombre y horario), así que ya es un prospecto caliente."""
    return "Alto"


SCORE_PRESETS = {
    "Alto":  {"nivel": "Alto",  "css": "badge-score-alto",  "pct": 92, "razon": "Prospecto llegó hasta el cierre de la demo con datos reales."},
    "Medio": {"nivel": "Medio", "css": "badge-score-medio", "pct": 58, "razon": "Avanzó en la demo pero no completó el cierre."},
    "Bajo":  {"nivel": "Bajo",  "css": "badge-score-bajo",  "pct": 28, "razon": "Interacción breve, sin calificación completa."},
}


def setup_formato():
    """Aplica diseño visual completo al Sheet."""
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = spreadsheet.sheet1

    sheet.update_title("Leads WhatsApp")

    sheet.update("A1:I1", [["Kyrios — Prospectos Demo Valentina"] + [""] * 8])
    sheet.merge_cells("A1:I1")
    format_cell_range(sheet, "A1:I1", CellFormat(
        backgroundColor=COLOR_TITULO,
        textFormat=TextFormat(bold=True, fontSize=14, foregroundColor=COLOR_BLANCO),
        horizontalAlignment="CENTER",
    ))

    sheet.update("A2:I2", [HEADERS])
    format_cell_range(sheet, "A2:I2", CellFormat(
        backgroundColor=COLOR_VERDE,
        textFormat=TextFormat(bold=True, fontSize=11, foregroundColor=COLOR_BLANCO),
        horizontalAlignment="CENTER",
    ))

    set_frozen(sheet, rows=2)

    body = {
        "requests": [
            {"updateDimensionProperties": {
                "range": {"sheetId": sheet.id, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": ancho},
                "fields": "pixelSize"
            }}
            for i, ancho in enumerate([150, 180, 180, 220, 200, 160, 100, 160, 220])
        ]
    }
    spreadsheet.batch_update(body)

    print("[Sheets] Formato aplicado correctamente")


def _aplicar_color_fila(sheet, fila_num: int):
    color = COLOR_FILA_PAR if fila_num % 2 == 0 else COLOR_BLANCO
    rango = f"A{fila_num}:I{fila_num}"
    format_cell_range(sheet, rango, CellFormat(backgroundColor=color))


def registrar_lead(telefono: str, nombre: str, tratamiento: str,
                   sucursal: str = "", horario: str = ""):
    """Registra un lead calificado en el Sheet."""
    print(f"[Sheets] Intentando registrar: {nombre} | {tratamiento} | {horario}")
    score = calcular_score(tratamiento)
    fila = [
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        telefono,
        nombre,
        tratamiento,
        sucursal,
        horario,
        score,
        ESTADO_A_TEXTO["pending"],
        "",
    ]

    sheet = None
    for intento in range(3):
        try:
            sheet = get_sheet()
            sheet.append_row(fila)
            suffix = f" (intento {intento + 1})" if intento > 0 else ""
            print(f"[Sheets] Fila escrita correctamente{suffix}")
            break
        except Exception as e:
            print(f"[Sheets] Error intento {intento + 1}/3: {type(e).__name__}: {e}")
            if intento == 2:
                return False

    try:
        fila_num = len(sheet.col_values(1))
        _aplicar_color_fila(sheet, fila_num)
    except Exception as e:
        print(f"[Sheets] Error al aplicar formato (dato guardado igualmente): {e}")

    return True


def listar_leads(limite: int = 200) -> list:
    """Lee los leads reales del Sheet para el dashboard.

    La fila 1 es el título fusionado (A1:I1) y la fila 2 son los headers
    reales (ver setup_formato) — get_all_records() asume headers en la
    fila 1, así que acá se lee todo con get_all_values() y se descartan
    las primeras 2 filas a mano. Los datos arrancan en la fila 3 del
    Sheet real, por eso "fila" = índice en la lista + 3.
    """
    sheet = get_sheet()
    filas = sheet.get_all_values()[2:]

    leads = []
    for i, fila in enumerate(filas):
        if len(fila) < 8 or not fila[1].strip():
            continue
        fecha, telefono, nombre, necesidad, rubro, horario, score_ia, estado_texto = fila[:8]
        notas = fila[8] if len(fila) > 8 else ""
        leads.append({
            "fila": i + 3,
            "telefono": telefono,
            "nombre": nombre,
            "necesidad": necesidad,
            "rubro": rubro,
            "horario": horario,
            "estado": TEXTO_A_ESTADO.get(estado_texto, "pending"),
            "score": SCORE_PRESETS.get(score_ia, SCORE_PRESETS["Bajo"]),
            "fecha": fecha,
            "initials": obtener_iniciales(nombre),
            "color": asignar_color(telefono or nombre),
            "notas": notas,
        })

    leads.reverse()
    return leads[:limite]


def actualizar_estado(fila: int, estado: str) -> bool:
    """Actualiza la columna Estado (H) de una fila puntual del Sheet."""
    texto = ESTADO_A_TEXTO.get(estado)
    if not texto:
        return False
    for intento in range(3):
        try:
            get_sheet().update_cell(fila, 8, texto)
            return True
        except Exception as e:
            print(f"[Sheets] Error actualizando estado (intento {intento + 1}/3): {type(e).__name__}: {e}")
    return False


def actualizar_notas(fila: int, notas: str) -> bool:
    """Actualiza la columna Notas (I) de una fila puntual del Sheet."""
    for intento in range(3):
        try:
            get_sheet().update_cell(fila, 9, notas)
            return True
        except Exception as e:
            print(f"[Sheets] Error actualizando notas (intento {intento + 1}/3): {type(e).__name__}: {e}")
    return False
