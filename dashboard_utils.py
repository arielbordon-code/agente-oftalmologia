"""
Utilidades compartidas para armar los datos que consume el dashboard
(iniciales y color determinístico por lead/conversación).
"""

COLORES = ["emerald", "blue", "purple", "yellow", "red", "teal", "pink", "indigo"]


def obtener_iniciales(nombre: str) -> str:
    partes = (nombre or "").strip().split()
    if not partes:
        return "??"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[1][0]).upper()


def asignar_color(semilla: str) -> str:
    indice = sum(ord(c) for c in (semilla or "")) % len(COLORES)
    return COLORES[indice]
