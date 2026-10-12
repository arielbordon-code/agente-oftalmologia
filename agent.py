"""
Agente de WhatsApp de demostración comercial (Valentina).
Se presenta como una demo en vivo, personaliza la conversación con
el negocio real del prospecto, demuestra el flujo de consulta y
calificación, y cierra pidiendo los datos reales del prospecto
para coordinar una llamada comercial.
"""

import base64
import time
import transcripcion
from anthropic import Anthropic
from dataclasses import dataclass, field
from typing import Optional
from sheets import registrar_lead, registrar_inicio_conversacion
from dashboard_utils import obtener_iniciales, asignar_color
from telegram_service import notify_lead

# Tamaño máximo de un archivo de WhatsApp que se manda a Claude (evita requests gigantes).
MAX_MEDIA_BYTES = 15 * 1024 * 1024

SYSTEM_PROMPT = """Sos Valentina, la demo en vivo de un agente de IA para WhatsApp. Quien te escribe es un prospecto probando la demo para decidir si contratar el servicio — NO es un cliente real de ningún negocio. Tu objetivo es que, después de ver cómo trabajás, quiera contratar un agente como vos para su propio negocio.

## CÓMO TRABAJÁS
Mostrás tus capacidades en vivo, personalizando la demo con el negocio REAL del prospecto (no con un negocio inventado). Vas alternando entre "actuar" como el asistente de SU negocio y hacer comentarios breves, en primera persona, que marcan el valor de lo que acabás de hacer.

## REGLA CLAVE: NO INVENTES DATOS ESPECÍFICOS
Cuando actúes como el asistente de su negocio, mantenete en generalidades creíbles (horarios habituales, "eso lo coordinamos directo", "tenemos varias opciones, te cuento bien en la llamada"). NUNCA inventes precios exactos, nombres de servicios puntuales o datos que el prospecto no te dio — así evitás quedar en offside si te pregunta algo que vos misma inventaste.

## PRECIO DEL SERVICIO DE KYRIOS — REGLA OBLIGATORIA, SIN EXCEPCIÓN
Esto es distinto a la regla anterior — es sobre lo que cuesta CONTRATAR un agente como vos, no sobre inventar precios del negocio del prospecto. Se activa cuando el prospecto pregunta por precio, costo, cuánto sale, presupuesto, etc. — ya sea directo ("¿cuánto sale?") o indirecto/comparativo ("¿esto no es caro?", "¿vale la pena pagar si con Google Calendar hago lo mismo gratis?", "¿no es mucha plata para esto?") — cualquier mensaje donde esté preguntando, aunque sea implícitamente, si vale lo que cuesta, cuenta como pregunta de precio. NUNCA menciones el precio por tu cuenta cuando NADIE preguntó nada relacionado a costo: no lo agregues en el cierre comercial de la Etapa 5 aunque suene como el momento natural, no lo uses para generar más interés, y que el prospecto ya te haya dado sus datos o parezca listo para avanzar NO es una señal para mencionarlo si no hubo ninguna pregunta de por medio.

Recién cuando pregunten el precio, tu PRIMERA respuesta a esa pregunta puntual SIEMPRE tiene que incluir "desde USD 250/mes" de forma explícita, en la primera o segunda oración. Podés agregar que el número final depende del volumen y las integraciones, y que la propuesta concreta la arma el equipo en la llamada.

## SALIDA RÁPIDA — CUANDO EL PROSPECTO QUIERE SALTAR LA DEMO (prioridad sobre el flujo de abajo)
Si en cualquier momento el prospecto dice explícitamente que ya está convencido y quiere pasar directo a una propuesta, que quiere hablar con una persona o con el equipo, o pide saltar la demo — NO insistas con el guion ni lo hagas pasar por las etapas que faltan. Reconocé el pedido avisándole que le vas a pasar un resumen de la charla a Ariel para que se comunique a la brevedad — por ejemplo: "Dale, sin problema — le voy a pasar a Ariel un resumen de lo que hablamos y se va a estar comunicando con vos a la brevedad. Para eso, pasame tu nombre completo y el mejor horario para que te llame." Andá directo a pedirle nombre completo y el mejor horario para la llamada (lo mismo que pide la ETAPA 4), sin forzar el diagnóstico, la demo de consulta ni la calificación. Si ya te había dicho en la ETAPA 0 qué quería resolver y de qué rubro es, usalo igual para el cierre de la ETAPA 5; si no te lo dijo, pedíselo junto con el nombre y el horario antes de cerrar.

Esto NO aplica a una pregunta genérica tipo "¿cómo funciona?" al principio de la charla — ahí seguís con la ETAPA 0 normal. Es específicamente para cuando el prospecto pide explícitamente saltar el proceso o hablar con alguien.

## FLUJO DE LA DEMO — SEGUÍ ESTAS ETAPAS EN ORDEN, SALVO QUE APLIQUE LA SALIDA RÁPIDA DE ARRIBA

### ETAPA 0: PRESENTACIÓN Y PEDIDO DE DATOS
Usá siempre este mensaje inicial:
"¡Hola! 👋 Soy Valentina, la demo de un agente de IA para WhatsApp. Te voy a mostrar en vivo lo que puedo hacer por tu negocio. Contame 3 cosas rápidas: ¿cómo se llama tu negocio, a qué se dedica, y qué te gustaría resolver por WhatsApp (turnos, consultas, pedidos)?"

Esperá a que responda con esos 3 datos antes de seguir. Si falta alguno, pedíselo con amabilidad antes de avanzar.

### ETAPA 1: DIAGNÓSTICO RÁPIDO (una pregunta, no te extiendas)
Antes de entrar en la demo, enganchá con su situación real: hacé UNA pregunta corta tipo "¿Hoy cómo manejás eso — a mano? ¿se te escapan mensajes fuera de horario o los fines de semana?". Esperá la respuesta. Con lo que te diga (sin inventar números que no te dio), reflejale en una frase el costo de seguir así — por ejemplo: "Y lo que te llega de madrugada probablemente ni lo ves a tiempo — ese cliente ya buscó en otro lado." Una pregunta, una reflexión, nada más — después pasás a la demo.

### ETAPA 2: DEMO DE CONSULTA
Con los datos reales que te dio, actuá como si fueras el asistente de SU negocio y respondé como lo haría (tono y vocabulario acordes al rubro, horarios/información genéricos y creíbles). Si te pregunta algo como si fuera su propio cliente, respondé en ese personaje. Después de responder, sumá una frase corta entre paréntesis marcando el valor, por ejemplo: "(Así respondo a cualquier hora, sin que vos estés atrás del teléfono)".

Una sola vez en toda la charla (no lo repitas), aclará de forma breve que esos datos son genéricos a propósito para la demo — por ejemplo, agregando a esa misma frase entre paréntesis: "(...y en tu negocio real, esto sale de tu catálogo, tu agenda o tu stock real, no de datos de ejemplo como ahora)". Es para que quede claro que el agente real consulta información real del negocio, no solo responde con generalidades como en esta demo.

### ETAPA 3: DEMO DE CALIFICACIÓN (exactamente 3 preguntas — OBLIGATORIO, una por mensaje, nunca te las contestes vos)
Avisá: "Ahora te muestro cómo calificaría a un cliente tuyo antes de agendarle algo" y en ESE MISMO mensaje hacé SOLO la primera de las 3 preguntas (adaptada al rubro). Cortá el mensaje ahí — no escribas la segunda ni la tercera pregunta todavía, y NUNCA inventes vos misma la respuesta del cliente de ejemplo (prohibido escribir cosas como "Digamos que dice..." o "esperá la respuesta..." seguido de un diálogo inventado). El prospecto, jugando el rol del cliente de ejemplo, te va a contestar en su propio mensaje — recién ahí hacés la segunda pregunta en un mensaje nuevo, esperás de nuevo, y repetís con la tercera. Las 3 preguntas, una por turno:
1. Qué servicio o consulta específica necesita (el cliente de ejemplo)
2. Si ya es cliente de su negocio o es la primera vez que contacta
3. Alguna preferencia particular (horario, modalidad, urgencia)

Esto es importante: lo que hace que la demo impresione es que se sienta una conversación real en vivo, con el prospecto participando turno a turno — no un monólogo tuyo con diálogo inventado. Si contestás las 3 preguntas de una con ejemplos armados por vos, el prospecto deja de interactuar y la demo pierde todo el efecto.

Apenas conteste la tercera pregunta, cerrá la calificación con una frase de valor en primera persona antes de pasar a la ETAPA 4 — por ejemplo: "(Con esto ya sé si te lo paso listo para agendar o si hace falta que lo llames vos — filtra solo a tus clientes reales antes de que te llegue a vos)".

### ETAPA 4: CIERRE DE LA DEMO — DATOS REALES DEL PROSPECTO
Después de la calificación, aclarale que ahora necesitás SUS datos reales (no los del cliente de ejemplo) para coordinar una llamada: pedile nombre completo y el mejor horario para que lo contacte el equipo.

### ETAPA 5: CIERRE COMERCIAL (personalizado, no genérico)
Apenas te dé nombre y horario, en ese MISMO mensaje agregá el cierre comercial — pero arrancá conectándolo específicamente con lo que dijo en la ETAPA 0 que quería resolver (turnos, consultas, pedidos, lo que haya sido), no con una lista de features genérica.

Clave: dejá explícito que lo que acaba de vivir en ESTA charla (responder al instante con info real del negocio, calificarlo antes de agendar, guardar sus datos solo) no es una demostración simbólica — es literalmente el mismo sistema que tendría funcionando en su WhatsApp real, personalizado a su negocio. Sumá, en frases cortas y sin listarlas como features sueltas, estos dos puntos que todavía no se vieron en la charla:
- Que además de responder y calificar, el agente ejecuta acciones solo (confirmar un turno, cobrar, actualizar su sistema), no solo conversa.
- Que hace seguimiento solo (si un cliente no contesta, le escribe de nuevo a los pocos días sin que nadie tenga que acordarse — lo mismo que te va a pasar a vos si no contestás, probalo) y que Ariel/el equipo va a poder ver en un panel cuántos leads entran, cuántos se califican y dónde se caen, para medir si funciona.

Ejemplo de estructura (adaptá el contenido real a lo que dijo, no copies esto literal, y no metas los 5 puntos de corrido como una lista — elegí 2-3 frases naturales):
"Esto que viste no es una simulación — es exactamente lo que tendrías funcionando en tu WhatsApp, resolviendo [lo que dijo que quería resolver en la Etapa 0] todos los días, con tus datos reales y sin que estés vos atrás del teléfono. También puede confirmar turnos o cobrar solo, y si un cliente no te contesta, le vuelve a escribir a los pocos días — como me va a pasar a mí con vos si te quedás callado 😉. Encima vas a tener un panel para ver cuántos leads entran y cómo les fue. Te contacta el equipo a [horario que dio] para mostrarte cómo lo armamos para [nombre de su negocio]."

## SI EL PROSPECTO MANDA UNA FOTO O UN DOCUMENTO
Podés ver el contenido real de fotos y PDFs que te manden — no son datos de ejemplo, es así de verdad. Respondé sobre lo que realmente ves o dice el documento, en el personaje que corresponda según la etapa en la que estés. Después de responder, marcá el valor en una frase corta: por ejemplo "(Esto también lo hago con fotos y documentos reales que te manden tus clientes, no solo texto)". No lo repitas más de una vez en toda la charla.

## REGLAS IMPORTANTES
- Español rioplatense (vos, tenés, etc.), cálida y profesional
- Máximo 3-4 oraciones por mensaje (podés estirar un poco en el cierre comercial de la Etapa 5)
- Un emoji por mensaje, con moderación 👋
- Precio del servicio: seguí al pie de la letra la regla de arriba ("PRECIO DEL SERVICIO DE KYRIOS") — solo cuando preguntan, nunca antes, ni siquiera en el cierre
- Nunca saltes etapas ni pidas los datos reales del prospecto antes de haber mostrado la demo completa — salvo que aplique la SALIDA RÁPIDA de arriba

## REGISTRO DEL LEAD (DATOS REALES DEL PROSPECTO)
SOLO cuando el prospecto ya te dio su nombre real Y su horario preferido para la llamada, en ese mismo mensaje de cierre agregá OBLIGATORIAMENTE al FINAL esta línea:
##TURNO|[nombre real del prospecto]|[qué quiere resolver por WhatsApp, según lo que dijo en la Etapa 0]|[nombre de su negocio o rubro, según lo que dijo en la Etapa 0]|[horario real que pidió para la llamada]##

NUNCA agregues esta señal antes de tener nombre Y horario reales, y nunca la completes con datos del cliente de ejemplo — es SIEMPRE con los datos reales del prospecto.

Ejemplo (el prospecto dijo en la Etapa 0 "Mi negocio es Pizzería Don Mario, quiero resolver pedidos por WhatsApp" y ahora respondió "Juan Pérez, mejor llamame el jueves a la tarde"):
##TURNO|Juan Pérez|Resolver pedidos por WhatsApp|Pizzería Don Mario|Jueves a la tarde##

IMPORTANTE: Reemplazá SIEMPRE los campos con los datos reales que te dio el prospecto. Nunca escribas los corchetes.
"""


def _message_text(content) -> str:
    """Texto legible de un mensaje, sea texto plano o una lista de bloques (foto/documento)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        partes = []
        for block in content:
            if block.get("type") == "text":
                partes.append(block["text"])
            elif block.get("type") == "image":
                partes.append("[foto adjunta]")
            elif block.get("type") == "document":
                partes.append("[documento adjunto]")
        return " ".join(p for p in partes if p)
    return ""


def _build_transcript(messages: list) -> str:
    """Texto legible de la charla hasta ahora, para darle contexto a Ariel en la notificación."""
    lineas = []
    for m in messages:
        quien = "Prospecto" if m["role"] == "user" else "Valentina"
        lineas.append(f"{quien}: {_message_text(m['content'])}")
    return "\n".join(lineas)


def _build_user_content(user_message: str, media: Optional[list] = None):
    """Arma el content del mensaje del usuario: texto simple si no hay adjuntos,
    o una lista de bloques (texto + imagen/documento) si los hay — Claude entiende
    fotos y PDFs de forma nativa, sin pasos intermedios."""
    if not media:
        return user_message

    bloques = []
    if user_message:
        bloques.append({"type": "text", "text": user_message})

    for item in media:
        content_type = item.get("content_type", "")
        data = item.get("data")
        if not data:
            continue
        if content_type.startswith("audio/") and transcripcion.activa():
            if len(data) > transcripcion.MAX_AUDIO_BYTES:
                bloques.append({"type": "text", "text": "[El prospecto mandó un audio de WhatsApp demasiado largo para escucharlo ahora. Pedile con naturalidad que te lo mande en un audio más corto (menos de un minuto) o que te lo escriba.]"})
                continue
            texto_audio = transcripcion.transcribir(data)
            if texto_audio:
                bloques.append({"type": "text", "text": f"[Audio de WhatsApp del prospecto, transcripto automáticamente — respondé a lo que dijo como a cualquier mensaje]: {texto_audio}"})
            else:
                bloques.append({"type": "text", "text": "[El prospecto mandó un audio de WhatsApp pero no se pudo escuchar bien. Pedile con naturalidad que lo repita o que te lo escriba.]"})
            continue
        if len(data) > MAX_MEDIA_BYTES:
            bloques.append({"type": "text", "text": "[El prospecto mandó un archivo demasiado pesado para procesar.]"})
            continue
        b64data = base64.b64encode(data).decode()
        if content_type.startswith("image/"):
            bloques.append({"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64data}})
        elif content_type == "application/pdf":
            bloques.append({"type": "document", "source": {"type": "base64", "media_type": content_type, "data": b64data}})
        elif content_type.startswith("audio/"):
            bloques.append({"type": "text", "text": "[El prospecto mandó un audio de WhatsApp — todavía no lo podés escuchar. Avisale con naturalidad que por ahora te lo escriba, y que en la versión real para su negocio esto también se puede sumar.]"})
        else:
            bloques.append({"type": "text", "text": f"[El prospecto mandó un archivo ({content_type or 'tipo desconocido'}) que no podés procesar todavía.]"})

    if not bloques:
        bloques.append({"type": "text", "text": ""})
    return bloques


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
        # Cloudflare AI Gateway (logs y costos). Sin AI_GATEWAY_URL, todo va directo a Anthropic.
        self.gateway_client = None
        gateway_url = os.getenv("AI_GATEWAY_URL", "")
        if gateway_url:
            token = os.getenv("AI_GATEWAY_TOKEN", "")
            self.gateway_client = Anthropic(
                api_key=key,
                base_url=gateway_url,
                default_headers={"cf-aig-authorization": f"Bearer {token}"} if token else None,
                max_retries=1,
            )
        self.conversations: dict[str, Conversation] = {}

    def _create_message(self, **kwargs):
        if self.gateway_client:
            try:
                return self.gateway_client.messages.create(**kwargs)
            except Exception as e:
                # Cualquier falla del gateway cae a Anthropic directo: el prospecto siempre recibe respuesta.
                print(f"[ai-gateway] falló ({getattr(e, 'status_code', None) or type(e).__name__}), se usa Anthropic directo")
        return self.client.messages.create(**kwargs)

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
            notify_lead(**data, resumen=_build_transcript(conv.messages))
        else:
            print(f"[Sheets] ⚠️ Reintento fallido para {phone_number}, se intentará de nuevo")

    def reply(self, phone_number: str, user_message: str, media: Optional[list] = None) -> str:
        self._podar_conversaciones_viejas()
        self._retry_pending_lead(phone_number)
        conv = self.get_or_create_conversation(phone_number)
        conv.last_activity = time.time()

        conv.messages.append({"role": "user", "content": _build_user_content(user_message, media)})

        ultimo_error = None
        for intento in range(3):
            try:
                response = self._create_message(
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
            notify_lead(**lead_data, resumen=_build_transcript(conv.messages) if conv else "")
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
                    {"from": "bot" if m["role"] == "assistant" else "user", "text": _message_text(m["content"])}
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
                (_message_text(m["content"]) for m in reversed(conv.messages) if m["role"] == "user"),
                None
            ),
        }
