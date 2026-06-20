"""
Oracle of Omaha - Vercel Serverless Function
POST /api/chat — Calls Gemini/Claude with 7 book skills + Firecrawl web search
"""
import os
import json
import requests as http
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
1. Cuando el usuario pregunte sobre un activo específico (acción, ETF, mercado), usa la herramienta `search_web` para investigar su cotización actual, noticias recientes, métricas financieras y contexto de mercado. Haz múltiples búsquedas si es necesario.
2. Integra siempre la información de mercado real con los frameworks teóricos de los 7 libros. No te limites a dar datos: analiza críticamente.
3. Aplica los marcos de trabajo relevantes al caso concreto.
4. Sé conciso pero profundo. No recites frameworks sin aplicarlos.
5. Responde SIEMPRE en español.
6. Habla en primera persona del plural ("Nosotros en Omaha pensamos...", "Charlie y yo siempre decimos...").
7. Usa analogías folclóricas, historias cortas o metáforas sobre la vida y los negocios.
8. Si el usuario pregunta sobre criptomonedas, llámalas "veneno para ratas al cuadrado". Si pregunta sobre oro, di que "no produce nada".
9. Para el 99%% de las personas, recomienda fondos indexados del S&P 500 como base.
10. Si la herramienta de búsqueda web no está disponible, responde con tu conocimiento de los libros y aclara que no pudiste verificar datos en tiempo real.

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
            return {"error": "Firecrawl error " + str(resp.status_code)}, 0

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


# ─── Gemini API ─────────────────────────────────────────────────────────────
def call_gemini(messages, api_key, firecrawl_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + GEMINI_MODEL + ":generateContent?key=" + api_key

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
        resp = http.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
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
            search_result, pages = firecrawl_search(query_str, firecrawl_key)
            meta["firecrawl_used"] = True
            meta["firecrawl_searches"] += 1
            meta["firecrawl_pages"] += pages
            meta["firecrawl_queries"].append(query_str)

            payload["contents"].append({"role": "model", "parts": [{"functionCall": fc}]})
            payload["contents"].append({"role": "user", "parts": [{"functionResponse": {"name": "search_web", "response": search_result}}]})
            continue

        text_parts = [p.get("text", "") for p in parts if "text" in p]
        return {"response": "".join(text_parts), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas.", "meta": meta}


# ─── Claude API ─────────────────────────────────────────────────────────────
def call_claude(messages, api_key, firecrawl_key):
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
        resp = http.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=120)
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
                    sr, pages = firecrawl_search(tb["input"]["query"], firecrawl_key)
                    meta["firecrawl_used"] = True
                    meta["firecrawl_searches"] += 1
                    meta["firecrawl_pages"] += pages
                    meta["firecrawl_queries"].append(tb["input"]["query"])
                    tool_results.append({"type": "tool_result", "tool_use_id": tb["id"], "content": json.dumps(sr, ensure_ascii=False)})

            payload["messages"].append({"role": "assistant", "content": result["content"]})
            payload["messages"].append({"role": "user", "content": tool_results})
            continue

        return {"response": " ".join(text_blocks), "meta": meta}

    return {"response": "Se excedio el numero maximo de busquedas.", "meta": meta}


# ─── Route ──────────────────────────────────────────────────────────────────
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
                return jsonify({"error": "ANTHROPIC_API_KEY no configurada"}), 400
            result = call_claude(messages, claude_key, firecrawl_key)
        else:
            if not gemini_key:
                return jsonify({"error": "GEMINI_API_KEY no configurada"}), 400
            result = call_gemini(messages, gemini_key, firecrawl_key)

        return jsonify({"response": result["response"], "meta": result["meta"]})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
