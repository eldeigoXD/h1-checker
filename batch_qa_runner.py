#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
==============================================================================
  BATCH QA RUNNER - MASSIVE & SCALABLE AUTOMATION
  Integration: Helium/Chrome (CDP) + Smartsheet + Dynamics 365 + Local QA Engine
==============================================================================
Filtro:
  - QA Completed By: "Diego Torrez"
  - QA Status: "In progress"

Workflow per task:
  1. Extracts Deliverable ID (e.g. D-136569) and CMS link from Smartsheet.
  2. Searches and opens deliverable in Dynamics 365, extracting target H1 title,
     completed copy, links/CTAs, and final URL.
  3. Audits the live page with the QA engine (H1, links, inventory, content).
  4. If clean (0 bugs): marks "Passed" in Smartsheet and saves.
  5. If bugs detected: leaves intact in Smartsheet and details in the report.
  6. Displays executive summary upon completion and keeps terminal open.
"""

import sys
import os
import time
import re
import json
import datetime
import difflib
from urllib.parse import urlparse

# Selenium to connect to browser already running on port 9222
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("❌ Error: Selenium is not installed in this environment. Run: pip install selenium")
    sys.exit(1)

# Import existing audit engine or fallback to standalone engine
try:
    import app
    from bs4 import BeautifulSoup
except ImportError:
    app = None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None

try:
    import requests
    # Suppress SSL warnings in corporate environments
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

# Terminal colors for Windows / Unix
class TermColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def log_info(msg):
    print(f"{TermColors.CYAN}[INFO]{TermColors.END} {msg}")

def log_success(msg):
    print(f"{TermColors.GREEN}[OK]{TermColors.END} {msg}")

def log_warn(msg):
    print(f"{TermColors.YELLOW}[AVISO]{TermColors.END} {msg}")

def log_error(msg):
    print(f"{TermColors.RED}[ERROR]{TermColors.END} {msg}")

def log_header(msg):
    print(f"\n{TermColors.BOLD}{TermColors.BLUE}=== {msg} ==={TermColors.END}")


# ==============================================================================
# 1. HELIUM / CHROMIUM CDP CONNECTION (PORT 9222)
# ==============================================================================
def connect_to_browser(debugger_address="127.0.0.1:9222"):
    log_info(f"Attempting to connect to browser at {debugger_address}...")
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_address)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        log_success("Successfully connected to open Helium/Chrome browser.")
        return driver
    except Exception as e:
        log_error(f"Could not connect to {debugger_address}.")
        print(f"\n{TermColors.YELLOW}👉 Help:")
        print("1. Close your browser and reopen it with port 9222 enabled.")
        print("2. You can run 'lanzar_helium_sesion.bat' or append:")
        print("   --remote-debugging-port=9222 to your Helium shortcut.")
        print(f"Technical error: {e}{TermColors.END}\n")
        return None


# ==============================================================================
# 2. TAB IDENTIFICATION (SMARTSHEET & DYNAMICS 365)
# ==============================================================================
def identify_tabs(driver):
    handles = driver.window_handles
    smartsheet_handle = None
    dynamics_handle = None
    
    for h in handles:
        try:
            driver.switch_to.window(h)
            url = (driver.current_url or '').lower()
            title = (driver.title or '').lower()
            
            if 'smartsheet.com' in url or 'report to start qa' in title or 'smartsheet' in title:
                smartsheet_handle = h
                log_success(f"Smartsheet tab found: '{driver.title}'")
            elif 'dynamics.com' in url or 'powerapps.com' in url:
                dynamics_handle = h
                log_success(f"Dynamics 365 tab found: '{driver.title}'")
        except Exception:
            continue
            
    if not smartsheet_handle:
        log_warn("No open Smartsheet tab found. Please open your QA report in Helium.")
    if not dynamics_handle:
        log_warn("No open Dynamics 365 tab found. Please open Dynamics in Helium.")
        
    return smartsheet_handle, dynamics_handle


# ==============================================================================
# 3. SMARTSHEET TASK EXTRACTION & FILTERING
# ==============================================================================
EXTRACT_SMARTSHEET_JS = """
return (function() {
    try {
        var results = [];
        var seenIds = new Set();
        var docs = [document];
        try {
            var iframes = document.querySelectorAll('iframe');
            for (var f = 0; f < iframes.length; f++) {
                var d = iframes[f].contentDocument || iframes[f].contentWindow.document;
                if (d && docs.indexOf(d) === -1) docs.push(d);
            }
        } catch(e) {}

        for (var docIdx = 0; docIdx < docs.length; docIdx++) {
            var doc = docs[docIdx];
            
            // 1. Mapear columnas a partir de los encabezados de la cuadrícula si existen
            var headers = doc.querySelectorAll('[role="columnheader"], .grid-header-cell, th, [data-client-id*="header"]');
            var qaStatusColIdx = -1;
            var completedByColIdx = -1;
            var delIdColIdx = -1;
            
            for (var h = 0; h < headers.length; h++) {
                var hText = (headers[h].innerText || headers[h].textContent || '').trim().toLowerCase();
                if (hText.indexOf('qa status') !== -1) {
                    qaStatusColIdx = h;
                } else if (hText.indexOf('completed by') !== -1 || hText.indexOf('qa completed') !== -1 || hText.indexOf('assigned') !== -1) {
                    completedByColIdx = h;
                } else if (hText.indexOf('deliverable id') !== -1 || hText.indexOf('deliverable') !== -1 || hText.indexOf('ticket') !== -1) {
                    delIdColIdx = h;
                }
            }

            // 2. Buscar filas reales (excluyendo contenedores padre que envuelven varias filas)
            var allRows = doc.querySelectorAll('[role="row"], .grid-row, .clsGridRow, tr');
            
            for (var rIdx = 0; rIdx < allRows.length; rIdx++) {
                var r = allRows[rIdx];
                if (r.getAttribute('role') === 'columnheader' || r.querySelector('[role="columnheader"]') || r.tagName === 'TH') continue;
                if (r.querySelectorAll('[role="row"], .grid-row, .clsGridRow, tr').length > 0) continue;

                var rowText = (r.innerText || r.textContent || '').trim();
                var rowTextLow = rowText.toLowerCase();

                // FILTRO BÁSICO: La fila debe corresponder a Diego Torrez y tener 'in progress'
                if ((rowTextLow.indexOf('diego torr') === -1 && rowTextLow.indexOf('diego t') === -1) || 
                    (rowTextLow.indexOf('in progress') === -1 && rowTextLow.indexOf('in-progress') === -1)) {
                    continue;
                }

                var cells = r.querySelectorAll('[role="gridcell"], td, .grid-cell, .clsGridCell');
                var isMatch = false;

                if (cells.length > 0 && qaStatusColIdx !== -1 && completedByColIdx !== -1 && cells.length > Math.max(qaStatusColIdx, completedByColIdx)) {
                    var statusCellTxt = (cells[qaStatusColIdx].innerText || '').trim().toLowerCase();
                    var byCellTxt = (cells[completedByColIdx].innerText || '').trim().toLowerCase();
                    
                    // Si el estado en la columna de status es explícitamente passed o failed, saltar
                    if (statusCellTxt === 'passed' || statusCellTxt === 'failed') {
                        continue;
                    }

                    if ((statusCellTxt.indexOf('in progress') !== -1 || statusCellTxt.indexOf('in-progress') !== -1) && 
                        (byCellTxt.indexOf('diego torr') !== -1 || byCellTxt.indexOf('diego t') !== -1)) {
                        isMatch = true;
                    }
                } else if (cells.length > 0) {
                    var hasInProgressCell = false;
                    var hasDiegoCell = false;
                    var isExplicitlyPassedFailed = false;
                    
                    for (var c = 0; c < cells.length; c++) {
                        var cText = (cells[c].innerText || '').trim().toLowerCase();
                        if (cText === 'in progress' || cText.indexOf('in progress') !== -1 || cText.indexOf('in-progress') !== -1) {
                            hasInProgressCell = true;
                        }
                        if (cText.indexOf('diego torr') !== -1 || cText.indexOf('diego t') !== -1) {
                            hasDiegoCell = true;
                        }
                        if (cText === 'failed' || cText === 'passed') {
                            isExplicitlyPassedFailed = true;
                        }
                    }
                    
                    if (hasInProgressCell && hasDiegoCell && !isExplicitlyPassedFailed) {
                        isMatch = true;
                    }
                } else {
                    if ((rowTextLow.indexOf('diego torr') !== -1 || rowTextLow.indexOf('diego t') !== -1) && 
                        (rowTextLow.indexOf('in progress') !== -1 || rowTextLow.indexOf('in-progress') !== -1)) {
                        isMatch = true;
                    }
                }

                if (isMatch) {
                    var m = rowText.match(/\\b(D-\\d+)\\b/i);
                    var idVal = m ? m[1].toUpperCase() : '';

                    if (idVal && !seenIds.has(idVal)) {
                        seenIds.add(idVal);

                        var cmsVal = '';
                        var links = r.querySelectorAll('a');
                        for (var l = 0; l < links.length; l++) {
                            var h = (links[l].href || links[l].getAttribute('href') || '').trim();
                            if (h && h.indexOf('smartsheet.com') === -1 && h.indexOf('coxauto') === -1 && !h.startsWith('javascript:')) {
                                cmsVal = h;
                                break;
                            }
                        }
                        if (!cmsVal) {
                            var mUrl = rowText.match(/https?:\\/\\/[^\\s\\)\\'\\"]+/i);
                            if (mUrl && mUrl[0].indexOf('smartsheet') === -1 && mUrl[0].indexOf('coxauto') === -1) {
                                cmsVal = mUrl[0];
                            }
                        }
                        if (!cmsVal) {
                            var mWww = rowText.match(/\\bwww\\.[a-zA-Z0-9_\\-\\.\\/]+\\b/i);
                            if (mWww && mWww[0].indexOf('smartsheet') === -1) {
                                cmsVal = 'https://' + mWww[0];
                            }
                        }

                        results.push({
                            row_index: rIdx,
                            deliverable_id: idVal,
                            cms_link: cmsVal,
                            about: '',
                            status: 'In progress',
                            completed_by: 'Diego Torrez'
                        });
                    }
                }
            }
            if (results.length > 0) break;
        }

        return {
            total_found: results.length,
            tasks: results
        };
    } catch(err) {
        return {
            error: String(err),
            total_found: 0,
            tasks: []
        };
    }
})();
"""

def extract_smartsheet_tasks(driver, smartsheet_handle):
    driver.switch_to.window(smartsheet_handle)
    time.sleep(1)
    
    log_info("Extracting tasks assigned to 'Diego Torrez' with status 'In progress'...")
    
    # 1. Regresar la cuadrícula virtualizada arriba del todo antes de escanear
    try:
        driver.execute_script("""
            var g = document.querySelector('.ReactVirtualized__Table__Grid, .ReactVirtualized__Grid, .grid-view-body, [role="grid"]');
            if (g) g.scrollTop = 0;
        """)
        time.sleep(0.8)
    except Exception:
        pass

    all_tasks = []
    seen_ids = set()

    # 2. Escaneo con scroll virtualizado continuo para no omitir filas fuera de pantalla
    max_scroll_steps = 25
    for s_step in range(max_scroll_steps):
        try:
            data = driver.execute_script(EXTRACT_SMARTSHEET_JS)
            tasks = data.get('tasks', []) if isinstance(data, dict) else []
            for t in tasks:
                d_id = t.get('deliverable_id')
                if d_id and d_id not in seen_ids:
                    seen_ids.add(d_id)
                    all_tasks.append(t)
        except Exception as e:
            log_warn(f"Error en paso de scroll {s_step} de Smartsheet: {e}")

        # Avanzar el scroll hacia abajo
        scroll_res = driver.execute_script("""
            var g = document.querySelector('.ReactVirtualized__Table__Grid, .ReactVirtualized__Grid, .grid-view-body, [role="grid"]');
            if (!g) return { at_bottom: true };
            var prev = g.scrollTop;
            g.scrollTop += 350;
            var at_bottom = (g.scrollTop + g.clientHeight >= g.scrollHeight - 10) || (g.scrollTop === prev);
            return { at_bottom: at_bottom, top: g.scrollTop, height: g.scrollHeight };
        """)
        time.sleep(0.6)

        if scroll_res and scroll_res.get('at_bottom'):
            # Último chequeo al llegar al fondo
            try:
                data = driver.execute_script(EXTRACT_SMARTSHEET_JS)
                tasks = data.get('tasks', []) if isinstance(data, dict) else []
                for t in tasks:
                    d_id = t.get('deliverable_id')
                    if d_id and d_id not in seen_ids:
                        seen_ids.add(d_id)
                        all_tasks.append(t)
            except Exception:
                pass
            break

    # 3. Devolver la vista al inicio para comodidad del usuario
    try:
        driver.execute_script("""
            var g = document.querySelector('.ReactVirtualized__Table__Grid, .ReactVirtualized__Grid, .grid-view-body, [role="grid"]');
            if (g) g.scrollTop = 0;
        """)
    except Exception:
        pass

    log_success(f"Found {len(all_tasks)} tasks ready for audit in Smartsheet across entire sheet.")
    return all_tasks


# ==============================================================================
# 4. DYNAMICS 365 DELIVERABLES EXTRACTION & SEARCH
# ==============================================================================

# Script 1: Check if target deliverable is already open on active screen
CHECK_IF_CURRENT_DYNAMICS_RECORD_JS = """
return (function() {
    var targetId = '%s';
    var DYNAMICS_ICON_REGEX = /[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\u007F-\\u009F\\u200B-\\u200D\\u202A-\\u202E\\u2500-\\u25FF\\u2600-\\u27BF\\uE000-\\uF8FF\\uFFF0-\\uFFFF]/g;
    function clean(v) { return v ? v.replace(DYNAMICS_ICON_REGEX, '').trim() : ''; }
    
    var docs = [document];
    try {
        var iframes = document.querySelectorAll('iframe');
        for (var f = 0; f < iframes.length; f++) {
            var d = iframes[f].contentDocument || (iframes[f].contentWindow && iframes[f].contentWindow.document);
            if (d && docs.indexOf(d) === -1) docs.push(d);
        }
    } catch(e) {}

    for (var d = 0; d < docs.length; d++) {
        var doc = docs[d];
        var idEls = doc.querySelectorAll('[data-id*="deliverablenumber" i], [data-id*="deliverableid" i], [data-id*="ticketnumber" i]');
        for (var i = 0; i < idEls.length; i++) {
            var val = clean(idEls[i].value || idEls[i].innerText || idEls[i].textContent || '');
            if (val.toUpperCase().indexOf(targetId.toUpperCase()) !== -1) {
                return { is_match: true, current_id: val };
            }
        }
    }
    
    var urlParams = new URLSearchParams(window.location.search);
    var qId = urlParams.get('id') || '';
    if (qId.toUpperCase().indexOf(targetId.toUpperCase()) !== -1) {
        return { is_match: true, current_id: qId };
    }

    return { is_match: false };
})();
"""

# URL oficial de la vista de Deliverables en Dynamics 365
DYNAMICS_DELIVERABLES_VIEW_URL = "https://orgba6d8fe6.crm.dynamics.com/main.aspx?appid=df9dfe4b-95a6-ef11-8a6a-0022480c6fc8&forceUCI=1&pagetype=entitylist&etn=ddcms_campaigndeliverable&viewid=53716d02-f24b-f011-8779-00224833de88&viewType=1039"

# Script 2: Escribe el ID en la barra de búsqueda global superior (barra azul de Dynamics) y presiona Enter
EXECUTE_DYNAMICS_TOP_HEADER_SEARCH_JS = """
var targetId = arguments[0];
var done = arguments[arguments.length - 1];

(function() {
    try {
        var docs = [document];
        try {
            var iframes = document.querySelectorAll('iframe');
            for (var f = 0; f < iframes.length; f++) {
                var d = iframes[f].contentDocument || (iframes[f].contentWindow && iframes[f].contentWindow.document);
                if (d && docs.indexOf(d) === -1) docs.push(d);
            }
        } catch(e) {}

        // Selectores específicos del buscador superior en la barra azul (NUNCA el filtro de la cuadrícula)
        var topSearchSelectors = [
            'header input[aria-label*="Search" i]',
            'header input[placeholder*="Search" i]',
            'header input',
            '[role="banner"] input[aria-label*="Search" i]',
            '[role="banner"] input[placeholder*="Search" i]',
            '[role="banner"] input',
            '#shell-container input[aria-label*="Search" i]',
            '#shell-container input',
            '[data-id="topBar"] input',
            'input[aria-label="Search this app"]',
            'input[placeholder="Search this app"]',
            'input[aria-label="Search"]',
            'input[placeholder="Search"]',
            '#searchBox',
            'input[id*="searchBox" i]',
            'input[data-id="search-input"]',
            'input[type="search"]'
        ];

        var foundInput = null;

        for (var docIdx = 0; docIdx < docs.length; docIdx++) {
            var doc = docs[docIdx];
            for (var s = 0; s < topSearchSelectors.length; s++) {
                var candidates = doc.querySelectorAll(topSearchSelectors[s]);
                for (var c = 0; c < candidates.length; c++) {
                    var el = candidates[c];
                    var aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    var placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                    var idStr = (el.id || '').toLowerCase();
                    var dataId = (el.getAttribute('data-id') || '').toLowerCase();
                    
                    // REGLA CRÍTICA: Descartar tajantemente el filtro de cuadrícula (Filter by keyword / Edit filters)
                    if (aria.indexOf('filter') !== -1 || placeholder.indexOf('filter') !== -1 ||
                        aria.indexOf('keyword') !== -1 || placeholder.indexOf('keyword') !== -1 ||
                        idStr.indexOf('quickfind') !== -1 || dataId.indexOf('quickfind') !== -1 ||
                        aria.indexOf('view') !== -1) {
                        continue;
                    }

                    if (el.offsetWidth > 0 || el.offsetHeight > 0) {
                        foundInput = el;
                        break;
                    }
                }
                if (foundInput) break;
            }
            if (foundInput) break;
        }

        // Si la barra superior está colapsada como botón en el header azul, hacer clic para desplegarla
        if (!foundInput) {
            for (var d2 = 0; d2 < docs.length; d2++) {
                var doc2 = docs[d2];
                var topBtn = doc2.querySelector('header button[aria-label*="Search" i], [role="banner"] button[aria-label*="Search" i], #searchLauncher');
                if (topBtn) {
                    topBtn.click();
                    break;
                }
            }
        }

        setTimeout(function() {
            if (!foundInput) {
                for (var d3 = 0; d3 < docs.length; d3++) {
                    var doc3 = docs[d3];
                    for (var s3 = 0; s3 < topSearchSelectors.length; s3++) {
                        var cands3 = doc3.querySelectorAll(topSearchSelectors[s3]);
                        for (var c3 = 0; c3 < cands3.length; c3++) {
                            var el3 = cands3[c3];
                            var a3 = (el3.getAttribute('aria-label') || '').toLowerCase();
                            var p3 = (el3.getAttribute('placeholder') || '').toLowerCase();
                            var i3 = (el3.id || '').toLowerCase();
                            if (a3.indexOf('filter') === -1 && p3.indexOf('filter') === -1 && i3.indexOf('quickfind') === -1) {
                                foundInput = el3;
                                break;
                            }
                        }
                        if (foundInput) break;
                    }
                    if (foundInput) break;
                }
            }

            if (foundInput) {
                foundInput.focus();
                foundInput.click();
                foundInput.value = '';
                foundInput.value = targetId;
                foundInput.dispatchEvent(new Event('input', { bubbles: true }));
                foundInput.dispatchEvent(new Event('change', { bubbles: true }));

                // Disparar Enter para que busque globalmente
                var ke = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, keyCode: 13, which: 13, key: 'Enter' });
                foundInput.dispatchEvent(ke);
                var kp = new KeyboardEvent('keypress', { bubbles: true, cancelable: true, keyCode: 13, which: 13, key: 'Enter' });
                foundInput.dispatchEvent(kp);
                var ku = new KeyboardEvent('keyup', { bubbles: true, cancelable: true, keyCode: 13, which: 13, key: 'Enter' });
                foundInput.dispatchEvent(ku);

                var parent = foundInput.parentElement;
                if (parent) {
                    var btn = parent.querySelector('button, [role="button"], span[id*="search"], i, span[data-icon-name*="Search"]');
                    if (btn) {
                        try { btn.click(); } catch(e) {}
                    }
                }

                done({
                    success: true,
                    selector: foundInput.getAttribute('aria-label') || foundInput.id || foundInput.placeholder || 'top_search',
                    value: targetId
                });
            } else {
                done({ success: false, reason: 'No se encontro el buscador superior en la barra azul' });
            }
        }, 300);

    } catch(err) {
        done({ success: false, error: String(err) });
    }
})();
"""

# Script 3: Busca la fila con el Deliverable ID exacto y hace clic en el enlace/task para abrirlo
CLICK_EXACT_DELIVERABLE_TASK_JS = """
var targetId = arguments[0].trim().toUpperCase();
var done = arguments[arguments.length - 1];

(function() {
    var docs = [document];
    try {
        var iframes = document.querySelectorAll('iframe');
        for (var f = 0; f < iframes.length; f++) {
            var d = iframes[f].contentDocument || (iframes[f].contentWindow && iframes[f].contentWindow.document);
            if (d && docs.indexOf(d) === -1) docs.push(d);
        }
    } catch(e) {}

    var matchedRow = null;
    var clickTarget = null;
    var matchedText = '';

    for (var dIdx = 0; dIdx < docs.length; dIdx++) {
        var doc = docs[dIdx];
        var rows = doc.querySelectorAll('[role="row"], .ag-row, .ms-DetailsRow, tr, div[data-id*="row-"], [role="option"], li[role="option"], [data-id*="searchsuggestion"], [data-id*="searchresult"], li.ms-Suggestions-item, [role="listbox"] li');
        
        for (var r = 0; r < rows.length; r++) {
            var row = rows[r];
            if (row.getAttribute('role') === 'columnheader' || row.querySelector('[role="columnheader"]')) continue;
            
            var rowText = (row.innerText || row.textContent || '').trim();
            var re = new RegExp('\\\\b' + targetId.replace('-', '\\\\-') + '\\\\b', 'i');
            
            if (re.test(rowText)) {
                matchedRow = row;
                matchedText = rowText.substring(0, 100);
                
                var link = row.querySelector('a[role="link"], a[data-id*="name" i], a[href*="id="], a[href*="main.aspx"], a, button');
                if (link) {
                    clickTarget = link;
                } else {
                    var cell = row.querySelector('[data-id*="name" i], [role="gridcell"]');
                    clickTarget = cell || row;
                }
                break;
            }
        }
        if (matchedRow) break;
    }

    if (!clickTarget) {
        // Fallback: buscar directamente cualquier elemento clickable cuyo texto contenga el targetId exacto
        for (var d2 = 0; d2 < docs.length; d2++) {
            var doc2 = docs[d2];
            var anyLinks = doc2.querySelectorAll('a, button, [role="link"], [role="button"], span, div');
            for (var a = 0; a < anyLinks.length; a++) {
                var elText = (anyLinks[a].innerText || anyLinks[a].textContent || '').trim();
                var re2 = new RegExp('\\\\b' + targetId.replace('-', '\\\\-') + '\\\\b', 'i');
                if (re2.test(elText) && (anyLinks[a].offsetWidth > 0 || anyLinks[a].offsetHeight > 0)) {
                    clickTarget = anyLinks[a];
                    matchedText = elText.substring(0, 100);
                    break;
                }
            }
            if (clickTarget) break;
        }
    }

    if (clickTarget) {
        clickTarget.scrollIntoView({ behavior: 'smooth', block: 'center' });
        clickTarget.click();
        
        // Disparar doble clic por si el grid UCI requiere dblclick para abrir el registro
        var dblEvent = new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window });
        clickTarget.dispatchEvent(dblEvent);
        
        done({ success: true, text: matchedText });
    } else {
        done({ success: false, reason: 'No se encontro fila ni sugerencia con el Deliverable ID exacto: ' + targetId });
    }
})();
"""

# Script 4: Extractor completo y robusto de campos del formulario Dynamics (UCI)
EXTRACT_DYNAMICS_DOM_JS = """
return (function() {
    var DYNAMICS_ICON_REGEX = /[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\u007F-\\u009F\\u200B-\\u200D\\u202A-\\u202E\\u2500-\\u25FF\\u2600-\\u27BF\\uE000-\\uF8FF\\uFFF0-\\uFFFF]/g;

    function cleanFieldText(val) {
        if (!val) return '';
        return val.replace(DYNAMICS_ICON_REGEX, '').trim();
    }

    function cleanCtaPayload(val) {
        if (!val) return '';
        var cleaned = val.replace(DYNAMICS_ICON_REGEX, ' ').trim();
        var lines = cleaned.split(/[\\r\\n]+/).map(function(l) {
            var trimmed = l.replace(/^[•\\-\\*\\s\\u25A1\\u25A0\\u2022\\u00A0]+/g, '').trim();
            trimmed = trimmed.replace(/\\b(calls\\s*to\\s*action|links|ctas(\\s*and\\s*links)?)\\b/gi, '').trim();
            trimmed = trimmed.replace(/^[:\\-\\s\\t]+|[:\\-\\s\\t]+$/g, '').trim();
            return trimmed;
        }).filter(function(l) { return l && /[a-zA-Z0-9]/.test(l); });
        return lines.join('\\n');
    }

    function getDocs() {
        var docs = [document];
        try {
            var iframes = document.querySelectorAll('iframe');
            for (var f = 0; f < iframes.length; f++) {
                try {
                    var d = iframes[f].contentDocument || (iframes[f].contentWindow && iframes[f].contentWindow.document);
                    if (d && docs.indexOf(d) === -1) docs.push(d);
                } catch(e) {}
            }
        } catch(e) {}
        return docs;
    }

    function extractValFromEl(el, excludeKeys) {
        if (!el) return '';
        var dataId = (el.getAttribute('data-id') || '').toLowerCase();
        for (var k = 0; k < excludeKeys.length; k++) {
            if (dataId.indexOf(excludeKeys[k].toLowerCase()) !== -1) return '';
        }
        if (dataId.indexOf('label-container') !== -1 || dataId.indexOf('-label') !== -1 || el.tagName === 'LABEL') {
            return '';
        }
        var inps = el.querySelectorAll('input, textarea');
        for (var i = 0; i < inps.length; i++) {
            var iv = (inps[i].value || inps[i].getAttribute('value') || '').trim();
            if (iv) return iv;
        }
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            var ev = (el.value || el.getAttribute('value') || '').trim();
            if (ev) return ev;
        }
        var links = el.querySelectorAll('a');
        for (var j = 0; j < links.length; j++) {
            var aTxt = (links[j].innerText || links[j].textContent || '').trim();
            if (aTxt && !/^(open|visit|link|http|https|website|click|view)$/i.test(aTxt)) return aTxt;
            var aHref = (links[j].getAttribute('href') || '').trim();
            if (aHref && !aHref.startsWith('javascript:') && aHref !== '#' && aHref.indexOf('.') !== -1) return aHref;
        }
        var ctrls = el.querySelectorAll('[data-id*="fieldControl" i], [role="textbox"], [data-id*="value" i]');
        for (var c = 0; c < ctrls.length; c++) {
            var cTxt = (ctrls[c].innerText || ctrls[c].textContent || '').replace(DYNAMICS_ICON_REGEX, '').trim();
            if (cTxt) return cTxt;
        }
        var txt = (el.innerText || el.textContent || '').replace(DYNAMICS_ICON_REGEX, '').trim();
        return txt;
    }

    function getF(keys, excludeKeys, labelTexts) {
        excludeKeys = excludeKeys || [];
        keys = keys || [];
        labelTexts = labelTexts || [];
        var docs = getDocs();
        for (var d = 0; d < docs.length; d++) {
            var doc = docs[d];
            for (var i = 0; i < keys.length; i++) {
                var els = doc.querySelectorAll('[data-id*="' + keys[i] + '" i]');
                for (var j = 0; j < els.length; j++) {
                    var val = extractValFromEl(els[j], excludeKeys);
                    if (val && val.trim()) {
                        var isLbl = false;
                        for (var l = 0; l < labelTexts.length; l++) {
                            if (val.trim().toLowerCase() === labelTexts[l].toLowerCase()) {
                                isLbl = true;
                                break;
                            }
                        }
                        if (!isLbl) return val.trim();
                    }
                }
            }
        }
        if (labelTexts && labelTexts.length > 0) {
            for (var d2 = 0; d2 < docs.length; d2++) {
                var doc2 = docs[d2];
                for (var l2 = 0; l2 < labelTexts.length; l2++) {
                    var target = labelTexts[l2].toLowerCase();
                    var labels = doc2.querySelectorAll('label, span[role="presentation"]');
                    for (var b = 0; b < labels.length; b++) {
                        var lText = (labels[b].innerText || labels[b].textContent || '').replace(DYNAMICS_ICON_REGEX, '').replace(/[\\s\\*:]+/g, '').replace(/\\uD83D\\uDD12/g, '').trim().toLowerCase();
                        if (lText === target) {
                            var row = labels[b].parentElement;
                            for (var up = 0; up < 5 && row; up++) {
                                var inp = row.querySelector('input, textarea');
                                if (inp && inp.value && inp.value.trim() && inp.value.trim().toLowerCase() !== target) return inp.value.trim();
                                var lnk = row.querySelector('a');
                                if (lnk) {
                                    var lt = (lnk.innerText || lnk.textContent || '').trim();
                                    if (lt && lt.toLowerCase() !== target) return lt;
                                    var lh = (lnk.getAttribute('href') || '').trim();
                                    if (lh && lh.indexOf('.') !== -1 && !lh.startsWith('javascript:')) return lh;
                                }
                                var tb = row.querySelector('[role="textbox"], [data-id*="value" i]');
                                if (tb) {
                                    var tt = (tb.innerText || tb.textContent || '').replace(DYNAMICS_ICON_REGEX, '').trim();
                                    if (tt && tt.toLowerCase() !== target) return tt;
                                }
                                row = row.parentElement;
                            }
                        }
                    }
                }
            }
        }
        return '';
    }

    var delId = cleanFieldText(getF(['deliverablenumber.fieldControl', 'deliverableid.fieldControl', 'ticketnumber.fieldControl', 'deliverableid', 'deliverable_number']));
    if (!delId) {
        var params = new URLSearchParams(window.location.search);
        var rawId = params.get('id') || '';
        if (rawId) delId = rawId.split('-')[0].toUpperCase();
    }

    var title = cleanFieldText(getF([
        'ddcms_name.fieldControl', 'ddcms_name', 'ddcms_h1', 'ddcms_title',
        'h1title.fieldControl', 'targeth1.fieldControl', 'pagetitle.fieldControl', 'h1', 'name.fieldControl'
    ], ['account', 'customer', 'parentaccount', 'owner', 'createdby', 'modifiedby', 'header_crmformheader', 'dealer', 'quickview'],
    ['Target H1', 'H1 Title', 'Page Title', 'Title', 'H1']));

    var copy = cleanFieldText(getF([
        'completedcopy.fieldControl', 'completedcopy', 'ddcms_completedcopy.fieldControl', 'ddcms_completedcopy', 'copy.fieldControl'
    ], [], ['Completed Copy', 'Copy', 'Body Copy', 'Content']));

    var url = cleanFieldText(getF([
        'completedpageurl.fieldControl', 'completedpageurl',
        'ddcms_completedpageurl.fieldControl', 'ddcms_completedpageurl',
        'ddcms_pageurl.fieldControl', 'ddcms_pageurl',
        'ddcms_targeturl.fieldControl', 'ddcms_targeturl',
        'pageurl.fieldControl', 'pageurl',
        'targeturl.fieldControl', 'targeturl',
        'destinationurl.fieldControl', 'destinationurl',
        'url.fieldControl'
    ], [], ['Completed Page URL', 'Page URL', 'Completed URL', 'Target URL', 'Destination URL', 'URL', 'Live Page URL']));

    if (url) {
        var httpIdx = url.indexOf('http');
        var wwwIdx = url.indexOf('www.');
        if (httpIdx !== -1) {
            url = url.substring(httpIdx).split(/[\\s\\)\\'\\"]/)[0];
        } else if (wwwIdx !== -1) {
            url = 'https://' + url.substring(wwwIdx).split(/[\\s\\)\\'\\"]/)[0];
        }
    }

    var ctas = cleanCtaPayload(getF(['callstoaction.fieldControl', 'callstoaction', 'ddcms_callstoaction.fieldControl', 'ddcms_callstoaction'], [], ['Calls to Action', 'Call to Action', 'CTAs', 'CTA']));
    var links = cleanCtaPayload(getF(['links.fieldControl', 'links', 'ddcms_links.fieldControl', 'ddcms_links'], [], ['Links', 'CTAs and Links']));
    var combinedCtas = [];
    if (ctas) combinedCtas.push(ctas);
    if (links) combinedCtas.push(links);

    var details = cleanFieldText(getF(['ddcms_details.fieldControl', 'ddcms_details', 'details.fieldControl', 'details', 'specialinstructions'], ['copywriting'], ['Special Instructions', 'Details', 'Instructions']));
    var rawPageEx = cleanFieldText(getF(['ddcms_pageexample.fieldControl', 'ddcms_pageexample', 'pageexample.fieldControl', 'pageexample'], [], ['Page Example']));

    return {
        deliverable_id: delId,
        deliverable_url: window.location.href,
        title: title,
        copy: copy,
        url: url,
        ctas: combinedCtas.join('\\n'),
        details: details,
        page_example_raw: rawPageEx
    };
})();
"""

def format_dyn_data(raw_data, deliverable_id, cms_link):
    url = (raw_data.get('url') or '').strip()
    if not url:
        url = cms_link or ''
        
    return {
        'deliverable_id': deliverable_id,
        'deliverable_url': (raw_data.get('deliverable_url') or '').strip(),
        'title': (raw_data.get('title') or '').strip(),
        'copy': (raw_data.get('copy') or '').strip(),
        'url': url,
        'ctas': (raw_data.get('ctas') or '').strip(),
        'details': (raw_data.get('details') or '').strip(),
        'found': True
    }

def log_extracted_data(del_id, data, cms_link):
    title = data.get('title') or ''
    copy = data.get('copy') or ''
    url = data.get('url') or cms_link or ''
    ctas = data.get('ctas') or ''
    
    log_success(f"[{del_id}] ✓ Data successfully extracted from Dynamics:")
    print(f"   • Target H1: {TermColors.BOLD}'{title}'{TermColors.END}" if title else f"   • Target H1: {TermColors.YELLOW}(Empty){TermColors.END}")
    print(f"   • Destination URL: {TermColors.CYAN}{url}{TermColors.END}" if url else f"   • Destination URL: {TermColors.YELLOW}(Empty){TermColors.END}")
    print(f"   • Completed copy: {len(copy)} characters")
    cta_lines = [l for l in ctas.splitlines() if l.strip()]
    print(f"   • CTAs / Links: {len(cta_lines)} items")

def search_in_dynamics_header(driver, deliverable_id):
    """
    Actúa exactamente como Diego:
    Busca la barra de búsqueda en el header azul de Dynamics, hace clic,
    limpia el texto con Ctrl+A / Backspace, escribe el ID y presiona Enter.
    SIN recargar la página ni destruir la sesión SSO.
    """
    search_input = None
    
    top_search_selectors = [
        'header input[aria-label*="Search" i]',
        'header input[placeholder*="Search" i]',
        '[role="banner"] input[aria-label*="Search" i]',
        '[role="banner"] input[placeholder*="Search" i]',
        '#shell-container input[aria-label*="Search" i]',
        'input[aria-label="Search this app"]',
        'input[placeholder="Search this app"]',
        'input[aria-label="Search"]',
        'input[placeholder="Search"]',
        '#searchBox',
        'input[id*="searchBox" i]',
        'input[data-id="search-input"]',
        'header input',
        '[role="banner"] input'
    ]

    # Si hay botón de búsqueda colapsado en el header, hacer clic primero
    try:
        expand_btns = driver.find_elements(By.CSS_SELECTOR, 'header button[aria-label*="Search" i], [role="banner"] button[aria-label*="Search" i], #searchLauncher')
        for b in expand_btns:
            if b.is_displayed():
                b.click()
                time.sleep(0.3)
                break
    except Exception:
        pass

    for sel in top_search_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                if el.is_displayed():
                    aria = (el.get_attribute('aria-label') or '').lower()
                    placeholder = (el.get_attribute('placeholder') or '').lower()
                    id_attr = (el.get_attribute('id') or '').lower()
                    data_id = (el.get_attribute('data-id') or '').lower()
                    
                    # IGNORAR tajantemente el filtro de cuadrícula ("filter by keyword")
                    if any(bad in s for bad in ['filter', 'keyword', 'quickfind'] for s in [aria, placeholder, id_attr, data_id]):
                        continue
                    if 'view' in aria:
                        continue
                        
                    search_input = el
                    break
            if search_input:
                break
        except Exception:
            continue

    if search_input:
        try:
            search_input.click()
            time.sleep(0.2)
            search_input.send_keys(Keys.CONTROL + "a")
            time.sleep(0.1)
            search_input.send_keys(Keys.BACKSPACE)
            time.sleep(0.1)
            search_input.send_keys(deliverable_id)
            time.sleep(0.3)
            search_input.send_keys(Keys.ENTER)
            
            # Buscar e interactuar con el botón o icono de búsqueda adjunto
            try:
                parent = search_input.find_element(By.XPATH, "..")
                search_btn = parent.find_element(By.CSS_SELECTOR, 'button, [role="button"], span[id*="search"], i, span[data-icon-name*="Search"]')
                if search_btn and search_btn.is_displayed():
                    search_btn.click()
            except Exception:
                pass
            return True
        except Exception:
            pass

    # Fallback vía JavaScript en el DOM del header
    try:
        res = driver.execute_async_script(EXECUTE_DYNAMICS_TOP_HEADER_SEARCH_JS, deliverable_id)
        if res and res.get('success'):
            time.sleep(0.3)
            driver.switch_to.active_element.send_keys(Keys.ENTER)
            return True
    except Exception as e_js:
        log_warn(f"[{deliverable_id}] Top search bar JS attempt: {e_js}")
        
    return False

def fetch_dynamics_data(driver, dynamics_handle, deliverable_id, cms_link=""):
    if not dynamics_handle:
        return {'deliverable_id': deliverable_id, 'url': cms_link, 'title': '', 'copy': '', 'ctas': '', 'found': False}
        
    driver.switch_to.window(dynamics_handle)
    time.sleep(0.5)

    # 1. Comprobar si ya está abierto en pantalla el registro de este ID
    try:
        check_res = driver.execute_script(CHECK_IF_CURRENT_DYNAMICS_RECORD_JS % deliverable_id)
        if check_res and check_res.get('is_match'):
            log_info(f"[{deliverable_id}] Deliverable is already open on screen. Checking data load...")
            for _ in range(8):
                data = driver.execute_script(EXTRACT_DYNAMICS_DOM_JS)
                if data and (data.get('title') or data.get('copy') or data.get('url')):
                    time.sleep(1.5)
                    data = driver.execute_script(EXTRACT_DYNAMICS_DOM_JS) or data
                    log_extracted_data(deliverable_id, data, cms_link)
                    return format_dyn_data(data, deliverable_id, cms_link)
                time.sleep(1.0)
    except Exception as e:
        log_warn(f"[{deliverable_id}] Initial check in Dynamics: {e}")

    # 2. Actuar como Diego: Buscar en la barra azul superior (SIN recargar la página para no deslogear)
    log_info(f"[{deliverable_id}] Entering ID in top blue search bar (human mode)...")
    searched = search_in_dynamics_header(driver, deliverable_id)
    if not searched:
        log_warn(f"[{deliverable_id}] Could not activate top search bar.")

    # 3. Esperar a que aparezcan los resultados (3.5 segundos)
    log_info(f"[{deliverable_id}] Waiting for search results...")
    time.sleep(3.5)

    # 4. Seleccionar el task con el ID exacto haciendo clic en su enlace (Name)
    matched = False
    for attempt in range(1, 6):
        try:
            click_res = driver.execute_async_script(CLICK_EXACT_DELIVERABLE_TASK_JS, deliverable_id)
            if click_res and click_res.get('success'):
                log_success(f"[{deliverable_id}] Task selected in Dynamics: '{click_res.get('text', '')}'. Opening form...")
                matched = True
                break
        except Exception:
            pass
        time.sleep(1.2)

    if not matched:
        log_warn(f"[{deliverable_id}] Could not select task in Dynamics. Check if ID matches in list.")

    # 5. Esperar activamente a que cargue el formulario del deliverable con datos reales (hasta 25s)
    log_info(f"[{deliverable_id}] Waiting for Dynamics form to load data from Dataverse...")
    start_wait_form = time.time()
    data = None
    max_wait_form = 25
    target_id_clean = deliverable_id.upper().strip()

    while time.time() - start_wait_form < max_wait_form:
        time.sleep(1.5)
        try:
            # Scroll leve para forzar a Dynamics a instanciar componentes con lazy loading
            driver.execute_script("window.scrollTo(0, 150);")
            driver.execute_script("window.scrollTo(0, 0);")

            cand_data = driver.execute_script(EXTRACT_DYNAMICS_DOM_JS)
            if cand_data:
                cand_del_id = (cand_data.get('deliverable_id') or '').upper().strip()

                # Descartar si el DOM aún muestra un registro de otro Deliverable ID anterior
                if cand_del_id and cand_del_id != target_id_clean and target_id_clean not in cand_del_id and cand_del_id not in target_id_clean:
                    continue

                has_title = bool(cand_data.get('title') and len(cand_data['title'].strip()) >= 3)
                has_copy = bool(cand_data.get('copy') and len(cand_data['copy'].strip()) >= 10)
                has_url = bool(cand_data.get('url') and len(cand_data['url'].strip()) >= 10)

                # Si tiene campos cargados y corresponde al ID (o cand_del_id está en blanco aún)
                if (has_title or has_copy or has_url) and (cand_del_id == target_id_clean or not cand_del_id):
                    elapsed_load = int(time.time() - start_wait_form)
                    log_success(f"[{deliverable_id}] Dynamics form loaded in {elapsed_load}s. Waiting 2s for stabilization...")
                    time.sleep(2.0)
                    data = driver.execute_script(EXTRACT_DYNAMICS_DOM_JS) or cand_data
                    break
        except Exception:
            pass

    # 6. Extraer campos del formulario DOM
    if not data or not (data.get('title') or data.get('copy') or data.get('url')):
        try:
            data = driver.execute_script(EXTRACT_DYNAMICS_DOM_JS)
        except Exception as e:
            log_error(f"[{deliverable_id}] Error extracting Dynamics form: {e}")
            data = None

    if data and (data.get('title') or data.get('copy') or data.get('url')):
        log_extracted_data(deliverable_id, data, cms_link)
        return format_dyn_data(data, deliverable_id, cms_link)

    log_warn(f"[{deliverable_id}] Dynamics form did not load data after {max_wait_form}s.")
    return {
        'deliverable_id': deliverable_id,
        'url': cms_link,
        'title': '',
        'copy': '',
        'ctas': '',
        'found': False
    }


# ==============================================================================
# 5. LOCAL AUDIT ENGINE
# ==============================================================================
def fetch_page_html(driver, url):
    """
    Obtiene el HTML de la página en vivo. Intenta primero vía HTTP requests para evitar
    abrir o cerrar pestañas en el navegador. Si requiere Helium, garantiza que NUNCA
    se cierre la pestaña de QA Tool, Smartsheet ni Dynamics, cerrando únicamente la temporal.
    """
    if not url:
        return None, "Empty URL"

    # 1. Intento ultrarrápido con requests para no tocar las pestañas del navegador
    if requests:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            resp = requests.get(url, headers=headers, timeout=7)
            if resp.status_code == 200 and len(resp.text) > 400:
                return resp.text, 200
        except Exception:
            pass

    # 2. Respaldo vía Helium con protección absoluta de identificadores de pestañas
    if not driver:
        return None, "Driver not available"

    orig_handle = None
    try:
        orig_handle = driver.current_window_handle
    except Exception:
        pass

    try:
        handles_before = set(driver.window_handles)
        driver.execute_script("window.open(arguments[0], '_blank');", url)
        time.sleep(1.2)
        new_handles = [h for h in driver.window_handles if h not in handles_before]
        
        if not new_handles:
            # Si no se creó una pestaña nueva, NO cerrar nada
            return None, "Could not open isolated browser tab"

        temp_handle = new_handles[0]
        driver.switch_to.window(temp_handle)
        
        # Esperar a que la página cargue en Helium (3.5s)
        time.sleep(3.5)
        html = driver.page_source
        
        # Cerrar ÚNICA y EXCLUSIVAMENTE la pestaña temporal recién creada
        driver.close()
        
        if orig_handle and orig_handle in driver.window_handles:
            driver.switch_to.window(orig_handle)
        elif driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
            
        return html, 200
    except Exception as e:
        try:
            if orig_handle and orig_handle in driver.window_handles:
                driver.switch_to.window(orig_handle)
        except Exception:
            pass
        return None, str(e)


def build_rich_audit_result(html, target_url, dyn_data):
    """
    Construye el payload completo de resultados compatible con renderResults() de la QA Web App.
    """
    del_id = dyn_data.get('deliverable_id', '')
    expected_title = (dyn_data.get('title') or '').strip()
    expected_copy = (dyn_data.get('copy') or '').strip()
    
    soup = BeautifulSoup(html, 'html.parser') if BeautifulSoup else None
    bugs = []
    
    if not soup:
        return {
            "success": True,
            "url": target_url,
            "count": 0,
            "h1_valid": False,
            "h1_error_msg": "Could not parse HTML.",
            "h1_snippets": [],
            "title_match": {"status": "no_input", "target": expected_title, "found": ""},
            "seo_coverage": -1,
            "seo_missing_chunks": [],
            "total_links_analyzed": 0,
            "broken_links": [],
            "bugs": [{'platform': 'M/D', 'type': 'Failed', 'category': 'General', 'message': 'Could not parse DOM'}]
        }

    # 1. H1 Tags
    h1_tags = soup.find_all('h1')
    valid_h1s = [h for h in h1_tags if not (h.get('role') == 'heading' and h.get('aria-level') == '2')]
    h1_snippets = [h.get_text(separator=' ', strip=True) for h in valid_h1s]
    h1_valid = True
    h1_error_msg = ""
    title_match_status = "no_input"
    primary_h1_text = ""
    
    if len(valid_h1s) == 0:
        h1_valid = False
        h1_error_msg = "No H1 tags found on this page."
        bugs.append({
            'platform': 'M/D',
            'type': 'Failed',
            'category': 'Content',
            'message': 'Missing mandatory H1 tag on page.'
        })
    elif len(valid_h1s) > 2:
        h1_valid = False
        h1_error_msg = f"Multiple H1 tags found ({len(valid_h1s)})."
        bugs.append({
            'platform': 'M/D',
            'type': 'Failed',
            'category': 'Content',
            'message': f"Excess H1 tags: found {len(valid_h1s)} H1 tags (maximum 1 or 2 with sr-only)."
        })
    else:
        primary_h1_text = valid_h1s[0].get_text(separator=' ', strip=True)
        if expected_title:
            sim = difflib.SequenceMatcher(None, primary_h1_text.lower(), expected_title.lower()).ratio()
            is_sub = expected_title.lower() in primary_h1_text.lower() or primary_h1_text.lower() in expected_title.lower()
            if sim >= 0.70 or is_sub:
                title_match_status = "success"
            else:
                title_match_status = "not_found"
                h1_valid = False
                h1_error_msg = f"Target H1 mismatch: '{primary_h1_text[:50]}' vs expected '{expected_title[:50]}'"
                bugs.append({
                    'platform': 'M/D',
                    'type': 'Failed',
                    'category': 'Content',
                    'message': f"H1 does not match Dynamics: '{primary_h1_text[:45]}' vs expected '{expected_title[:45]}'"
                })
        else:
            title_match_status = "no_input"

    # 2. Links
    anchors = soup.find_all('a', href=True)
    broken_links = []
    for a in anchors:
        href = a['href'].strip()
        if href.startswith(('#', 'javascript:', 'tel:', 'mailto:')): continue
        if 'broken' in href.lower() or '404' in href:
            broken_links.append(href)
            bugs.append({
                'platform': 'M/D',
                'type': 'Critical',
                'category': 'Link',
                'message': f"Broken link detected: {href[:60]}"
            })
            break

    # 3. Content Copy Coverage
    seo_coverage = -1
    missing_chunks = []
    if expected_copy and len(expected_copy) > 30:
        page_text = soup.get_text()
        sentences = [s.strip() for s in re.split(r'[\r\n.]+', expected_copy) if len(s.strip()) > 20]
        found_count = 0
        for s in sentences:
            if s.lower() in page_text.lower():
                found_count += 1
            else:
                missing_chunks.append(s[:100] + ("..." if len(s) > 100 else ""))
                
        if sentences:
            seo_coverage = int((found_count / len(sentences)) * 100)
        else:
            seo_coverage = 100
            
        if seo_coverage < 70:
            bugs.append({
                'platform': 'M/D',
                'type': 'Observed',
                'category': 'Content',
                'message': f"Low SEO content coverage ({seo_coverage}%). Dynamics paragraphs not detected on page."
            })

    return {
        "success": True,
        "url": target_url,
        "count": len(valid_h1s),
        "h1_valid": h1_valid,
        "h1_error_msg": h1_error_msg,
        "h1_snippets": [f"<h1>{s}</h1>" for s in h1_snippets] if h1_snippets else [],
        "title_match": {
            "status": title_match_status,
            "target": expected_title,
            "found": primary_h1_text
        },
        "seo_coverage": seo_coverage,
        "seo_missing_chunks": missing_chunks,
        "total_links_analyzed": len(anchors),
        "broken_links": broken_links,
        "bugs": bugs
    }


def audit_task(driver, task_data):
    url = task_data.get('url') or task_data.get('cms_link') or ''
    del_id = task_data.get('deliverable_id', 'Unknown')
    
    if not url:
        return {
            'deliverable_id': del_id,
            'url': 'No URL',
            'is_passed': False,
            'bugs': ['CMS URL empty or not detected']
        }
        
    try:
        html, status = fetch_page_html(driver, url)
        if not html:
            return {
                'deliverable_id': del_id,
                'url': url,
                'is_passed': False,
                'bugs': [f"Page did not respond or was blocked (HTTP {status})"]
            }
            
        rich_data = build_rich_audit_result(html, url, task_data)
        bugs = rich_data.get('bugs', [])
        return {
            'deliverable_id': del_id,
            'url': url,
            'is_passed': (len(bugs) == 0),
            'bugs': bugs
        }
    except Exception as e:
        return {
            'deliverable_id': del_id,
            'url': url,
            'is_passed': False,
            'bugs': [f"Audit execution error: {str(e)[:100]}"]
        }


def open_brand_new_qa_tab(driver, reserved_handles=None, app_url="https://qa-tool-brown.vercel.app"):
    """
    Abre de forma 100% garantizada una pestaña COMPLETAMENTE NUEVA para el caso.
    NUNCA reutiliza ni sobreescribe ninguna pestaña previa (ni Smartsheet, ni Dynamics,
    ni pestañas ya revisadas con títulos ✅, ❌ o ⚠️).
    """
    if reserved_handles is None:
        reserved_handles = set()

    initial_handles = set(driver.window_handles)
    qa_tab = None

    # Método 1: Selenium 4 W3C nativo (independiente del DOM y libre de bloqueadores de popups)
    try:
        driver.switch_to.new_window('tab')
        time.sleep(0.8)
        current = driver.current_window_handle
        if current not in initial_handles and current not in reserved_handles:
            qa_tab = current
            driver.get(app_url)
    except Exception:
        pass

    # Método 2: CDP (Chrome DevTools Protocol) Target.createTarget
    if not qa_tab:
        try:
            driver.execute_cdp_cmd("Target.createTarget", {"url": app_url})
            time.sleep(1.2)
            fresh_handles = [h for h in driver.window_handles if h not in initial_handles and h not in reserved_handles]
            if fresh_handles:
                qa_tab = fresh_handles[0]
                driver.switch_to.window(qa_tab)
        except Exception:
            pass

    # Método 3: window.open vía JS asegurando que el handle resultante sea estrictamente NUEVO
    if not qa_tab:
        try:
            driver.execute_script("window.open(arguments[0], '_blank');", app_url)
            time.sleep(1.5)
            fresh_handles = [h for h in driver.window_handles if h not in initial_handles and h not in reserved_handles]
            if fresh_handles:
                qa_tab = fresh_handles[0]
                driver.switch_to.window(qa_tab)
        except Exception:
            pass

    # Verificación final de seguridad: NUNCA permitir que qa_tab sea una pestaña reservada o con título de dictamen
    if qa_tab:
        try:
            title = (driver.title or '').strip()
            if any(title.startswith(emoji) for emoji in ['✅', '❌', '⚠️']):
                # Si por alguna anomalía la pestaña tiene un dictamen previo, forzar apertura de otra limpia
                driver.switch_to.new_window('tab')
                driver.get(app_url)
                qa_tab = driver.current_window_handle
        except Exception:
            pass

    return qa_tab


def run_qa_app_audit(driver, dyn_data, smartsheet_handle, dynamics_handle, reserved_handles=None):
    """
    Flujo solicitado por Diego:
      1. Abre SIEMPRE pestaña nueva e independiente con QA Web Tool (https://qa-tool-brown.vercel.app)
         para CADA caso detectado. NUNCA se sobreescribe una pestaña previa.
      2. Llena automáticamente todos los campos del deliverable.
      3. Si falta la URL, deja la pestaña abierta con título '⚠️ D-XXXXXX (Sin URL)'
         y aviso en pantalla para que Diego pueda introducirla manualmente.
      4. Si la URL está presente, ejecuta el escaneo en la app ('Scan Quality').
      5. Si el worker del Home PC no está activo, asiste como worker autónomo
         para completar el trabajo en Vercel con el DOM obtenido.
      6. Lee el dictamen en la interfaz:
         - Si todo está PASSED (0 bugs):
             • Marca 'Passed' en Smartsheet y guarda.
             • DEJA LA PESTAÑA ABIERTA con título '✅ D-XXXXXX' (¡NUNCA SE CIERRA!).
         - Si está OBSERVED / tiene fallas:
             • DEJA LA PESTAÑA ABIERTA con el análisis visible y título '❌ D-XXXXXX'.
             • Hace scroll directo a los bugs.
             • Deja Smartsheet 'In progress' para su revisión manual.
    """
    del_id = dyn_data.get('deliverable_id', 'Unknown')
    target_url = (dyn_data.get('url') or dyn_data.get('cms_link') or '').strip()
    if target_url and not target_url.startswith(('http://', 'https://')):
        if target_url.startswith('www.') or '.' in target_url:
            target_url = 'https://' + target_url

    log_info(f"[{del_id}] Opening fresh, isolated QA Web Tool tab in Helium...")
    
    # 1. Abrir SIEMPRE una pestaña NUEVA e INDEPENDIENTE (nunca sobreescribir)
    qa_tab = open_brand_new_qa_tab(driver, reserved_handles=reserved_handles)
    if not qa_tab:
        log_error(f"[{del_id}] Could not create a fresh browser tab. Skipping to prevent overwriting existing tabs.")
        return {
            'deliverable_id': del_id,
            'url': target_url,
            'is_passed': False,
            'bugs': ['No se pudo crear una pestaña nueva e independiente en el navegador']
        }
        
    if reserved_handles is not None:
        reserved_handles.add(qa_tab)
    
    try:
        # 2. Esperar a que el formulario cargue en pantalla
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "url-form")))
        
        # 3. Rellenar el formulario con los datos disponibles
        log_info(f"[{del_id}] Filling deliverable data into the app...")
        form_payload = dict(dyn_data)
        form_payload['url'] = target_url
        form_payload['deliverable_id'] = del_id

        driver.execute_script("""
            var d = arguments[0];
            
            // 1. Abrir sección de SEO / Campos avanzados si está oculta
            var seoBody = document.querySelector('.seo-panel-body');
            var toggle = document.getElementById('toggle-seo-inputs');
            if (toggle && (!seoBody || window.getComputedStyle(seoBody).display === 'none')) {
                toggle.click();
            }
            
            function setField(id, val) {
                var el = document.getElementById(id);
                if (el) {
                    el.value = val || '';
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                    return true;
                }
                return false;
            }
            
            setField('case-number-input', d.deliverable_id);
            setField('url-input', d.url);
            setField('expected-title-input', d.title);
            setField('expected-content-input', d.copy);
            setField('special-instructions-input', d.ctas);
            setField('custom-rules-input', d.details);
            setField('expected-page-example-input', d.page_example_raw);
            window.currentDynamicsData = d;
        """, form_payload)
        
        # Si NO hay URL, NUNCA cerrar ni saltar la pestaña: dejarla lista para Diego
        if not target_url:
            log_warn(f"[{del_id}] ⚠️ No URL found in Dynamics or Smartsheet. Leaving QA Tool tab OPEN with prefilled ID.")
            try:
                driver.execute_script(f"""
                    document.title = '⚠️ {del_id} (Sin URL)';
                    var err = document.getElementById('error-message');
                    if (err) {{
                        err.innerText = '⚠️ No se encontró la URL en Dynamics ni Smartsheet. Introduce la URL manualmente para analizar este caso.';
                        err.style.display = 'block';
                    }}
                """)
            except Exception:
                pass
            driver.switch_to.window(dynamics_handle)
            return {
                'deliverable_id': del_id,
                'url': 'Sin URL',
                'is_passed': False,
                'bugs': ['URL no encontrada en Dynamics ni Smartsheet. Pestaña abierta para revisión de Diego.']
            }

        # Esperar 2.0 segundos para que los datos queden completamente visibles
        title_snippet = (dyn_data.get('title') or '')[:35]
        copy_len = len(dyn_data.get('copy') or '')
        log_info(f"[{del_id}] Data entered into QA Web App (Title: '{title_snippet}...', Copy: {copy_len} chars). Triggering scan...")
        time.sleep(1.8)
        
        # 4. Enviar formulario (Scan Quality) haciendo click en el botón de submit o dispatchEvent
        driver.execute_script("""
            var btn = document.getElementById('submit-btn');
            var form = document.getElementById('url-form');
            if (btn) {
                btn.click();
            } else if (form) {
                form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
            }
        """)
        
        # 5. Esperar resultado y asistir como worker autónomo si Home PC no responde
        max_scan_timeout = 180  # Ampliado a 3 minutos para permitir escaneos profundos de inventario y relays
        log_info(f"[{del_id}] Waiting for app to complete analysis (up to {max_scan_timeout}s)...")
        start_wait = time.time()
        completed = False
        scan_outcome = None
        page_html = None
        last_logged_sec = 0
        
        while time.time() - start_wait < max_scan_timeout:
            time.sleep(2)
            elapsed = time.time() - start_wait
            
            # Comprobar estado de la pestaña
            try:
                status_check = driver.execute_script("""
                    var resultsArea = document.getElementById('results-area');
                    var loader = document.querySelector('#submit-btn .loader');
                    var submitBtn = document.getElementById('submit-btn');
                    var btnText = document.querySelector('#submit-btn .btn-text') || submitBtn;
                    var errorMsg = document.getElementById('error-message');
                    var hasError = errorMsg && window.getComputedStyle(errorMsg).display !== 'none' && errorMsg.innerText.trim().length > 0;
                    var isDone = resultsArea && window.getComputedStyle(resultsArea).display !== 'none' && (!loader || window.getComputedStyle(loader).display === 'none');
                    var progressText = btnText ? (btnText.innerText || btnText.textContent || '').trim() : '';
                    var hasScanData = Boolean(window.lastScanData && window.lastScanData.success);
                    
                    return {
                        is_done: isDone && (hasScanData || Boolean(document.getElementById('bug-report-card'))),
                        is_error: hasError,
                        error_text: hasError ? errorMsg.innerText.trim() : '',
                        progress_text: progressText,
                        has_scan_data: hasScanData
                    };
                """)
                
                if status_check:
                    if status_check.get('is_error'):
                        err_text = status_check.get('error_text', 'Unknown app error')
                        log_error(f"[{del_id}] QA Tool reported an error: {err_text}")
                        scan_outcome = {
                            'is_passed': False,
                            'bugs': [f"Error in QA App: {err_text}"],
                            'bug_count': 1
                        }
                        completed = False
                        break
                        
                    if status_check.get('is_done'):
                        completed = True
                        log_success(f"[{del_id}] ✅ Scan completed successfully in the tool ({int(elapsed)}s).")
                        break
                        
                    # Feedback periódico cada 10 segundos
                    if int(elapsed) - last_logged_sec >= 10:
                        last_logged_sec = int(elapsed)
                        p_text = status_check.get('progress_text') or 'Scanning elements...'
                        log_info(f"[{del_id}] ⏳ Scan in progress ({last_logged_sec}s elapsed)... [Status: {p_text}]")
            except Exception:
                pass
                
            # Si pasaron 5 segundos y sigue pendiente, verificar si Vercel tiene un job relay pendiente
            if elapsed > 5 and requests:
                try:
                    p_resp = requests.get('https://qa-tool-brown.vercel.app/api/jobs/pending?key=h1-checker-secret-key-2026', timeout=4)
                    if p_resp.status_code == 200:
                        j_data = p_resp.json()
                        job_id = j_data.get('job_id')
                        if job_id:
                            log_info(f"[{del_id}] Assisting autonomous scan in Vercel (Job: {job_id})...")
                            if not page_html:
                                page_html, _ = fetch_page_html(driver, target_url)
                                driver.switch_to.window(qa_tab)
                                
                            rich_res = build_rich_audit_result(page_html or "<html></html>", target_url, dyn_data)
                            requests.post('https://qa-tool-brown.vercel.app/api/jobs/complete?key=h1-checker-secret-key-2026', json={'job_id': job_id, 'result': rich_res}, timeout=6)
                except Exception:
                    try:
                        driver.switch_to.window(qa_tab)
                    except Exception:
                        pass

        # 6. Extraer y verificar dictamen final desde la interfaz de la QA App
        if completed:
            time.sleep(1) # Breve pausa para asegurar renderizado final de cards
            try:
                scan_outcome = driver.execute_script("""
                    var noBugsEl = document.getElementById('no-bugs-msg');
                    var isNoBugs = noBugsEl && window.getComputedStyle(noBugsEl).display !== 'none';
                    var bugRows = document.querySelectorAll('#bug-list .bug-row');
                    var bugCount = bugRows.length;
                    var bugs = [];
                    
                    if (window.lastScanData && Array.isArray(window.lastScanData.bugs) && window.lastScanData.bugs.length > 0) {
                        bugs = window.lastScanData.bugs;
                    } else {
                        bugRows.forEach(function(r) {
                            var msg = r.querySelector('.bug-message-text');
                            var typeBadge = r.querySelector('.bug-badge.badge-failed, .bug-badge.badge-observed, .bug-badge.badge-critical');
                            bugs.push({
                                type: typeBadge ? typeBadge.innerText.trim() : 'Observed',
                                message: msg ? msg.innerText.trim() : r.innerText.trim()
                            });
                        });
                    }
                    
                    var isPassed = isNoBugs && (bugCount === 0 && bugs.length === 0);
                    return {
                        is_passed: isPassed,
                        bug_count: bugs.length || bugCount,
                        bugs: bugs,
                        has_data: Boolean(window.lastScanData)
                    };
                """)
            except Exception as e_res:
                log_warn(f"[{del_id}] Error reading results from app: {e_res}")
                scan_outcome = {'is_passed': False, 'bugs': [f"App read error: {e_res}"], 'bug_count': 1}
        else:
            if not scan_outcome:
                log_warn(f"[{del_id}] ⏱️ Scan timed out after {max_scan_timeout} seconds.")
                scan_outcome = {
                    'is_passed': False,
                    'bugs': [f"Scan timed out ({max_scan_timeout}s) in QA Tool"],
                    'bug_count': 1
                }

        if not scan_outcome:
            scan_outcome = {'is_passed': False, 'bugs': ['App returned no results'], 'bug_count': 1}

        is_passed = scan_outcome.get('is_passed', False)
        bugs = scan_outcome.get('bugs', [])
        
        # 7. Acción según resultado:
        if is_passed:
            log_success(f"[{del_id}] ✅ PASSED (0 bugs detected in the app).")
            log_info(f"[{del_id}] Marking as 'Passed' in Smartsheet...")
            save_smartsheet_passed(driver, smartsheet_handle, del_id)
            
            # En la pestaña de QA App: NO CERRAR. Renombrar con emoji verde y el ID para Diego
            try:
                driver.switch_to.window(qa_tab)
                driver.execute_script(f"document.title = '✅ {del_id}';")
                driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
            except Exception:
                pass
            log_info(f"[{del_id}] QA App tab left OPEN with title '✅ {del_id}' for quick review.")
            driver.switch_to.window(dynamics_handle)
            
            return {
                'deliverable_id': del_id,
                'url': target_url,
                'is_passed': True,
                'bugs': []
            }
        else:
            bug_count = len(bugs) or scan_outcome.get('bug_count', 1)
            log_warn(f"[{del_id}] ⚠️ OBSERVED ({bug_count} bugs/observations). Tab left OPEN with title '❌ {del_id}'.")
            
            # En la pestaña de QA App: Renombrar con emoji rojo y el ID, y hacer scroll al reporte de bugs
            try:
                driver.switch_to.window(qa_tab)
                driver.execute_script(f"document.title = '❌ {del_id}';")
                driver.execute_script("var el = document.getElementById('bug-report-card'); if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});")
            except Exception:
                pass
                
            # NO CERRAR LA PESTAÑA: Dejarla abierta en Helium para Diego
            driver.switch_to.window(dynamics_handle)
            
            return {
                'deliverable_id': del_id,
                'url': target_url,
                'is_passed': False,
                'bugs': bugs
            }
            
    except Exception as e_app:
        log_error(f"[{del_id}] Error interacting with QA App: {e_app}")
        try:
            driver.switch_to.window(dynamics_handle)
        except Exception:
            pass
        return {
            'deliverable_id': del_id,
            'url': target_url,
            'is_passed': False,
            'bugs': [f"Error in QA App: {str(e_app)[:100]}"]
        }


# ==============================================================================
# 6. SMARTSHEET AUTO-SAVE (PASSED -> SAVE)
# ==============================================================================
CLICK_AND_SAVE_PASSED_JS = """
var delId = arguments[0];
var done = arguments[arguments.length - 1];

(function() {
    try {
        var docs = [document];
        try {
            var iframes = document.querySelectorAll('iframe');
            for (var f = 0; f < iframes.length; f++) {
                var d = iframes[f].contentDocument || iframes[f].contentWindow.document;
                if (d && docs.indexOf(d) === -1) docs.push(d);
            }
        } catch(e) {}

        function fireMouseEvent(el, type) {
            try {
                el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
            } catch(e) {}
        }

        function getRowIdFromEl(el) {
            if (!el) return null;
            if (el.getAttribute && el.getAttribute('data-row-id')) return el.getAttribute('data-row-id');
            for (var key in el) {
                if (key.indexOf('reactFiber') !== -1 || key.indexOf('reactInternal') !== -1 || key.indexOf('reactProps') !== -1) {
                    var p = el[key];
                    for (var depth = 0; depth < 10 && p; depth++) {
                        if (p.memoizedProps) {
                            if (p.memoizedProps.row && p.memoizedProps.row.id) return String(p.memoizedProps.row.id);
                            if (p.memoizedProps.rowData && p.memoizedProps.rowData.id) return String(p.memoizedProps.rowData.id);
                            if (p.memoizedProps.rowId) return String(p.memoizedProps.rowId);
                            if (p.memoizedProps.id) return String(p.memoizedProps.id);
                        }
                        p = p.return;
                    }
                }
            }
            return null;
        }

        // =========================================================================
        // HELPER: Find EXCLUSIVELY the 'QA Status' combobox (NEVER the names combobox)
        // =========================================================================
        function getQAStatusCombobox(panel) {
            if (!panel) return null;

            // 0. EXACT ID from Smartsheet Dynamic View: #pli-2 is QA Status (#pli-1 is Owner/Name)
            var pli2 = panel.querySelector('#pli-2') || document.querySelector('#pli-2');
            if (pli2) return pli2;

            // 1. By current value: QA Status has 'in progress' (or 'passed', 'failed', 'opportunity', 'critical')
            // The names field has a person's name (e.g. 'Diego Torrez')
            var cbs = panel.querySelectorAll('input[role="combobox"], [role="combobox"], input.sds-select-combobox-input, [id^="pli-"]');
            for (var c = 0; c < cbs.length; c++) {
                if (cbs[c].id === 'pli-1') continue; // Skip Owner/Name combobox explicitly
                if (cbs[c].id === 'pli-2') return cbs[c];
                var val = (cbs[c].value || cbs[c].getAttribute('value') || cbs[c].innerText || '').trim().toLowerCase();
                if (val === 'in progress' || val === 'opportunity' || val === 'failed' || val === 'critical' || val === 'passed') {
                    return cbs[c];
                }
            }

            // 2. By form field container label: 'QA Status' (and NOT 'Completed' nor 'Name')
            var items = panel.querySelectorAll('.details-item, .field-wrapper, [data-client-id*="ffw"], .form-group, div');
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var lbl = it.querySelector('label, .field-label, [data-client-id*="label"], .sds-field-label, span');
                if (lbl) {
                    var lText = (lbl.innerText || lbl.textContent || '').trim().toLowerCase();
                    if (lText.indexOf('qa status') !== -1 && lText.indexOf('completed') === -1) {
                        var targetCb = it.querySelector('input[role="combobox"], [role="combobox"], input.sds-select-combobox-input, [id="pli-2"], input');
                        if (targetCb) return targetCb;
                    }
                }
            }

            // 3. Fallback: Search all labels in the panel and walk up DOM tree
            var allLabels = panel.querySelectorAll('label, .field-label, [data-client-id*="label"], div, span');
            for (var l = 0; l < allLabels.length; l++) {
                var lblEl = allLabels[l];
                var txt = (lblEl.innerText || lblEl.textContent || '').trim().toLowerCase();
                if (txt.indexOf('qa status') !== -1 && txt.indexOf('completed') === -1) {
                    var p = lblEl.parentElement;
                    for (var up = 0; up < 5 && p && p !== panel; up++) {
                        var foundCb = p.querySelector('input[role="combobox"], [role="combobox"], input.sds-select-combobox-input, [id="pli-2"]');
                        if (foundCb) return foundCb;
                        p = p.parentElement;
                    }
                }
            }

            // 4. Fallback by position: In this sheet form:
            // Combobox 0 (#pli-1): QA Completed By (Name)
            // Combobox 1 (#pli-2): QA Status (In progress / Passed)
            if (cbs.length >= 2) {
                // Always return the second combobox (QA Status), NEVER the first (Name)
                return cbs[1];
            } else if (cbs.length === 1) {
                var v0 = (cbs[0].value || cbs[0].getAttribute('value') || '').trim().toLowerCase();
                if (v0.indexOf('diego') === -1 && v0.indexOf('torrez') === -1 && cbs[0].id !== 'pli-1') {
                    return cbs[0];
                }
            }

            return null;
        }

        // =========================================================================
        // PASO 1: Check if details panel is ALREADY open for THIS deliverable ID
        // =========================================================================
        for (var d = 0; d < docs.length; d++) {
            var curDoc = docs[d];
            var detailsPanel = curDoc.querySelector('.details-data, .details-list, div[id*="panel-gen-id"]');
            if (detailsPanel) {
                var pText = (detailsPanel.innerText || detailsPanel.textContent || '').trim();
                var re = new RegExp('\\\\b' + delId.replace('-', '\\\\-') + '\\\\b', 'i');
                // ONLY proceed if panel explicitly contains this Deliverable ID
                if (re.test(pText)) {
                    proceedWithDetailsPanel(detailsPanel, curDoc);
                    return;
                }
            }
        }

        // =========================================================================
        // PASO 2: Find row in virtualized grid with smart scrolling
        // =========================================================================
        findTargetRowWithScroll(function(targetRow, activeDoc) {
            if (!targetRow) {
                trySessionFetchFallback(null);
                return;
            }

            targetRow.scrollIntoView({ behavior: 'auto', block: 'center' });

            var rowIdFromRow = getRowIdFromEl(targetRow);

            // Click a cell that is NOT a link and NOT the assignee name
            var cellTargets = targetRow.querySelectorAll('.data-cell, .cell-content, [data-testid="value-with-spans"], .outer-cell, [role="gridcell"], td, .grid-cell');
            var clickTarget = null;
            for (var c = 0; c < cellTargets.length; c++) {
                var cell = cellTargets[c];
                if (cell.querySelector('a')) continue;
                var cTxt = (cell.innerText || cell.textContent || '').trim();
                if (cTxt.toLowerCase().indexOf('diego') !== -1 || cTxt.toLowerCase().indexOf('torrez') !== -1) continue;
                if (cTxt.length > 0) {
                    clickTarget = cell;
                    break;
                }
            }
            if (!clickTarget) clickTarget = targetRow;

            clickTarget.focus && clickTarget.focus();
            fireMouseEvent(clickTarget, 'mousedown');
            fireMouseEvent(clickTarget, 'mouseup');
            clickTarget.click();

            // Wait for side details panel to open
            var startWaitPanel = Date.now();
            var panelTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitPanel;
                var panel = null;
                for (var d = 0; d < docs.length; d++) {
                    panel = docs[d].querySelector('.details-data, .details-list, div[id*="panel-gen-id"]');
                    if (panel) { activeDoc = docs[d]; break; }
                }

                if (panel) {
                    clearInterval(panelTimer);
                    proceedWithDetailsPanel(panel, activeDoc, rowIdFromRow);
                } else if (elapsed > 6000) {
                    clearInterval(panelTimer);
                    trySessionFetchFallback(rowIdFromRow);
                }
            }, 250);
        });

        // Smart scroll in ReactVirtualized__Grid
        function findTargetRowWithScroll(callback) {
            var grid = null;
            var activeDoc = document;
            for (var d = 0; d < docs.length; d++) {
                var g = docs[d].querySelector('.ReactVirtualized__Grid, .grid-view-body, .ReactVirtualized__Table__Grid');
                if (g) { grid = g; activeDoc = docs[d]; break; }
            }

            function scan() {
                for (var d = 0; d < docs.length; d++) {
                    var cDoc = docs[d];
                    var rows = cDoc.querySelectorAll('.ReactVirtualized__Table__row, [role="row"], .grid-row, tr');
                    for (var i = 0; i < rows.length; i++) {
                        if (rows[i].querySelectorAll('.ReactVirtualized__Table__row, [role="row"], .grid-row, tr').length > 0) continue;
                        var rText = (rows[i].innerText || rows[i].textContent || '').trim();
                        var re = new RegExp('\\\\b' + delId.replace('-', '\\\\-') + '\\\\b', 'i');
                        if (re.test(rText)) {
                            return { row: rows[i], doc: cDoc };
                        }
                    }
                }
                return null;
            }

            var initialMatch = scan();
            if (initialMatch) {
                callback(initialMatch.row, initialMatch.doc);
                return;
            }

            if (!grid) {
                callback(null, activeDoc);
                return;
            }

            var scrollCount = 0;
            var maxScrollSteps = 25;
            var scrollStepPx = 350;

            if (grid.scrollTop > 500) {
                grid.scrollTop = 0;
            }

            var scrollInterval = setInterval(function() {
                scrollCount++;
                var m = scan();
                if (m) {
                    clearInterval(scrollInterval);
                    callback(m.row, m.doc);
                    return;
                }

                var atBottom = (grid.scrollTop + grid.clientHeight >= grid.scrollHeight - 15);
                if (scrollCount >= maxScrollSteps || atBottom) {
                    clearInterval(scrollInterval);
                    setTimeout(function() {
                        var finalM = scan();
                        callback(finalM ? finalM.row : null, finalM ? finalM.doc : activeDoc);
                    }, 300);
                    return;
                }

                grid.scrollTop += scrollStepPx;
            }, 250);
        }

        // =========================================================================
        // PASO 3: Change QA Status to "Passed" in the details panel
        // =========================================================================
        function proceedWithDetailsPanel(detailsPanel, activeDoc, knownRowId) {
            var rowId = knownRowId || getRowIdFromEl(detailsPanel);
            var startWaitCb = Date.now();
            var cbTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitCb;
                var qaCombobox = getQAStatusCombobox(detailsPanel);

                if (qaCombobox) {
                    clearInterval(cbTimer);

                    var currentVal = (qaCombobox.value || qaCombobox.getAttribute('value') || qaCombobox.innerText || '').trim().toLowerCase();
                    if (currentVal === 'passed') {
                        triggerSaveBtn(activeDoc, rowId);
                        return;
                    }

                    // Open QA Status dropdown
                    qaCombobox.focus && qaCombobox.focus();
                    fireMouseEvent(qaCombobox, 'mousedown');
                    fireMouseEvent(qaCombobox, 'mouseup');
                    qaCombobox.click();

                    // Wait for option "Passed"
                    var startOptWait = Date.now();
                    var optTimer = setInterval(function() {
                        var optElapsed = Date.now() - startOptWait;
                        var passedOpt = null;

                        // 0. EXACT ID from Smartsheet recording: #pli-2-item-1 is "Passed"
                        for (var d0 = 0; d0 < docs.length; d0++) {
                            passedOpt = docs[d0].querySelector('#pli-2-item-1') || docs[d0].querySelector('[id="pli-2-item-1"]');
                            if (passedOpt) break;
                        }

                        if (!passedOpt) {
                            for (var d = 0; d < docs.length; d++) {
                                var cDoc = docs[d];
                                var options = cDoc.querySelectorAll('[role="option"], div[id*="item"], .sds-option-base, li, span');
                                for (var o = 0; o < options.length; o++) {
                                    var oTxt = (options[o].innerText || options[o].textContent || '').trim().toLowerCase();
                                    if (oTxt === 'passed') {
                                        passedOpt = options[o].closest('[role="option"], div') || options[o];
                                        break;
                                    }
                                }
                                if (passedOpt) break;
                            }
                        }

                        if (passedOpt) {
                            clearInterval(optTimer);
                            fireMouseEvent(passedOpt, 'mousedown');
                            fireMouseEvent(passedOpt, 'mouseup');
                            passedOpt.click();

                            if (qaCombobox.tagName === 'INPUT') {
                                qaCombobox.value = 'Passed';
                                qaCombobox.dispatchEvent(new Event('input', { bubbles: true }));
                                qaCombobox.dispatchEvent(new Event('change', { bubbles: true }));
                            }

                            setTimeout(function() {
                                triggerSaveBtn(activeDoc, rowId);
                            }, 500);
                        } else if (optElapsed > 3500) {
                            clearInterval(optTimer);
                            // Dropdown option not clickable: apply PATCH fallback immediately
                            trySessionFetchFallback(rowId);
                        }
                    }, 200);

                } else if (elapsed > 5000) {
                    clearInterval(cbTimer);
                    trySessionFetchFallback(rowId);
                }
            }, 200);
        }

        // =========================================================================
        // PASO 4: Click Save button when active and enabled
        // =========================================================================
        function triggerSaveBtn(activeDoc, rowId) {
            var startWaitSave = Date.now();
            var saveTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitSave;
                var saveBtn = null;

                for (var d = 0; d < docs.length; d++) {
                    saveBtn = docs[d].querySelector('button#detailsDataFooterSaveBtn, #detailsDataFooterSaveBtn, button[data-client-id="details-footer-save"]');
                    if (saveBtn) break;
                }

                if (!saveBtn) {
                    for (var d2 = 0; d2 < docs.length; d2++) {
                        var buttons = docs[d2].querySelectorAll('.details-data button, .details-list button, button');
                        for (var b = 0; b < buttons.length; b++) {
                            var bTxt = (buttons[b].innerText || buttons[b].textContent || buttons[b].value || '').trim().toLowerCase();
                            if (bTxt === 'save' || bTxt === 'guardar') {
                                saveBtn = buttons[b];
                                break;
                            }
                        }
                        if (saveBtn) break;
                    }
                }

                if (saveBtn) {
                    var isDisabled = saveBtn.disabled || saveBtn.getAttribute('aria-disabled') === 'true' || saveBtn.classList.contains('disabled');
                    if (!isDisabled) {
                        clearInterval(saveTimer);
                        saveBtn.focus && saveBtn.focus();
                        fireMouseEvent(saveBtn, 'mousedown');
                        fireMouseEvent(saveBtn, 'mouseup');
                        saveBtn.click();

                        setTimeout(function() {
                            done({ success: true, saved: true, method: 'ui_click' });
                        }, 1800);
                        return;
                    } else if (elapsed > 2000) {
                        // Button still disabled after 2s: execute PATCH fallback
                        clearInterval(saveTimer);
                        trySessionFetchFallback(rowId);
                        return;
                    }
                } else if (elapsed > 3500) {
                    clearInterval(saveTimer);
                    trySessionFetchFallback(rowId);
                }
            }, 250);
        }

        // =========================================================================
        // PASO 5: Fallback via authenticated PATCH in active session
        // =========================================================================
        function trySessionFetchFallback(knownRowId) {
            try {
                var m = window.location.pathname.match(/\\/views\\/([a-f0-9\\-]+)/i);
                var viewId = m ? m[1] : '';
                if (!viewId) {
                    done({ success: false, saved: false, reason: 'Could not obtain viewId from Smartsheet URL' });
                    return;
                }

                var foundRowId = knownRowId;
                if (!foundRowId) {
                    for (var d = 0; d < docs.length; d++) {
                        var cDoc = docs[d];
                        var rows = cDoc.querySelectorAll('.ReactVirtualized__Table__row, [role="row"], .grid-row, tr');
                        for (var i = 0; i < rows.length; i++) {
                            var rText = (rows[i].innerText || rows[i].textContent || '').trim();
                            var re = new RegExp('\\\\b' + delId.replace('-', '\\\\-') + '\\\\b', 'i');
                            if (re.test(rText)) {
                                foundRowId = getRowIdFromEl(rows[i]);
                                if (foundRowId) break;
                            }
                        }
                        if (foundRowId) break;
                    }
                }

                if (foundRowId) {
                    fetch('/dynamicview/api/views/' + viewId + '/rows/' + foundRowId, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ form: [{ columnId: 1959290843991940, value: 'Passed' }] })
                    }).then(function(res) {
                        if (res.ok) {
                            done({ success: true, saved: true, method: 'session_fetch', rowId: foundRowId });
                        } else {
                            done({ success: false, saved: false, reason: 'Fetch PATCH failed with HTTP code ' + res.status });
                        }
                    }).catch(function(err) {
                        done({ success: false, saved: false, reason: 'Fetch PATCH error: ' + String(err) });
                    });
                } else {
                    done({ success: false, saved: false, reason: 'Row not found in Smartsheet after full scroll' });
                }
            } catch(e) {
                done({ success: false, saved: false, error: String(e) });
            }
        }

    } catch(err) {
        done({ success: false, saved: false, error: String(err) });
    }
})();
"""

def save_smartsheet_passed(driver, smartsheet_handle, deliverable_id):
    driver.switch_to.window(smartsheet_handle)
    time.sleep(1)

    for attempt in range(1, 4):
        try:
            log_info(f"[{deliverable_id}] Attempt {attempt}/3 to mark 'Passed' in Smartsheet...")
            res = driver.execute_async_script(CLICK_AND_SAVE_PASSED_JS, deliverable_id)
            if res and res.get('saved'):
                method = res.get('method', 'ui_click')
                log_success(f"[{deliverable_id}] ✅ Marked as 'Passed' and saved in Smartsheet (Method: {method}).")
                time.sleep(1.5)
                return True
            else:
                reason = res.get('reason') if res else 'No response'
                log_warn(f"[{deliverable_id}] Attempt {attempt}/3 did not save: {reason}.")
                time.sleep(1.5)
        except Exception as e:
            log_warn(f"[{deliverable_id}] Attempt {attempt}/3 error: {e}")
            time.sleep(1.5)

    log_error(f"[{deliverable_id}] ❌ Failed to auto-save in Smartsheet after 3 attempts. Please mark as 'Passed' manually.")
    return False


# ==============================================================================
# 7. FINAL REPORT GENERATOR & SUMMARY
# ==============================================================================
def print_and_export_summary(results):
    log_header("BATCH QA EXECUTIVE SUMMARY")
    
    total = len(results)
    passed = [r for r in results if r.get('is_passed')]
    failed = [r for r in results if not r.get('is_passed')]
    
    print(f"\n📊 Total Tasks Analyzed: {TermColors.BOLD}{total}{TermColors.END}")
    print(f"✅ Passed Tasks (Auto-Saved in Smartsheet): {TermColors.GREEN}{len(passed)}{TermColors.END}")
    print(f"⚠️  Tasks with Bugs (For Manual Review): {TermColors.RED}{len(failed)}{TermColors.END}\n")
    
    if failed:
        print(f"{TermColors.BOLD}{TermColors.RED}LIST OF TASKS REQUIRING MANUAL REVIEW:{TermColors.END}")
        print("-" * 75)
        for idx, f in enumerate(failed, 1):
            del_id = f.get('deliverable_id', 'N/A')
            url = f.get('url', 'No URL')
            bugs_list = f.get('bugs', [])
            formatted_bugs = []
            for b in bugs_list:
                if isinstance(b, dict):
                    formatted_bugs.append(b.get('description') or b.get('message') or str(b))
                else:
                    formatted_bugs.append(str(b))
            bugs_str = " | ".join(formatted_bugs) if formatted_bugs else "Manual review needed"
            print(f"{idx}. {TermColors.BOLD}{del_id}{TermColors.END} ➔ {url}")
            print(f"   Failure reason: {TermColors.YELLOW}{bugs_str}{TermColors.END}")
        print("-" * 75)
        
    try:
        report_filename = f"qa_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Batch QA Report - Diego Torrez</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; }}
        .stats {{ display: flex; gap: 1rem; margin: 1.5rem 0; }}
        .card {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; flex: 1; border: 1px solid #334155; }}
        .card.green {{ border-left: 5px solid #22c55e; }}
        .card.red {{ border-left: 5px solid #ef4444; }}
        .num {{ font-size: 2rem; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; background: #1e293b; border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 0.8rem 1rem; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #334155; color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; }}
        .badge-passed {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold; }}
        .badge-failed {{ background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Batch QA Audit Report</h1>
        <p>Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Analyst: <strong>Diego Torrez</strong></p>
        <div class="stats">
            <div class="card"><div>Total Analyzed</div><div class="num">{total}</div></div>
            <div class="card green"><div>Passed (Auto-Saved)</div><div class="num" style="color: #4ade80;">{len(passed)}</div></div>
            <div class="card red"><div>For Manual Review</div><div class="num" style="color: #f87171;">{len(failed)}</div></div>
        </div>
        <table>
            <thead>
                <tr><th>Deliverable ID</th><th>Status</th><th>Audited URL</th><th>Observations / Bugs Detected</th></tr>
            </thead>
            <tbody>
    """
        for r in results:
            status_badge = '<span class="badge-passed">Passed ✓</span>' if r.get('is_passed') else '<span class="badge-failed">Review ⚠️</span>'
            bugs_list = r.get('bugs', [])
            formatted = []
            for b in bugs_list:
                if isinstance(b, dict):
                    formatted.append(b.get('description') or b.get('message') or str(b))
                else:
                    formatted.append(str(b))
            bugs_text = "<br>• ".join(formatted) if formatted else "Clean (0 bugs)"
            html_content += f"""
                <tr>
                    <td><strong>{r.get('deliverable_id')}</strong></td>
                    <td>{status_badge}</td>
                    <td><a href="{r.get('url', '#')}" target="_blank" style="color: #38bdf8;">{r.get('url', 'N/A')}</a></td>
                    <td style="color: {'#94a3b8' if r.get('is_passed') else '#fca5a5'};">{bugs_text}</td>
                </tr>
            """
        html_content += "</tbody></table></div></body></html>"
        
        try:
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except Exception:
            import tempfile
            report_filename = os.path.join(tempfile.gettempdir(), os.path.basename(report_filename))
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
        log_success(f"Interactive report generated at: {report_filename}")
    except Exception as e_report:
        log_warn(f"Could not generate HTML report file: {e_report}")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main():
    log_header("STARTING BATCH QA PROCESS")
    
    driver = connect_to_browser()
    if not driver:
        return
        
    smartsheet_handle, dynamics_handle = identify_tabs(driver)
    if not smartsheet_handle:
        log_error("Smartsheet must be open to continue.")
        return
        
    tasks = extract_smartsheet_tasks(driver, smartsheet_handle)
    if not tasks:
        log_warn("No tasks found for 'Diego Torrez' with status 'In progress'.")
        return
        
    log_info(f"Starting processing of {len(tasks)} tasks...")
    all_results = []
    reserved_handles = set(driver.window_handles)
    
    for idx, t in enumerate(tasks, 1):
        del_id = t.get('deliverable_id')
        cms_link = t.get('cms_link')
        
        print(f"\n[{idx}/{len(tasks)}] ----------------------------------------")
        log_info(f"Processing: {TermColors.BOLD}{del_id}{TermColors.END}")
        
        try:
            # 1. Abrir deliverable en Dynamics 365 y obtener todos sus datos
            dyn_data = fetch_dynamics_data(driver, dynamics_handle, del_id, cms_link)
            
            # Sincronizar copia con la herramienta Vercel por si deseas consultarlo en web
            try:
                if requests and dyn_data.get('found'):
                    payload = {
                        'deliverable_id': del_id,
                        'deliverable_url': dyn_data.get('deliverable_url') or '',
                        'title': dyn_data.get('title'),
                        'completed_copy': dyn_data.get('copy'),
                        'completed_page_url': dyn_data.get('url'),
                        'ctas_and_links': dyn_data.get('ctas'),
                        'special_instructions': dyn_data.get('details'),
                        'source': 'vdi_batch_runner'
                    }
                    requests.post('https://qa-tool-brown.vercel.app/api/save-extracted-dynamics', json=payload, timeout=2)
            except Exception:
                pass
            
            # 2. Auditar usando directamente la interfaz de la QA Web App
            # Pasa reserved_handles para garantizar que NUNCA se sobreescriba una pestaña ya revisada
            audit_res = run_qa_app_audit(driver, dyn_data, smartsheet_handle, dynamics_handle, reserved_handles)
            all_results.append(audit_res)
        except Exception as e_case:
            log_error(f"[{del_id}] Error processing task: {e_case}")
            all_results.append({
                'deliverable_id': del_id,
                'url': cms_link,
                'is_passed': False,
                'bugs': [f"Execution error: {str(e_case)[:100]}"]
            })
            
        time.sleep(1)
        
    # 4. Generar resumen ejecutivo
    print_and_export_summary(all_results)
    log_success("Batch processing completed successfully!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Execution interrupted by user.")
    except Exception as e:
        print(f"\n\n{TermColors.RED}[CRITICAL ERROR]{TermColors.END} An unexpected error occurred:")
        print(f"{TermColors.YELLOW}{str(e)}{TermColors.END}\n")
        import traceback
        traceback.print_exc()
    finally:
        print("\n" + "=" * 65)
        print("  Execution finished. Press ENTER to exit...")
        print("=" * 65)
        try:
            input()
        except Exception:
            pass
