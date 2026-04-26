"""
Módulo para registrar leads calificados en Google Sheets.
"""

import gspread
from gspread_formatting import CellFormat, Color, TextFormat, set_frozen, format_cell_range
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

SHEET_ID = os.getenv("SHEET_ID", "")
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
    "Estado",
]

# Azul Centro de Ojos
COLOR_AZUL = Color(0.12, 0.35, 0.65)
COLOR_TITULO = Color(0.07, 0.22, 0.45)
COLOR_FILA_PAR = Color(0.88, 0.92, 0.97)
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


def setup_formato():
    """Aplica diseño visual completo al Sheet."""
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = spreadsheet.sheet1

    sheet.update_title("Leads WhatsApp")

    sheet.update("A1:G1", [["Centro de Ojos La Rioja — Leads WhatsApp"] + [""] * 6])
    sheet.merge_cells("A1:G1")
    format_cell_range(sheet, "A1:G1", CellFormat(
        backgroundColor=COLOR_TITULO,
        textFormat=TextFormat(bold=True, fontSize=14, foregroundColor=COLOR_BLANCO),
        horizontalAlignment="CENTER",
    ))

    sheet.update("A2:G2", [HEADERS])
    format_cell_range(sheet, "A2:G2", CellFormat(
        backgroundColor=COLOR_AZUL,
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
            for i, ancho in enumerate([150, 180, 180, 220, 200, 160, 160])
        ]
    }
    spreadsheet.batch_update(body)

    print("[Sheets] Formato aplicado correctamente")


def _aplicar_color_fila(sheet, fila_num: int):
    color = COLOR_FILA_PAR if fila_num % 2 == 0 else COLOR_BLANCO
    rango = f"A{fila_num}:G{fila_num}"
    format_cell_range(sheet, rango, CellFormat(backgroundColor=color))


def registrar_lead(telefono: str, nombre: str, tratamiento: str,
                   sucursal: str = "", horario: str = ""):
    """Registra un lead calificado en el Sheet."""
    try:
        sheet = get_sheet()
        fila = [
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            telefono,
            nombre,
            tratamiento,
            sucursal,
            horario,
            "Pendiente confirmar",
        ]
        sheet.append_row(fila)

        fila_num = len(sheet.col_values(1))
        _aplicar_color_fila(sheet, fila_num)

        return True
    except Exception as e:
        print(f"[Sheets] Error al registrar lead: {e}")
        return False
