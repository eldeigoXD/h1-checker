# QA Web Tool Pro - Documentation

## Part 1: Overview & Architecture (English)

### What is QA Web Tool Pro?
QA Web Tool Pro is an advanced, automated Quality Assurance (QA) application designed specifically for automotive dealership websites. Its primary goal is to audit landing pages, inventory pages, and semantic coherence to ensure that SEO strategies, Call to Actions (CTAs), and inventory filters align perfectly with the user's intent and the dealership's inventory.

### Technologies & Libraries Used
The tool is built with a modern, lightweight, and local-first architecture:
- **Backend:** Python with **Flask** for the API and server logic.
- **HTML Parsing:** **BeautifulSoup4** for rapid DOM navigation, metadata extraction, and element targeting.
- **Semantic Engine:** **SentenceTransformers** (`all-MiniLM-L6-v2`) for fast, local cosine-similarity checks, combined with **Ollama** running local LLMs (e.g., `phi3:mini`) for deep semantic reasoning and entity matching.
- **Memory & RAG:** **ChromaDB** for storing historical audit patterns and retrieving context-aware rules.
- **Frontend:** Vanilla **HTML, CSS, and JavaScript** for a lightning-fast, reactive user interface without heavy frameworks.

### Workflow
1. **Input:** The user enters a Target URL, a Case Number, an Expected H1 Title, and optional custom instructions.
2. **Fetch & Parse:** The backend fetches the page's HTML and passes it to BeautifulSoup to extract the H1 tags, links, text content, and navigation menus.
3. **Automated Audits:** 
   - *Inventory Check:* Analyzes the URL slug and navigation to infer the correct inventory filter (e.g., Make, Model, Condition).
   - *Sitemap Check:* Pings `/sitemap.xml` and `/sitemap.htm` to verify indexability.
   - *Link & CTA Check:* Scans the DOM for specific CTAs and checks their health, destination, and text relevance.
4. **Semantic Analysis:** The local LLM and SentenceTransformer analyze the page's visible text against the URL intent to find contradictions (e.g., an F-150 URL showing Equinox content).
5. **Output:** The UI renders a complete Bug Report, highlighting passing metrics in green and specific issues in red, allowing the user to export a PDF report or review historical audits.

---

## Part 2: App Features & Bug Detection (English)

### Graphical User Interface (GUI) Features
*(Insert Image: Main Dashboard)*
- **Search Bar:** A clean interface to input the URL, Case Number, Target Title, and special instructions.
- **Real-Time Progress Indicator:** A dynamic loader that informs the user which part of the audit is currently running (Fetching, Parsing, LLM Analysis).
- **Audit Categories (Tabs):** Results are organized into clear tabs for easy navigation:
  - *Overview:* High-level stats and pass/fail status.
  - *Inventory:* Shows dynamic filter inferences and mismatches.
  - *Links/CTAs:* Lists missing or broken buttons.
  - *Sitemaps:* Status of XML and HTML sitemaps.
  - *Semantic Coherence:* The score and LLM verdict on content alignment.
- **Bug Report Card:** A dedicated panel that summarizes all found errors.
- **Audit History:** A modal (accessible via the "📜 History" button) that saves past audits locally. It includes a real-time search bar to filter by ID, Title, or Path.
- **PDF Export:** A one-click button to download the Bug Report for clients or developers.

### Detectable Bugs
*(Insert Image: Bug Examples)*
1. **H1 Mismatches:** Detects if the H1 is missing, multiple H1s exist, or if the text doesn't match the expected target.
2. **Inventory Filter Mismatch:** Identifies when a page claims to show a specific model (e.g., `New Ford Bronco`) but the backend URL filter actually loads a different model or condition.
3. **Sitemap Errors:** Flags when `sitemap.xml` or `sitemap.htm` return 404 Not Found.
4. **Missing CTAs:** Detects if required buttons (e.g., "Schedule Test Drive", "View Inventory") are missing from the page.
5. **Link Health Issues:** Finds dead links, empty `href` attributes, or external links missing the `target="_blank"` attribute.
6. **Semantic Coherence Bugs:** Uses AI to read the page and flag if the content contradicts the URL. (e.g., The URL is about used EV cars, but the text discusses gas-powered trucks).
7. **Typo Detection:** Finds common spelling errors in buttons (e.g., "fiannce" instead of "finance").

---
---

## Parte 1: Visión General y Arquitectura (Español)

### ¿Qué es QA Web Tool Pro?
QA Web Tool Pro es una aplicación de aseguramiento de calidad (QA) avanzada y automatizada, diseñada específicamente para sitios web de concesionarios de automóviles. Su objetivo principal es auditar landing pages, páginas de inventario y la coherencia semántica para garantizar que las estrategias de SEO, los Call to Actions (CTAs) y los filtros de inventario se alineen perfectamente con la intención del usuario y el inventario del concesionario.

### Tecnologías y Librerías Utilizadas
La herramienta está construida con una arquitectura moderna, ligera y de ejecución local:
- **Backend:** Python con **Flask** para la API y la lógica del servidor.
- **Parseo HTML:** **BeautifulSoup4** para la navegación rápida del DOM, extracción de metadatos y selección de elementos.
- **Motor Semántico:** **SentenceTransformers** (`all-MiniLM-L6-v2`) para comprobaciones rápidas de similitud de cosenos a nivel local, combinado con **Ollama** ejecutando LLMs locales (ej. `phi3:mini`) para razonamiento semántico profundo y coincidencia de entidades.
- **Memoria y RAG:** **ChromaDB** para almacenar patrones históricos de auditoría y recuperar reglas basadas en contexto.
- **Frontend:** **HTML, CSS y JavaScript** puros para una interfaz de usuario ultrarrápida y reactiva sin frameworks pesados.

### Flujo de Trabajo
1. **Entrada:** El usuario ingresa una URL, un Número de Caso, un Título H1 esperado e instrucciones personalizadas opcionales.
2. **Obtención y Parseo:** El backend descarga el HTML de la página y lo pasa a BeautifulSoup para extraer las etiquetas H1, enlaces, contenido de texto y menús de navegación.
3. **Auditorías Automatizadas:** 
   - *Revisión de Inventario:* Analiza el slug de la URL y la navegación para inferir el filtro de inventario correcto (ej. Marca, Modelo, Condición).
   - *Revisión de Sitemap:* Consulta `/sitemap.xml` y `/sitemap.htm` para verificar la indexabilidad.
   - *Revisión de Enlaces y CTAs:* Escanea el DOM en busca de CTAs específicos y verifica su salud, destino y relevancia de texto.
4. **Análisis Semántico:** El LLM local y SentenceTransformer analizan el texto visible de la página en contraste con la intención de la URL para encontrar contradicciones (ej. una URL de F-150 mostrando contenido de Equinox).
5. **Salida:** La interfaz gráfica renderiza un Reporte de Bugs completo, resaltando las métricas aprobadas en verde y los problemas específicos en rojo, permitiendo al usuario exportar un reporte en PDF o revisar auditorías históricas.

---

## Parte 2: Funcionalidades de la App y Detección de Bugs (Español)

### Funcionalidades de la Interfaz Gráfica (GUI)
*(Insertar Imagen: Panel Principal)*
- **Barra de Búsqueda:** Una interfaz limpia para ingresar la URL, el Número de Caso, el Título Objetivo e instrucciones especiales.
- **Indicador de Progreso en Tiempo Real:** Un cargador dinámico que informa al usuario qué parte de la auditoría se está ejecutando (Descargando, Parseando, Análisis LLM).
- **Categorías de Auditoría (Pestañas):** Los resultados se organizan en pestañas claras para facilitar la navegación:
  - *Overview (Resumen):* Estadísticas de alto nivel y estado de aprobación/fallo.
  - *Inventory (Inventario):* Muestra inferencias de filtros dinámicos y discrepancias.
  - *Links/CTAs:* Enumera botones faltantes o rotos.
  - *Sitemaps:* Estado de los mapas de sitio XML y HTML.
  - *Semantic Coherence (Coherencia Semántica):* El puntaje y el veredicto del LLM sobre la alineación del contenido.
- **Tarjeta de Reporte de Bugs:** Un panel dedicado que resume todos los errores encontrados.
- **Historial de Auditorías:** Un modal (accesible mediante el botón "📜 History") que guarda las auditorías pasadas localmente. Incluye una barra de búsqueda en tiempo real para filtrar por ID, Título o Path.
- **Exportación a PDF:** Un botón de un solo clic para descargar el Reporte de Bugs para clientes o desarrolladores.

### Bugs Detectables
*(Insertar Imagen: Ejemplos de Bugs)*
1. **Discrepancias en H1:** Detecta si falta el H1, si existen múltiples H1 o si el texto no coincide con el objetivo esperado.
2. **Discrepancia en Filtro de Inventario:** Identifica cuando una página afirma mostrar un modelo específico (ej. `New Ford Bronco`) pero el filtro de la URL en el backend realmente carga un modelo o condición diferente.
3. **Errores de Sitemap:** Marca cuando `sitemap.xml` o `sitemap.htm` devuelven un error 404 Not Found.
4. **CTAs Faltantes:** Detecta si faltan botones requeridos (ej. "Schedule Test Drive", "View Inventory") en la página.
5. **Problemas de Salud de Enlaces:** Encuentra enlaces muertos, atributos `href` vacíos o enlaces externos a los que les falta el atributo `target="_blank"`.
6. **Bugs de Coherencia Semántica:** Utiliza IA para leer la página y marcar si el contenido contradice la URL. (ej. La URL trata sobre autos EV usados, pero el texto habla de camionetas a gasolina).
7. **Detección de Errores Tipográficos:** Encuentra errores ortográficos comunes en los botones (ej. "fiannce" en lugar de "finance").
