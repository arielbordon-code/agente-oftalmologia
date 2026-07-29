"""
Módulo para registrar leads calificados en Google Sheets.
"""

import gspread
from gspread_formatting import CellFormat, Color, TextFormat, set_frozen, format_cell_range
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

SHEET_ID = os.getenv("SHEET_ID", "1H8Zzqvhju80ePBawZGy8W1-zvXeR5HfyMSI3DCQqCA8")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google-credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Fecha",
    "Teléfono",
    "Nombre",
    "Motivo de consulta",
    "Sede",
    "Horario preferido",
    "Score IA",
    "Estado",
]

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
    """Asigna score IA según el tipo de tratamiento detectado."""
    t = tratamiento.lower()
    keywords_alto = [
        "cirugía", "cirugia", "catarata", "retina", "glaucoma", "queratocono",
        "láser", "laser", "crosslinking", "vitrectomía", "vitrectomia",
        "desprendimiento", "trasplante", "refractiva", "miopía", "miopia",
        "hipermetropía", "hipermetropia", "astigmatismo", "presbicia",
        "lente intraocular", "pterigion", "dacriocistitis", "urgencia", "emergencia",
    ]
    keywords_bajo = [
        "información", "informacion", "precio", "costo", "duda", "pregunta", "consulta general",
    ]
    if any(k in t for k in keywords_alto):
        return "Alto"
    elif any(k in t for k in keywords_bajo):
        return "Bajo"
    return "Medio"


def setup_formato():
    """Aplica diseño visual completo al Sheet."""
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = spreadsheet.sheet1

    sheet.update_title("Leads WhatsApp")

    sheet.update("A1:H1", [["Centro de Ojos La Rioja — Pacientes WhatsApp"] + [""] * 7])
    sheet.merge_cells("A1:H1")
    format_cell_range(sheet, "A1:H1", CellFormat(
        backgroundColor=COLOR_TITULO,
        textFormat=TextFormat(bold=True, fontSize=14, foregroundColor=COLOR_BLANCO),
        horizontalAlignment="CENTER",
    ))

    sheet.update("A2:H2", [HEADERS])
    format_cell_range(sheet, "A2:H2", CellFormat(
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
            for i, ancho in enumerate([150, 180, 180, 220, 200, 160, 100, 160])
        ]
    }
    spreadsheet.batch_update(body)

    print("[Sheets] Formato aplicado correctamente")


def _aplicar_color_fila(sheet, fila_num: int):
    color = COLOR_FILA_PAR if fila_num % 2 == 0 else COLOR_BLANCO
    rango = f"A{fila_num}:H{fila_num}"
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
        "Pendiente confirmar",
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
