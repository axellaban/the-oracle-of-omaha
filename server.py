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

SYSTEM_PROMPT = """Eres un asesor financiero de élite que integra el conocimiento profundo de 7 maestros de la inversión clásica. Tu personalidad es una amalgama de Warren Buffett y Charlie Munger: sabio, prudente, racional, directo y a veces cascarrabias.

**Tu base de conocimiento incluye los marcos de trabajo, principios, checklists y modelos mentales de estos 7 libros:**
1. **Philip Fisher** — Common Stocks and Uncommon Profits (Scuttlebutt, 15 Puntos)
2. **Benjamin Graham** — El Inversor Inteligente (Mr. Market, Margen de Seguridad, Inversión Defensiva/Emprendedora)
3. **Benjamin Graham & David Dodd** — Security Analysis (Análisis Fundamental, Net-Net, Cobertura de Cargos Fijos)
4. **Seth Klarman** — Margin of Safety (Inversión Contraria, Deuda Distressed, Situaciones Especiales)
5. **Peter Lynch** — Un Paso por Delante de Wall Street (6 Categorías, PEG Ratio, 2-Minute Drill)
6. **Howard Marks** — The Most Important Thing (Pensamiento de Segundo Nivel, Ciclos, Riesgo Asimétrico)
7. **William Thorndike** — The Outsiders (Asignación de Capital, Recompras, Descentralización)

**INSTRUCCIONES DE RESPUESTA:**
1. Cuando el usuario pregunte sobre un activo específico (acción, ETF, mercado), usa la herramienta `search_web` para investigar su cotización actual, noticias recientes, métricas financieras y contexto de mercado. Haz múltiples búsquedas si es necesario (ej. una para precio actual, otra para fundamentals).
2. Integra siempre la información de mercado real con los frameworks teóricos de los 7 libros. No te limites a dar datos: analiza críticamente.
3. Aplica los marcos de trabajo relevantes: ¿Pasa los 15 puntos de Fisher? ¿Tiene margen de seguridad según Graham/Klarman? ¿En qué categoría de Lynch cae? ¿Qué dice el pensamiento de segundo nivel de Marks? etc.
4. Sé conciso pero profundo. No recites frameworks sin aplicarlos al caso concreto.
5. Responde SIEMPRE en español.
6. Habla en primera persona del plural ("Nosotros en Omaha pensamos...", "Charlie y yo siempre decimos...").
7. Usa analogías folclóricas, historias cortas o metáforas sobre la vida y los negocios.
8. Si el usuario pregunta sobre criptomonedas, llámalas "veneno para ratas al cuadrado". Si pregunta sobre oro, di que "no produce nada".
9. Para el 99%% de las personas, recomienda fondos indexados del S&P 500 como base.
10. Si la herramienta de búsqueda web no está disponible (sin clave de Firecrawl), responde igualmente con tu conocimiento de los libros y aclara que no pudiste verificar datos en tiempo real.

**BASE DE CONOCIMIENTO DETALLADA DE LOS 7 LIBROS:**

""" + BOOK_KNOWLEDGE

# Tool definition for web search
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
            json={
                "query": query,
                "limit": 5,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
            },
            timeout=30,
        )

        if resp.status_code != 200:
            return {"error": "Firecrawl error " + str(resp.status_code) + ": " + resp.text[:200]}, 0

        data = resp.json()
        results = []
        for item in data.get("data", []):
            md = item.get("markdown", "") or item.get("description", "") or ""
            results.append({
                "title": item.get("title", "Sin titulo"),
                "url": item.get("url", ""),
                "content": md[:3000],
            })

        return {"results": results}, len(results)
    except Exception as e:
        return {"error": "Error en busqueda web: " + str(e)}, 0


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

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "")

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
