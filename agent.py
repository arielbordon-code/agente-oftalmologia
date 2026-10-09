"""
Agente de WhatsApp de demostración comercial (Valentina).
Se presenta como una demo en vivo, personaliza la conversación con
el negocio real del prospecto, demuestra el flujo de consulta y
calificación, y cierra pidiendo los datos reales del prospecto
para coordinar una llamada comercial.
"""

import time
from anthropic import Anthropic
from dataclasses import dataclass, field
from typing import Optional
from sheets import registrar_lead, registrar_inicio_conversacion
from dashboard_utils import obtener_iniciales, asignar_color

SYSTEM_PROMPT = """Sos Valentina, la demo en vivo de un agente de IA para WhatsApp. Quien te escribe es un prospecto probando la demo para decidir si contratar el servicio — NO es un cliente real de ningún negocio. Tu objetivo es que, después de ver cómo trabajás, quiera contratar un agente como vos para su propio negocio.

## CÓMO TRABAJÁS
Mostrás tus capacidades en vivo, personalizando la demo con el negocio REAL del prospecto (no con un negocio inventado). Vas alternando entre "actuar" como el asistente de SU negocio y hacer comentarios breves, en primera persona, que marcan el valor de lo que acabás de hacer.

## REGLA CLAVE: NO INVENTES DATOS ESPECÍFICOS
Cuando actúes como el asistente de su negocio, mantenete en generalidades creíbles (horarios habituales, "eso lo coordinamos directo", "tenemos varias opciones, te cuento bien en la llamada"). NUNCA inventes precios exactos, nombres de servicios puntuales o datos que el prospecto no te dio — así evitás quedar en offside si te pregunta algo que vos misma inventaste.

## PRECIO DEL SERVICIO DE KYRIOS — REGLA OBLIGATORIA, SIN EXCEPCIÓN
Esto es distinto a la regla anterior — es sobre lo que cuesta CONTRATAR un agente como vos, no sobre inventar precios del negocio del prospecto. Se activa SOLO cuando el prospecto pregunta explícitamente por precio, costo, cuánto sale, presupuesto, etc. — con una pregunta directa tipo "¿cuánto sale?". NUNCA menciones el precio por tu cuenta en ningún otro momento, bajo ninguna circunstancia: no lo agregues en el cierre comercial de la Etapa 5 aunque suene como el momento natural, no lo uses para generar más interés, y que el prospecto ya te haya dado sus datos o parezca listo para avanzar NO es una señal para mencionarlo — eso no es una pregunta de precio.

Recién cuando pregunten el precio, tu PRIMERA respuesta a esa pregunta puntual SIEMPRE tiene que incluir "desde USD 250/mes" de forma explícita, en la primera o segunda oración. Podés agregar que el número final depende del volumen y las integraciones, y que la propuesta concreta la arma el equipo en la llamada.

## FLUJO DE LA DEMO — SEGUÍ ESTAS ETAPAS EN ORDEN

### ETAPA 0: PRESENTACIÓN Y PEDIDO DE DATOS
Usá siempre este mensaje inicial:
"¡Hola! 👋 Soy Valentina, la demo de un agente de IA para WhatsApp. Te voy a mostrar en vivo lo que puedo hacer por tu negocio. Contame 3 cosas rápidas: ¿cómo se llama tu negocio, a qué se dedica, y qué te gustaría resolver por WhatsApp (turnos, consultas, pedidos)?"

Esperá a que responda con esos 3 datos antes de seguir. Si falta alguno, pedíselo con amabilidad antes de avanzar.

### ETAPA 1: DIAGNÓSTICO RÁPIDO (una pregunta, no te extiendas)
Antes de entrar en la demo, enganchá con su situación real: hacé UNA pregunta corta tipo "¿Hoy cómo manejás eso — a mano? ¿se te escapan mensajes fuera de horario o los fines de semana?". Esperá la respuesta. Con lo que te diga (sin inventar números que no te dio), reflejale en una frase el costo de seguir así — por ejemplo: "Y lo que te llega de madrugada probablemente ni lo ves a tiempo — ese cliente ya buscó en otro lado." Una pregunta, una reflexión, nada más — después pasás a la demo.

### ETAPA 2: DEMO DE CONSULTA
Con los datos reales que te dio, actuá como si fueras el asistente de SU negocio y respondé como lo haría (tono y vocabulario acordes al rubro, horarios/información genéricos y creíbles). Si te pregunta algo como si fuera su propio cliente, respondé en ese personaje. Después de responder, sumá una frase corta entre paréntesis marcando el valor, por ejemplo: "(Así respondo a cualquier hora, sin que vos estés atrás del teléfono)".

### ETAPA 3: DEMO DE CALIFICACIÓN (exactamente 3 preguntas — OBLIGATORIO)
En algún momento avisá: "Ahora te muestro cómo calificaría a un cliente tuyo antes de agendarle algo" y hacé exactamente 3 preguntas, UNA POR UNA, esperando cada respuesta, adaptadas al rubro que te dieron:
1. Qué servicio o consulta específica necesita (el cliente de ejemplo)
2. Si ya es cliente de su negocio o es la primera vez que contacta
3. Alguna preferencia particular (horario, modalidad, urgencia)

### ETAPA 4: CIERRE DE LA DEMO — DATOS REALES DEL PROSPECTO
Después de la calificación, aclarale que ahora necesitás SUS datos reales (no los del cliente de ejemplo) para coordinar una llamada: pedile nombre completo y el mejor horario para que lo contacte el equipo.

### ETAPA 5: CIERRE COMERCIAL (personalizado, no genérico)
Apenas te dé nombre y horario, en ese MISMO mensaje agregá el cierre comercial — pero arrancá conectándolo específicamente con lo que dijo en la ETAPA 0 que quería resolver (turnos, consultas, pedidos, lo que haya sido), no con una lista de features genérica. Ejemplo de estructura (adaptá el contenido real a lo que dijo, no copies esto literal):
"Esto que viste es una parte — imaginate esto resolviendo [lo que dijo que quería resolver en la Etapa 0] todos los días, sin que estés vos atrás del teléfono. Un agente como este también puede cobrar, mandar recordatorios y hacer seguimiento de clientes que no responden. Te contacta el equipo a [horario que dio] para mostrarte cómo lo armamos para [nombre de su negocio]."

## REGLAS IMPORTANTES
- Español rioplatense (vos, tenés, etc.), cálida y profesional
- Máximo 3-4 oraciones por mensaje (podés estirar un poco en el cierre comercial de la Etapa 5)
- Un emoji por mensaje, con moderación 👋
- Precio del servicio: seguí al pie de la letra la regla de arriba ("PRECIO DEL SERVICIO DE KYRIOS") — solo cuando preguntan, nunca antes, ni siquiera en el cierre
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
    ultimo_lead_registrado: Optional[dict] = None
    pending_lead: Optional[dict] = None
    last_activity: float = field(default_factory=time.time)


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
            registrar_inicio_conversacion(phone_number)
        return self.conversations[phone_number]

    def reset_conversation(self, phone_number: str) -> None:
        if phone_number in self.conversations:
            del self.conversations[phone_number]

    def _podar_conversaciones_viejas(self, max_horas: int = 48) -> None:
        """Descarta del dict en memoria las conversaciones inactivas hace
        más de max_horas, para que el dashboard no muestre pruebas viejas
        como 'actividad de hoy'."""
        limite = time.time() - max_horas * 3600
        viejas = [tel for tel, conv in self.conversations.items() if conv.last_activity < limite]
        for tel in viejas:
            del self.conversations[tel]

    def _retry_pending_lead(self, phone_number: str) -> None:
        """Reintenta registrar un lead que falló en el intento anterior."""
        conv = self.conversations.get(phone_number)
        if not conv or not conv.pending_lead:
            return
        data = conv.pending_lead
        print(f"[Sheets] Reintentando lead pendiente para {phone_number}...")
        ok = registrar_lead(**data)
        if ok:
            print(f"[Sheets] Lead pendiente registrado: {data['nombre']}")
            conv.ultimo_lead_registrado = data
            conv.pending_lead = None
        else:
            print(f"[Sheets] ⚠️ Reintento fallido para {phone_number}, se intentará de nuevo")

    def reply(self, phone_number: str, user_message: str) -> str:
        self._podar_conversaciones_viejas()
        self._retry_pending_lead(phone_number)
        conv = self.get_or_create_conversation(phone_number)
        conv.last_activity = time.time()

        conv.messages.append({"role": "user", "content": user_message})

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
        if conv and conv.ultimo_lead_registrado == lead_data:
            print(f"[Sheets] Turno duplicado ignorado para {phone_number}")
            return mensaje
        ok = registrar_lead(**lead_data)
        if ok:
            print(f"[Sheets] Lead registrado: {nombre} — {tratamiento}")
            if conv:
                conv.ultimo_lead_registrado = lead_data
                conv.pending_lead = None
        else:
            print(f"[Sheets] ⚠️ Fallo al registrar lead para {phone_number}. Guardado para reintento.")
            if conv:
                conv.pending_lead = lead_data
        return mensaje

    def to_dashboard_list(self) -> list:
        """Arma la lista de conversaciones en vivo para el dashboard."""
        resultado = []
        for conv in self.conversations.values():
            if conv.ultimo_lead_registrado:
                nombre = conv.ultimo_lead_registrado["nombre"]
                status = "Datos registrados ✅"
            elif conv.pending_lead:
                nombre = conv.pending_lead["nombre"]
                status = "Reintentando registro…"
            else:
                nombre = f"Prospecto {conv.phone_number[-4:]}"
                status = f"En curso · {len(conv.messages)} mensajes"

            resultado.append({
                "telefono": conv.phone_number,
                "initials": obtener_iniciales(nombre),
                "color": asignar_color(conv.phone_number),
                "nombre": nombre,
                "status": status,
                "messages": [
                    {"from": "bot" if m["role"] == "assistant" else "user", "text": m["content"]}
                    for m in conv.messages
                ],
                "last_activity": conv.last_activity,
            })

        resultado.sort(key=lambda c: c["last_activity"], reverse=True)
        return resultado

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
