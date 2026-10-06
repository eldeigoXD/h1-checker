#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
SMARTSHEET CASE ASSIGNMENT TOOL - DIEGO TORREZ
Automated Case Claimer: Claims unassigned cases from the top of the Smartsheet queue
and sets:
  - Date: Current Date (MM/dd/yy)
  - QA Completed By: Diego Torrez
  - QA Status: In progress
================================================================================
"""

import sys
import os
import json
import time
import datetime
import argparse
from urllib.parse import urlparse

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("❌ Error: Selenium is not installed in this environment. Run: pip install selenium")
    sys.exit(1)

# Terminal colors
class TermColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
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
# ASSIGNEE MANAGEMENT HELPERS (HISTORIAL Y SELECCIÓN DE NOMBRES)
# ==============================================================================
ASSIGNEES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_assignees.json")

def load_saved_assignees():
    default_assignees = ["Diego Torrez"]
    if not os.path.exists(ASSIGNEES_FILE):
        return default_assignees
    try:
        with open(ASSIGNEES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list) and data:
                cleaned = []
                for name in data:
                    if isinstance(name, str) and name.strip() and name.strip() not in cleaned:
                        cleaned.append(name.strip())
                if "Diego Torrez" not in cleaned:
                    cleaned.insert(0, "Diego Torrez")
                return cleaned
    except Exception:
        pass
    return default_assignees

def save_assignees(assignees_list):
    try:
        with open(ASSIGNEES_FILE, "w", encoding="utf-8") as f:
            json.dump(assignees_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_warn(f"No se pudo guardar la lista de asignados: {e}")

def select_assignee(cli_name=None):
    saved_list = load_saved_assignees()
    if cli_name:
        chosen = cli_name.strip()
        if chosen and chosen not in saved_list:
            saved_list.append(chosen)
            save_assignees(saved_list)
        return chosen

    print(f"\n{TermColors.BOLD}¿A quién deseas asignar los casos?{TermColors.END}")
    for idx, name in enumerate(saved_list, 1):
        suffix = " (Por defecto - Presiona ENTER o 1)" if idx == 1 else ""
        print(f"  [{idx}] {name}{suffix}")
    
    new_opt_num = len(saved_list) + 1
    print(f"  [{new_opt_num}] Ingresar un nuevo nombre...")

    try:
        choice = input(f"{TermColors.CYAN}Opción [Por defecto: 1 - {saved_list[0]}]: {TermColors.END}").strip()
    except (KeyboardInterrupt, Exception):
        return saved_list[0]

    # Si presiona ENTER o 1 -> Diego Torrez
    if not choice or choice == "1":
        return saved_list[0]

    # Si eligió ingresar nuevo nombre
    if choice == str(new_opt_num) or choice.lower() in ["nuevo", "new", "+"]:
        try:
            custom_name = input(f"{TermColors.CYAN}Escribe el nombre y apellido a asignar: {TermColors.END}").strip()
            if custom_name:
                if custom_name not in saved_list:
                    saved_list.append(custom_name)
                    save_assignees(saved_list)
                return custom_name
        except (KeyboardInterrupt, Exception):
            pass
        return saved_list[0]

    # Si ingresó un número de la lista existente
    if choice.isdigit():
        idx_choice = int(choice) - 1
        if 0 <= idx_choice < len(saved_list):
            return saved_list[idx_choice]

    # Si escribió directamente un nombre (ej. "Carlos Lopez")
    if len(choice) >= 2 and not choice.isdigit():
        custom_name = choice.strip()
        if custom_name not in saved_list:
            saved_list.append(custom_name)
            save_assignees(saved_list)
        return custom_name

    return saved_list[0]

# ==============================================================================
# DATE PARSING & PATTERN GENERATION HELPERS
# ==============================================================================
def parse_user_date(input_str, default_date=None):
    """
    Parsea una fecha ingresada por el usuario en varios formatos posibles.
    Retorna un objeto datetime.date o None si es inválido.
    """
    today = datetime.date.today()
    if default_date is None:
        default_date = today - datetime.timedelta(days=1)
        
    if not input_str:
        return default_date
        
    s = input_str.strip().lower()
    
    if s in ['1', 'ayer', 'yesterday']:
        return today - datetime.timedelta(days=1)
        
    if s in ['2', 'hoy', 'today']:
        return today
        
    if s in ['antier', 'anteayer']:
        return today - datetime.timedelta(days=2)
        
    formats = [
        "%m/%d/%y",      # 09/29/26
        "%m/%d/%Y",      # 09/29/2026
        "%d/%m/%y",      # 29/09/26
        "%d/%m/%Y",      # 29/09/2026
        "%Y-%m-%d",      # 2026-09-29
        "%m-%d-%y",      # 09-29-26
        "%m-%d-%Y",      # 09-29-2026
        "%m/%d",         # 09/29 (año actual)
        "%m-%d",         # 09-29 (año actual)
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if "%y" not in fmt.lower():
                dt = dt.replace(year=today.year)
            return dt.date()
        except ValueError:
            continue
            
    return None

def generate_date_patterns(target_date):
    """
    Genera todas las variaciones de texto en que una fecha puede aparecer en una fila de Smartsheet.
    """
    m = target_date.month
    d = target_date.day
    y = target_date.year
    yy = str(y)[-2:]
    
    month_names_en = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_full_en = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    
    patterns = set()
    
    # MM/DD/YY y M/D/YY
    patterns.add(f"{m:02d}/{d:02d}/{yy}")   # 09/29/26
    patterns.add(f"{m}/{d}/{yy}")           # 9/29/26
    patterns.add(f"{m:02d}/{d}/{yy}")       # 09/29/26
    patterns.add(f"{m}/{d:02d}/{yy}")       # 9/29/26
    
    # MM/DD/YYYY y M/D/YYYY
    patterns.add(f"{m:02d}/{d:02d}/{y}")    # 09/29/2026
    patterns.add(f"{m}/{d}/{y}")            # 9/29/2026
    
    # Con guiones
    patterns.add(f"{m:02d}-{d:02d}-{yy}")   # 09-29-26
    patterns.add(f"{m}-{d}-{yy}")           # 9-29-26
    patterns.add(f"{y}-{m:02d}-{d:02d}")   # 2026-09-29
    
    # Nombres de mes
    if 1 <= m <= 12:
        patterns.add(f"{month_names_en[m]} {d}")
        patterns.add(f"{month_names_en[m]} {d:02d}")
        patterns.add(f"{month_full_en[m]} {d}")
        if m == 9:
            patterns.add(f"Sept {d}")
            patterns.add(f"Sept {d:02d}")
            
    return list(patterns)

# Connect to Helium/Chrome
def connect_to_browser(debugger_address="127.0.0.1:9222"):
    log_info(f"Conectando a Chrome/Helium en {debugger_address}...")
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_address)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        log_success("Conectado con éxito a Chrome/Helium.")
        return driver
    except Exception as e:
        log_error(f"No se pudo conectar a {debugger_address}.")
        print(f"\n{TermColors.YELLOW}👉 Ayuda:")
        print("1. Abre Helium con el puerto de depuración ejecutando 'lanzar_helium_sesion.bat'.")
        print("2. O agrega '--remote-debugging-port=9222' a tu acceso directo de Helium.")
        print(f"Error técnico: {e}{TermColors.END}\n")
        return None

# Find Smartsheet tab
def find_smartsheet_tab(driver):
    log_info("Buscando pestaña de Smartsheet...")
    smartsheet_handle = None
    
    try:
        handles = driver.window_handles
        for h in handles:
            driver.switch_to.window(h)
            url = driver.current_url.lower()
            title = driver.title.lower()
            if 'smartsheet.com' in url or 'report to start qa' in title or 'dynamicview' in url or 'smartsheet' in title:
                smartsheet_handle = h
                log_success(f"Pestaña de Smartsheet encontrada: '{driver.title}'")
                break
    except Exception as e:
        log_error(f"Error inspeccionando pestañas: {e}")
        return None

    if not smartsheet_handle:
        log_error("No se encontró la pestaña de Smartsheet. Abre 'Report to start QA V2' en Helium.")
    return smartsheet_handle

# JavaScript to scan unassigned rows from top to bottom
SCAN_UNASSIGNED_ROWS_JS = """
var targetPatterns = arguments[0]; // array de strings con patrones de la fecha ej. ["09/29/26", "9/29/26", ...]
var targetOwner = (arguments[1] || 'Diego Torrez').trim().toLowerCase();
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
            // Buscar el contenedor del cuerpo de la tabla virtualizada (no el encabezado)
            var bodyGrid = doc.querySelector('.ReactVirtualized__Table__Grid') || doc.querySelector('.ReactVirtualized__Grid:not(.ReactVirtualized__Table__headerGrid)');
            var container = bodyGrid || doc;
            var rawRows = container.querySelectorAll('.ReactVirtualized__Table__row, [role="row"], div.ReactVirtualized__Grid > div > div');
            var rows = Array.prototype.slice.call(rawRows);

            // FILTRO DE FILAS REALES (descartar encabezados y contenedores madre)
            var validRows = [];
            for (var i = 0; i < rows.length; i++) {
                var r = rows[i];
                if (r.getAttribute('role') === 'columnheader' || r.querySelector('[role="columnheader"]') || r.tagName === 'TH' || r.classList.contains('ReactVirtualized__Table__headerRow')) continue;
                if (r.querySelectorAll('.ReactVirtualized__Table__row, [role="row"]').length > 0) continue;
                validRows.push(r);
            }

            // ORDENAMIENTO ESTRICTO DE ARRIBA HACIA ABAJO (por posición física real en pantalla)
            validRows.sort(function(a, b) {
                var rectA = a.getBoundingClientRect();
                var rectB = b.getBoundingClientRect();
                return rectA.top - rectB.top;
            });

            for (var rIdx = 0; rIdx < validRows.length; rIdx++) {
                var row = validRows[rIdx];
                var rText = (row.innerText || row.textContent || '').trim();
                var rTextLow = rText.toLowerCase();

                // Debe contener un Deliverable ID valido: D-\\d+
                var m = rText.match(/\\b(D-\\d+)\\b/i);
                if (!m) continue;
                var delId = m[1].toUpperCase();
                if (seenIds.has(delId)) continue;

                // Descartar si ya tiene un estado de QA explícito en la fila
                if (/\\b(passed|failed|in progress|opportunity|critical)\\b/i.test(rTextLow)) {
                    continue;
                }

                // Descartar si ya tiene asignado al owner objetivo
                if (targetOwner && rTextLow.indexOf(targetOwner) !== -1) {
                    continue;
                }

                // FILTRO ESTRICTO DE FECHA: Si se especificaron patrones, la fila DEBE coincidir con la fecha seleccionada
                if (targetPatterns && targetPatterns.length > 0) {
                    var matchesDate = false;
                    for (var p = 0; p < targetPatterns.length; p++) {
                        var pat = targetPatterns[p];
                        if (pat && rText.indexOf(pat) !== -1) {
                            matchesDate = true;
                            break;
                        }
                    }
                    if (!matchesDate) {
                        continue; // No pertenece a la fecha seleccionada
                    }
                }

                seenIds.add(delId);
                results.push({
                    deliverable_id: delId,
                    row_index: rIdx
                });
            }
            if (results.length > 0) break;
        }

        return { total: results.length, cases: results };
    } catch(err) {
        return { total: 0, cases: [], error: String(err) };
    }
})();
"""

# JavaScript to scroll the grid (targeting the body table, not the header)
SCROLL_GRID_JS = """
var direction = arguments[0]; // 'top' or 'down'
return (function() {
    function findScrollableGrid() {
        var g = document.querySelector('.ReactVirtualized__Table__Grid');
        if (g) return g;
        var allGrids = document.querySelectorAll('.ReactVirtualized__Grid');
        for (var i = 0; i < allGrids.length; i++) {
            if (!allGrids[i].classList.contains('ReactVirtualized__Table__headerGrid')) {
                return allGrids[i];
            }
        }
        return document.querySelector('.grid-view-body, [role="grid"]');
    }

    var grid = findScrollableGrid();
    if (grid) {
        if (direction === 'top') {
            grid.scrollTop = 0;
            return { at_bottom: false, top: 0 };
        } else {
            var prev = grid.scrollTop;
            grid.scrollTop += 380;
            var at_bottom = (grid.scrollTop + grid.clientHeight >= grid.scrollHeight - 10) || (grid.scrollTop === prev);
            return { at_bottom: at_bottom, top: grid.scrollTop };
        }
    }
    return { at_bottom: true, top: 0 };
})();
"""

# JavaScript to claim a single case with deliberate pacing
CLAIM_SINGLE_CASE_JS = """
var delId = arguments[0];
var todayDateStr = arguments[1]; // e.g. "09/30/26" (SIEMPRE FECHA DE HOY)
var todayDayNumber = arguments[2]; // e.g. 30 (SIEMPRE DÍA DE HOY)
var targetOwner = arguments[3] || 'Diego Torrez';
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

        // 1. Encontrar la fila que corresponde a delId
        var targetRow = null;
        var activeDoc = document;
        for (var docIdx = 0; docIdx < docs.length; docIdx++) {
            var doc = docs[docIdx];
            var rows = doc.querySelectorAll('.ReactVirtualized__Table__row, [role="row"], tr, div.ReactVirtualized__Grid > div > div');
            for (var r = 0; r < rows.length; r++) {
                var txt = (rows[r].innerText || rows[r].textContent || '');
                var re = new RegExp('\\\\b' + delId.replace('-', '\\\\-') + '\\\\b', 'i');
                if (re.test(txt)) {
                    targetRow = rows[r];
                    activeDoc = doc;
                    break;
                }
            }
            if (targetRow) break;
        }

        if (!targetRow) {
            done({ success: false, reason: 'Fila ' + delId + ' no encontrada en la vista actual' });
            return;
        }

        targetRow.scrollIntoView({ behavior: 'auto', block: 'center' });

        // Clic en la celda con el ID o celda de la fila para abrir el panel lateral
        var clickTarget = null;
        var cells = targetRow.querySelectorAll('.data-cell, .cell-content, [data-testid="value-with-spans"], [role="gridcell"], div');
        for (var c = 0; c < cells.length; c++) {
            var cTxt = (cells[c].innerText || cells[c].textContent || '').trim();
            if (cTxt.toUpperCase().indexOf(delId.toUpperCase()) !== -1) {
                clickTarget = cells[c];
                break;
            }
        }
        if (!clickTarget) clickTarget = targetRow;

        // Clic firme en la fila y en la celda
        fireMouseEvent(targetRow, 'mousedown');
        fireMouseEvent(targetRow, 'mouseup');
        targetRow.click();
        if (clickTarget && clickTarget !== targetRow) {
            clickTarget.focus && clickTarget.focus();
            fireMouseEvent(clickTarget, 'mousedown');
            fireMouseEvent(clickTarget, 'mouseup');
            clickTarget.click();
        }

        // 2. Esperar que el panel lateral de detalles se abra Y muestre los datos de este caso
        var startWaitPanel = Date.now();
        var panelTimer = setInterval(function() {
            var elapsed = Date.now() - startWaitPanel;
            var panel = null;
            for (var d = 0; d < docs.length; d++) {
                panel = docs[d].querySelector('.details-data, .details-list, div[id*="panel-gen-id"]');
                if (panel) break;
            }

            if (panel) {
                // Verificar si el panel ya cargó los datos de este delId
                var panelText = (panel.innerText || panel.textContent || '');
                var reId = new RegExp('\\\\b' + delId.replace('-', '\\\\-') + '\\\\b', 'i');
                var hasThisCase = reId.test(panelText);

                if (hasThisCase || elapsed > 2000) {
                    clearInterval(panelTimer);
                    // Pausa deliberada de 1.2s para que Smartsheet termine de renderizar los inputs
                    setTimeout(function() {
                        fillDetailsAndSave(panel, activeDoc);
                    }, 1200);
                    return;
                }
            }

            if (elapsed > 7500) {
                clearInterval(panelTimer);
                done({ success: false, reason: 'El panel lateral no abrió o no cargó los datos de ' + delId + ' tras 7.5s' });
            }
        }, 200);

        // 3. Llenar campos paso a paso con tiempos generosos
        function fillDetailsAndSave(panel, doc) {
            var statusCbCheck = panel.querySelector('#pli-2') || doc.querySelector('#pli-2');
            var ownerCbCheck = panel.querySelector('#pli-1') || doc.querySelector('#pli-1');
            
            var currentStatus = statusCbCheck ? (statusCbCheck.value || statusCbCheck.getAttribute('value') || statusCbCheck.innerText || '').trim().toLowerCase() : '';
            var currentOwner = ownerCbCheck ? (ownerCbCheck.value || ownerCbCheck.getAttribute('value') || ownerCbCheck.innerText || '').trim().toLowerCase() : '';

            var targetOwnerLow = (targetOwner || '').trim().toLowerCase();
            var ownerParts = targetOwnerLow.split(/\\s+/).filter(Boolean);
            var ownerAlreadyMatches = ownerParts.length > 0 && ownerParts.every(function(p) { return currentOwner.indexOf(p) !== -1; });

            // Solo omitir si ya está asignado al targetOwner y en progreso
            if (currentStatus === 'in progress' && ownerAlreadyMatches) {
                done({ success: true, saved: true, already_assigned: true, deliverable_id: delId });
                return;
            }

            // PASO A: Fecha
            setDateField(panel, doc, function() {
                // Pausa deliberada de 800ms antes del Owner
                setTimeout(function() {
                    // PASO B: Owner
                    setOwnerField(panel, doc, function() {
                        // Pausa deliberada de 800ms antes del Status
                        setTimeout(function() {
                            // PASO C: QA Status (In progress)
                            setQAStatusField(panel, doc, function() {
                                // Pausa deliberada de 1.2s para que Smartsheet active Save
                                setTimeout(function() {
                                    // PASO D: Clic en Save
                                    clickSave(panel, doc);
                                }, 1200);
                            });
                        }, 800);
                    });
                }, 800);
            });
        }

        // =====================================================================
        // PASO A: Seleccionar Fecha ([data-testid='ffw-3']) -> SIEMPRE FECHA DE HOY
        // =====================================================================
        function setDateField(panel, doc, next) {
            var wrapper = panel.querySelector("[data-testid='ffw-3']") || doc.querySelector("[data-testid='ffw-3']");
            var dateInput = wrapper ? (wrapper.querySelector('input') || wrapper) : panel.querySelector('input[aria-label*="MM/dd" i], input[placeholder*="MM/dd" i]');
            
            if (!dateInput && !wrapper) {
                console.warn('[CLAIM] Campo de fecha no encontrado, continuando...');
                setTimeout(next, 400);
                return;
            }

            var clickTarget = dateInput || wrapper;
            clickTarget.focus && clickTarget.focus();
            fireMouseEvent(clickTarget, 'mousedown');
            fireMouseEvent(clickTarget, 'mouseup');
            clickTarget.click();

            // Esperar que el calendario emergente aparezca (#dateSelectorWrapper)
            var startWaitPicker = Date.now();
            var pickerTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitPicker;
                var targetDay = null;

                for (var d = 0; d < docs.length; d++) {
                    var cDoc = docs[d];
                    
                    // La fecha de asignación SIEMPRE es la fecha de HOY
                    targetDay = cDoc.querySelector('#dateSelectorWrapper .react-datepicker__day--today, .react-datepicker__day--today');
                    if (targetDay) break;

                    // Fallback: día exacto de hoy (todayDayNumber)
                    var dayPad = (todayDayNumber < 10 ? '00' : '0') + todayDayNumber;
                    var dayPad2 = (todayDayNumber < 10 ? '0' : '') + todayDayNumber;

                    var dayCandidates = cDoc.querySelectorAll(
                        '#dateSelectorWrapper .react-datepicker__day--' + dayPad + ':not(.react-datepicker__day--outside-month), ' +
                        '#dateSelectorWrapper .react-datepicker__day--' + dayPad2 + ':not(.react-datepicker__day--outside-month), ' +
                        '.react-datepicker__day--' + dayPad + ':not(.react-datepicker__day--outside-month), ' +
                        '.react-datepicker__day--' + dayPad2 + ':not(.react-datepicker__day--outside-month)'
                    );
                    if (dayCandidates.length > 0) {
                        targetDay = dayCandidates[0];
                        break;
                    }

                    var allDays = cDoc.querySelectorAll('#dateSelectorWrapper .react-datepicker__day:not(.react-datepicker__day--outside-month), .react-datepicker__day:not(.react-datepicker__day--outside-month)');
                    for (var dy = 0; dy < allDays.length; dy++) {
                        var dTxt = (allDays[dy].innerText || allDays[dy].textContent || '').trim();
                        if (dTxt === String(todayDayNumber)) {
                            targetDay = allDays[dy];
                            break;
                        }
                    }
                    if (targetDay) break;
                }

                if (targetDay) {
                    clearInterval(pickerTimer);
                    fireMouseEvent(targetDay, 'mousedown');
                    fireMouseEvent(targetDay, 'mouseup');
                    targetDay.click();

                    // Disparar además el valor nativo para que React registre el cambio con la fecha de HOY
                    try {
                        var realInput = (dateInput && dateInput.tagName === 'INPUT') ? dateInput : (wrapper ? wrapper.querySelector('input') : null);
                        if (realInput) {
                            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeSetter.call(realInput, todayDateStr);
                            realInput.dispatchEvent(new Event('input', { bubbles: true }));
                            realInput.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    } catch(e) {}

                    // Pausa deliberada de 800ms tras seleccionar fecha de hoy
                    setTimeout(next, 800);
                } else if (elapsed > 4000) {
                    clearInterval(pickerTimer);
                    // Fallback directo mediante valor nativo de input con fecha de hoy
                    try {
                        var realInput = (dateInput && dateInput.tagName === 'INPUT') ? dateInput : (wrapper ? wrapper.querySelector('input') : null);
                        if (realInput) {
                            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeSetter.call(realInput, todayDateStr);
                            realInput.dispatchEvent(new Event('input', { bubbles: true }));
                            realInput.dispatchEvent(new Event('change', { bubbles: true }));
                            realInput.dispatchEvent(new Event('blur', { bubbles: true }));
                        }
                    } catch(e) {}
                    setTimeout(next, 600);
                }
            }, 200);
        }

        // =====================================================================
        // PASO B: Seleccionar Owner -> targetOwner (#pli-1)
        // =====================================================================
        function setOwnerField(panel, doc, next) {
            var ownerCb = panel.querySelector('#pli-1') || doc.querySelector('#pli-1');
            if (!ownerCb) {
                console.warn('[CLAIM] Campo de Owner #pli-1 no encontrado');
                setTimeout(next, 400);
                return;
            }

            var currentVal = (ownerCb.value || ownerCb.getAttribute('value') || ownerCb.innerText || '').trim().toLowerCase();
            var targetOwnerLow = (targetOwner || '').trim().toLowerCase();
            var ownerParts = targetOwnerLow.split(/\\s+/).filter(Boolean);
            var alreadyMatched = ownerParts.length > 0 && ownerParts.every(function(p) { return currentVal.indexOf(p) !== -1; });

            if (alreadyMatched) {
                // Ya tiene al targetOwner
                setTimeout(next, 300);
                return;
            }

            ownerCb.focus && ownerCb.focus();
            fireMouseEvent(ownerCb, 'mousedown');
            fireMouseEvent(ownerCb, 'mouseup');
            ownerCb.click();

            // Esperar opciones del desplegable
            var startWaitOwner = Date.now();
            var ownerTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitOwner;
                var targetOpt = null;

                for (var d = 0; d < docs.length; d++) {
                    var cDoc = docs[d];
                    
                    // Selector rápido histórico para Diego Torrez: #pli-1-item-14
                    if (targetOwnerLow.indexOf('diego') !== -1 && targetOwnerLow.indexOf('torrez') !== -1) {
                        targetOpt = cDoc.querySelector('#pli-1-item-14');
                        if (targetOpt) break;
                    }

                    var options = cDoc.querySelectorAll('[role="option"], div[id*="item"], .sds-option-base, li, span');
                    for (var o = 0; o < options.length; o++) {
                        var oTxt = (options[o].innerText || options[o].textContent || '').trim().toLowerCase();
                        if (ownerParts.length > 0 && ownerParts.every(function(p) { return oTxt.indexOf(p) !== -1; })) {
                            targetOpt = options[o].closest('[role="option"], div') || options[o];
                            break;
                        }
                    }
                    if (targetOpt) break;
                }

                if (targetOpt) {
                    clearInterval(ownerTimer);
                    fireMouseEvent(targetOpt, 'mousedown');
                    fireMouseEvent(targetOpt, 'mouseup');
                    targetOpt.click();

                    if (ownerCb.tagName === 'INPUT') {
                        ownerCb.value = targetOwner;
                        ownerCb.dispatchEvent(new Event('input', { bubbles: true }));
                        ownerCb.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    // Pausa deliberada de 800ms tras seleccionar Owner
                    setTimeout(next, 800);
                } else if (elapsed > 4500) {
                    clearInterval(ownerTimer);
                    setTimeout(next, 300);
                }
            }, 200);
        }

        // =====================================================================
        // PASO C: Seleccionar QA Status -> In progress (#pli-2)
        // =====================================================================
        function setQAStatusField(panel, doc, next) {
            var statusCb = panel.querySelector('#pli-2') || doc.querySelector('#pli-2');
            if (!statusCb) {
                console.warn('[CLAIM] Campo de QA Status #pli-2 no encontrado');
                setTimeout(next, 400);
                return;
            }

            var currentVal = (statusCb.value || statusCb.getAttribute('value') || statusCb.innerText || '').trim().toLowerCase();
            if (currentVal === 'in progress') {
                setTimeout(next, 300);
                return;
            }

            statusCb.focus && statusCb.focus();
            fireMouseEvent(statusCb, 'mousedown');
            fireMouseEvent(statusCb, 'mouseup');
            statusCb.click();

            // Esperar opción "In progress"
            var startWaitStatus = Date.now();
            var statusTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitStatus;
                var inProgOpt = null;

                for (var d = 0; d < docs.length; d++) {
                    var cDoc = docs[d];
                    // Selector exacto de la grabación: #pli-2-item-0
                    inProgOpt = cDoc.querySelector('#pli-2-item-0');
                    if (inProgOpt) break;

                    var options = cDoc.querySelectorAll('[role="option"], div[id*="item"], .sds-option-base, li, span');
                    for (var o = 0; o < options.length; o++) {
                        var oTxt = (options[o].innerText || options[o].textContent || '').trim().toLowerCase();
                        if (oTxt === 'in progress') {
                            inProgOpt = options[o].closest('[role="option"], div') || options[o];
                            break;
                        }
                    }
                    if (inProgOpt) break;
                }

                if (inProgOpt) {
                    clearInterval(statusTimer);
                    fireMouseEvent(inProgOpt, 'mousedown');
                    fireMouseEvent(inProgOpt, 'mouseup');
                    inProgOpt.click();

                    if (statusCb.tagName === 'INPUT') {
                        statusCb.value = 'In progress';
                        statusCb.dispatchEvent(new Event('input', { bubbles: true }));
                        statusCb.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    // Pausa deliberada de 800ms tras seleccionar Status
                    setTimeout(next, 800);
                } else if (elapsed > 4500) {
                    clearInterval(statusTimer);
                    setTimeout(next, 300);
                }
            }, 200);
        }

        // =====================================================================
        // PASO D: Clic en Save (#detailsDataFooterSaveBtn) con tiempo de guardado
        // =====================================================================
        function clickSave(panel, doc) {
            var startWaitSave = Date.now();
            var saveTimer = setInterval(function() {
                var elapsed = Date.now() - startWaitSave;
                var saveBtn = null;

                for (var d = 0; d < docs.length; d++) {
                    saveBtn = docs[d].querySelector('#detailsDataFooterSaveBtn, button#detailsDataFooterSaveBtn, button[data-client-id="details-footer-save"]');
                    if (saveBtn) break;
                }

                if (saveBtn) {
                    var isDisabled = saveBtn.disabled || saveBtn.getAttribute('aria-disabled') === 'true' || saveBtn.classList.contains('disabled');
                    if (!isDisabled) {
                        clearInterval(saveTimer);
                        saveBtn.focus && saveBtn.focus();
                        fireMouseEvent(saveBtn, 'mousedown');
                        fireMouseEvent(saveBtn, 'mouseup');
                        saveBtn.click();
                        var span = saveBtn.querySelector('span');
                        if (span) span.click();

                        // PAUSA GENEROSA POST-GUARDADO: 2.8 segundos para que Smartsheet complete la petición de red
                        setTimeout(function() {
                            done({ success: true, saved: true, deliverable_id: delId });
                        }, 2800);
                        return;
                    }
                }

                if (elapsed > 5500) {
                    clearInterval(saveTimer);
                    done({ success: true, saved: false, reason: 'El botón Save estuvo deshabilitado o expiró el tiempo', deliverable_id: delId });
                }
            }, 250);
        }

    } catch(err) {
        done({ success: false, error: String(err) });
    }
})();
"""

def main():
    parser = argparse.ArgumentParser(description="Auto-claim Smartsheet QA cases")
    parser.add_argument("--count", type=int, default=None, help="Number of unassigned cases to claim (default: prompt user, default 10)")
    parser.add_argument("--date", type=str, default=None, help="Target date to filter and claim (e.g. '09/29/26', 'ayer', 'today')")
    parser.add_argument("--owner", "--name", dest="owner", type=str, default=None, help="Owner name to assign cases to (default: prompt user)")
    parser.add_argument("--port", type=str, default="127.0.0.1:9222", help="Chrome remote debugging address")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("   📋 SMARTSHEET CASE ASSIGNMENT TOOL")
    print("=" * 60)

    # 1. Selección de Owner a quien asignar
    target_owner = select_assignee(args.owner)

    # 2. Cantidad de casos
    target_count = args.count
    if target_count is None:
        try:
            val = input(f"\n{TermColors.BOLD}¿Cuántos casos en blanco deseas asignar a {target_owner}? [Por defecto: 10]: {TermColors.END}").strip()
            if not val:
                target_count = 10
            else:
                target_count = int(val)
        except (ValueError, KeyboardInterrupt):
            target_count = 10

    if target_count <= 0:
        log_warn("La cantidad de casos debe ser mayor a 0.")
        return

    # 3. Selección de fecha de los casos a tomar (fecha en que fue completado el caso)
    filter_date = None
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    
    today_str = today.strftime("%m/%d/%y") # e.g. "09/30/26" (SIEMPRE FECHA DE HOY PARA ASIGNACIÓN)
    today_day_number = today.day # e.g. 30
    yesterday_str = yesterday.strftime("%m/%d/%y") # e.g. "09/29/26"
    
    if args.date:
        filter_date = parse_user_date(args.date, default_date=yesterday)
        if not filter_date:
            log_warn(f"No se pudo interpretar la fecha '{args.date}'. Usando casos de ayer ({yesterday_str}).")
            filter_date = yesterday
    else:
        print(f"\n{TermColors.BOLD}¿De qué fecha completada deseas tomar los casos de la tabla?{TermColors.END}")
        print(f"  [1] Ayer ({yesterday_str}) [Presiona ENTER para casos de ayer]")
        print(f"  [2] Hoy ({today_str})")
        print(f"  O escribe una fecha específica (ej: 09/29/26):")
        print(f"  {TermColors.YELLOW}(Nota: Tus datos de asignación siempre se registrarán con la fecha de HOY: {today_str}){TermColors.END}")
        
        try:
            date_input = input(f"{TermColors.CYAN}Opción o fecha [Por defecto: 1 - Ayer ({yesterday_str})]: {TermColors.END}").strip()
            filter_date = parse_user_date(date_input, default_date=yesterday)
            if not filter_date:
                filter_date = yesterday
        except (KeyboardInterrupt, Exception):
            filter_date = yesterday

    filter_date_str = filter_date.strftime("%m/%d/%y") # e.g. "09/29/26"
    date_patterns = generate_date_patterns(filter_date)

    log_header("CONFIGURACIÓN DE ASIGNACIÓN")
    print(f" • Cantidad de casos a tomar:     {TermColors.BOLD}{target_count}{TermColors.END}")
    print(f" • Filtro de casos en tabla:      {TermColors.BOLD}{filter_date_str}{TermColors.END} ({filter_date.strftime('%A, %B %d, %Y')})")
    print(f" • Fecha de registro (HOY):       {TermColors.BOLD}{today_str}{TermColors.END} (¡Esta fecha SIEMPRE es hoy y no cambia!)")
    print(f" • Asignado a (Owner):            {TermColors.BOLD}{target_owner}{TermColors.END}")
    print(f" • Estado (QA Status):            {TermColors.BOLD}In progress{TermColors.END}")
    print(f" • Orden de selección:            De arriba hacia abajo (solo casos del {filter_date_str})")
    print("=" * 60 + "\n")

    # 4. Connect to browser
    driver = connect_to_browser(args.port)
    if not driver:
        return

    # 5. Find Smartsheet tab
    smartsheet_handle = find_smartsheet_tab(driver)
    if not smartsheet_handle:
        return

    driver.switch_to.window(smartsheet_handle)
    time.sleep(1.5)

    # Scroll grid to top first
    log_info("Desplazando la tabla al inicio (arriba del todo)...")
    driver.execute_script(SCROLL_GRID_JS, 'top')
    time.sleep(2.0)

    claimed_cases = []
    seen_ids = set()
    scroll_attempts = 0
    max_scrolls = 35

    log_header("PROCESANDO ASIGNACIÓN DE CASOS")
    log_info(f"Buscando casos de arriba hacia abajo completados el {TermColors.BOLD}{filter_date_str}{TermColors.END} (asignando a {target_owner} con fecha de hoy {today_str})...")

    while len(claimed_cases) < target_count and scroll_attempts < max_scrolls:
        # Escaneo en tiempo real: buscando filas sin asignar que coincidan con la fecha completada
        scan_data = driver.execute_script(SCAN_UNASSIGNED_ROWS_JS, date_patterns, target_owner) or {}
        available_cases = scan_data.get('cases', [])
        
        # Filtrar IDs ya procesados en esta ejecución
        fresh_cases = [c for c in available_cases if c.get('deliverable_id') not in seen_ids]

        if not fresh_cases:
            # Desplazar hacia abajo para cargar más filas de esa fecha
            scroll_attempts += 1
            log_info(f"Buscando más casos de {filter_date_str} hacia abajo (scroll {scroll_attempts}/{max_scrolls})...")
            scroll_res = driver.execute_script(SCROLL_GRID_JS, 'down')
            time.sleep(2.0)
            
            # Si llegamos al final del scroll y no hay más casos de esa fecha
            if scroll_res and scroll_res.get('at_bottom'):
                # Intento final en el fondo
                final_scan = driver.execute_script(SCAN_UNASSIGNED_ROWS_JS, date_patterns, target_owner) or {}
                final_fresh = [c for c in final_scan.get('cases', []) if c.get('deliverable_id') not in seen_ids]
                if not final_fresh:
                    log_warn(f"Se llegó al final de la tabla en Smartsheet y no hay más casos para la fecha {filter_date_str}.")
                    break
            continue

        # TOMAR SIEMPRE EL PRIMER CASO DE LA LISTA (el más arriba visualmente de esa fecha)
        case_info = fresh_cases[0]
        del_id = case_info.get('deliverable_id')
        seen_ids.add(del_id)
        current_num = len(claimed_cases) + 1
        log_info(f"[{current_num}/{target_count}] Reclamando caso {TermColors.BOLD}{del_id}{TermColors.END} para {target_owner} (Completado: {filter_date_str} | Registrando con fecha de hoy: {today_str})...")

        # Reclamar caso mediante script asíncrono pasando SIEMPRE la fecha de HOY y target_owner
        try:
            res = driver.execute_async_script(CLAIM_SINGLE_CASE_JS, del_id, today_str, today_day_number, target_owner)
        except Exception as e_claim:
            log_error(f"[{del_id}] Error interactuando con Smartsheet: {e_claim}")
            res = {'success': False, 'error': str(e_claim)}

        if res and res.get('success') and res.get('saved'):
            log_success(f"[{current_num}/{target_count}] ✅ Caso {del_id} asignado con éxito a {target_owner} | In progress | Fecha asignada: {today_str}")
            claimed_cases.append(del_id)
            # Pausa de 1.8 segundos para estabilización de Smartsheet
            time.sleep(1.8)
        else:
            reason = (res or {}).get('reason') or (res or {}).get('error') or 'Desconocido'
            log_warn(f"[{del_id}] ⚠️ No se pudo asignar: {reason}. Continuando con el siguiente...")
            time.sleep(1.0)

    # F5: Refrescar la página de Smartsheet si se asignaron casos
    if len(claimed_cases) > 0:
        log_info("🔄 Refrescando la página de Smartsheet (F5) para asentar y visualizar todos los cambios...")
        try:
            driver.refresh()
            time.sleep(3.5)
            log_success("Página de Smartsheet refrescada correctamente.")
        except Exception as e_ref:
            log_warn(f"No se pudo refrescar la página automáticamente: {e_ref}")

    # Summary report
    print("\n" + "=" * 60)
    print("   📊 RESUMEN DE CASOS ASIGNADOS")
    print("=" * 60)
    print(f" • Casos solicitados:             {target_count}")
    print(f" • Casos asignados:               {len(claimed_cases)}")
    print(f" • Fecha de casos tomada (filtro): {filter_date_str}")
    print(f" • Fecha de asignación puesta:    {today_str} (HOY)")
    print(f" • Owner asignado:                {target_owner}")
    print(f" • Estado asignado:               In progress")
    print("\n Lista de IDs asignados:")
    for idx, c_id in enumerate(claimed_cases, 1):
        print(f"   {idx}. {c_id}")

    if len(claimed_cases) > 0:
        print("\n" + TermColors.GREEN + f"🎉 ¡Listo! Ya tienes {len(claimed_cases)} casos asignados a {target_owner} en 'In progress'." + TermColors.END + "\n")
    else:
        log_warn(f"No se encontraron casos en blanco disponibles para la fecha {filter_date_str} en esta vista.")

    print("=" * 60)

if __name__ == "__main__":
    main()
