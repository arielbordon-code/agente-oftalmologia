"""
Agente de WhatsApp de demostración (Negocio Ejemplo).
Detecta la consulta del cliente, hace 3 preguntas de calificación
y ofrece turno si corresponde. Detecta solicitudes urgentes.
"""

from anthropic import Anthropic
from dataclasses import dataclass, field
from typing import Optional
from sheets import registrar_lead

SYSTEM_PROMPT = """Sos Valentina, agente de tu negocio. Tu objetivo es atender consultas por WhatsApp, entender qué necesita el cliente y ayudarlo a agendar un turno de manera rápida y cálida.

## SOBRE NEGOCIO EJEMPLO
Negocio Ejemplo es una empresa de servicios que atiende consultas y turnos por WhatsApp para sus clientes.

Dirección: Av. Ejemplo 123, Ciudad Ejemplo
Teléfono: +54 11 5555-0100
WhatsApp: +54 9 11 5555-0100
Email: info@negocioejemplo.com

Horarios:
- Lunes a viernes: 9:00 a 13:00 y de 15:00 a 20:00
- Sábados: 9:00 a 13:00
- Domingos y feriados: cerrado

## SERVICIOS QUE OFRECEMOS
- Servicio Premium: atención personalizada de alta gama
- Servicio Estándar: atención habitual para consultas generales
- Primera consulta: evaluación inicial gratuita para nuevos clientes
- Seguimiento y control: turnos de seguimiento para clientes existentes

Si el cliente pregunta por algo muy específico que no está acá, respondé de forma general y ofrecé confirmarlo con el equipo.

## ⚠️ SOLICITUDES URGENTES — PRIORIDAD MÁXIMA
Si el cliente describe una situación urgente que necesita atención inmediata (por ejemplo: "es urgente", "necesito ayuda ya", "es una emergencia"), interrumpí el flujo normal y respondé de inmediato que debe contactar directamente.

En ese caso decile: "Entiendo que es urgente. Por favor contactanos ahora mismo al +54 11 5555-0100 o acercate directamente a nuestro local en Av. Ejemplo 123."

## FLUJO DE CONVERSACIÓN — SEGUÍ ESTAS ETAPAS EN ORDEN

### ETAPA 1: BIENVENIDA Y DETECCIÓN
Usá siempre este saludo inicial:
"¡Hola! Soy Valentina 👋, agente de tu negocio. Puedo contarte sobre nuestros servicios, horarios y ubicación, y también agendarte un turno cuando quieras. ¿En qué te ayudo hoy?"

Antes de continuar, verificá si hay señales de urgencia en lo que describe el cliente.

### ETAPA 2: CALIFICACIÓN (exactamente 3 preguntas — OBLIGATORIO)
Una vez identificada la consulta, SIEMPRE hacé exactamente 3 preguntas, UNA POR UNA, esperando la respuesta antes de hacer la siguiente. NUNCA saltes al agendamiento sin haber hecho las 3 preguntas.

Preguntas generales (adaptalas según lo que haya pedido el cliente):
1. Qué servicio o consulta específica necesita
2. Si ya es cliente o es la primera vez que nos contacta
3. Si tiene alguna preferencia particular a tener en cuenta (horario, modalidad, urgencia del pedido)

### ETAPA 3: CIERRE
Después de las 3 respuestas, evaluá la situación:

SI HAY URGENCIA → Derivá de inmediato (ver sección de arriba).

SI ES CONSULTA HABITUAL → En un solo mensaje: decí brevemente que el equipo lo va a atender, y pedile su nombre completo y preferencia de día y horario. Esperá a que el cliente responda con esos datos ANTES de confirmar el turno.

## REGLAS IMPORTANTES
- Sé siempre cálida, clara y profesional
- Escribí en español rioplatense (vos, tenés, etc.)
- **BREVEDAD OBLIGATORIA**: máximo 3 oraciones por mensaje. Nunca uses listas largas. Si el cliente pide información extensa, respondé con 2-3 ejemplos y ofrecé ampliar
- Nunca prometas precios exactos ni resultados que el negocio no pueda garantizar
- Ante la duda de si es urgente, siempre priorizá derivar
- Si el cliente pregunta algo que no sabés (precio exacto, disponibilidad puntual), decile que lo consultás y le confirmás. NUNCA apliques esto a los turnos: los turnos se agendan directamente sin "verificar disponibilidad"
- Un emoji por mensaje, con moderación 👋
- Siempre recordá que sos Valentina, agente de tu negocio

## REGISTRO DE TURNO
SOLO cuando el cliente ya te respondió con su nombre Y su horario preferido, en el mensaje de confirmación del turno agregá OBLIGATORIAMENTE al FINAL esta línea:
##TURNO|[nombre real del cliente]|[motivo real de consulta]|Negocio Ejemplo|[día y horario real que pidió]##

NUNCA agregues esta señal en el mensaje donde pedís el nombre y horario — solo en el mensaje de confirmación, después de que el cliente los haya dado.

Ejemplo con datos reales (el cliente ya respondió "Juan Pérez, prefiero el martes a la mañana"):
##TURNO|Juan Pérez|Consulta general|Negocio Ejemplo|Martes a la mañana##

IMPORTANTE: Reemplazá SIEMPRE los campos con los datos reales del cliente. Nunca escribas los corchetes.
"""


@dataclass
class Conversation:
    """Estado de la conversación con un cliente."""
    phone_number: str
    messages: list = field(default_factory=list)
    stage: str = "inicio"
    turno_registrado: bool = False
    pending_lead: Optional[dict] = None


class OftalmologiaAgent:
    """Agente conversacional de demostración (Negocio Ejemplo)."""

    MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: Optional[str] = None):
        import os
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada")
        self.client = Anthropic(api_key=key)
        self.conversations: dict[str, Conversation] = {}

    def get_or_create_conversation(self, phone_number: str) -> Conversation:
        if phone_number not in self.conversations:
            self.conversations[phone_number] = Conversation(phone_number=phone_number)
        return self.conversations[phone_number]

    def reset_conversation(self, phone_number: str) -> None:
        if phone_number in self.conversations:
            del self.conversations[phone_number]

    def _retry_pending_lead(self, phone_number: str) -> None:
        """Reintenta registrar un lead que falló en el intento anterior."""
        conv = self.conversations.get(phone_number)
        if not conv or not conv.pending_lead or conv.turno_registrado:
            return
        data = conv.pending_lead
        print(f"[Sheets] Reintentando lead pendiente para {phone_number}...")
        ok = registrar_lead(**data)
        if ok:
            print(f"[Sheets] Lead pendiente registrado: {data['nombre']}")
            conv.turno_registrado = True
            conv.pending_lead = None
        else:
            print(f"[Sheets] ⚠️ Reintento fallido para {phone_number}, se intentará de nuevo")

    def reply(self, phone_number: str, user_message: str) -> str:
        self._retry_pending_lead(phone_number)
        conv = self.get_or_create_conversation(phone_number)

        conv.messages.append({"role": "user", "content": user_message})

        import time
        ultimo_error = None
        for intento in range(3):
            try:
                response = self.client.messages.create(
                    model=self.MODEL,
                    max_tokens=450,
                    temperature=0.7,
                    system=SYSTEM_PROMPT,
                    messages=conv.messages,
                )
                break
            except Exception as e:
                ultimo_error = e
                if intento < 2:
                    print(f"[Claude] Error transitorio (intento {intento + 1}/3): {e}. Reintentando...")
                    time.sleep(2)
                else:
                    print(f"[Claude] Error después de 3 intentos: {e}")
                    conv.messages.pop()
                    return "Disculpá, estoy teniendo un problema técnico en este momento. ¿Podés volver a escribirme en un instante? 🙏"

        assistant_message = next((b.text for b in response.content if b.type == "text"), "")
        assistant_message = self._procesar_turno(phone_number, assistant_message)

        conv.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message

    def _procesar_turno(self, phone_number: str, mensaje: str) -> str:
        """Detecta la señal de turno, registra en Sheets y la limpia del mensaje."""
        import re
        patron = r"##TURNO\|([^|]*)\|([^|]*)\|([^|]*)\|([^#]*)##"
        match = re.search(patron, mensaje)
        mensaje = re.sub(patron, "", mensaje).strip()
        if not match:
            return mensaje
        conv = self.conversations.get(phone_number)
        if conv and conv.turno_registrado:
            print(f"[Sheets] Turno duplicado ignorado para {phone_number}")
            return mensaje
        nombre, tratamiento, sucursal, horario = match.groups()
        if not nombre.strip():
            print(f"[Sheets] Señal ##TURNO## sin nombre — ignorada (señal prematura del modelo)")
            return mensaje
        lead_data = {
            "telefono": phone_number,
            "nombre": nombre.strip(),
            "tratamiento": tratamiento.strip(),
            "sucursal": sucursal.strip(),
            "horario": horario.strip(),
        }
        ok = registrar_lead(**lead_data)
        if ok:
            print(f"[Sheets] Lead registrado: {nombre} — {tratamiento}")
            if conv:
                conv.turno_registrado = True
                conv.pending_lead = None
        else:
            print(f"[Sheets] ⚠️ Fallo al registrar lead para {phone_number}. Guardado para reintento.")
            if conv:
                conv.pending_lead = lead_data
        return mensaje

    def get_conversation_summary(self, phone_number: str) -> dict:
        conv = self.conversations.get(phone_number)
        if not conv:
            return {"phone_number": phone_number, "status": "sin conversación"}
        return {
            "phone_number": phone_number,
            "total_mensajes": len(conv.messages),
            "ultimo_mensaje_usuario": next(
                (m["content"] for m in reversed(conv.messages) if m["role"] == "user"),
                None
            ),
        }
