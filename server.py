"""
Oracle of Omaha - Investment Advisory Server
Connects the frontend with LLMs (Gemini/Claude) + 7 book skills + Firecrawl web search
Run with: uv run --with flask --with requests --with python-dotenv python server.py
"""
import os
import json
import requests as http
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

GEMINI_MODEL = "gemini-2.5-flash"


# ─── Load Book Skills Knowledge Base ────────────────────────────────────────
def load_book_knowledge():
    """Load summary .md files from each book skill (SKILL, cheatsheet, patterns, glossary)"""
    knowledge_parts = []
    skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted_skills")

    if not os.path.exists(skills_dir):
        return "(No se encontraron skills de libros en extracted_skills/)"

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

SYSTEM_PROMPT = """Eres el Oracle of Omaha: un asesor financiero de élite con la personalidad de Warren Buffett y Charlie Munger. Sabio, prudente, racional, directo y a veces cascarrabias.

**REGLA ABSOLUTA — BUSCAR SIEMPRE PRIMERO:**
Antes de responder CUALQUIER pregunta que involucre:
- Un activo específico (acción, ETF, índice, bono, materia prima)
- Una empresa o sector
- Datos macroeconómicos (inflación, tasas, PIB, empleo)
- Mercados o tendencias actuales
- Noticias o eventos financieros recientes

DEBES llamar a `search_web` PRIMERO. Si la pregunta menciona más de un activo o tema, haz múltiples llamadas. No respondas sobre finanzas actuales sin buscar datos reales primero.

Para preguntas puramente filosóficas o conceptuales (ej. "¿qué es el margen de seguridad?"), busca un ejemplo real o noticia reciente que ilustre el concepto antes de responder.

**CÓMO BUSCAR:**
- Acciones: "[empresa] [ticker] stock price earnings 2025"
- Macro: "[indicador] [país] [mes/año] latest data"
- Noticias: "[empresa/sector] news analysis [mes año]"
- Fundamentals: "[empresa] P/E ratio revenue debt margin 2025"
Haz 2-3 búsquedas cuando el tema lo requiera.

**TU BASE DE CONOCIMIENTO — 7 MAESTROS:**
1. **Philip Fisher** — Common Stocks & Uncommon Profits: Scuttlebutt, 15 Puntos de calidad, crecimiento a largo plazo
2. **Benjamin Graham** — El Inversor Inteligente: Mr. Market, Margen de Seguridad, Inversión Defensiva vs Emprendedora
3. **Graham & Dodd** — Security Analysis: Análisis Fundamental, Net-Net, Cobertura de Cargos Fijos, valor intrínseco
4. **Seth Klarman** — Margin of Safety: Inversión Contraria, Deuda Distressed, Spin-offs, el precio NO es el valor
5. **Peter Lynch** — Un Paso por Delante: 6 Categorías (slow grower, stalwart, fast grower, cyclical, turnaround, asset play), PEG Ratio, 2-Minute Drill
6. **Howard Marks** — The Most Important Thing: Pensamiento de Segundo Nivel, Ciclos de Mercado, Riesgo Asimétrico, el precio importa
7. **William Thorndike** — The Outsiders: CEOs extraordinarios, Asignación de Capital, Recompras inteligentes, Descentralización

**CÓMO APLICAR LOS 7 FRAMEWORKS AL ANALIZAR UN ACTIVO (DEBES APLICAR LOS 7 FRAMEWORKS EN CADA ANÁLISIS):**
En cada análisis, debes aplicar obligatoriamente y sin excepción los frameworks de cada uno de los 7 libros de la base de conocimiento:
1. Fisher: Evalúa si pasa los 15 puntos de Fisher (moat de I+D, ventas y organización).
2. Graham (Inversor Inteligente): Analiza el comportamiento de Mr. Market con respecto al precio actual y define si la inversión es para un perfil defensivo o emprendedor.
3. Graham & Dodd (Security Analysis): Calcula/estima el valor intrínseco y verifica si hay margen de seguridad contable (ej. cobertura de cargos fijos).
4. Klarman: Evalúa si el precio de cotización difiere significativamente del valor y busca irracionalidades del mercado o situaciones especiales.
5. Lynch: Clasifica el activo en una de las 6 categorías de Lynch, calcula el PEG ratio y realiza el monólogo de dos minutos (2-Minute Drill).
6. Marks: Determina en qué punto del ciclo de mercado estamos y aplica pensamiento de segundo nivel para cuestionar la opinión del consenso.
7. Thorndike: Audita la asignación de capital del management (recompras de acciones, nivel de deuda y descentralización).

**ESTILO DE RESPUESTA:**
- Responde SIEMPRE en español
- Primera persona del plural: "Nosotros en Omaha...", "Charlie y yo siempre decimos..."
- Usa analogías, historias cortas y metáforas de negocios y vida cotidiana
- Criptomonedas = "veneno para ratas al cuadrado". Oro = "no produce nada"
- Para el 99%% de las personas: fondos indexados S&P 500 como base
- Sé directo y crítico. No halagues activos sin fundamento real

**BASE DE CONOCIMIENTO DETALLADA DE LOS 7 LIBROS:**

""" + BOOK_KNOWLEDGE

SEARCH_TOOL_DESC = (
    "Busca información actualizada en internet. DEBES usarla antes de responder sobre "
    "cualquier activo (acción, ETF, bono, materia prima), empresa, sector, dato macro "
    "(inflación, tasas, PIB), o evento de mercado. También úsala para encontrar ejemplos "
    "reales que ilustren conceptos de inversión."
)

SEARCH_QUERY_DESC = (
    "Consulta de búsqueda específica en inglés o español. Incluye ticker/nombre + métrica + año. "
    "Ejemplos: 'Apple AAPL P/E ratio revenue 2025', 'Tesla Q1 2025 earnings results', "
    "'US inflation CPI May 2025', 'Mercado Libre MELI stock analysis 2025'."
)


# ─── Firecrawl Web Search ───────────────────────────────────────────────────
def firecrawl_search(query, api_key):
    """Search the web using Firecrawl REST API. Returns (result_dict, pages_count)."""
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
            timeout=30,
        )

        print(f"[Firecrawl] query='{query}' status={resp.status_code}")

        if resp.status_code != 200:
            err = f"Firecrawl error {resp.status_code}: {resp.text[:300]}"
            print(f"[Firecrawl] ERROR: {err}")
            return {"error": err}, 0

        data = resp.json()
        if not data.get("success", True):
            err = data.get("error", "Firecrawl returned success=false")
            print(f"[Firecrawl] ERROR: {err}")
            return {"error": err}, 0

        raw_results = data.get("data", [])
        print(f"[Firecrawl] {len(raw_results)} resultados encontrados")

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

        return {"results": results}, len(results)
    except Exception as e:
        err = f"Error en busqueda web: {str(e)}"
        print(f"[Firecrawl] EXCEPTION: {err}")
        return {"error": err}, 0


# ─── Gemini API with Function Calling ───────────────────────────────────────
def call_gemini(messages, api_key, firecrawl_key):
    """Returns dict with: response (text), model, firecrawl_used, firecrawl_searches, firecrawl_pages, firecrawl_queries"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + GEMINI_MODEL + ":generateContent?key=" + api_key

    # Track metadata
    meta = {
        "model": GEMINI_MODEL,
        "firecrawl_used": False,
        "firecrawl_searches": 0,
        "firecrawl_pages": 0,
        "firecrawl_queries": [],
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
        "toolConfig": {
            "functionCallingConfig": {"mode": "AUTO"}
        },
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192},
    }

    for _ in range(5):
        resp = http.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        if resp.status_code != 200:
            raise Exception("Gemini API error " + str(resp.status_code) + ": " + resp.text[:300])

        result = resp.json()

        # Extract actual model version from response
        actual_model = result.get("modelVersion", GEMINI_MODEL)
        meta["model"] = actual_model

        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])

        # Find function call
        fc = None
        for p in parts:
            if "functionCall" in p:
                fc = p["functionCall"]
                break

        if fc and fc["name"] == "search_web":
            query = fc["args"]["query"]
            search_result, pages = firecrawl_search(query, firecrawl_key)

            meta["firecrawl_used"] = True
            meta["firecrawl_searches"] += 1
            meta["firecrawl_pages"] += pages
            meta["firecrawl_queries"].append(query)

            payload["contents"].append({
                "role": "model",
                "parts": [{"functionCall": fc}],
            })
            payload["contents"].append({
                "role": "user",
                "parts": [{"functionResponse": {
                    "name": "search_web",
                    "response": search_result,
                }}],
            })
            continue

        # Return final text + metadata
        text_parts = []
        for p in parts:
            if "text" in p:
                text_parts.append(p["text"])
        return {"response": "".join(text_parts), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas. Reformula tu pregunta.", "meta": meta}


# ─── Claude API with Tool Use ───────────────────────────────────────────────
def call_claude(messages, api_key, firecrawl_key):
    """Returns dict with: response (text), model, firecrawl metadata"""
    url = "https://api.anthropic.com/v1/messages"
    claude_model = "claude-sonnet-4-20250514"

    meta = {
        "model": claude_model,
        "firecrawl_used": False,
        "firecrawl_searches": 0,
        "firecrawl_pages": 0,
        "firecrawl_queries": [],
    }

    tools = [{
        "name": "search_web",
        "description": SEARCH_TOOL_DESC,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La consulta de busqueda. Se especifico.",
                }
            },
            "required": ["query"],
        },
    }]

    # Convert from Gemini message format to Claude format
    claude_msgs = []
    for m in messages:
        role = "assistant" if m.get("role") == "model" else "user"
        text_parts = []
        for p in m.get("parts", []):
            if "text" in p:
                text_parts.append(p["text"])
        text = " ".join(text_parts)
        if text:
            claude_msgs.append({"role": role, "content": text})

    payload = {
        "model": claude_model,
        "max_tokens": 8192,
        "system": SYSTEM_PROMPT,
        "tools": tools,
        "messages": claude_msgs,
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    for _ in range(5):
        resp = http.post(url, json=payload, headers=headers, timeout=120)
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
                    query = tb["input"]["query"]
                    sr, pages = firecrawl_search(query, firecrawl_key)
                    meta["firecrawl_used"] = True
                    meta["firecrawl_searches"] += 1
                    meta["firecrawl_pages"] += pages
                    meta["firecrawl_queries"].append(query)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb["id"],
                        "content": json.dumps(sr, ensure_ascii=False),
                    })

            payload["messages"].append({"role": "assistant", "content": result["content"]})
            payload["messages"].append({"role": "user", "content": tool_results})
            continue

        return {"response": " ".join(text_blocks), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas.", "meta": meta}


# ─── Flask Routes ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "buscador_de_inversiones.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    llm = data.get("llm", "gemini")

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
    claude_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip("'\"")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "").strip().strip("'\"")

    try:
        if llm == "claude":
            if not claude_key:
                return jsonify({"error": "ANTHROPIC_API_KEY no configurada en .env"}), 400
            result = call_claude(messages, claude_key, firecrawl_key)
        else:
            if not gemini_key:
                return jsonify({"error": "GEMINI_API_KEY no configurada en .env"}), 400
            result = call_gemini(messages, gemini_key, firecrawl_key)

        return jsonify({
            "response": result["response"],
            "meta": result["meta"],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    gk = "OK" if os.getenv("GEMINI_API_KEY") else "NO"
    ck = "OK" if os.getenv("ANTHROPIC_API_KEY") else "NO"
    fk = "OK" if os.getenv("FIRECRAWL_API_KEY") else "NO"
    kb = len(BOOK_KNOWLEDGE)

    print("")
    print("Oracle of Omaha - Servidor de Inversiones")
    print("Base de conocimiento: " + str(kb) + " caracteres de 7 libros")
    print("Gemini:    " + gk)
    print("Claude:    " + ck)
    print("Firecrawl: " + fk)
    print("")
    print("Abre http://localhost:5000 en tu navegador")
    print("")
    app.run(host="0.0.0.0", port=5000, debug=True)
