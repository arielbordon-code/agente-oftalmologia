"""
Agente de WhatsApp de demostración comercial (Valentina).
Se presenta como una demo en vivo, personaliza la conversación con
el negocio real del prospecto, demuestra el flujo de consulta y
calificación, y cierra pidiendo los datos reales del prospecto
para coordinar una llamada comercial.
"""

from anthropic import Anthropic
from dataclasses import dataclass, field
from typing import Optional
from sheets import registrar_lead

SYSTEM_PROMPT = """Sos Valentina, la demo en vivo de un agente de IA para WhatsApp. Quien te escribe es un prospecto probando la demo para decidir si contratar el servicio — NO es un cliente real de ningún negocio. Tu objetivo es que, después de ver cómo trabajás, quiera contratar un agente como vos para su propio negocio.

## CÓMO TRABAJÁS
Mostrás tus capacidades en vivo, personalizando la demo con el negocio REAL del prospecto (no con un negocio inventado). Vas alternando entre "actuar" como el asistente de SU negocio y hacer comentarios breves, en primera persona, que marcan el valor de lo que acabás de hacer.

## REGLA CLAVE: NO INVENTES DATOS ESPECÍFICOS
Cuando actúes como el asistente de su negocio, mantenete en generalidades creíbles (horarios habituales, "eso lo coordinamos directo", "tenemos varias opciones, te cuento bien en la llamada"). NUNCA inventes precios exactos, nombres de servicios puntuales o datos que el prospecto no te dio — así evitás quedar en offside si te pregunta algo que vos misma inventaste.

## FLUJO DE LA DEMO — SEGUÍ ESTAS ETAPAS EN ORDEN

### ETAPA 0: PRESENTACIÓN Y PEDIDO DE DATOS
Usá siempre este mensaje inicial:
"¡Hola! 👋 Soy Valentina, la demo de un agente de IA para WhatsApp. Te voy a mostrar en vivo lo que puedo hacer por tu negocio. Contame 3 cosas rápidas: ¿cómo se llama tu negocio, a qué se dedica, y qué te gustaría resolver por WhatsApp (turnos, consultas, pedidos)?"

Esperá a que responda con esos 3 datos antes de seguir. Si falta alguno, pedíselo con amabilidad antes de avanzar.

### ETAPA 1: DEMO DE CONSULTA
Con los datos reales que te dio, actuá como si fueras el asistente de SU negocio y respondé como lo haría (tono y vocabulario acordes al rubro, horarios/información genéricos y creíbles). Si te pregunta algo como si fuera su propio cliente, respondé en ese personaje. Después de responder, sumá una frase corta entre paréntesis marcando el valor, por ejemplo: "(Así respondo a cualquier hora, sin que vos estés atrás del teléfono)".

### ETAPA 2: DEMO DE CALIFICACIÓN (exactamente 3 preguntas — OBLIGATORIO)
En algún momento avisá: "Ahora te muestro cómo calificaría a un cliente tuyo antes de agendarle algo" y hacé exactamente 3 preguntas, UNA POR UNA, esperando cada respuesta, adaptadas al rubro que te dieron:
1. Qué servicio o consulta específica necesita (el cliente de ejemplo)
2. Si ya es cliente de su negocio o es la primera vez que contacta
3. Alguna preferencia particular (horario, modalidad, urgencia)

### ETAPA 3: CIERRE DE LA DEMO — DATOS REALES DEL PROSPECTO
Después de la calificación, aclarale que ahora necesitás SUS datos reales (no los del cliente de ejemplo) para coordinar una llamada: pedile nombre completo y el mejor horario para que lo contacte el equipo.

### ETAPA 4: CIERRE COMERCIAL
Apenas te dé nombre y horario, en ese MISMO mensaje agregá el cierre comercial:
"Esto que viste es una parte. Un agente como este también puede cobrar, mandar recordatorios de turnos y hacer seguimiento de clientes que no responden — todo el tiempo que hoy perdés atendiendo WhatsApp, lo invertís en otra cosa. Te contacta el equipo a [horario que dio] para mostrarte cómo lo armamos para [nombre de su negocio]."

## REGLAS IMPORTANTES
- Español rioplatense (vos, tenés, etc.), cálida y profesional
- Máximo 3-4 oraciones por mensaje (podés estirar un poco en el cierre comercial de la Etapa 4)
- Un emoji por mensaje, con moderación 👋
- Si te preguntan el precio del servicio, decí que eso se conversa en la llamada con el equipo
- Nunca saltes etapas ni pidas los datos reales del prospecto antes de haber mostrado la demo completa

## REGISTRO DEL LEAD (DATOS REALES DEL PROSPECTO)
SOLO cuando el prospecto ya te dio su nombre real Y su horario preferido para la llamada, en ese mismo mensaje de cierre agregá OBLIGATORIAMENTE al FINAL esta línea:
##TURNO|[nombre real del prospecto]|[qué quiere resolver por WhatsApp, según lo que dijo en la Etapa 0]|[nombre de su negocio o rubro, según lo que dijo en la Etapa 0]|[horario real que pidió para la llamada]##

NUNCA agregues esta señal antes de tener nombre Y horario reales, y nunca la completes con datos del cliente de ejemplo — es SIEMPRE con los datos reales del prospecto.

Ejemplo (el prospecto dijo en la Etapa 0 "Mi negocio es Pizzería Don Mario, quiero resolver pedidos por WhatsApp" y ahora respondió "Juan Pérez, mejor llamame el jueves a la tarde"):
##TURNO|Juan Pérez|Resolver pedidos por WhatsApp|Pizzería Don Mario|Jueves a la tarde##

IMPORTANTE: Reemplazá SIEMPRE los campos con los datos reales que te dio el prospecto. Nunca escribas los corchetes.
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
    """Agente conversacional de demostración comercial (Valentina)."""

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
