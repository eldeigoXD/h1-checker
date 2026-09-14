# 🚗 Arquitectura Técnica: Dealer.com (DDC) Composer, Banco de Imágenes y Sistema de Reportes

Este documento detalla la arquitectura, ingeniería inversa del DOM de **Dealer.com (DDC)**, replicación visual del **Composer / Page Designer**, el funcionamiento del **Banco de Imágenes Automotriz (Image Harvester)** y el **Sistema de Auditoría y Reportes de Bugs**. Está diseñado para servir como manual de referencia directo para Antigravity en cualquier máquina de desarrollo.

---

## 1. Interpretación del DOM de Dealer.com (DDC) y Composer

En el CMS de **Dealer.com (DDC)**, los sitios web automotrices no están construidos como páginas estáticas comunes, sino a través de un motor de ensamblado modular basado en **Apache Velocity**. 

Cada página se compone de una jerarquía de:
1. **Page Template** (Plantilla base que define las secciones habilitadas).
2. **Sections** (Contenedores horizontales principales).
3. **Containers / Columns** (Divisiones de columnas: una columna, 50/50, tercios o multi-columna).
4. **Widgets / Portlets** (Bloques individuales funcionales o de contenido WYSIWYG).

---

### A. Anatomía del DOM en Sitios DDC
El extractor inspecciona el código HTML en `app.py` mediante la función:
```python
def extract_sections_and_widgets(soup, url: str = "")
```

Para identificar las secciones superiores reales sin confundirlas con contenedores anidados, se aplica la siguiente regla de filtrado top-level:
```python
all_sec = soup.find_all(lambda el: el.name in ['section'] or (el.name == 'div' and 'page-section' in el.get('class', [])))
top_sections = []
for s in all_sec:
    parent_sec = s.find_parent(lambda p: p != s and (p.name in ['section'] or (p.name == 'div' and 'page-section' in p.get('class', []))))
    if not parent_sec:
        top_sections.append(s)
```

#### Nombres de Secciones y Normalización Oficial
DDC utiliza identificadores con sufijos de versión o IDs dinámicos (ej. `content-background-image-right.1-2` o `inventory-search-results-1`). La función `clean_section_title(raw)` normaliza estos nombres para que coincidan exactamente con la terminología de Composer:
* `title` / `page-title` $\rightarrow$ **Page Title**
* `slideshow` $\rightarrow$ **Slideshow**
* `seo-content` / `additional-seo` $\rightarrow$ **Additional SEO Content**
* `inventory-search-results` $\rightarrow$ **Inventory Search Results**
* `content-centered` $\rightarrow$ **Content Centered**
* `content-wide` $\rightarrow$ **Content Wide**
* `content-background-image-right` $\rightarrow$ **Content w/ Image Right**
* `content-background-image-left` $\rightarrow$ **Content w/ Image Left**
* `content-thirds` $\rightarrow$ **Content Thirds**
* `content-left-over-background-image` $\rightarrow$ **Content Left Over Background Image**
* `content-right-over-background-image` $\rightarrow$ **Content Right Over Background Image**
* `map-hours` / `map` $\rightarrow$ **Contact and Map**

---

### B. El Misterio de las Secciones Ocultas (Hidden Sections)

#### ¿Por qué aparecen en Composer pero no siempre en el HTML publicado?
En Composer, el panel lateral izquierdo (**Page Designer**) lista todas las secciones configuradas en la plantilla maestra de la página. Cada sección posee un conmutador de visibilidad (ícono de ojo).

1. **Cuando una sección se oculta en Composer**: El backend de DDC (Apache Velocity) **suprime por completo la generación del markup HTML** en el sitio en vivo o le asigna clases de ocultamiento (`d-none`, `hide`, `display: none`). Esto se hace para:
   * Evitar penalizaciones de SEO por bloques vacíos o contenido redundante.
   * Acelerar los tiempos de renderizado y respuesta del servidor.
2. **Cómo las detecta y reconstruye nuestro motor**:
   El extractor compara las secciones obligatorias del template DDC (`Page Title`, `Slideshow`, `Additional SEO Content`) con las secciones encontradas en el DOM activo:
   ```python
   template_hidden_sections = []
   if 'Page Title' not in dom_sec_names:
       template_hidden_sections.append(('page-title-hidden', 'Page Title', 'Hidden from view in page template'))
   if 'Slideshow' not in dom_sec_names and any('inventory' in n.lower() or 'image' in n.lower() for n in dom_sec_names):
       template_hidden_sections.append(('slideshow-hidden', 'Slideshow', 'Hidden from view in page template'))
   if 'Additional SEO Content' not in dom_sec_names and any('inventory' in n.lower() or 'content' in n.lower() for n in dom_sec_names):
       template_hidden_sections.append(('seo-content-hidden', 'Additional SEO Content', 'Hidden from view in page template'))
   ```
   Estas secciones se inyectan en la respuesta con:
   * `is_hidden: True`
   * `layout_type: 'hidden'`
   * `hidden_reason: 'Hidden from view in page template'`

En el **Page Designer Sidebar** se muestran con el ícono **`🚫`** y en el **Composer Canvas** como un bloque atenuado punteado con la advertencia correspondiente.

---

### C. Detección y Representación de Layouts Complejos Multi-Columna

DDC implementa varios patrones de diseño que nuestro sistema parsea en estructuras semánticas:

#### 1. Content w/ Image Right (`layout_type: 'image-right'`)
* **Estructura**: Divide la sección en 2 columnas:
  * **Izquierda**: Contenido WYSIWYG (`Content (contentX)`).
  * **Derecha**: Imagen destacada del vehículo.
* **Extracción de Imagen**: `find_section_image(sec_node)` busca en atributos `data-src` (para saltar el `blank.gif` o base64 de lazy-load), `src`, o en propiedades CSS `background-image: url(...)`.

#### 2. Content w/ Image Left (`layout_type: 'image-left'`)
* **Estructura**: Idéntica a la anterior pero invertida:
  * **Izquierda**: Imagen destacada del vehículo / flota.
  * **Derecha**: Contenido WYSIWYG.

#### 3. Content Thirds (`layout_type: 'thirds'`)
* **Estructura**: Grilla responsiva de 3 columnas de igual ancho:
  * `Column 1`: Primer widget de contenido (`content6`).
  * `Column 2`: Segundo widget de contenido (`content7`).
  * `Column 3`: Tercer widget de contenido (`content8`).
* **Algoritmo de división**:
  ```python
  c_first = sec.find(attrs={'data-name': re.compile(r'first')})
  c_second = sec.find(attrs={'data-name': re.compile(r'second')})
  c_third = sec.find(attrs={'data-name': re.compile(r'third')})
  # Si los contenedores no tienen data-name explícito, divide los widgets en 3 bloques
  ```

#### 4. Content Over Background Image (`layout_type: 'over-background-image'`)
* **Estructura**: Secciones con banners fotográficos o texturas como fondo:
  * En el **Page Designer Sidebar**: Se le asigna la bandera `has_bg_image: True` y se renderiza el ícono de fotografía **`🖼️`**.
  * En el **Composer Canvas**: Aplica un contenedor `.ddc-bg-image-section` con la imagen de fondo y un overlay translúcido donde se ubican los widgets superpuestos.

#### 5. Inventory Search Results (`layout_type: 'inventory-search-results'`)
* **Estructura**: Identifica el contenedor split de SRP (Search Results Page):
  * **Columna Izquierda (Facetas)**: `ws-inv-facets (Inventory-facets1)` con filtros por año, marca, modelo, precio.
  * **Columna Derecha (Listado)**: `ws-inv-listing (Inventory-results1)` con las tarjetas de vehículos del inventario.

---

### D. Replicación Visual de Widgets (Composer UI Look & Feel)

Cada widget renderizado en el Canvas replica el diseño visual de Composer:
1. **Barra de Herramientas Superior**: Fondo gris (`#e4e4e4`), borde sutil, ícono de documento o tipo de widget a la izquierda, título oficial en tipografía Helvetica/Arial clara, y a la derecha los **4 botones estándar de Composer**:
   * `ℹ️ Info` (Información del componente)
   * `📂 Props` (Propiedades y configuración)
   * `🖥️ Preview` (Vista previa en dispositivo)
   * `❌ Delete` (Eliminar del layout)
2. **Cuerpo del Widget**: Recuadro con bordes punteados suaves (`1px dashed #bbb`) y texto auxiliar descriptivo:
   * WYSIWYG: *"Space for entering in WYSIWYG content."*
   * Disclaimer: *"Widget for dynamically pulling in disclaimer text."*
   * Dynamic Map: *"Google Maps dealership location"*.
   * Quick Links: *"Navigation Links (X links)"*.

---

## 2. El Banco de Imágenes (Image Harvester & Image Bank Engine)

Los archivos principales son:
* [`image_harvester.py`](file:///c:/Users/Diego%20PC/Documents/Diego/Proyectos/h1-checker-main/h1-checker-main/image_harvester.py): Motor de extracción y clasificación inteligente.
* [`image_bank_db.py`](file:///c:/Users/Diego%20PC/Documents/Diego/Proyectos/h1-checker-main/h1-checker-main/image_bank_db.py): Capa de persistencia SQLite (`image_bank.db`).

---

### A. Taxonomía y Detección de Vehículos
El motor cuenta con un diccionario de 16 marcas automotrices principales (`AUTO_MAKES`) con sus respectivos modelos:
* `Ford`: Bronco, F-150, Explorer, Mustang, Edge, Escape, etc.
* `Chevrolet`: Silverado, Tahoe, Suburban, Equinox, Corvette, etc.
* `Subaru`: Outback, Forester, Crosstrek, Ascent, Impreza, WRX, etc.
* `Toyota`, `Jeep`, `RAM`, `Dodge`, `GMC`, `Honda`, `Nissan`, `Hyundai`, `Kia`, etc.

#### Inferencia Multicriterio
Determina automáticamente:
1. **Marca y Modelo**: Cruzando la URL, el `Page Title`, el primer encabezado `<h1>` y el nombre del archivo de imagen.
2. **Condición**: Identifica si es `new`, `used` o `cpo` (Certified Pre-Owned).

---

### B. Categorización Temática por Palabras Clave
Clasifica cada imagen en una de 6 categorías funcionales según los atributos `alt`, `title`, clases CSS y texto circundante:
1. **`performance`**: `engine`, `horsepower`, `towing`, `torque`, `mpg`, `awd`, `ecoboost`, `v6`, `v8`, etc.
2. **`exterior`**: `wheel`, `grille`, `body`, `led`, `headlight`, `styling`, `tires`, `bumper`, etc.
3. **`interior`**: `cabin`, `seat`, `leather`, `cargo`, `dashboard`, `console`, `panoramic`, `space`, etc.
4. **`safety`**: `airbag`, `blind spot`, `braking`, `collision`, `camera`, `sensor`, `driver assist`, etc.
5. **`technology`**: `touchscreen`, `sync`, `infotainment`, `apple carplay`, `android auto`, `audio`, `wifi`, etc.
6. **`trims`**: Paquetes y versiones (`badlands`, `rubicon`, `denali`, `xlt`, `lariat`, `overland`, etc.).

---

### C. Filtros de Exclusión Inteligente
Para evitar contaminar el banco con basura o íconos del sitio, se descartan automáticamente:
* Extensiones vectoriales: `.svg`.
* UI Assets: `logo`, `icon`, `badge`, `avatar`, `pixel`, `tracking`, `spinner`, `blank.gif`.
* Redes sociales y proveedores externos: `facebook`, `twitter`, `instagram`, `carfax`, `autocheck`.
* Menús y navegación: `nav-`, `menu-`, `footer-`, `header-`, `spacer`.

---

### D. Esquema de Persistencia SQLite (`image_bank.db`)
* **Tabla `image_assets`**:
  * `image_url` (UNIQUE): URL absoluta de alta resolución de la imagen.
  * `make`, `model`, `condition`, `category`.
  * `surrounding_text`, `alt_text`, `section_title`, `dealer_id`.
  * `use_count`: Contador de veces que se ha visto la imagen en diferentes páginas.
  * `first_seen`, `last_seen`.
* **Tabla `image_occurrences`**:
  * Registro de auditoría histórica relacionando `image_url`, `page_url`, `case_id` y `timestamp`.
* **Índices**: Optimizados para búsquedas instantáneas por marca, modelo, categoría y conteo de uso.

---

## 3. El Sistema de Auditoría y Reporte de Bugs

El sistema realiza una auditoría automatizada integral y genera reportes reproducibles tanto en UI interactiva como en PDF y portapapeles.

---

### A. Clasificación de Severidad y Categorías de Bugs
Cada bug se modela como un objeto JSON estructurado con los siguientes atributos estándar:
* **Severidad (`type`)**:
  * `Failed`: Incumplimiento crítico de requerimiento (ej. H1 faltante, enlace roto 404 en CTA principal, discrepancia en modelo de inventario).
  * `Issue`: Problema de mediana prioridad (ej. enlace absoluto en lugar de relativo, advertencias de sitemap).
  * `Observed`: Observación informativa o de estilo (ej. falta clase `w-100` en imagen, texto alternativo muy corto).
* **Plataforma (`platform`)**:
  * `D`: Solo afecta versión Desktop.
  * `M`: Solo afecta versión Mobile.
  * `D/M` o `M/D`: Afecta ambas plataformas.
* **Categorías (`category`)**:
  * `Layout`: Problemas de estructura, múltiples H1, secciones desalineadas.
  * `Content`: Errores de texto, incoherencia semántica, falta de cobertura de texto SEO entregable.
  * `Link`: Enlaces 404, anclas `#id` inexistentes, enlaces que no abren en nueva pestaña.
  * `Form`: Errores en fuentes de Lead Forms o campos de contacto.
  * `Styling`: Clases CSS faltantes en imágenes responsivas.
  * `Inventory`: Discrepancias entre los filtros solicitados en el ticket y la URL final de búsqueda generada.

---

### B. Módulos de Auditoría Automatizada

1. **H1 & Title Hierarchy**:
   * Verifica que exista exactamente **1 H1 principal**.
   * Filtra falsos positivos (popups promocionales o widgets con `aria-level="2"`).
   * Compara el texto del H1 contra el `expected_title` del ticket.

2. **Validación de Enlaces y CTAs (Concurrente)**:
   * Extrae los enlaces internos y botones de acción.
   * Utiliza un `ThreadPoolExecutor` con **15 workers concurrentes** enviando peticiones `HEAD` (y `GET` condicional con timeout estricto) para validar códigos de estado `404`, `500` o bloqueos.
   * Detecta anclas rotas (`#href`) verificando que el ID destino exista en el DOM.

3. **Verificación Mobile con Renderer DDC**:
   * Realiza una segunda petición inyectando el parámetro oficial de Dealer.com:
     `url + '?_renderer=mobile'`
   * Compara la cobertura de texto en Mobile contra Desktop para detectar si el diseñador ocultó accidentalmente el contenido SEO en móviles.

4. **Captura Automatizada de Evidencias (Screenshots con Selenium)**:
   * Cuando se ejecuta en entorno local con Chrome disponible, el worker adjunta una sesión de Chrome (o inicia una en modo debug port 9222).
   * Localiza los selectores XPath del elemento con fallo, le aplica un contorno rojo (`outline: 4px solid red; box-shadow: inset 0 0 0 5px red;`), hace scroll centrado y toma una captura recortada que se adjunta al reporte.

5. **Motor de Aprendizaje Adaptativo de Inventario (`inventory_learner.py`)**:
   * Almacena reglas y excepciones históricas por concesionario en `inventory_patterns.json`.
   * Permite guardar correcciones manuales vía `/api/save-correction` para que futuras auditorías del mismo dealer infieran los filtros con 100% de precisión.

---

## 4. Estructura de Archivos Clave para Antigravity

```text
h1-checker-main/
├── app.py                      # Servidor Flask, lógica de extracción y endpoints
├── image_harvester.py          # Extracción y clasificación de imágenes
├── image_bank_db.py            # Persistencia de imágenes en SQLite (image_bank.db)
├── inventory_learner.py        # Aprendizaje de patrones de inventario
├── semantic_qa.py              # Análisis de coherencia semántica con embeddings
├── static/                     # Archivos estáticos para ejecución local con Flask
│   ├── script.js               # Frontend reactivo (sincronizado con vercel/public)
│   └── styles.css              # Estilos y visualización Composer (sincronizado)
└── vercel/
    └── public/                 # Archivos estáticos para despliegue en Vercel
        ├── script.js           # Idéntico a static/script.js
        └── styles.css          # Idéntico a static/styles.css
```

### Reglas de Mantenimiento de Código:
* **Sincronización Obligatoria**: Cualquier cambio realizado en `vercel/public/script.js` o `vercel/public/styles.css` debe copiarse idénticamente a `static/script.js` y `static/styles.css` (o viceversa).
* **Compatibilidad de Plataforma**: El backend debe seguir funcionando tanto localmente en Windows (`python app.py` escuchando en `http://127.0.0.1:5000`) como en producción serverless con Vercel.
