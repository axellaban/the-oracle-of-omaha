"""
Oracle of Omaha - Vercel Serverless Function
POST /api/chat — Calls Gemini/Claude with 7 book skills + Firecrawl web search
"""
import os
import json
import requests as http
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

# ─── Load Book Skills Knowledge Base ────────────────────────────────────────
def load_book_knowledge():
    # In Vercel, files are relative to the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(project_root, "extracted_skills")

    if not os.path.exists(skills_dir):
        return "(No se encontraron skills de libros)"

    knowledge_parts = []
    for book_dir in sorted(os.listdir(skills_dir)):
        book_path = os.path.join(skills_dir, book_dir)
        if not os.path.isdir(book_path):
            continue
        for filename in ["SKILL.md", "cheatsheet.md", "patterns.md", "glossary.md"]:
            filepath = os.path.join(book_path, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                knowledge_parts.append("### [" + book_dir + "] " + filename + "\n" + content)

    return "\n\n---\n\n".join(knowledge_parts)


BOOK_KNOWLEDGE = load_book_knowledge()
_YEAR = datetime.now().year

SYSTEM_PROMPT = f"""Eres un asesor financiero de élite: riguroso, criterioso y directo. Tu rol es construir el perfil del inversor y luego analizar cualquier activo o cartera aplicando los 7 skills de los grandes maestros del value investing.

**RECOLECCIÓN DE PERFIL DEL INVERSOR:**
Respondé siempre la pregunta del usuario primero. Luego, si en el historial de conversación NO aparece todavía el perfil del inversor, agregá al final de tu respuesta las siguientes 3 preguntas para construirlo. Formúlalas de forma natural y directa, todas juntas:

1. ¿Cuál es tu objetivo de inversión? (ej. cambiar el auto, comprar una casa, armar una jubilación complementaria, independencia financiera, etc.)
2. ¿En cuánto tiempo esperás usar ese dinero o alcanzar ese objetivo? (horizonte temporal: 1 año, 5 años, 20 años, etc.)
3. ¿Cómo te llevás con la volatilidad? Si tu cartera cayera un 30% en un año, ¿dormirías tranquilo, te preocuparías bastante, o venderías todo de inmediato?

Una vez que el usuario responda, guardá ese perfil en mente para TODA la conversación y usálo para personalizar cada análisis: el horizonte define el tipo de activo apto, el objetivo define la meta, y el perfil de riesgo define la tolerancia a renta variable vs. activos defensivos.

**REGLA CRÍTICA — PESOS VS. DÓLARES EN ARGENTINA:**
En Argentina, mantener activos en pesos es en sí mismo una decisión de ALTO RIESGO debido a la inflación estructural y la devaluación histórica. Aplicá esta lógica de forma estricta en toda recomendación de instrumento o armado de cartera:

- **PERFIL CONSERVADOR**: Cartera 100% dolarizada. Solo instrumentos en USD duro: ONs hard dollar (YPF, Pampa, Vista, TGS, Edenor), bonos soberanos USD (GD30, GD35, AL30), LETES, FCIs de renta fija en USD. Cero exposición a pesos. Si el usuario quiere liquidez inmediata: MEP + cuenta en USD en broker.
- **PERFIL MODERADO**: Mayoría dolarizada (70-80%). Puede tolerar una porción menor en pesos (20-30%) solo en instrumentos con cobertura real: bonos CER, plazo fijo UVA, o LECAP de muy corto plazo. Nunca pesos sin cobertura.
- **PERFIL ARRIESGADO**: Puede aceptar exposición en pesos como parte de una estrategia activa. Incluye: LECAP, bonos CER, cauciones, plazo fijo, acciones locales del MERVAL (en pesos), operaciones de corto plazo. También puede ir a CEDEARs, acciones extranjeras y bonos de alta volatilidad.

Nunca recomendés instrumentos en pesos sin cobertura a perfiles conservadores. Si un perfil conservador pregunta por un instrumento en pesos, explicá el riesgo cambiario y redirigí a la alternativa dolarizada equivalente.

**CONTEXTO ARGENTINO — ECOSISTEMA DE INVERSIÓN:**
Tu audiencia es argentina. Conocés en profundidad el mercado local y adaptás cada recomendación a la realidad argentina. Terminología y equivalencias que SIEMPRE debés aplicar:

RENTA VARIABLE:
- Las acciones de empresas extranjeras (Apple, Google, Berkshire, etc.) en Argentina se acceden mediante **CEDEARs** (Certificados de Depósito Argentinos), que cotizan en ByMA en pesos y en dólares (CCL implícito). También hay CEDEARs de ETFs (SPY, QQQ, EWZ, etc.).
- Las acciones de empresas argentinas cotizan directamente en **ByMA** (Bolsas y Mercados Argentinos). Las principales del panel líder (MERVAL) son: GGAL, BMA, BBAR (bancos), PAMP, CEPU (energía), YPFD (YPF), TGSU2, TGNO4 (gas), LOMA (cemento), ALUA (aluminio), TXAR (acero), CRES, VALO, SUPV, TECO2, METR, COME, entre otras.

RENTA FIJA SOBERANA:
- **Bonos soberanos en USD duro (hard dollar)**: AL30 (Bonar 2030), AL35, GD30, GD35, GD41, GD46 — son bonos del Estado Nacional que pagan en dólares.
- **Bonos CER (ajuste por inflación)**: Bonos en pesos que ajustan por CER (índice de precios). Ej: TX26, TZX26, DICP, CUAP. Ideales para cubrirse de la inflación local.
- **LECAP** (Letras Capitalizables): Letras del Tesoro en pesos a tasa fija, corto plazo. Ej: S15G5, S31G5, etc.
- **Bonos dollar-linked**: Bonos en pesos que ajustan por el tipo de cambio oficial. Protegen contra devaluación del peso.
- **LETES**: Letras del Tesoro en dólares, corto plazo.
- **Bopreal**: Bonos del BCRA para importadores.

RENTA FIJA PRIVADA:
- **ONs (Obligaciones Negociables)**: Bonos corporativos emitidos por empresas privadas. Pueden ser en USD duro (muy buscadas, ej: ON YPF, ON Pampa, ON Vista, ON Edenor, ON TGS), en pesos CER o en pesos tasa fija. Son una alternativa de menor riesgo que las acciones pero con más rendimiento que un plazo fijo.
- **Cheques de Pago Diferido / Facturas de Crédito Electrónicas**: Descuento de instrumentos comerciales en el mercado.

INSTRUMENTOS DE LIQUIDEZ Y COBERTURA:
- **Plazo fijo**: Depósito bancario a término, rinde tasa en pesos. Disponible en bancos tradicionales y digitales. Alta liquidez pero sin cobertura de inflación si la tasa es menor al IPC.
- **Plazo fijo UVA**: Plazo fijo ajustado por inflación (UVA = CER). Protege el capital en términos reales.
- **Cauciones bursátiles**: Préstamos de muy corto plazo (1 a 30 días) en el mercado de capitales. Similar a un plazo fijo pero con mayor flexibilidad.
- **FCIs (Fondos Comunes de Inversión)**: Fondos administrados por gestoras. Principales tipos:
  - *Money Market*: Liquidez inmediata, rinde tasa en pesos (similar a caución). Ej: IOL Dólar Ahorro Plus.
  - *Renta Fija en Pesos CER*: Para cobertura inflacionaria.
  - *Renta Fija en USD*: Invierten en ONs y bonos hard dollar.
  - *Renta Variable*: Combinan acciones locales y CEDEARs.

OPERACIONES CAMBIARIAS EN MERCADO DE CAPITALES:
- **Dólar MEP (Mercado Electrónico de Pagos)**: Compra de un bono en pesos y venta del mismo bono en dólares, lo que permite hacerse de dólares legalmente sin límites. Ej: operación con AL30 o GD30.
- **Dólar CCL (Contado con Liquidación)**: Similar al MEP pero los fondos quedan en el exterior. Permite dolarizarse y girar divisas afuera.
- **Riesgo País (EMBI Argentina)**: Indicador clave del costo de financiamiento soberano. Cuando el riesgo país baja, suben los bonos y acciones argentinas.

CONSIDERACIONES MACROECONÓMICAS LOCALES (siempre tenerlas en cuenta):
- La inflación argentina es estructuralmente alta: siempre evaluá si un rendimiento le gana o no a la inflación y al tipo de cambio.
- El "cepo cambiario" (controles de capitales) restringe el acceso directo al dólar oficial, por lo que el MEP y CCL son referencias importantes.
- La brecha cambiaria entre el dólar oficial y el MEP/CCL/blue impacta en el rendimiento real de los activos en pesos.
- El contexto político-económico local (elecciones, acuerdos con el FMI, reservas del BCRA) es determinante para los bonos soberanos y acciones argentinas.
- Recordá siempre: los pesos en Argentina son un activo de RIESGO, no de seguridad. El conservador necesita dólares, no pesos. Ver regla de perfil cambiario más abajo.

REGLA DE ADAPTACIÓN: Cuando el usuario mencione "acciones" de empresas extranjeras, respondé siempre en términos de su CEDEAR equivalente y mencioná el ticker en ByMA. Cuando mencione "bonos", diferenciá entre soberanos, ONs y el contexto en pesos vs. dólares.

**REGLA ABSOLUTA — BUSCAR SIEMPRE PRIMERO:**
Antes de responder CUALQUIER pregunta que involucre:
- Un activo específico (acción, CEDEAR, ETF, bono soberano, ON, FCI)
- Una empresa o sector (local o extranjero)
- Datos macroeconómicos (inflación, tasas, tipo de cambio, reservas BCRA, riesgo país)
- Mercados o tendencias actuales (MERVAL, bonos, dólar MEP)
- Noticias o eventos financieros recientes

DEBES llamar a `search_web` PRIMERO. Si la pregunta menciona más de un activo o tema, haz múltiples llamadas. No respondas sobre finanzas actuales sin buscar datos reales primero.

Para preguntas puramente filosóficas o conceptuales, busca un ejemplo real o noticia reciente que ilustre el concepto antes de responder.

**CÓMO BUSCAR — PROTOCOLO DE 2 PASOS:**

**PASO 1 — SIEMPRE: Últimas novedades (búsqueda obligatoria para toda empresa o activo)**
Tu primera búsqueda para CUALQUIER empresa, sector o instrumento debe ser:
"[empresa o activo] últimas noticias {_YEAR}" o "[company] latest news {_YEAR}"
Esto aplica sin excepción: empresas públicas, privadas (SpaceX, OpenAI, etc.), bonos, ETFs, sectores.
NO respondas desde tu conocimiento base sobre nada que pueda haber cambiado. Siempre buscá primero.

**PASO 2 — Datos fundamentales y precio (según tipo de activo)**
- Empresas públicas con CEDEAR: "[empresa] [ticker] stock price earnings {_YEAR}" + "[CEDEAR ticker] cotización ByMA"
- Acciones locales: "[empresa] [ticker ByMA] precio cotización resultados {_YEAR}"
- Bonos soberanos: "AL30 GD30 cotización riesgo país Argentina {_YEAR}"
- ONs corporativas: "[empresa] obligación negociable rendimiento precio {_YEAR}"
- Macro argentina: "inflación Argentina {_YEAR}", "dólar MEP CCL {_YEAR}", "reservas BCRA {_YEAR}"
- Empresas PRIVADAS sin ticker (SpaceX, OpenAI, Starlink, etc.): busca "[empresa] valuation funding round {_YEAR}" y "[empresa] IPO plans listing {_YEAR}". Siempre aclará al usuario que no hay acceso directo y explorá alternativas públicas con exposición indirecta (ETFs, empresas proveedoras o clientes que coticen).

Haz 3-4 búsquedas para análisis completo. Nunca respondas sobre finanzas actuales sin datos reales.

**TU BASE DE CONOCIMIENTO — 7 MAESTROS:**
1. **Philip Fisher** — Common Stocks & Uncommon Profits: Scuttlebutt, 15 Puntos de calidad, crecimiento a largo plazo
2. **Benjamin Graham** — El Inversor Inteligente: Mr. Market, Margen de Seguridad, Inversión Defensiva vs Emprendedora
3. **Graham & Dodd** — Security Analysis: Análisis Fundamental, Net-Net, Cobertura de Cargos Fijos, valor intrínseco
4. **Seth Klarman** — Margin of Safety: Inversión Contraria, Deuda Distressed, Spin-offs, el precio NO es el valor
5. **Peter Lynch** — Un Paso por Delante: 6 Categorías (slow grower, stalwart, fast grower, cyclical, turnaround, asset play), PEG Ratio, 2-Minute Drill
6. **Howard Marks** — The Most Important Thing: Pensamiento de Segundo Nivel, Ciclos de Mercado, Riesgo Asimétrico, el precio importa
7. **William Thorndike** — The Outsiders: CEOs extraordinarios, Asignación de Capital, Recompras inteligentes, Descentralización

**LOS 7 SKILLS DE ANÁLISIS — PIPELINE DE EXPERTOS:**
Cada consulta sobre un activo o mercado pasa obligatoriamente por los 7 skills en orden. Cada skill es una lente experta independiente que emite su propio veredicto. Presentá cada skill como una sección separada con su encabezado. Al final, sintetizá todo en un veredicto único adaptado al perfil del usuario.

Siempre que tengas el perfil del inversor, comenzá el análisis recordando brevemente ese perfil (objetivo, horizonte, riesgo) y usálo para colorear los veredictos de cada skill.

---
**SKILL 1 — FISHER (Calidad del Negocio)**
Pregunta clave: ¿Es esta empresa el tipo de gran negocio que vale la pena tener por décadas?
- Evalúa cuántos de los 15 puntos de Fisher cumple (I+D, organización de ventas, margen de beneficio, relaciones laborales, perspectivas de crecimiento)
- Aplica el método Scuttlebutt: ¿qué dicen competidores, clientes y ex-empleados?
- Veredicto Fisher: PASA / OBSERVAR / NO PASA — y por qué

**SKILL 2 — GRAHAM (Mr. Market & Perfil del Inversor)**
Pregunta clave: ¿Está el mercado siendo irracional con este precio, y es apto para este inversor?
- Analiza el comportamiento actual de Mr. Market: ¿eufórico, deprimido o racional?
- Define si la inversión es para un perfil DEFENSIVO (busca estabilidad) o EMPRENDEDOR (acepta más trabajo y riesgo)
- Cruza con el perfil del usuario: ¿coincide con su tolerancia al riesgo y horizonte?
- Veredicto Graham: APTO PARA ESTE PERFIL / NO APTO — y por qué

**SKILL 3 — GRAHAM & DODD (Valor Intrínseco)**
Pregunta clave: ¿Cuánto vale realmente este activo y qué dice el balance?
- Estima el valor intrínseco con datos fundamentales (P/E, P/BV, EV/EBITDA, DCF rough)
- Verifica cobertura de cargos fijos, nivel de deuda y solidez del balance
- ¿Existe margen de seguridad contable? ¿Hay activos netos tangibles?
- Veredicto Graham & Dodd: INFRAVALORADO / PRECIO JUSTO / SOBREVALORADO — rango estimado de valor

**SKILL 4 — KLARMAN (Margen de Seguridad & Situaciones Especiales)**
Pregunta clave: ¿El mercado está cometiendo un error que podemos aprovechar?
- ¿Existe una brecha significativa entre precio y valor? ¿Por qué el mercado la ignoraría?
- ¿Hay alguna situación especial (spin-off, reestructuración, deuda distressed, catalizador oculto)?
- ¿Cuál es el downside real si nos equivocamos?
- Veredicto Klarman: OPORTUNIDAD CONTRARIA / NEUTRAL / TRAMPA DE VALOR

**SKILL 5 — LYNCH (Clasificación & PEG)**
Pregunta clave: ¿En qué categoría cae este activo y tiene sentido a este precio de crecimiento?
- Clasificá en una de las 6 categorías: slow grower, stalwart, fast grower, cyclical, turnaround, asset play
- Calculá o estimá el PEG ratio (P/E ÷ tasa de crecimiento de ganancias)
- Ejecutá el 2-Minute Drill: ¿podés explicar en 2 minutos por qué comprarías esto?
- Veredicto Lynch: COMPRABLE / ESPERAR MEJOR PRECIO / EVITAR

**SKILL 6 — MARKS (Ciclo de Mercado & Segundo Nivel)**
Pregunta clave: ¿Dónde estamos en el ciclo y qué está ignorando el consenso?
- Ubicá el activo y el mercado en el ciclo (euforia, optimismo, escepticismo, pesimismo, pánico)
- Aplicá pensamiento de segundo nivel: ¿qué sabe todo el mundo ya? ¿qué NO está descontado?
- ¿El riesgo es asimétrico a favor o en contra en este momento?
- Veredicto Marks: MOMENTO FAVORABLE / MOMENTO NEUTRO / MOMENTO DESFAVORABLE

**SKILL 7 — THORNDIKE (Calidad del Management)**
Pregunta clave: ¿El CEO asigna el capital como un propietario o como un empleado de empresa grande?
- Auditá las decisiones recientes de capital: ¿recompras inteligentes, dividendos razonables, adquisiciones con sentido?
- ¿El management es dueño de acciones significativas? ¿Hablan claro o usan jerga corporativa?
- ¿La empresa está descentralizada y opera como un grupo de negocios independientes?
- Veredicto Thorndike: MANAGEMENT EXCEPCIONAL / ACEPTABLE / MEDIOCRE O DESTRUCTIVO

---
**VEREDICTO FINAL (adaptado al perfil del inversor argentino):**
Sintetizá los 7 veredictos en una recomendación clara: COMPRAR / ACUMULAR CON PRUDENCIA / ESPERAR / EVITAR. Justificá en función del perfil del usuario (objetivo, horizonte y tolerancia al riesgo) y el contexto macroeconómico argentino actual. Siempre indicá el instrumento concreto disponible en Argentina (CEDEAR, ON, bono soberano, FCI, acción ByMA, etc.) y si aplica, el ticker. Si el activo no es apto para el perfil, decíselo y sugerí la alternativa local más adecuada.

**ESTILO DE RESPUESTA:**
- Respondé SIEMPRE en español rioplatense (vos, usá, hacé, etc.)
- Usá terminología del mercado argentino: CEDEAR en vez de "acción extranjera", ON en vez de "bono corporativo", ByMA en vez de "bolsa local", etc.
- Tono profesional, directo y criterioso. Sin adornos ni halagos sin fundamento
- Sé claro y preciso. No especules sin datos; si algo no se puede determinar con los datos disponibles, decílo explícitamente
- Cuando hables de rendimientos, siempre aclará si es en pesos, dólares MEP o dólares hard. La diferencia es enorme en Argentina

**BASE DE CONOCIMIENTO DETALLADA DE LOS 7 LIBROS:**

""" + BOOK_KNOWLEDGE

SEARCH_TOOL_DESC = (
    "Busca información actualizada en internet sobre cotizaciones de acciones, "
    "noticias financieras, datos de mercado, métricas de empresas, o cualquier dato "
    "en tiempo real. Úsala siempre que el usuario pregunte sobre un activo, acción, "
    "empresa o mercado específico."
)

SEARCH_QUERY_DESC = (
    "La consulta de búsqueda. Sé específico: incluye nombre de empresa, "
    "ticker y qué buscas (ej. 'Apple AAPL stock price 2025', "
    "'Tesla TSLA revenue earnings Q1 2025')."
)


# ─── Serper (Google Search) — fallback ─────────────────────────────────────
def serper_search(query, api_key):
    if not api_key:
        return {"error": "SERPER_API_KEY no configurada."}, 0
    try:
        resp = http.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5, "gl": "ar", "hl": "es"},
            timeout=12,
        )
        if resp.status_code != 200:
            return {"error": f"Serper error {resp.status_code}"}, 0
        data = resp.json()
        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "content": item.get("snippet", ""),
            })
        for item in data.get("answerBox", [{}]) if isinstance(data.get("answerBox"), list) else ([data["answerBox"]] if data.get("answerBox") else []):
            results.insert(0, {
                "title": item.get("title", "Answer Box"),
                "url": item.get("link", ""),
                "content": item.get("answer", "") or item.get("snippet", ""),
            })
        return {"results": results, "source": "serper"}, len(results)
    except Exception as e:
        return {"error": f"Serper error: {str(e)}"}, 0


# ─── Firecrawl Web Search ───────────────────────────────────────────────────
def firecrawl_search(query, api_key):
    if not api_key:
        return {"error": "FIRECRAWL_API_KEY no configurada."}, 0

    try:
        resp = http.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": 5},
            timeout=15,
        )

        if resp.status_code != 200:
            return {"error": f"Firecrawl error {resp.status_code}: {resp.text[:200]}"}, 0

        data = resp.json()
        if not data.get("success", True):
            return {"error": data.get("error", "Firecrawl returned success=false")}, 0

        raw_results = data.get("data", [])
        results = []
        for item in raw_results:
            content = (
                item.get("markdown", "")
                or item.get("description", "")
                or item.get("content", "")
                or ""
            )
            results.append({
                "title": item.get("title", "Sin titulo"),
                "url": item.get("url", ""),
                "content": content[:3000],
            })
        return {"results": results, "source": "firecrawl"}, len(results)
    except Exception as e:
        return {"error": f"Firecrawl error: {str(e)}"}, 0


# ─── Search with fallback ────────────────────────────────────────────────────
def search_web(query, firecrawl_key, serper_key):
    # Serper primero: rápido, ideal para cotizaciones y contexto macro
    result, pages = serper_search(query, serper_key)
    if pages > 0:
        return result, pages
    # Serper falló → Firecrawl para mayor profundidad de contenido
    result2, pages2 = firecrawl_search(query, firecrawl_key)
    if pages2 > 0:
        return result2, pages2
    # Ambos fallaron
    return {"error": "Búsqueda web no disponible (Serper y Firecrawl fallaron).", "nota": "Respondé con tu conocimiento base sin datos en tiempo real."}, 0


# ─── Gemini API ─────────────────────────────────────────────────────────────
def call_gemini(messages, api_key, firecrawl_key, serper_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + GEMINI_MODEL + ":generateContent?key=" + api_key

    meta = {
        "model": GEMINI_MODEL,
        "firecrawl_used": False,
        "firecrawl_searches": 0,
        "firecrawl_pages": 0,
        "firecrawl_queries": [],
        "search_source": None,
    }

    tools = [{
        "functionDeclarations": [{
            "name": "search_web",
            "description": SEARCH_TOOL_DESC,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": SEARCH_QUERY_DESC,
                    }
                },
                "required": ["query"],
            },
        }]
    }]

    payload = {
        "contents": messages,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "tools": tools,
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }

    for _ in range(5):
        resp = http.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
        if resp.status_code != 200:
            raise Exception("Gemini API error " + str(resp.status_code) + ": " + resp.text[:300])

        result = resp.json()
        meta["model"] = result.get("modelVersion", GEMINI_MODEL)
        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])

        fc = None
        for p in parts:
            if "functionCall" in p:
                fc = p["functionCall"]
                break

        if fc and fc["name"] == "search_web":
            query_str = fc["args"]["query"]
            search_result, pages = search_web(query_str, firecrawl_key, serper_key)
            meta["firecrawl_used"] = True
            meta["firecrawl_searches"] += 1
            meta["firecrawl_pages"] += pages
            meta["firecrawl_queries"].append(query_str)
            if pages > 0 and not meta["search_source"]:
                meta["search_source"] = search_result.get("source")

            payload["contents"].append({"role": "model", "parts": [{"functionCall": fc}]})
            payload["contents"].append({"role": "user", "parts": [{"functionResponse": {"name": "search_web", "response": search_result}}]})
            continue

        text_parts = [p.get("text", "") for p in parts if "text" in p]
        return {"response": "".join(text_parts), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas.", "meta": meta}


# ─── Claude API ─────────────────────────────────────────────────────────────
def call_claude(messages, api_key, firecrawl_key, serper_key):
    claude_model = "claude-sonnet-4-20250514"
    meta = {
        "model": claude_model,
        "firecrawl_used": False,
        "firecrawl_searches": 0,
        "firecrawl_pages": 0,
        "firecrawl_queries": [],
        "search_source": None,
    }

    tools = [{
        "name": "search_web",
        "description": SEARCH_TOOL_DESC,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "La consulta de busqueda."}},
            "required": ["query"],
        },
    }]

    claude_msgs = []
    for m in messages:
        role = "assistant" if m.get("role") == "model" else "user"
        text = " ".join(p.get("text", "") for p in m.get("parts", []) if "text" in p)
        if text:
            claude_msgs.append({"role": role, "content": text})

    payload = {"model": claude_model, "max_tokens": 8192, "system": SYSTEM_PROMPT, "tools": tools, "messages": claude_msgs}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}

    for _ in range(5):
        resp = http.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=45)
        if resp.status_code != 200:
            raise Exception("Claude API error " + str(resp.status_code) + ": " + resp.text[:300])

        result = resp.json()
        meta["model"] = result.get("model", claude_model)
        tool_blocks = [b for b in result.get("content", []) if b.get("type") == "tool_use"]
        text_blocks = [b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"]

        if tool_blocks and result.get("stop_reason") == "tool_use":
            tool_results = []
            for tb in tool_blocks:
                if tb["name"] == "search_web":
                    sr, pages = search_web(tb["input"]["query"], firecrawl_key, serper_key)
                    meta["firecrawl_used"] = True
                    meta["firecrawl_searches"] += 1
                    meta["firecrawl_pages"] += pages
                    meta["firecrawl_queries"].append(tb["input"]["query"])
                    if pages > 0 and not meta["search_source"]:
                        meta["search_source"] = sr.get("source")
                    tool_results.append({"type": "tool_result", "tool_use_id": tb["id"], "content": json.dumps(sr, ensure_ascii=False)})

            payload["messages"].append({"role": "assistant", "content": result["content"]})
            payload["messages"].append({"role": "user", "content": tool_results})
            continue

        return {"response": " ".join(text_blocks), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas.", "meta": meta}


# ─── Route ──────────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
@app.route("/", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    llm = data.get("llm", "gemini")

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
    claude_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip("'\"")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "").strip().strip("'\"")
    serper_key = os.getenv("SERPER_API_KEY", "").strip().strip("'\"")

    try:
        if llm == "claude":
            if not claude_key:
                return jsonify({"error": "ANTHROPIC_API_KEY no configurada"}), 400
            result = call_claude(messages, claude_key, firecrawl_key, serper_key)
        else:
            if not gemini_key:
                return jsonify({"error": "GEMINI_API_KEY no configurada"}), 400
            result = call_gemini(messages, gemini_key, firecrawl_key, serper_key)

        return jsonify({"response": result["response"], "meta": result["meta"]})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
