# El Oráculo de los 7
## Cómo construí un asesor financiero agéntico en producción

*Junio 2026*

---

## Resumen ejecutivo

Proceso completo para pasar de una necesidad personal de análisis financiero con IA a un producto desplegado en producción que cualquier persona puede consumir vía web — y que con un login encima se convierte en un SaaS monetizable.

La arquitectura central es un **consejo de 7 agentes especializados** (uno por libro canónico de inversión) coordinados por un agente orquestador. Cada agente evalúa un activo desde su propio marco; el orquestador sintetiza los veredictos en una recomendación accionable.

> No se necesita saber programar. Las herramientas de IA (Antigravity, Claude Code) escriben y ejecutan el código. El rol del builder es tomar decisiones, dar instrucciones e iterar.

---

## Paso 0 — Instalar las herramientas base

**¿Qué son las dependencias?** Librerías y herramientas de código que el proyecto necesita para funcionar. En lugar de programar todo desde cero, se reutiliza lo que otros ya construyeron. Se instalan en segundos.

Abrí **Antigravity o Claude Code** y pegá este único prompt:

> "Instalá en mi computadora las siguientes herramientas si no las tengo: Git, Python 3, Node.js. Luego instalá las dependencias Python del proyecto: flask, requests y python-dotenv. Verificá que todo quedó instalado correctamente."

---

## Paso 1 — Diseñar la arquitectura agéntica

Todo partió de evaluar instrumentos financieros con IA de forma rigurosa. El mejor resultado llegó al combinar múltiples perspectivas en un único análisis: una skill por cada libro canónico de inversión.

| # | Autor | Libro | Marco conceptual |
|---|-------|-------|-----------------|
| 1 | Philip Fisher | Common Stocks & Uncommon Profits | Calidad del negocio, moat, crecimiento |
| 2 | Benjamin Graham | El Inversor Inteligente | Mr. Market, Margen de Seguridad |
| 3 | Graham & Dodd | Security Analysis | Valor intrínseco, análisis fundamental |
| 4 | Seth Klarman | Margin of Safety | Inversión contraria, brecha precio-valor |
| 5 | Peter Lynch | Un Paso por Delante de Wall Street | 6 categorías de empresa, PEG ratio |
| 6 | Howard Marks | The Most Important Thing | Ciclos de mercado, riesgo asimétrico |
| 7 | William Thorndike | The Outsiders | Asignación de capital, recompras |

Sobre las 7 skills se construyó un **agente orquestador** ("Council of 7") que normaliza los datos, hace hablar a cada experto con su propio marco, detecta consensos y divergencias, y emite una síntesis ejecutiva accionable.

> El sistema vivía originalmente en Claude Projects y se usaba de forma manual. La arquitectura multi-skill demostró ser muy superior a un único prompt monolítico.

---

## Paso 1.5 — Configuración de las 7 skills

Antes de avanzar con el código, necesitás preparar el conocimiento especializado que los agentes consultarán.

**Instrucción para generar y guardar las skills:**
> "Para cada libro, subile el PDF a Claude y pedile que extraiga los frameworks clave en un archivo SKILL.md. Guardá cada uno en `extracted_skills/[nombre-del-libro]/SKILL.md`. También creá la skill orquestadora `extracted_skills/council-of-7-investors/SKILL.md` con el protocolo del Council."

---

## Paso 2 — Crear las cuentas y obtener las API keys

Todas son gratuitas en su tier básico.

| Servicio | Para qué | Web |
|----------|----------|-----|
| **GitHub** | Guarda el código en la nube | github.com |
| **Vercel** | Publica el proyecto en internet, conectado a GitHub | vercel.com |
| **Anthropic** | API Key de Claude Sonnet 4.6 — el cerebro principal del sistema | console.anthropic.com |
| **Google AI Studio** | API Key de Gemini 2.5 Flash — fallback del sistema | aistudio.google.com |
| **Serper API** | Búsquedas Google en tiempo real (cotizaciones, noticias) | serper.dev |
| **Firecrawl** | Web scraping profundo como fallback de Serper | firecrawl.dev |

---

## Paso 3 — Construir el frontend

El frontend es la pantalla que ve el usuario: barra de búsqueda estilo Google y chat. Es un único archivo HTML.

**Instrucción para Antigravity / Claude Code:**
> "Construime un frontend en un único archivo HTML estilo Google Search. Pantalla inicial con logotipo cromático ('El Oráculo de los 7' con letras en azul/rojo/amarillo/verde), barra de búsqueda centrada y dos botones: 'Pedir Consejo' y 'Pregunta al Azar'. Al enviar, transicionar a modo chat con barra fija arriba e input abajo. Mensajes del usuario en burbujas azules a la derecha; respuestas de la IA en Markdown (tablas, listas, código). Animación de 'agente pensando' con texto rotativo, botón Stop para cancelar, y persistencia del historial en localStorage."

---

## Paso 4 — Construir el backend

El backend recibe la pregunta, consulta las 7 skills, llama a Claude Sonnet (con Gemini como fallback) y busca datos en internet antes de responder.

**Instrucción para Antigravity / Claude Code:**
> "Tengo este frontend HTML con un chat que llama a /api/chat. Construime el backend en Python para Vercel que use Claude Sonnet 4.6 como LLM primario y Gemini 2.5 Flash como fallback, cargue los archivos de la carpeta extracted_skills/ como contexto, y pueda buscar en internet con Serper y Firecrawl. Las API keys vienen de variables de entorno."

---

## Paso 5 — Crear el repositorio en GitHub y subir el código

**El repositorio en GitHub se crea manualmente:** entrá a github.com, hacé clic en "New repository", poné el nombre y crealo vacío (sin README).

Una vez creado, copiá la URL del repo y pegale esta instrucción a Antigravity o Claude Code:

**Instrucción para Antigravity / Claude Code:**
> "Inicializá Git en esta carpeta, hacé el primer commit con todos los archivos excepto .env, y subilo al repositorio de GitHub [pegá la URL del repo aquí]."

Luego en Vercel: importá ese repositorio y Vercel lo desplegará automáticamente. Cada push futuro actualiza el sitio solo.

---

## Paso 6 — Configurar las API keys en Vercel

En Vercel → tu proyecto → **Settings → Environment Variables**, cargar:

| Variable | Valor |
|----------|-------|
| `ANTHROPIC_API_KEY` | Tu key de Anthropic |
| `GEMINI_API_KEY` | Tu key de Google AI Studio |
| `SERPER_API_KEY` | Tu key de Serper |
| `FIRECRAWL_API_KEY` | Tu key de Firecrawl |

Listo. El sitio ya está vivo y funcional.

---

## Paso 7 — Iterar hasta que funcione como querés

Con el sitio vivo, probás, ves lo que no anda como esperabas, y le describís el problema a Antigravity o Claude Code en lenguaje llano. La IA lo corrige, subís el cambio a GitHub y Vercel actualiza el sitio solo en segundos. El ciclo es rápido y no requiere saber programar — cuanto más claro describís lo que querés, mejor resulta.

---

## Casos de uso de la misma arquitectura

| Caso | Cómo |
|------|------|
| Uso personal | Tal cual está |
| Equipo de trabajo | Reemplazar las 7 skills por playbooks o SOPs de la empresa |
| Producto para clientes | Agregar login (Clerk, Auth0) encima del HTML existente |
| SaaS monetizable | Integrar Stripe + límites de uso por plan |
| Otro dominio | Cambiar los libros por medicina, legal, marketing, RRHH, etc. |

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | HTML + Tailwind CSS + Vanilla JS |
| Backend | Python 3 · Flask · Vercel Serverless |
| LLM | Claude Sonnet 4.6 (cerebro) · Gemini 2.5 Flash (fallback) |
| Búsqueda | Serper + Firecrawl |
| Hosting | Vercel + GitHub |
| Dev tools | Antigravity · Claude Code |

---

*MVP funcional en producción, gratuito en sus tiers básicos, construido en horas.*
