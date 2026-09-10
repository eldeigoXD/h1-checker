// Global State & Helpers accessible across all modules/modals
window.lastScanData = null;
window.escapeHtml = function(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
};
window.escapeHTML = window.escapeHtml;

document.addEventListener('DOMContentLoaded', () => {
    // Helper to poll background relay jobs when deployed on Vercel Cloud
    async function pollRelayJob(jobId) {
        const startTime = Date.now();
        const timeoutMs = 180000; // 3 minutes timeout for deep local scans
        const btnTextEl = document.querySelector('.btn-text');

        while (Date.now() - startTime < timeoutMs) {
            const elapsedSec = Math.round((Date.now() - startTime) / 1000);
            if (btnTextEl) {
                btnTextEl.style.display = 'inline';
                btnTextEl.textContent = `Home PC scanning... (${elapsedSec}s)`;
            }

            await new Promise(res => setTimeout(res, 2500));

            try {
                const res = await fetch(`/api/jobs/status?job_id=${encodeURIComponent(jobId)}`);
                const jobData = await res.json();

                if (jobData.status === 'completed' && jobData.result) {
                    if (btnTextEl) btnTextEl.textContent = 'Scan Quality';
                    return jobData.result;
                }
                if (jobData.status === 'failed') {
                    if (btnTextEl) btnTextEl.textContent = 'Scan Quality';
                    throw new Error(jobData.error || 'The audit scan failed on Home PC.');
                }
            } catch (e) {
                if (e.message && !e.message.includes('fetch') && !e.message.includes('HTTP')) {
                    throw e;
                }
            }
        }
        if (btnTextEl) btnTextEl.textContent = 'Scan Quality';
        throw new Error('Timeout: Home PC did not respond within 3 minutes. Please verify start_remote_worker.bat is running on your Home PC.');
    }

    // Helper to poll PDF relay jobs when deployed on Vercel Cloud
    async function pollRelayPdfJob(jobId) {
        const startTime = Date.now();
        const timeoutMs = 120000; // 2 minutes timeout for PDF generation
        const pdfBtn = document.getElementById('download-pdf-btn');

        while (Date.now() - startTime < timeoutMs) {
            const elapsedSec = Math.round((Date.now() - startTime) / 1000);
            if (pdfBtn) {
                pdfBtn.innerHTML = `<div class="loader" style="width:14px; height:14px;"></div> Generating on PC... (${elapsedSec}s)`;
            }

            await new Promise(res => setTimeout(res, 2000));

            try {
                const res = await fetch(`/api/jobs/status?job_id=${encodeURIComponent(jobId)}`);
                const jobData = await res.json();

                if (jobData.status === 'completed' && jobData.result) {
                    return jobData.result;
                }
                if (jobData.status === 'failed') {
                    throw new Error(jobData.error || 'PDF generation failed on Home PC.');
                }
            } catch (e) {
                if (e.message && !e.message.includes('fetch') && !e.message.includes('HTTP')) {
                    throw e;
                }
            }
        }
        throw new Error('Timeout: Home PC worker did not complete PDF generation within 2 minutes. Please verify start_remote_worker.bat is running on your PC.');
    }

    // Helper to poll Dynamics relay jobs when deployed on Vercel Cloud
    async function pollDynamicsRelayJob(jobId) {
        const startTime = Date.now();
        const timeoutMs = 120000;
        const statusMsgEl = document.getElementById('dynamics-status-msg');

        while (Date.now() - startTime < timeoutMs) {
            const elapsedSec = Math.round((Date.now() - startTime) / 1000);
            if (statusMsgEl) {
                statusMsgEl.textContent = `⏳ Home PC scraping Dynamics CRM... (${elapsedSec}s)`;
            }

            await new Promise(res => setTimeout(res, 2500));

            try {
                const res = await fetch(`/api/jobs/status?job_id=${encodeURIComponent(jobId)}`);
                const jobData = await res.json();

                if (jobData.status === 'completed' && jobData.result) {
                    return jobData.result;
                }
                if (jobData.status === 'failed') {
                    throw new Error(jobData.error || 'Dynamics extraction failed on Home PC.');
                }
            } catch (e) {
                if (e.message && !e.message.includes('fetch') && !e.message.includes('HTTP')) {
                    throw e;
                }
            }
        }
        throw new Error('Timeout: Home PC did not respond within 2 minutes. Make sure start_remote_worker.bat is running on your Home PC.');
    }

    function populateFormWithDynamicsData(data) {
        if (!data) return;

        const caseNumberInput = document.getElementById('case-number-input');
        const urlInput = document.getElementById('url-input');
        const expectedTitleInput = document.getElementById('expected-title-input');
        const expectedContentInput = document.getElementById('expected-content-input');
        const specialInstructionsInput = document.getElementById('special-instructions-input');
        const customRulesInput = document.getElementById('custom-rules-input');

        const seoPanelBody = document.querySelector('#seo-inputs-section .seo-panel-body');
        const toggleIcon = document.querySelector('#toggle-seo-inputs .toggle-icon');
        if (seoPanelBody && (seoPanelBody.style.display === 'none' || !seoPanelBody.style.display)) {
            seoPanelBody.style.display = 'block';
            if (toggleIcon) toggleIcon.textContent = '▲';
        }

        let filledCount = 0;

        const DYNAMICS_ICON_REGEX = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F\u200B-\u200D\u202A-\u202E\u2500-\u25FF\u2600-\u27BF\uE000-\uF8FF\uFFF0-\uFFFF]/g;

        function cleanFieldText(val) {
            if (!val) return '';
            return val.replace(DYNAMICS_ICON_REGEX, '').trim();
        }

        function cleanCtaPayload(val) {
            if (!val) return '';
            let cleaned = val.replace(DYNAMICS_ICON_REGEX, ' ').trim();
            let lines = cleaned.split(/[\r\n]+/)
                .map(l => {
                    let trimmed = l.replace(/^[•\-\*\s\u25A1\u25A0\u2022\u00A0]+/g, '').trim();
                    trimmed = trimmed.replace(/\b(calls\s*to\s*action|links|ctas(\s*and\s*links)?)\b/gi, '').trim();
                    trimmed = trimmed.replace(/^[:\-\s\t]+|[:\-\s\t]+$/g, '').trim();
                    return trimmed;
                })
                .filter(l => l && /[a-zA-Z0-9]/.test(l));
            return lines.join('\n');
        }

        const cleanedId = cleanFieldText(data.deliverable_id);
        if (cleanedId && caseNumberInput) {
            caseNumberInput.value = cleanedId;
            flashField(caseNumberInput);
            filledCount++;
        }

        const cleanedUrl = cleanFieldText(data.completed_page_url);
        if (cleanedUrl && urlInput) {
            urlInput.value = cleanedUrl;
            flashField(urlInput);
            filledCount++;
        }

        const cleanedTitle = cleanFieldText(data.title);
        if (cleanedTitle && expectedTitleInput) {
            expectedTitleInput.value = cleanedTitle;
            flashField(expectedTitleInput);
            filledCount++;
        }

        const cleanedCopy = cleanFieldText(data.completed_copy);
        if (cleanedCopy && expectedContentInput) {
            expectedContentInput.value = cleanedCopy;
            flashField(expectedContentInput);
            filledCount++;
        }

        const cleanedCtas = cleanCtaPayload(data.ctas_and_links || '');
        if (specialInstructionsInput) {
            specialInstructionsInput.value = cleanedCtas;
            if (cleanedCtas) {
                flashField(specialInstructionsInput);
                filledCount++;
            }
        }

        const cleanedDetails = cleanFieldText(data.special_instructions || '');
        if (customRulesInput) {
            customRulesInput.value = cleanedDetails;
            if (cleanedDetails) {
                flashField(customRulesInput);
                filledCount++;
            }
        }

        showDynamicsStatus(`✅ Successfully imported ${filledCount} fields from Dynamics CRM! Form is ready for scan.`, 'success');
    }

    // Dynamics CRM Import Handler
    const importDynamicsBtn = document.getElementById('import-dynamics-btn');
    const dynamicsUrlInput = document.getElementById('dynamics-url-input');
    const dynamicsStatusMsg = document.getElementById('dynamics-status-msg');

    if (importDynamicsBtn && dynamicsUrlInput) {
        importDynamicsBtn.addEventListener('click', async () => {
            const dynUrl = (dynamicsUrlInput.value || '').trim();

            importDynamicsBtn.disabled = true;
            const dynBtnText = importDynamicsBtn.querySelector('.btn-text');
            const dynLoader = importDynamicsBtn.querySelector('.loader');
            if (dynBtnText) dynBtnText.textContent = 'Loading...';
            if (dynLoader) dynLoader.style.display = 'inline-block';

            try {
                let data = null;

                if (!dynUrl) {
                    showDynamicsStatus('Fetching latest 1-Click Bookmarklet import...', 'info');
                    const res = await fetch('/api/get-latest-dynamics');
                    const resData = await res.json();
                    if (resData.success && resData.data) {
                        data = resData.data;
                    } else {
                        throw new Error('Please paste a Dynamics CRM URL or use the 1-Click Bookmarklet.');
                    }
                } else {
                    if (!dynUrl.includes('crm.dynamics.com') && !dynUrl.includes('main.aspx')) {
                        throw new Error('URL must be a Microsoft Dynamics CRM link.');
                    }
                    showDynamicsStatus('Connecting to Dynamics CRM session...', 'info');
                    const response = await fetch('/api/extract-dynamics', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: dynUrl })
                    });

                    if (!response.ok) {
                        const errData = await response.json().catch(() => ({}));
                        throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                    }

                    data = await response.json();

                    if (data.is_relay && data.job_id) {
                        data = await pollDynamicsRelayJob(data.job_id);
                    }
                }

                if (data && (data.deliverable_id || data.title || data.completed_copy || data.completed_page_url)) {
                    populateFormWithDynamicsData(data);
                } else {
                    showDynamicsStatus('⚠️ Extraction completed, but no deliverable fields were found.', 'error');
                }
            } catch (err) {
                console.error('Dynamics import error:', err);
                showDynamicsStatus(`❌ ${err.message}`, 'error');
            } finally {
                importDynamicsBtn.disabled = false;
                if (dynBtnText) dynBtnText.textContent = '⚡ Auto-Fill Form';
                if (dynLoader) dynLoader.style.display = 'none';
            }
        });
    }

    async function checkLatestDynamicsImportOnLoad() {
        try {
            const res = await fetch('/api/get-latest-dynamics');
            const resData = await res.json();
            if (resData.success && resData.data) {
                const data = resData.data;
                const ageMs = Date.now() - (data.updatedAt || 0);
                if (ageMs < 30 * 60 * 1000) {
                    populateFormWithDynamicsData(data);
                }
            }
        } catch (e) {}
    }
    checkLatestDynamicsImportOnLoad();

    function showDynamicsStatus(msg, type) {
        if (!dynamicsStatusMsg) return;
        dynamicsStatusMsg.textContent = msg;
        dynamicsStatusMsg.className = `dynamics-status ${type}`;
        dynamicsStatusMsg.style.display = 'block';
    }

    function flashField(element) {
        if (!element) return;
        element.classList.remove('field-autofilled');
        void element.offsetWidth;
        element.classList.add('field-autofilled');
    }

    const form = document.getElementById('url-form');

    const input = document.getElementById('url-input');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');

    const errorMsg = document.getElementById('error-message');
    const resultsArea = document.getElementById('results-area');
    const resultUrl = document.getElementById('result-url');
    const h1Count = document.getElementById('h1-count');
    const snippetsContainer = document.getElementById('snippets-container');

    // Global State
    let lastScanData = null;
    let currentBugs = [];

    // UI Toggles
    const toggleSeoInputs = document.getElementById('toggle-seo-inputs');
    if (toggleSeoInputs) {
        toggleSeoInputs.addEventListener('click', () => {
            const body = document.querySelector('.seo-panel-body');
            const icon = toggleSeoInputs.querySelector('.toggle-icon');
            if (body.style.display === 'none') {
                body.style.display = 'flex';
                icon.textContent = '▲';
            } else {
                body.style.display = 'none';
                icon.textContent = '▼';
            }
        });
    }

    const toggleValidLinks = document.getElementById('toggle-valid-links');
    if (toggleValidLinks) {
        toggleValidLinks.addEventListener('click', () => {
            const container = document.getElementById('valid-links-container');
            const span = toggleValidLinks.querySelector('span');
            if (container.style.display === 'none') {
                container.style.display = 'block';
                span.textContent = '▲';
            } else {
                container.style.display = 'none';
                span.textContent = '▼';
            }
        });
    }

    const togglePageAudit = document.getElementById('toggle-page-audit');
    if (togglePageAudit) {
        togglePageAudit.addEventListener('click', () => {
            const content = document.getElementById('page-audit-content');
            const icon = togglePageAudit.querySelector('.toggle-icon');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                icon.textContent = '▲';
            } else {
                content.style.display = 'none';
                icon.textContent = '▼';
            }
        });
    }

    const clearBtn = document.getElementById('clear-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            input.value = '';
            document.getElementById('case-number-input').value = '';
            document.getElementById('expected-title-input').value = '';
            document.getElementById('expected-content-input').value = '';
            document.getElementById('special-instructions-input').value = '';
            document.getElementById('custom-rules-input').value = '';
            resultsArea.style.display = 'none';
            hideError();
            // Full state reset to avoid data leaking into next scan
            lastScanData = null;
            currentBugs = [];
            // Reset all dynamic cards visibility
            const cardsToHide = [
                'seo-coverage-card', 'inventory-card', 'media-audit-card',
                'rules-validation-card', 'custom-layout-rules-card', 'sitemap-card',
                'lead-form-card', 'coherence-card', 'links-card', 'bug-report-card',
                'page-audit-card'
            ];
            cardsToHide.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });
            input.focus();
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const url = input.value.trim();
        if (!url) return;

        const caseNumber = document.getElementById('case-number-input')?.value.trim() || '';
        const expectedTitle = document.getElementById('expected-title-input')?.value.trim() || '';
        const expectedContent = document.getElementById('expected-content-input')?.value.trim() || '';
        const specialInstructions = document.getElementById('special-instructions-input')?.value.trim() || '';
        const customRules = document.getElementById('custom-rules-input')?.value.trim() || '';

        // Reset UI Context
        setLoading(true);
        hideError();
        resultsArea.style.display = 'none';

        try {
            const response = await fetch('/api/extract-h1', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: url,
                    case_number: caseNumber,
                    expected_title: expectedTitle,
                    expected_content: expectedContent,
                    special_instructions: specialInstructions,
                    custom_rules: customRules
                })
            });
            let data = await response.json();

            // Handle Vercel Cloud Relay mode
            if (data && data.is_relay && data.job_id) {
                data = await pollRelayJob(data.job_id);
            }

            if (!response.ok || !data || !data.success) {
                throw new Error((data && data.error) || 'An error occurred while processing the URL.');
            }

            renderResults(data);
            saveScanToHistory(data);


        } catch (error) {
            showError(error.message);
        } finally {
            setLoading(false);
        }
    });

    function setLoading(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            btnText.style.display = 'none';
            loader.style.display = 'inline-block';
        } else {
            submitBtn.disabled = false;
            btnText.style.display = 'inline';
            loader.style.display = 'none';
        }
    }

    function showError(message) {
        errorMsg.textContent = message;
        errorMsg.style.display = 'block';
    }

    function hideError() {
        errorMsg.style.display = 'none';
    }

    function renderResults(data) {
        lastScanData = data;
        window.lastScanData = data;
        resultUrl.textContent = data.url;
        h1Count.textContent = data.count;

        const statsCard = h1Count.parentElement.parentElement;
        const existingError = statsCard.querySelector('.h1-rule-error');
        if (existingError) existingError.remove();

        h1Count.style.color = data.h1_valid ? '#bb86fc' : '#ff4d4d';

        if (!data.h1_valid && data.h1_error_msg) {
            const errorDiv = document.createElement('div');
            errorDiv.classList.add('error-msg', 'h1-rule-error');
            errorDiv.style.marginTop = '1rem';
            errorDiv.textContent = data.h1_error_msg;
            statsCard.appendChild(errorDiv);
        }

        snippetsContainer.innerHTML = '';

        if (data.count === 0) {
            const noRes = document.createElement('div');
            noRes.classList.add('snippet-card');
            noRes.innerHTML = `<div class="snippet-body" style="text-align: center; color: var(--text-muted);">No H1 tags found on this page.</div>`;
            snippetsContainer.appendChild(noRes);
        } else {
            data.h1_snippets.forEach((snippet, index) => {
                const card = document.createElement('div');
                card.classList.add('snippet-card');

                // Escape HTML para mostrarlo como codigo
                const escapedSnippet = escapeHTML(snippet);

                card.innerHTML = `
                    <div class="snippet-header">
                        <span>H1 Tag #${index + 1}</span>
                        <button class="copy-btn" onclick="copyToClipboard(this)">Copy</button>
                    </div>
                    <div class="snippet-body">
                        <code>${escapedSnippet}</code>
                    </div>
                `;
                snippetsContainer.appendChild(card);
            });
        }

        // SEO Coverage Logic
        const seoCard = document.getElementById('seo-coverage-card');
        if (data.title_match || data.seo_coverage !== undefined) {
            seoCard.style.display = 'block';

            // Title logic
            const tm = document.getElementById('title-match-status');
            if (data.title_match) {
                if (data.title_match.status === 'success') {
                    tm.textContent = 'Matches Found H1';
                    tm.style.color = '#4caf50';
                } else if (data.title_match.status === 'not_found') {
                    tm.textContent = 'Not Found in H1 elements';
                    tm.style.color = '#ff4d4d';
                } else if (data.title_match.status === 'no_input') {
                    tm.textContent = 'Not provided by user';
                    tm.style.color = 'var(--text-muted)';
                }
            }

            // Helper: render one coverage bar + missing chunks
            function renderCoverage(cov, missingChunks, barFillId, txtId, explId, missingContainerId, missingListId) {
                const fill = document.getElementById(barFillId);
                const txt = document.getElementById(txtId);
                const expl = document.getElementById(explId);
                const missingContainer = document.getElementById(missingContainerId);
                const missingList = document.getElementById(missingListId);
                
                if (!fill || !txt || !expl) return;

                if (cov === null || cov === undefined || cov === -1) {
                    txt.textContent = cov === -1 ? 'N/A' : '-';
                    fill.style.width = '0%';
                    fill.style.background = '#454e59';
                    txt.style.color = 'var(--text-muted)';
                    expl.textContent = 'No SEO text supplied.';
                    if (missingContainer) missingContainer.style.display = 'none';
                    if (missingList) missingList.innerHTML = '';
                    return;
                }

                txt.textContent = `${cov}%`;
                setTimeout(() => { fill.style.width = `${cov}%`; }, 300);

                if (cov > 80) {
                    fill.style.background = '#4caf50';
                    txt.style.color = '#4caf50';
                    expl.textContent = 'Great! Most of the content supplied exists on the page.';
                } else if (cov > 40) {
                    fill.style.background = '#ffeb3b';
                    txt.style.color = '#ffeb3b';
                    expl.textContent = 'Partial match. Some paragraphs or sentences might be missing.';
                } else {
                    fill.style.background = '#ff4d4d';
                    txt.style.color = '#ff4d4d';
                    expl.textContent = 'Low coverage. The text does not appear to be included substantially on the page.';
                }

                // Use the variables already declared at the top of the function
                if (missingContainer && missingList) {
                    if (missingChunks && missingChunks.length > 0 && cov < 100) {
                        missingContainer.style.display = 'block';
                        missingList.innerHTML = '';
                        missingChunks.forEach(chunk => {
                            const li = document.createElement('li');

                            let chunkHtml = '';
                            if (Array.isArray(chunk)) {
                                chunk.forEach(token => {
                                    if (token.status === 'found') {
                                        chunkHtml += `<span style="color: #4caf50;">${escapeHTML(token.text)}</span> `;
                                    } else {
                                        chunkHtml += `<span style="color: #ff7b72; font-weight: 600; background: rgba(255, 123, 114, 0.1); padding: 0 2px; border-radius: 3px;">${escapeHTML(token.text)}</span> `;
                                    }
                                });
                            } else {
                                chunkHtml = escapeHTML(chunk);
                            }

                            li.innerHTML = `<span class="missing-bullet">⚠</span> ${chunkHtml}`;
                            missingList.appendChild(li);
                        });
                    } else {
                        missingContainer.style.display = 'none';
                    }
                }
            }

            // Desktop
            renderCoverage(
                data.seo_coverage,
                data.seo_missing_chunks,
                'coverage-bar-fill', 'coverage-percentage-text', 'coverage-explanation',
                'missing-chunks-container', 'missing-chunks-list'
            );
            // Mobile
            renderCoverage(
                data.seo_coverage_mobile,
                data.seo_missing_chunks_mobile,
                'coverage-bar-fill-mobile', 'coverage-percentage-text-mobile', 'coverage-explanation-mobile',
                'missing-chunks-container-mobile', 'missing-chunks-list-mobile'
            );
        } else {
            if (seoCard) seoCard.style.display = 'none';
        }

        // Inventory Validation Logic
        const invCard = document.getElementById('inventory-card');
        const invStatus = document.getElementById('inventory-status-badge');
        const invPageCount = document.getElementById('inventory-page-count');
        const invFilterCount = document.getElementById('inventory-filter-count');
        const invFilterLink = document.getElementById('inventory-filter-link');
        const invLayout = document.getElementById('inventory-layout');
        const invBreadcrumbs = document.getElementById('inventory-breadcrumbs');

        if (data.inventory_info) {
            invCard.style.display = 'block';
            const info = data.inventory_info;

            // 1. Render Source Badge (Transparency on Token usage)
            let sourceHTML = '';
            if (info.source === 'database_hit') {
                sourceHTML = '<span class="source-badge db-hit" title="Matched from Patterns Database">🗄️ Pattern DB Match</span>';
            } else if (info.source === 'local_match') {
                sourceHTML = '<span class="source-badge local-hit" title="Matched by Local Python Engine (0 tokens)">⚡ Local Inference</span>';
            } else if (info.source === 'ai_inference') {
                sourceHTML = '<span class="source-badge ai-pred" title="Predicted by AI learning">🤖 AI Prediction</span>';
            } else if (info.source === 'manual_correction') {
                sourceHTML = '<span class="source-badge" style="background: #e65100; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;" title="Learned from manual correction">✍️ Manual Correction</span>';
            }

            const titleEl = invCard.querySelector('h2');
            if (titleEl) {
                // Keep the icon, add source badge next to it
                titleEl.innerHTML = `<span style="font-size: 1.2rem;">🚗</span> Inventory Validation ${sourceHTML}`;
            }

            // Dynamic Layout & Breadcrumbs display
            const lbRow = document.getElementById('layout-breadcrumbs-row');
            const reqLayout = info.requires_layout_ui;
            const reqBreadcrumbs = info.requires_breadcrumb_ui;

            if (reqLayout || reqBreadcrumbs) {
                if (lbRow) lbRow.style.display = 'flex';
                
                if (reqLayout && invLayout) {
                    invLayout.textContent = info.layout || 'Unknown';
                    invLayout.style.display = 'inline-block';
                } else if (invLayout) {
                    invLayout.style.display = 'none';
                }
                
                if (reqBreadcrumbs && invBreadcrumbs) {
                    const hasBc = data.breadcrumbs_info && data.breadcrumbs_info.present;
                    invBreadcrumbs.textContent = hasBc ? 'Breadcrumbs: Found ✅' : 'Breadcrumbs: Missing ❌';
                    invBreadcrumbs.style.display = 'inline-block';
                } else if (invBreadcrumbs) {
                    invBreadcrumbs.style.display = 'none';
                }
            } else {
                if (lbRow) lbRow.style.display = 'none';
            }

            if (info.page_count !== undefined) {
                invPageCount.textContent = info.page_count;
                invFilterCount.textContent = info.filter_count || '-';

                // Config links logic
                const generateConfigLinks = (siteId, configIds) => {
                    if (!siteId || !configIds || configIds.length === 0) return '';
                    let links = configIds.map(id => {
                        let cleanId = id.startsWith('auto-') ? id.substring(5) : id;
                        let url = `https://apps.dealercenter.coxautoinc.com/landing/dealer/${siteId}/dashboard/websiteInventoryConfigs/${cleanId}`;
                        return `<a href="${url}" target="_blank" title="Open Inventory Config" style="color: #64b5f6; margin-left: 5px; text-decoration: none;">${id}</a>`;
                    });
                    return `<span style="color: var(--text-muted);">Configs:</span> ` + links.join(', ');
                };

                const currentConfigsEl = document.getElementById('inv-current-configs');
                if (currentConfigsEl) {
                    if (info.config_ids && info.config_ids.length > 0 && info.site_id) {
                        currentConfigsEl.innerHTML = generateConfigLinks(info.site_id, info.config_ids);
                        currentConfigsEl.style.display = 'block';
                    } else {
                        currentConfigsEl.style.display = 'none';
                    }
                }

                const targetConfigsEl = document.getElementById('inv-target-configs');
                if (targetConfigsEl) {
                    if (info.target_config_ids && info.target_config_ids.length > 0 && info.target_site_id) {
                        targetConfigsEl.innerHTML = generateConfigLinks(info.target_site_id, info.target_config_ids);
                        targetConfigsEl.style.display = 'block';
                    } else {
                        targetConfigsEl.style.display = 'none';
                    }
                }

                const invActions = document.getElementById('inventory-actions');
                invActions.innerHTML = '';

                if (info.filter_url) {
                    if (info.filter_url.startsWith('SUM:')) {
                        invFilterLink.textContent = 'Multi-link Sum';
                        const urls = info.filter_url.replace('SUM:', '').split('|');
                        urls.forEach((u, idx) => {
                            const path = u.trim();
                            const btn = document.createElement('a');
                            btn.className = 'inventory-btn';
                            btn.target = '_blank';
                            btn.href = data.url ? (new URL(path, data.url)).href : '#';
                            btn.innerHTML = `<span>Page ${idx + 1}</span> ↗`;
                            invActions.appendChild(btn);
                        });
                    } else {
                        invFilterLink.textContent = info.filter_url;
                        invFilterLink.href = data.url ? (new URL(info.filter_url, data.url)).href : '#';

                        const btn = document.createElement('a');
                        btn.className = 'inventory-btn';
                        btn.target = '_blank';
                        btn.href = invFilterLink.href;
                        btn.innerHTML = `<span>View Target</span> ↗`;
                        invActions.appendChild(btn);
                    }
                } else {
                    invFilterLink.textContent = '-';
                    invFilterLink.removeAttribute('href');
                }
            }

            // 2. Render Status Badge
            if (info.status === 'match') {
                invStatus.textContent = 'Matched ✅';
                invStatus.style.color = '#4caf50';
                invCard.style.borderLeftColor = '#4caf50';
            } else if (info.status === 'mismatch') {
                invStatus.textContent = 'Mismatch ❌';
                invStatus.style.color = '#ff4d4d';
                invCard.style.borderLeftColor = '#ff4d4d';
            } else if (info.status === 'no_local_widget') {
                invStatus.textContent = 'No Local Widget ℹ️';
                invStatus.style.color = '#94a3b8';
                invCard.style.borderLeftColor = '#94a3b8';
            } else if (info.status === 'informational') {
                invStatus.textContent = 'Informational Page 📄';
                invStatus.style.color = '#4caf50';
                invCard.style.borderLeftColor = '#4caf50';
            } else if (info.status === 'not_found' || info.status === 'none') {
                invStatus.textContent = 'Filter Not Found ⚠️';
                invStatus.style.color = '#94a3b8';
                invCard.style.borderLeftColor = '#454e59';
            } else if (info.status === 'error') {
                invStatus.textContent = 'System Error ❗';
                invStatus.style.color = '#ff4d4d';
                invCard.style.borderLeftColor = '#ff4d4d';
            } else {
                invStatus.textContent = 'Manual Review Needed ⚠️';
                invStatus.style.color = '#ffeb3b';
                invCard.style.borderLeftColor = '#ffeb3b';
            }
        } else {
            if (invCard) invCard.style.display = 'none';
        }

        // Media Library Audit Logic (Dual Space)


        const mediaCard = document.getElementById('media-audit-card');
        const mediaBadge = document.getElementById('media-audit-badge');

        if (data.media_audit_desktop && data.media_audit_mobile && mediaCard) {
            mediaCard.style.display = 'block';

            const renderAuditSpace = (ma, containerId, dealerIdId, galleryId) => {
                const container = document.getElementById(containerId);
                const dealerElem = document.getElementById(dealerIdId);
                if (!container || !ma) return;

                if (ma.dealer_id) {
                    dealerElem.textContent = `Dealer Account ID: ${ma.dealer_id}`;
                } else {
                    dealerElem.textContent = 'Dealer Account ID: Not detected';
                }

                let analyzedCount = ma.analyzed_images ? ma.analyzed_images.length : 0;
                let summaryText = analyzedCount > 0 ? `<p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1rem;">Analyzed ${analyzedCount} content image${analyzedCount !== 1 ? 's' : ''}.</p>` : '';

                let galleryHtml = '';
                if (analyzedCount > 0) {
                    galleryHtml = `<div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);">
                        <h4 style="margin: 0 0 0.8rem 0; font-size: 0.9rem; color: #ccc; cursor: pointer; display: flex; align-items: center; gap: 0.5rem;" onclick="const g = document.getElementById('${galleryId}'); g.style.display = g.style.display === 'none' ? 'flex' : 'none'; this.querySelector('span').textContent = g.style.display === 'none' ? '▶' : '▼';">
                            <span>▶</span> View All Analyzed Images
                        </h4>
                        <div id="${galleryId}" style="display: none; flex-wrap: wrap; gap: 0.8rem;">`;

                    ma.analyzed_images.forEach(img => {
                        const fullSrc = img.src.startsWith('//') ? 'https:' + img.src : img.src;
                        const isOffending = ma.offending_images && ma.offending_images.some(o => o.src === img.src);
                        const borderCol = isOffending ? '#ff4d4d' : '#4caf50';
                        galleryHtml += `
                            <div style="position: relative; width: 64px; height: 64px; border-radius: 4px; overflow: hidden; border: 2px solid ${borderCol}; background: #1a1a2e;" title="Widget: ${escapeHTML(img.widget || 'Unknown')}">
                                <a href="${fullSrc}" target="_blank">
                                    <img src="${fullSrc}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'">
                                </a>
                                ${isOffending ? '<div style="position: absolute; top: -2px; right: -2px; background: #ff4d4d; color: white; font-size: 10px; padding: 1px 4px; border-bottom-left-radius: 4px; font-weight: bold;">❌</div>' : ''}
                            </div>
                        `;
                    });
                    galleryHtml += `</div></div>`;
                }

                if (ma.status === 'pass') {
                    container.innerHTML = summaryText + '<p style="color: #4caf50; margin: 0.5rem 0;">✅ All content images are hosted in the dealer\'s Media Library.</p>' + galleryHtml;
                } else if (ma.status === 'fail') {
                    const offCount = ma.offending_images.length;
                    let html = summaryText + `<p style="color: #ff4d4d; margin-bottom: 1rem;">⚠️ ${offCount} image${offCount > 1 ? 's' : ''} found that ${offCount > 1 ? 'are' : 'is'} not hosted in the Dealer's Media Library.</p>`;
                    html += `<div style="display: flex; flex-direction: column; gap: 0.8rem;">`;
                    ma.offending_images.forEach(off => {
                        html += `
                            <div style="background: rgba(255,255,255,0.03); padding: 0.8rem; border-radius: 6px; border-left: 3px solid #ff4d4d;">
                                <div style="font-size: 0.85rem; margin-bottom: 0.4rem; color: #ff7b72;">${escapeHTML(off.widget)}</div>
                                <div style="display: flex; gap: 10px; align-items: center;">
                                    <img src="${off.src}" style="width: 50px; height: 50px; border-radius: 4px; object-fit: cover; background: #000;">
                                    <a href="${off.src}" target="_blank" style="font-size: 0.75rem; color: #8b949e; word-break: break-all;">${off.src}</a>
                                </div>
                            </div>
                        `;
                    });
                    html += `</div>` + galleryHtml;
                    container.innerHTML = html;
                } else if (ma.status === 'no_id') {
                    container.innerHTML = '<p style="color: var(--text-muted);">Could not detect Dealer Account ID on this page. Image audit skipped.</p>';
                } else {
                    container.innerHTML = '<p style="color: var(--text-muted);">Media audit skipped or not applicable for this page.</p>';
                }
            };

            renderAuditSpace(data.media_audit_desktop, 'media-audit-container-desktop', 'media-audit-dealer-id-desktop', 'media-gallery-desktop');
            renderAuditSpace(data.media_audit_mobile, 'media-audit-container-mobile', 'media-audit-dealer-id-mobile', 'media-gallery-mobile');

            // Combined Badge
            const dStatus = data.media_audit_desktop.status;
            const mStatus = data.media_audit_mobile.status;
            if (dStatus === 'fail' || mStatus === 'fail') {
                mediaBadge.textContent = 'Library Mismatch ❌';
                mediaBadge.style.color = '#ff4d4d';
                mediaCard.style.borderLeftColor = '#ff4d4d';
            } else if (dStatus === 'pass' && mStatus === 'pass') {
                mediaBadge.textContent = 'All Images OK ✅';
                mediaBadge.style.color = '#4caf50';
                mediaCard.style.borderLeftColor = '#4caf50';
            } else {
                mediaBadge.textContent = 'Audited 📋';
                mediaBadge.style.color = 'var(--text-muted)';
            }
        } else {
            if (mediaCard) mediaCard.style.display = 'none';
        }


        const rulesCard = document.getElementById('rules-validation-card');
        const rulesStatus = document.getElementById('rules-status-badge');
        const rulesContainer = document.getElementById('rules-container');

        if (data.cta_evaluations && data.cta_evaluations.length > 0) {
            rulesCard.style.display = 'block';

            const evals = data.cta_evaluations;
            const hasErrors = evals.some(e => e.status === 'error');

            if (!hasErrors) {
                rulesStatus.textContent = 'All Found ✅';
                rulesStatus.style.color = '#4caf50';
                rulesCard.style.borderLeftColor = '#4caf50';
            } else {
                rulesStatus.textContent = 'Missing CTAs ❌';
                rulesStatus.style.color = '#ff4d4d';
                rulesCard.style.borderLeftColor = '#ff4d4d';
            }

            let html = '<ul style="list-style:none; padding:0; margin:0;">';
            evals.forEach(c => {
                const isSuccess = c.status === 'success';
                const hasCoherenceWarn = isSuccess && c.coherence_warning;

                let icon, color, msg, subMsg;
                if (isSuccess && !hasCoherenceWarn) {
                    icon = '✅'; color = '#4caf50';
                    msg = `Found CTA for "${escapeHTML(c.original)}"`;
                    const foundText = c.found_text ? ` → Linked text: "${escapeHTML(c.found_text)}"` : '';
                    subMsg = `Resolved URL: ${escapeHTML(c.found_href || 'N/A')}${foundText}`;
                } else if (isSuccess && hasCoherenceWarn) {
                    icon = '⚠️'; color = '#ffb74d';
                    msg = `Path found for "${escapeHTML(c.original)}" but link text may be incoherent`;
                    subMsg = `${escapeHTML(c.coherence_warning)} — Resolved URL: ${escapeHTML(c.found_href || 'N/A')}, Actual text: "${escapeHTML(c.found_text || '')}"`;
                } else {
                    icon = '❌'; color = '#ff7b72';
                    msg = `Could not find CTA matching "${escapeHTML(c.original)}"`;
                    subMsg = `Please check if it exists on the page.`;
                }


                html += `
                    <li style="margin-bottom:0.8rem; display:flex; align-items:flex-start; gap:0.6rem;">
                        <span style="font-size:1rem;">${icon}</span>
                        <div>
                            <div style="font-size:0.85rem; font-weight:600; color:${color};">${msg}</div>
                            <div style="font-size:0.8rem; color:var(--text-muted);">${subMsg}</div>
                        </div>
                    </li>
                `;
            });
            html += '</ul>';
            rulesContainer.innerHTML = html;
        } else {
            if (rulesCard) rulesCard.style.display = 'none';
        }

        const layoutRulesCard = document.getElementById('custom-layout-rules-card');
        const layoutRulesStatus = document.getElementById('custom-layout-status-badge');
        const layoutRulesContainer = document.getElementById('custom-layout-rules-container');

        if (data.custom_layout_evaluations && data.custom_layout_evaluations.length > 0) {
            layoutRulesCard.style.display = 'block';

            const evals = data.custom_layout_evaluations;
            const hasErrors = evals.some(e => e.status === 'error');
            const hasManual = evals.some(e => e.status === 'manual_review');

            if (hasErrors) {
                layoutRulesStatus.textContent = 'Missing Layout / Rules ❌';
                layoutRulesStatus.style.color = '#ff4d4d';
                layoutRulesCard.style.borderLeftColor = '#ff4d4d';
            } else if (hasManual) {
                layoutRulesStatus.textContent = 'Manual Review Needed ⚠️';
                layoutRulesStatus.style.color = '#ffeb3b';
                layoutRulesCard.style.borderLeftColor = '#ffeb3b';
            } else {
                layoutRulesStatus.textContent = 'All Found ✅';
                layoutRulesStatus.style.color = '#4caf50';
                layoutRulesCard.style.borderLeftColor = '#4caf50';
            }

            let html = '<ul style="list-style:none; padding:0; margin:0;">';
            evals.forEach(c => {
                let icon, color, msg, subMsg;
                if (c.status === 'success') {
                    icon = '✅'; color = '#4caf50';
                    msg = `Rule Verified: "${escapeHTML(c.original)}"`;
                    subMsg = `Detected: ${escapeHTML(c.reason || c.found_text || 'Matched via HTML inspection')}`;
                } else if (c.status === 'manual_review') {
                    icon = '⚠️'; color = '#ffeb3b';
                    msg = `Review Needed: "${escapeHTML(c.original)}"`;
                    subMsg = escapeHTML(c.reason || c.found_text || 'Could not verify automatically. Please check manually.');
                } else {
                    icon = '❌'; color = '#ff7b72';
                    msg = `Rule Failed: "${escapeHTML(c.original)}"`;
                    subMsg = escapeHTML(c.reason || c.found_text || 'Could not find the requested component/layout.');
                }

                html += `
                    <li style="margin-bottom:0.8rem; display:flex; align-items:flex-start; gap:0.6rem;">
                        <span style="font-size:1rem;">${icon}</span>
                        <div>
                            <div style="font-size:0.85rem; font-weight:600; color:${color};">${msg}</div>
                            <div style="font-size:0.8rem; color:var(--text-muted);">${subMsg}</div>
                        </div>
                    </li>
                `;
            });
            html += '</ul>';
            layoutRulesContainer.innerHTML = html;
        } else {
            if (layoutRulesCard) layoutRulesCard.style.display = 'none';
        }

        // Sitemap UI Logic
        const sitemapCard = document.getElementById('sitemap-card');
        const sitemapStatus = document.getElementById('sitemap-status-badge');
        const xmlBadge = document.getElementById('sitemap-xml-badge');
        const htmlBadge = document.getElementById('sitemap-html-badge');
        const xmlUrlElem = document.getElementById('sitemap-xml-url');
        const htmlUrlElem = document.getElementById('sitemap-html-url');

        if (data.sitemap_info && sitemapCard) {
            sitemapCard.style.display = 'block';
            const sinfo = data.sitemap_info;

            // XML Sitemap status
            if (sinfo.xml_url) {
                xmlUrlElem.innerHTML = `<a href="${escapeHTML(sinfo.xml_url)}" target="_blank" style="color: #64b5f6; text-decoration: none;">${escapeHTML(sinfo.xml_url)} ↗</a>`;
            } else {
                xmlUrlElem.textContent = '-';
            }

            if (sinfo.xml_found === true) {
                xmlBadge.textContent = 'Found ✅';
                xmlBadge.style.backgroundColor = 'rgba(76, 175, 80, 0.2)';
                xmlBadge.style.color = '#4caf50';
            } else if (sinfo.xml_found === false) {
                xmlBadge.textContent = 'Not Found ❌';
                xmlBadge.style.backgroundColor = 'rgba(244, 67, 54, 0.2)';
                xmlBadge.style.color = '#f44336';
            } else {
                xmlBadge.textContent = 'N/A ⚠️';
                xmlBadge.style.backgroundColor = 'rgba(255, 152, 0, 0.2)';
                xmlBadge.style.color = '#ff9800';
            }

            // HTML Sitemap status
            if (sinfo.html_url) {
                htmlUrlElem.innerHTML = `<a href="${escapeHTML(sinfo.html_url)}" target="_blank" style="color: #64b5f6; text-decoration: none;">${escapeHTML(sinfo.html_url)} ↗</a>`;
            } else {
                htmlUrlElem.textContent = '-';
            }

            if (sinfo.html_found === true) {
                htmlBadge.textContent = 'Found ✅';
                htmlBadge.style.backgroundColor = 'rgba(76, 175, 80, 0.2)';
                htmlBadge.style.color = '#4caf50';
            } else if (sinfo.html_found === false) {
                htmlBadge.textContent = 'Not Found ❌';
                htmlBadge.style.backgroundColor = 'rgba(244, 67, 54, 0.2)';
                htmlBadge.style.color = '#f44336';
            } else {
                htmlBadge.textContent = 'N/A ⚠️';
                htmlBadge.style.backgroundColor = 'rgba(255, 152, 0, 0.2)';
                htmlBadge.style.color = '#ff9800';
            }

            // Overall sitemap status
            if (sinfo.xml_found === true && sinfo.html_found === true) {
                sitemapStatus.textContent = 'Fully Verified ✅';
                sitemapStatus.style.color = '#4caf50';
                sitemapCard.style.borderLeftColor = '#4caf50';
            } else if (sinfo.xml_found === false || sinfo.html_found === false) {
                sitemapStatus.textContent = 'Missing ❌';
                sitemapStatus.style.color = '#ff4d4d';
                sitemapCard.style.borderLeftColor = '#ff4d4d';
            } else {
                sitemapStatus.textContent = 'Manual Review Needed ⚠️';
                sitemapStatus.style.color = '#ffeb3b';
                sitemapCard.style.borderLeftColor = '#ffeb3b';
            }
        } else {
            if (sitemapCard) sitemapCard.style.display = 'none';
        }

        // Lead Form Source UI Logic
        const leadFormCard = document.getElementById('lead-form-card');
        const leadFormBadge = document.getElementById('lead-form-badge');
        const leadFormSourceValue = document.getElementById('lead-form-source-value');
        const leadFormExpectedRow = document.getElementById('lead-form-expected-row');
        const leadFormExpectedValue = document.getElementById('lead-form-expected-value');

        if (data.lead_form_info && data.lead_form_info.has_form && leadFormCard) {
            leadFormCard.style.display = 'block';
            const lfi = data.lead_form_info;

            // Show the current source value
            leadFormSourceValue.textContent = lfi.source_value || '(empty)';

            if (lfi.status === 'ok') {
                leadFormBadge.textContent = 'OK ✅';
                leadFormBadge.style.backgroundColor = 'rgba(76, 175, 80, 0.2)';
                leadFormBadge.style.color = '#4caf50';
                leadFormCard.style.borderLeftColor = '#4caf50';
                leadFormSourceValue.style.color = '#4caf50';
                leadFormExpectedRow.style.display = 'none';
            } else if (lfi.status === 'wrong') {
                leadFormBadge.textContent = 'Source Wrong ❌';
                leadFormBadge.style.backgroundColor = 'rgba(244, 67, 54, 0.2)';
                leadFormBadge.style.color = '#f44336';
                leadFormCard.style.borderLeftColor = '#f44336';
                leadFormSourceValue.style.color = '#ff7b72';
                if (lfi.expected) {
                    leadFormExpectedRow.style.display = 'block';
                    leadFormExpectedValue.textContent = lfi.expected;
                }
            } else if (lfi.status === 'missing') {
                leadFormBadge.textContent = 'Source Missing ⚠️';
                leadFormBadge.style.backgroundColor = 'rgba(255, 152, 0, 0.2)';
                leadFormBadge.style.color = '#ff9800';
                leadFormCard.style.borderLeftColor = '#ff9800';
                leadFormSourceValue.textContent = '(hidden source input not found)';
                leadFormSourceValue.style.color = '#ffb74d';
                leadFormExpectedRow.style.display = 'none';
            }
        } else {
            if (leadFormCard) leadFormCard.style.display = 'none';
        }

        // Coherence UI Logic
        const coherenceCard = document.getElementById('coherence-card');
        const coherenceCircle = document.getElementById('coherence-circle');
        const coherenceValue = document.getElementById('coherence-value');
        const coherenceExplanation = document.getElementById('coherence-explanation');

        coherenceCard.style.display = 'block';
        coherenceCircle.setAttribute('stroke-dasharray', `0, 100`);
        coherenceValue.textContent = '0%';

        if (data.coherence_score !== null && data.coherence_score !== undefined) {
            coherenceExplanation.textContent = data.coherence_explanation;

            const score = parseInt(data.coherence_score);
            let color = '#ff4d4d'; // Red (Incoherent)
            if (score >= 70) color = '#4caf50'; // Green (Highly coherent)
            else if (score >= 45) color = '#ffeb3b'; // Yellow (Medium)

            coherenceCircle.style.stroke = color;
            coherenceValue.style.fill = color;

            setTimeout(() => {
                coherenceCircle.setAttribute('stroke-dasharray', `${score}, 100`);
                coherenceValue.textContent = `${score}%`;
            }, 300);

        } else {
            coherenceExplanation.textContent = data.coherence_explanation || "Not available.";
            coherenceValue.textContent = '-';
            coherenceCircle.style.stroke = 'var(--text-muted)';
            coherenceValue.style.fill = 'var(--text-muted)';
        }

        // Page Audit UI Logic
        const pageAuditCard = document.getElementById('page-audit-card');
        if (data.page_audit && pageAuditCard && data.page_audit.score !== null) {
            pageAuditCard.style.display = 'block';

            const pa = data.page_audit;
            const scoreBadge = document.getElementById('page-audit-score-badge');
            let badgeColor = '#ff4d4d'; // default red
            let textColor = '#fff';
            if (pa.score >= 80) {
                badgeColor = '#4caf50'; // green
                textColor = '#fff';
            } else if (pa.score >= 60) {
                badgeColor = '#ffeb3b'; // yellow
                textColor = '#121212';
            }

            scoreBadge.textContent = `${pa.score}/100`;
            scoreBadge.style.backgroundColor = badgeColor;
            scoreBadge.style.color = textColor;

            const summary = document.getElementById('page-audit-summary');
            summary.innerHTML = `
                <span><strong>${pa.total_checks}</strong> Checks</span>
                <span style="color:#4caf50;"><strong>${pa.passes}</strong> Passed</span>
                <span style="color:#ffeb3b;"><strong>${pa.warns}</strong> Warnings</span>
                <span style="color:#ff4d4d;"><strong>${pa.fails}</strong> Failed</span>
            `;

            const catsContainer = document.getElementById('page-audit-categories');
            catsContainer.innerHTML = '';

            const cats = [
                { id: 'performance', title: '⚡ Performance' },
                { id: 'seo', title: '🔍 SEO' },
                { id: 'accessibility', title: '♿ Accessibility' },
                { id: 'best_practices', title: '🛠 Best Practices' }
            ];

            cats.forEach(c => {
                const checks = pa.categories[c.id];
                if (!checks || checks.length === 0) return;

                let html = `<div style="background: rgba(0,0,0,0.2); border-radius: 6px; padding: 0.8rem; border-left: 3px solid rgba(255,255,255,0.1);">
                    <h3 style="margin: 0 0 0.6rem 0; font-size: 1rem; color: #fff;">${c.title}</h3>
                    <div style="display: flex; flex-direction: column; gap: 0.6rem;">`;

                checks.forEach(check => {
                    let icon = '✅';
                    let color = '#4caf50';
                    if (check.status === 'warn') { icon = '⚠️'; color = '#ffeb3b'; }
                    else if (check.status === 'fail') { icon = '❌'; color = '#ff4d4d'; }

                    html += `
                        <div style="display: flex; gap: 0.6rem; align-items: flex-start; font-size: 0.85rem; padding-bottom: 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="flex-shrink: 0; font-size: 1rem;">${icon}</span>
                            <div>
                                <strong style="color: #fff;">${check.name}</strong>
                                <div style="color: ${color}; margin-top: 0.2rem; line-height: 1.4;">${check.message}</div>
                                ${check.detail ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem; word-break: break-all; opacity: 0.8;">${check.detail}</div>` : ''}
                            </div>
                        </div>
                    `;
                });

                html += `</div></div>`;
                catsContainer.innerHTML += html;
            });
        } else {
            if (pageAuditCard) pageAuditCard.style.display = 'none';
        }

        // Links UI Logic
        const linksCard = document.getElementById('links-card');
        const countTxt = document.getElementById('total-links-count');
        const brokenLinksContainer = document.getElementById('broken-links-container');
        const brokenAnchorsContainer = document.getElementById('broken-anchors-container');
        const validLinksContainer = document.getElementById('valid-links-container');
        const popupLinksContainer = document.getElementById('popup-links-container');
        const coherenceLinksContainer = document.getElementById('coherence-links-container');

        const brokenLinksList = document.getElementById('broken-links-list');
        const brokenAnchorsList = document.getElementById('broken-anchors-list');
        const validLinksList = document.getElementById('valid-links-list');
        const popupLinksList = document.getElementById('popup-links-list');
        const coherenceLinksList = document.getElementById('coherence-links-list');
        const linksSuccessMsg = document.getElementById('links-success-msg');

        if (data.total_links_analyzed !== undefined) {
            countTxt.textContent = data.total_links_analyzed || 0;

            brokenLinksList.innerHTML = '';
            brokenAnchorsList.innerHTML = '';
            validLinksList.innerHTML = '';
            popupLinksList.innerHTML = '';
            coherenceLinksList.innerHTML = '';

            brokenLinksContainer.style.display = 'none';
            brokenAnchorsContainer.style.display = 'none';
            validLinksContainer.style.display = 'none';
            popupLinksContainer.style.display = 'none';
            coherenceLinksContainer.style.display = 'none';
            linksSuccessMsg.style.display = 'none';

            let hasLinkErrors = false;

            // Render Popups Warnings
            if (data.popup_links && data.popup_links.length > 0) {
                hasLinkErrors = true;
                popupLinksContainer.style.display = 'block';
                data.popup_links.forEach(item => {
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <span class="link-text">CTA Text: ${escapeHTML(item.text)}</span>
                        <span class="link-href">Pop-up Target: ${escapeHTML(item.target)}</span>
                        <span class="link-widget">Container Widget: ${escapeHTML(item.widget || 'N/A')}</span>
                        <span class="link-status" style="color:#ffb74d; background:rgba(255,152,0,0.1);">Warning: Manual Check Required</span>
                    `;
                    popupLinksList.appendChild(li);
                });
            }

            // Render Semantic Coherence Alerts for Links
            if (data.coherence_warnings && data.coherence_warnings.length > 0) {
                hasLinkErrors = true;
                coherenceLinksContainer.style.display = 'block';
                data.coherence_warnings.forEach(item => {
                    const isRed = item.level === 'red';
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <span class="link-text">CTA Text: ${escapeHTML(item.text)}</span>
                        <span class="link-href">Destination URL: ${escapeHTML(item.href)}</span>
                        <span class="link-widget">Reason: ${escapeHTML(item.reason)}</span>
                        <span class="link-status" style="color:${isRed ? '#ff4d4d' : '#ffb74d'}; background:${isRed ? 'rgba(255,77,77,0.1)' : 'rgba(255,152,0,0.1)'};">
                            ${isRed ? 'Error: Text Mismatch' : 'Warning: Potential Typo or Ambiguity'}
                        </span>
                    `;
                    coherenceLinksList.appendChild(li);
                });
            }

            // Render 404 Broken links
            if (data.broken_links && data.broken_links.length > 0) {
                hasLinkErrors = true;
                brokenLinksContainer.style.display = 'block';
                data.broken_links.forEach(item => {
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <span class="link-text">CTA Text: ${escapeHTML(item.text)}</span>
                        <span class="link-href">URL: ${escapeHTML(item.href)}</span>
                        <span class="link-widget">Container Widget: ${escapeHTML(item.widget || 'N/A')}</span>
                        <span class="link-status">Error HTTP: ${escapeHTML(String(item.status))}</span>
                    `;
                    brokenLinksList.appendChild(li);
                });
            }

            // Render Anchors Rotos
            if (data.broken_anchors && data.broken_anchors.length > 0) {
                hasLinkErrors = true;
                brokenAnchorsContainer.style.display = 'block';
                data.broken_anchors.forEach(item => {
                    const li = document.createElement('li');
                    li.innerHTML = `
                        <span class="link-text">CTA Text: ${escapeHTML(item.text)}</span>
                        <span class="link-href">Anchor Path: ${escapeHTML(item.href)}</span>
                        <span class="link-widget">Container Widget: ${escapeHTML(item.widget || 'N/A')}</span>
                        <span class="link-status">Broken Rule: ${escapeHTML(item.error)}</span>
                    `;
                    brokenAnchorsList.appendChild(li);
                });
            }

            // Render Valid Links (Healthy Links)
            if (data.valid_links && data.valid_links.length > 0) {
                data.valid_links.forEach(item => {
                    const li = document.createElement('li');
                    const isBtn = item.type === 'button';
                    li.innerHTML = `
                        <span class="link-text">${isBtn ? '🔘 Button CTA' : '🔗 Text CTA'}: ${escapeHTML(item.text)}</span>
                        <span class="link-href">URL: ${escapeHTML(item.href)}</span>
                        <span class="link-widget">Container Widget: ${escapeHTML(item.widget || 'N/A')}</span>
                        <span class="link-status" style="color:#4caf50; background:rgba(76,175,80,0.1);">HTTP 200 OK</span>
                    `;
                    validLinksList.appendChild(li);
                });
            } else {
                validLinksList.innerHTML = `<li style="text-align:center;color:var(--text-muted)">No internal links were traced.</li>`;
            }

            if (!hasLinkErrors && data.total_links_analyzed > 0) {
                linksSuccessMsg.style.display = 'block';
            }

            linksCard.style.display = 'block';
        } else {
            if (linksCard) linksCard.style.display = 'none';
        }

        // Sections and Widgets
        if (data.sections_and_widgets) {
            renderSectionsAndWidgets(data.sections_and_widgets);
        }

        // Bug Report
        renderBugReport(data);

        resultsArea.style.display = 'flex';
    }

    function renderBugReport(data) {
        if (data && data.bugs) {
            currentBugs = data.bugs.map(b => ({
                platform: b.platform || 'M/D',
                type: b.type || 'Failed',
                category: b.category || 'Content',
                message: b.message || '',
                screenshot_link: b.screenshot_link || '',
                img: b.img || '',
                isEditing: false
            }));
        }

        const bugList = document.getElementById('bug-list');
        const noBugsMsg = document.getElementById('no-bugs-msg');
        const summaryText = document.getElementById('bug-summary-text');
        const card = document.getElementById('bug-report-card');

        bugList.innerHTML = '';
        card.style.display = 'block';

        if (currentBugs.length === 0) {
            noBugsMsg.style.display = 'block';
            summaryText.textContent = '';
            return;
        }

        noBugsMsg.style.display = 'none';
        summaryText.innerHTML = `Found <strong>${currentBugs.length}</strong> reports.`;

        const CAT_COLORS = { Content: '#22c55e', Link: '#3b82f6', Config: '#eab308', Styling: '#ec4899' };
        const TYPE_CLASS = { 'Critical': 'badge-critical', 'Failed': 'badge-failed', 'Opportunity': 'badge-opportunity', 'Observed': 'badge-observed' };

        const getBugImageUrl = (bug) => {
            if (!bug) return '';
            const isValid = (url) => {
                if (!url || typeof url !== 'string') return false;
                const low = url.trim().toLowerCase();
                if (low.startsWith('data:image/')) return false;
                if (['blank.gif', 'spacer.gif', 'pixel.gif', 'transparent.png', 'cleardot.gif', 'empty.gif'].some(p => low.includes(p))) return false;
                return low.startsWith('http://') || low.startsWith('https://') || low.startsWith('/') || low.startsWith('//');
            };

            let url = (bug.img && isValid(bug.img)) ? bug.img : ((bug.screenshot_link && isValid(bug.screenshot_link)) ? bug.screenshot_link : '');
            
            if (!url && bug.message) {
                const match = bug.message.match(/https?:\/\/[^\s\)\'\"]+(?:\.jpg|\.png|\.webp|\.gif|\.jpeg|pictures\.dealer\.com[^\s\)\'\"]*|images\.dealer\.com[^\s\)\'\"]*)/i);
                if (match && isValid(match[0])) {
                    url = match[0];
                }
            }

            if (!url) return '';
            url = url.trim().replace(/ /g, '%20');
            return url.startsWith('//') ? 'https:' + url : url;
        };

        currentBugs.forEach((bug, i) => {
            const row = document.createElement('div');
            row.className = 'bug-row';

            const cleanImgUrl = getBugImageUrl(bug);
            const isRealImg = Boolean(cleanImgUrl);

            // Sync resolved image URL back to bug object so edit modal receives it
            if (cleanImgUrl) {
                bug.screenshot_link = cleanImgUrl;
                bug.img = cleanImgUrl;
            }

            if (bug.isEditing) {
                // Edit Mode
                row.innerHTML = `
                    <div class="bug-edit-container">
                        <div class="edit-grid">
                            <div class="edit-field">
                                <label>Platform</label>
                                <input type="text" value="${escapeHTML(bug.platform || 'D/M')}" onchange="updateBugField(${i}, 'platform', this.value)">
                            </div>
                            <div class="edit-field">
                                <label>Priority</label>
                                <select onchange="updateBugField(${i}, 'type', this.value)">
                                    <option value="Critical" ${bug.type === 'Critical' ? 'selected' : ''}>Critical</option>
                                    <option value="Failed" ${bug.type === 'Failed' ? 'selected' : ''}>Failed</option>
                                    <option value="Opportunity" ${bug.type === 'Opportunity' ? 'selected' : ''}>Opportunity</option>
                                    <option value="Observed" ${bug.type === 'Observed' ? 'selected' : ''}>Observed</option>
                                </select>
                            </div>
                            <div class="edit-field">
                                <label>Category</label>
                                <input type="text" value="${escapeHTML(bug.category || 'General')}" onchange="updateBugField(${i}, 'category', this.value)">
                            </div>
                        </div>
                        <div class="edit-field">
                            <label>Message</label>
                            <textarea onchange="updateBugField(${i}, 'message', this.value)">${escapeHTML(bug.message || '')}</textarea>
                        </div>
                        <div class="edit-field">
                            <label>Screenshot Link / Image URL</label>
                            <input type="text" value="${escapeHTML(cleanImgUrl)}" onchange="updateBugField(${i}, 'screenshot_link', this.value); updateBugField(${i}, 'img', this.value)">
                        </div>
                        <div class="edit-actions">
                            <button class="done-btn" onclick="toggleEditBug(${i})">Done</button>
                            <button class="delete-btn-text" onclick="deleteBug(${i})">Delete Entry</button>
                        </div>
                    </div>
                `;
            } else {
                // View Mode (Media Visualizer Style Card)
                const typeClass = TYPE_CLASS[bug.type] || 'badge-failed';
                const catColor = CAT_COLORS[bug.category] || '#94a3b8';

                row.innerHTML = `
                    <div class="bug-view-header">
                        <div class="header-badges">
                            <span class="bug-idx">#${i + 1}</span>
                            <span class="bug-badge small">${escapeHTML(bug.platform)}</span>
                            <span class="bug-badge ${typeClass}">${escapeHTML(bug.type)}</span>
                            <span class="bug-badge small" style="color:${catColor}">${escapeHTML(bug.category)}</span>
                            ${isRealImg ? '<span class="bug-badge screenshot-tag">📸 Image Added</span>' : ''}
                        </div>
                        <div class="header-actions">
                            <button class="icon-btn copy-bug-btn" title="Copy for Smartsheet">📋</button>
                            <button class="icon-btn edit-bug-btn" onclick="toggleEditBug(${i})" title="Edit Bug">✏️</button>
                            <button class="icon-btn delete-bug-btn" onclick="deleteBug(${i})" title="Delete Bug">🗑️</button>
                        </div>
                    </div>
                    <div class="bug-view-content">
                        <p class="bug-message-text">${escapeHTML(bug.message)}</p>
                        ${isRealImg ? `
                            <div class="media-visualizer-preview" style="margin-top: 0.85rem; padding: 0.85rem; background: rgba(0, 0, 0, 0.35); border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.12); border-left: 4px solid #ff4d4d;">
                                <div style="font-size: 0.75rem; font-weight: 700; color: #ff7b72; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 0.4rem;">
                                    <span>🖼️ Image Visualizer</span>
                                </div>
                                <div style="display: flex; gap: 0.85rem; align-items: center; flex-wrap: wrap;">
                                    <a href="${escapeHTML(cleanImgUrl)}" target="_blank" title="Click to view image in full resolution">
                                        <img 
                                            src="${escapeHTML(cleanImgUrl)}" 
                                            alt="Bug Image Visualizer"
                                            style="width: 80px; height: 80px; border-radius: 6px; object-fit: cover; background: #111; border: 1.5px solid rgba(255, 255, 255, 0.2); cursor: pointer; transition: transform 0.2s;"
                                            onmouseover="this.style.transform='scale(1.05)';"
                                            onmouseout="this.style.transform='scale(1)';"
                                            onerror="this.style.opacity='0.4';"
                                        />
                                    </a>
                                    <div style="flex: 1; min-width: 180px; word-break: break-all;">
                                        <a href="${escapeHTML(cleanImgUrl)}" target="_blank" style="font-size: 0.82rem; color: #64b5f6; font-weight: 600; text-decoration: underline; line-height: 1.4; display: inline-block;">
                                            ${escapeHTML(cleanImgUrl)} ↗
                                        </a>
                                        <div style="font-size: 0.73rem; color: #94a3b8; margin-top: 4px;">
                                            Click thumbnail or URL link to view image in full resolution.
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                `;



                // Copy listener
                const copyBtn = row.querySelector('.copy-bug-btn');
                copyBtn.addEventListener('click', function () {
                    const b = currentBugs[i];
                    let text = `${b.platform} | ${b.type} | ${b.category} | ${b.message}`;
                    text = text.replace(/;/g, ',').replace(/"/g, '').replace(/'/g, '').replace(/\r?\n|\r/g, ' ');
                    navigator.clipboard.writeText(text).then(() => {
                        const original = this.innerHTML;
                        this.innerHTML = '✅';
                        setTimeout(() => { this.innerHTML = original; }, 1500);
                    });
                });
            }
            bugList.appendChild(row);
        });
    }

    // Bug Management Helpers
    window.updateBugField = (idx, field, value) => {
        if (currentBugs[idx]) currentBugs[idx][field] = value;
    };

    window.toggleEditBug = (idx) => {
        if (currentBugs[idx]) {
            currentBugs[idx].isEditing = !currentBugs[idx].isEditing;
            renderBugReport();
        }
    };

    window.deleteBug = (idx) => {
        currentBugs.splice(idx, 1);
        renderBugReport();
    };

    const addManualBugBtn = document.getElementById('add-manual-bug-btn');
    if (addManualBugBtn) {
        addManualBugBtn.addEventListener('click', () => {
            currentBugs.push({
                platform: 'M/D',
                type: 'Failed',
                category: 'Manual',
                message: 'New manual bug description...',
                screenshot_link: ''
            });
            renderBugReport();
        });
    }

    // Toggle for Sections & Widgets Card
    const toggleSectionsWidgetsBtn = document.getElementById('toggle-sections-widgets');
    const sectionsWidgetsContent = document.getElementById('sections-widgets-content');
    if (toggleSectionsWidgetsBtn && sectionsWidgetsContent) {
        toggleSectionsWidgetsBtn.addEventListener('click', () => {
            const isHidden = sectionsWidgetsContent.style.display === 'none';
            sectionsWidgetsContent.style.display = isHidden ? 'block' : 'none';
            const icon = toggleSectionsWidgetsBtn.querySelector('.toggle-icon');
            if (icon) icon.textContent = isHidden ? '▲' : '▼';
        });
    }

    function getWidgetIcon(wType) {
        switch (wType) {
            case 'image': return '🖼️';
            case 'content': return '📄';
            case 'navigation': return '🧭';
            case 'form': return '📋';
            case 'inventory': return '🚗';
            default: return '📦';
        }
    }

    function renderContainerNodeHtml(node) {
        let widgetsHtml = '';
        if (node.widgets && node.widgets.length > 0) {
            widgetsHtml = node.widgets.map(w => `
                <div class="tree-widget-item">
                    <span class="tree-widget-name">${getWidgetIcon(w.type)} ${escapeHTML(w.name)}</span>
                    <span class="tree-widget-id">${escapeHTML(w.id || w.widget_type)}</span>
                </div>
            `).join('');
        }

        let childContainersHtml = '';
        if (node.containers && node.containers.length > 0) {
            childContainersHtml = node.containers.map(c => renderContainerNodeHtml(c)).join('');
        }

        if (!widgetsHtml && !childContainersHtml) {
            widgetsHtml = `<div class="tree-widget-item" style="color: var(--text-muted); font-style: italic;">Empty container</div>`;
        }

        return `
            <div class="tree-container-node" style="margin-bottom: 0.4rem;">
                <div class="tree-container-header" onclick="event.stopPropagation(); const body = this.nextElementSibling; const isH = body.style.display === 'none'; body.style.display = isH ? 'block' : 'none'; this.querySelector('.tree-c-arrow').textContent = isH ? '▼' : '►';" style="display: flex; align-items: center; justify-content: space-between; padding: 0.35rem 0.6rem; background: rgba(255,255,255,0.03); border-radius: 4px; cursor: pointer; user-select: none;">
                    <div style="font-size: 0.8rem; font-weight: 600; color: #a5d6ff; font-family: monospace; display: flex; align-items: center; gap: 0.4rem;">
                        <span class="tree-c-arrow" style="font-size: 0.7rem;">▼</span> <span>📂 ${escapeHTML(node.name)}</span>
                    </div>
                </div>
                <div class="tree-container-body" style="display: block; padding-left: 0.8rem; border-left: 1.5px solid rgba(124, 77, 255, 0.3); margin-top: 0.3rem;">
                    ${widgetsHtml}
                    ${childContainersHtml}
                </div>
            </div>
        `;
    }

    function renderSectionsAndWidgets(swData) {
        const card = document.getElementById('sections-widgets-card');
        const badge = document.getElementById('sections-widgets-badge');
        const container = document.getElementById('sections-tree-container');

        if (!card || !container) return;

        if (!swData || !swData.sections || swData.sections.length === 0) {
            card.style.display = 'none';
            return;
        }

        card.style.display = 'block';
        if (badge) {
            badge.textContent = `${swData.total_sections || swData.sections.length} Sections | ${swData.total_widgets || 0} Widgets`;
        }

        container.innerHTML = '';

        swData.sections.forEach((sec) => {
            const secItem = document.createElement('div');
            secItem.className = 'tree-section-item';

            let containersHtml = '';
            if (sec.containers && sec.containers.length > 0) {
                containersHtml = sec.containers.map(c => renderContainerNodeHtml(c)).join('');
            } else {
                containersHtml = `<div style="color: var(--text-muted); font-style: italic; padding: 0.5rem;">No containers</div>`;
            }

            secItem.innerHTML = `
                <div class="tree-section-header" onclick="const w = this.nextElementSibling; const isH = w.style.display === 'none'; w.style.display = isH ? 'block' : 'none'; this.querySelector('.tree-arrow').textContent = isH ? '▼' : '►';">
                    <div class="tree-section-title">
                        <span class="tree-arrow">▼</span> <strong>${escapeHTML(sec.name)}</strong>
                    </div>
                    <span class="tree-section-badge">${sec.total_widgets || 0} Widget${sec.total_widgets === 1 ? '' : 's'}</span>
                </div>
                <div class="tree-subsections-wrapper" style="display: block; padding: 0.6rem 0.8rem 0.8rem 0.8rem;">
                    ${containersHtml}
                </div>
            `;

            container.appendChild(secItem);
        });
    }


    // PDF Download
    const pdfBtn = document.getElementById('download-pdf-btn');
    if (pdfBtn) {
        pdfBtn.addEventListener('click', async () => {
            if (!lastScanData) return;
            pdfBtn.disabled = true;
            pdfBtn.innerHTML = '<div class="loader" style="width:14px; height:14px;"></div> Generating…';

            const caseNum = document.getElementById('case-number-input')?.value.trim() || '';
            const payload = {
                url: lastScanData.url,
                bugs: currentBugs,
                case_number: caseNum
            };

            try {
                const resp = await fetch('/api/generate-pdf', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!resp.ok) throw new Error('PDF generation failed');

                const contentType = resp.headers.get('content-type') || '';
                let blob;
                let downloadFilename = caseNum ? `${caseNum}.pdf` : 'Bug-Report.pdf';

                if (contentType.includes('application/json')) {
                    const data = await resp.json();
                    if (data.is_relay && data.job_id) {
                        const jobResult = await pollRelayPdfJob(data.job_id);
                        if (jobResult && jobResult.pdf_base64) {
                            if (jobResult.filename) downloadFilename = jobResult.filename;
                            const byteCharacters = atob(jobResult.pdf_base64);
                            const byteNumbers = new Array(byteCharacters.length);
                            for (let i = 0; i < byteCharacters.length; i++) {
                                byteNumbers[i] = byteCharacters.charCodeAt(i);
                            }
                            const byteArray = new Uint8Array(byteNumbers);
                            blob = new Blob([byteArray], { type: 'application/pdf' });
                        } else {
                            throw new Error('No PDF payload returned from Home PC worker.');
                        }
                    } else {
                        throw new Error('Unexpected JSON response from server.');
                    }
                } else {
                    blob = await resp.blob();
                }

                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = downloadFilename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(blobUrl);
            } catch (err) {
                alert('Could not generate PDF: ' + err.message);
            } finally {
                pdfBtn.disabled = false;
                pdfBtn.textContent = '⬇ Download PDF';
            }
        });
    }


    function escapeHTML(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    window.renderResults = renderResults;
});

// Global functions for copy buttons
window.copyToClipboard = function (btnElement) {
    const codeElement = btnElement.parentElement.nextElementSibling.querySelector('code');
    let textToCopy = codeElement.innerText; // Unescaped text

    // Smartsheet Sanitation: Remove ;, " and line breaks
    textToCopy = textToCopy
        .replace(/;/g, ',')
        .replace(/"/g, "'")
        .replace(/\r?\n|\r/g, ' ');

    navigator.clipboard.writeText(textToCopy).then(() => {
        const originalText = btnElement.innerText;
        btnElement.innerText = 'Copied!';
        btnElement.style.color = '#58a6ff';

        setTimeout(() => {
            btnElement.innerText = originalText;
            btnElement.style.color = 'var(--text-muted)';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
};

window.copyBugToClipboard = function (btn, platform, type, category, message) {
    // Format: Platform | Type | Category | Message
    let textToCopy = `${platform} | ${type} | ${category} | ${message}`;

    // Smartsheet Sanitation: Remove ;, " and line breaks
    textToCopy = textToCopy
        .replace(/;/g, ',')
        .replace(/"/g, "'")
        .replace(/\r?\n|\r/g, ' ');

    navigator.clipboard.writeText(textToCopy).then(() => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<span>Copied!</span>';
        btn.classList.add('copied');

        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
};
window.switchMediaTab = function (tab) {
    const desktopView = document.getElementById('media-view-desktop');
    const mobileView = document.getElementById('media-view-mobile');
    const desktopTab = document.getElementById('tab-desktop');
    const mobileTab = document.getElementById('tab-mobile');

    if (tab === 'desktop') {
        desktopView.style.display = 'block';
        mobileView.style.display = 'none';
        desktopTab.classList.add('active');
        mobileTab.classList.remove('active');
    } else {
        desktopView.style.display = 'none';
        mobileView.style.display = 'block';
        desktopTab.classList.remove('active');
        mobileTab.classList.add('active');
    }
};

window.saveInventoryCorrection = function() {
    const btn = document.getElementById('correction-save-btn');
    const input = document.getElementById('correction-input');
    const newFilter = input.value.trim();
    const url = document.getElementById('url-input').value.trim();
    
    if (!newFilter || !url) return;
    
    const originalText = btn.innerText;
    btn.innerText = 'Saving...';
    btn.disabled = true;
    
    fetch('/api/save-correction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, filter_url: newFilter })
    })
    .then(async r => {
        let data = await r.json();
        if (data && data.is_relay && data.job_id) {
            data = await pollRelayJob(data.job_id);
        }
        return data;
    })
    .then(data => {
        if (data.status === 'ok') {
            btn.innerText = 'Saved!';
            btn.style.backgroundColor = '#2e7d32';
            setTimeout(() => {
                document.getElementById('correction-container').style.display = 'none';
                document.getElementById('correction-toggle-btn').style.display = 'inline-block';
                btn.innerText = originalText;
                btn.style.backgroundColor = '#4caf50';
                btn.disabled = false;
                
                // Update the UI link to show the new filter
                const linkEl = document.getElementById('inventory-filter-link');
                linkEl.textContent = newFilter;
                linkEl.href = new URL(newFilter, url).href;
            }, 1500);
        } else {
            alert('Error saving correction: ' + data.message);
            btn.innerText = originalText;
            btn.disabled = false;
        }
    })
    .catch(err => {
        console.error(err);
        alert('Failed to contact server');
        btn.innerText = originalText;
        btn.disabled = false;
    });
};

async function saveScanToHistory(data) {
    if (!data || !data.success) return;
    try {
        const caseNum = (document.getElementById('case-number-input')?.value || data.case_id || '').trim();
        const rawUrl = (document.getElementById('url-input')?.value || data.url || '').trim();
        let pathStr = '';
        if (rawUrl) {
            try { pathStr = new URL(rawUrl, window.location.origin).pathname; } catch(e) { pathStr = rawUrl; }
        }

        const payload = {
            id: caseNum || `D-${Date.now().toString().slice(-6)}`,
            title: data.page_title || (document.getElementById('expected-title-input')?.value || '').trim() || 'Scanned Page',
            url: rawUrl,
            path: pathStr,
            timestamp: Math.floor(Date.now() / 1000),
            has_bugs: Array.isArray(data.bugs) && data.bugs.length > 0,
            bug_count: Array.isArray(data.bugs) ? data.bugs.length : 0,
            bugs: data.bugs || [],
            full_result: data
        };

        await fetch('/api/save-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch(e) {
        console.error('Failed to auto-save scan to history:', e);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ==========================================
// HISTORY MODAL LOGIC
// ==========================================

const historyBtn = document.getElementById('history-btn');
const historyModal = document.getElementById('history-modal');
const closeHistoryBtn = document.getElementById('close-history-btn');
const historyList = document.getElementById('history-list');
const historySearch = document.getElementById('history-search');

let allHistoryData = [];

if (historyBtn && historyModal && closeHistoryBtn) {
    historyBtn.addEventListener('click', async () => {
        historyModal.style.display = 'flex';
        historyList.innerHTML = '<li style="text-align:center; color:var(--text-muted); padding: 1.5rem;">Loading history...</li>';
        
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            allHistoryData = Array.isArray(data) ? data : [];
            renderHistory(allHistoryData);
        } catch (e) {
            console.error(e);
            historyList.innerHTML = '<li style="text-align:center; color:#ff7b72; padding: 1.5rem;">Failed to load history.</li>';
        }
    });

    closeHistoryBtn.addEventListener('click', () => {
        historyModal.style.display = 'none';
        if (historySearch) historySearch.value = '';
    });

    // Close on overlay click
    historyModal.addEventListener('click', (e) => {
        if (e.target === historyModal) {
            historyModal.style.display = 'none';
            if (historySearch) historySearch.value = '';
        }
    });

    // Search filter
    if (historySearch) {
        historySearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const filtered = allHistoryData.filter(item => {
                const idMatch = item.id && item.id.toLowerCase().includes(query);
                const titleMatch = item.title && item.title.toLowerCase().includes(query);
                const pathMatch = item.path && item.path.toLowerCase().includes(query);
                const bugMatch = item.bugs && JSON.stringify(item.bugs).toLowerCase().includes(query);
                return idMatch || titleMatch || pathMatch || bugMatch;
            });
            renderHistory(filtered);
        });
    }
}

function renderHistory(items) {
    if (!historyList) return;
    if (!items || items.length === 0) {
        historyList.innerHTML = '<li style="text-align:center; color:var(--text-muted); padding: 1.5rem;">No matching history records found.</li>';
        return;
    }

    historyList.innerHTML = '';
    items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'history-item';
        li.style.cursor = 'pointer';

        let timeStr = '';
        if (item.timestamp) {
            const d = new Date(item.timestamp * 1000);
            timeStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        const bugCount = item.bug_count !== undefined ? item.bug_count : (Array.isArray(item.bugs) ? item.bugs.length : null);
        const hasBugs = item.has_bugs !== undefined ? item.has_bugs : (bugCount && bugCount > 0);

        let badgeHtml = '';
        if (bugCount === 0 || hasBugs === false) {
            badgeHtml = `<span class="history-badge pass">✅ 0 Bugs (PASS)</span>`;
        } else if (bugCount > 0 || hasBugs === true) {
            badgeHtml = `<span class="history-badge fail">❌ ${bugCount || 1} Bug${bugCount === 1 ? '' : 's'} (FAIL)</span>`;
        } else {
            badgeHtml = `<span class="history-badge info">ℹ️ Audited</span>`;
        }

        const titleTxt = item.title || item.path || 'Scanned Page';
        const pathTxt = item.path || item.url || '';
        const idTxt = item.id || 'N/A';

        li.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 0.4rem; gap: 0.5rem;">
                <span class="history-title" style="font-weight: 600; color: var(--text-main); font-size: 0.95rem; word-break: break-word;">${escapeHtml(titleTxt)}</span>
                ${badgeHtml}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size: 0.8rem; color: var(--text-muted); flex-wrap: wrap; gap: 0.4rem;">
                <div>
                    <strong style="color: #a78bfa; margin-right: 0.5rem;">📁 ${escapeHtml(idTxt)}</strong>
                    <span>${escapeHtml(pathTxt)}</span>
                </div>
                <span>${timeStr}</span>
            </div>
        `;

        li.addEventListener('click', async () => {
            if (historyModal) historyModal.style.display = 'none';
            if (historySearch) historySearch.value = '';

            const caseNumberInput = document.getElementById('case-number-input');
            const urlInput = document.getElementById('url-input');

            if (item.id && caseNumberInput) caseNumberInput.value = item.id;
            if (item.url && urlInput) urlInput.value = item.url;
            else if (item.path && urlInput && !urlInput.value) urlInput.value = item.path;

            const fnRender = window.renderResults;
            if (item.full_result && typeof item.full_result === 'object' && fnRender) {
                fnRender(item.full_result);
                const resultsArea = document.getElementById('results-area');
                if (resultsArea) {
                    resultsArea.style.display = 'block';
                    resultsArea.scrollIntoView({ behavior: 'smooth' });
                }
            } else {
                try {
                    const res = await fetch(`/api/history?id=${encodeURIComponent(item.id || item.url)}`);
                    const resData = await res.json();
                    if (resData.success && resData.data && resData.data.full_result && fnRender) {
                        fnRender(resData.data.full_result);
                        const resultsArea = document.getElementById('results-area');
                        if (resultsArea) {
                            resultsArea.style.display = 'block';
                            resultsArea.scrollIntoView({ behavior: 'smooth' });
                        }
                    } else if (urlInput && urlInput.value) {
                        const submitBtn = document.getElementById('submit-btn');
                        if (submitBtn) submitBtn.click();
                    }
                } catch(e) {
                    if (urlInput && urlInput.value) {
                        const submitBtn = document.getElementById('submit-btn');
                        if (submitBtn) submitBtn.click();
                    }
                }
            }
        });

        historyList.appendChild(li);
    });
}

// -----------------------------------------------------------------------------
// IMAGE BANK CONTROLLER
// -----------------------------------------------------------------------------
const imageBankBtn = document.getElementById('image-bank-btn');
const imageBankModal = document.getElementById('image-bank-modal');
const closeImageBankBtn = document.getElementById('close-image-bank-btn');
const imgBankGrid = document.getElementById('image-bank-grid');

const makeSelect = document.getElementById('img-bank-make-select');
const modelSelect = document.getElementById('img-bank-model-select');
const conditionSelect = document.getElementById('img-bank-condition-select');
const categorySelect = document.getElementById('img-bank-category-select');
const searchInput = document.getElementById('img-bank-search-input');

if (imageBankBtn && imageBankModal) {
    imageBankBtn.addEventListener('click', () => {
        imageBankModal.style.display = 'flex';
        loadBankStats();
        fetchImageBankAssets();
    });
}

if (closeImageBankBtn && imageBankModal) {
    closeImageBankBtn.addEventListener('click', () => {
        imageBankModal.style.display = 'none';
    });
}

[makeSelect, modelSelect, conditionSelect, categorySelect].forEach(select => {
    if (select) {
        select.addEventListener('change', () => fetchImageBankAssets());
    }
});

if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => fetchImageBankAssets(), 350);
    });
}

async function loadBankStats() {
    try {
        const res = await fetch('/api/image-bank/stats');
        const data = await res.json();
        if (data.success && data.stats) {
            const stats = data.stats;
            if (makeSelect && makeSelect.options.length <= 1) {
                stats.makes.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.make;
                    opt.textContent = `${m.make} (${m.count})`;
                    makeSelect.appendChild(opt);
                });
            }
            if (modelSelect && modelSelect.options.length <= 1) {
                stats.models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.model;
                    opt.textContent = `${m.model} (${m.count})`;
                    modelSelect.appendChild(opt);
                });
            }
        }
    } catch(err) {
        console.warn('Failed to load Image Bank stats:', err);
    }
}

async function fetchImageBankAssets() {
    if (!imgBankGrid) return;
    imgBankGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #aaa;">Loading harvested assets...</div>';

    const make = makeSelect ? makeSelect.value : '';
    const model = modelSelect ? modelSelect.value : '';
    const condition = conditionSelect ? conditionSelect.value : 'all';
    const category = categorySelect ? categorySelect.value : 'all';
    const search = searchInput ? searchInput.value.trim() : '';

    const params = new URLSearchParams();
    if (make) params.append('make', make);
    if (model) params.append('model', model);
    if (condition && condition !== 'all') params.append('condition', condition);
    if (category && category !== 'all') params.append('category', category);
    if (search) params.append('search', search);

    try {
        const res = await fetch(`/api/image-bank?${params.toString()}`);
        const data = await res.json();

        const totalEl = document.getElementById('img-bank-total-count');
        if (totalEl) totalEl.textContent = data.total || 0;

        if (!data.success || !data.assets || data.assets.length === 0) {
            imgBankGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem; color: #888;">
                    <div style="font-size: 2rem; margin-bottom: 0.5rem;">🔍</div>
                    <p style="margin:0;">No harvested images found matching the selected filters.</p>
                    <p style="font-size:0.8rem; color:#666; margin-top:0.3rem;">Audit more dealer landing pages to automatically populate the Image Bank!</p>
                </div>
            `;
            return;
        }

        imgBankGrid.innerHTML = '';
        data.assets.forEach(asset => {
            const card = document.createElement('div');
            card.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; position: relative;';

            const catBadgeColors = {
                'performance': '#ff9800',
                'exterior': '#2196f3',
                'interior': '#9c27b0',
                'safety': '#4caf50',
                'technology': '#00bcd4',
                'trims': '#e91e63',
                'general': '#78909c'
            };
            const catColor = catBadgeColors[asset.category] || '#78909c';

            card.innerHTML = `
                <div style="position: relative; width: 100%; height: 160px; background: #0c0c12; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                    <a href="${escapeHtml(asset.image_url)}" target="_blank" rel="noreferrer" title="Click para ver en resolución completa" style="display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;">
                        <img src="${escapeHtml(asset.image_url)}" alt="${escapeHtml(asset.alt_text || 'Vehicle Asset')}" referrerpolicy="no-referrer" style="max-width: 100%; max-height: 100%; object-fit: contain;" onerror="this.onerror=null; this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\' viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'%23666\\' stroke-width=\\'2\\'><rect x=\\'3\\' y=\\'3\\' width=\\'18\\' height=\\'18\\' rx=\\'2\\'/><circle cx=\\'8.5\\' cy=\\'8.5\\' r=\\'1.5\\'/><polyline points=\\'21 15 16 10 5 21\\'/></svg>';">
                    </a>
                    
                    <span style="position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.75); color: #4fc3f7; font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 10px; border: 1px solid rgba(79,195,247,0.4);">
                        🔥 ${asset.use_count} ${asset.use_count === 1 ? 'use' : 'uses'}
                    </span>

                    <span style="position: absolute; top: 6px; left: 6px; background: ${catColor}; color: #fff; font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">
                        ${escapeHtml(asset.category)}
                    </span>
                </div>

                <div style="padding: 0.7rem; display: flex; flex-direction: column; flex-grow: 1; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 600; color: #fff; margin-bottom: 0.3rem;">
                            <span>${escapeHtml(asset.make || 'Unknown')} ${escapeHtml(asset.model || '')}</span>
                            <span style="color: #aaa; font-size: 0.75rem; text-transform: capitalize;">${escapeHtml(asset.condition || 'General')}</span>
                        </div>
                        <p style="font-size: 0.75rem; color: #bbb; margin: 0 0 0.5rem 0; line-clamp: 2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${escapeHtml(asset.alt_text || asset.section_title || asset.surrounding_text || '')}">
                            ${escapeHtml(asset.alt_text || asset.section_title || asset.surrounding_text || 'No text snippet')}
                        </p>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr auto; gap: 0.4rem; margin-top: 0.4rem;">
                        <button class="copy-img-btn secondary-btn" style="font-size: 0.75rem; padding: 0.35rem;" data-url="${escapeHtml(asset.image_url)}">
                            📋 Copiar Link
                        </button>
                        <button class="delete-img-btn icon-btn" style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #ff6b6b; padding: 0.35rem 0.6rem; border-radius: 6px; font-size: 0.8rem;" title="Eliminar imagen del banco">
                            🗑️
                        </button>
                    </div>
                </div>
            `;

            const copyBtn = card.querySelector('.copy-img-btn');
            if (copyBtn) {
                copyBtn.addEventListener('click', () => {
                    navigator.clipboard.writeText(asset.image_url);
                    copyBtn.textContent = '✅ Copiado!';
                    setTimeout(() => { copyBtn.textContent = '📋 Copiar Link'; }, 1500);
                });
            }

            const delBtn = card.querySelector('.delete-img-btn');
            if (delBtn) {
                delBtn.addEventListener('click', async () => {
                    if (!confirm(`¿Deseas eliminar esta imagen de la base de datos?\n\nMake: ${asset.make || 'Desconocido'}\nModel: ${asset.model || 'Desconocido'}`)) return;
                    try {
                        delBtn.disabled = true;
                        delBtn.textContent = '⏳';
                        const res = await fetch(`/api/image-bank?id=${asset.id}`, { method: 'DELETE' });
                        const resData = await res.json();
                        if (resData.success) {
                            card.style.transition = 'all 0.3s ease';
                            card.style.opacity = '0';
                            card.style.transform = 'scale(0.85)';
                            setTimeout(() => {
                                card.remove();
                                const totalEl = document.getElementById('img-bank-total-count');
                                if (totalEl) {
                                    const currentVal = parseInt(totalEl.textContent) || 0;
                                    totalEl.textContent = Math.max(0, currentVal - 1);
                                }
                            }, 300);
                        } else {
                            alert('Error al eliminar imagen: ' + (resData.error || 'Error desconocido'));
                            delBtn.disabled = false;
                            delBtn.textContent = '🗑️';
                        }
                    } catch(e) {
                        console.error('Error deleting asset:', e);
                        alert('Error al conectar con el servidor.');
                        delBtn.disabled = false;
                        delBtn.textContent = '🗑️';
                    }
                });
            }

            imgBankGrid.appendChild(card);
        });
    } catch(err) {
        console.error('Error fetching Image Bank assets:', err);
        imgBankGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ff6b6b;">Failed to load Image Bank assets.</div>';
    }
}

// ==========================================
// REPORT TOOL BUG & REVIEW CASES CONTROLLER
// ==========================================
const reportToolBugBtn = document.getElementById('report-tool-bug-btn');
const reportBugModal = document.getElementById('report-bug-modal');
const closeReportBugBtn = document.getElementById('close-report-bug-btn');
const cancelReportBugBtn = document.getElementById('cancel-report-bug-btn');
const submitReportBugBtn = document.getElementById('submit-report-bug-btn');
const reportBugTargetUrl = document.getElementById('report-bug-target-url');
const reportBugCommentInput = document.getElementById('report-bug-comment-input');

const toolBugsBtn = document.getElementById('tool-bugs-btn');
const toolBugsBadge = document.getElementById('tool-bugs-badge');
const toolBugsModal = document.getElementById('tool-bugs-modal');
const closeToolBugsBtn = document.getElementById('close-tool-bugs-btn');
const toolBugsSearch = document.getElementById('tool-bugs-search');
const toolBugsListContainer = document.getElementById('tool-bugs-list-container');

let allReportedToolBugs = [];

function buildAiDebugPrompt(bugItem) {
    const scan = bugItem.full_scan_data || {};
    const url = bugItem.url || scan.url || 'N/A';
    const caseId = bugItem.case_id || scan.case_id || 'N/A';
    const path = bugItem.path || '';
    const title = bugItem.title || scan.page_title || '';
    const comment = bugItem.user_comment || 'No specific comment provided.';

    let prompt = `<USER_REQUEST>\n`;
    prompt += `Hola AI, hay un error / caso incorrecto reportado en el Tool de QA:\n\n`;
    prompt += `📍 DETALLES DEL CASO:\n`;
    prompt += `- URL: ${url}\n`;
    prompt += `- Case #: ${caseId}\n`;
    if (path) prompt += `- Path: ${path}\n`;
    if (title) prompt += `- Title: ${title}\n`;
    prompt += `\n💬 EXPLICACIÓN DEL PROBLEMA / LO QUE DEBERÍA DAR EL TOOL:\n`;
    prompt += `${comment}\n\n`;

    prompt += `📊 DATOS CAPTURADOS POR EL TOOL:\n`;
    prompt += `- Total H1 Tags: ${scan.count ?? 'N/A'} (Válido: ${scan.h1_valid ?? 'N/A'})\n`;
    if (scan.h1s && Array.isArray(scan.h1s)) {
        prompt += `- H1 Text(s): ${scan.h1s.map(h => `"${h.text}"`).join(', ')}\n`;
    }
    if (scan.bugs && Array.isArray(scan.bugs) && scan.bugs.length > 0) {
        prompt += `- Bugs Detectados por Tool: ${JSON.stringify(scan.bugs, null, 2)}\n`;
    } else {
        prompt += `- Bugs Detectados por Tool: Ninguno (0 bugs)\n`;
    }

    if (scan.inventory_validation) {
        const inv = scan.inventory_validation;
        prompt += `\n🛒 INVENTORY VALIDATION TOOL DATA:\n`;
        prompt += `- Status: ${inv.status || 'N/A'}\n`;
        prompt += `- Recommendation / Type: ${inv.recommendation || inv.match_type || 'N/A'}\n`;
        prompt += `- Current Page Vehicles: ${inv.current_vehicles ?? 'N/A'}\n`;
        prompt += `- Target Filter URL: ${inv.target_filter_url || 'N/A'}\n`;
        prompt += `- Target Filter Vehicles: ${inv.target_vehicles ?? 'N/A'}\n`;
        prompt += `- Matched Configs: ${JSON.stringify(inv.configs || inv.matched_configs || [])}\n`;
        prompt += `- Full Inventory Validation Payload:\n\`\`\`json\n${JSON.stringify(inv, null, 2)}\n\`\`\`\n`;
    }

    if (scan.custom_cta_results) {
        prompt += `\n🔗 CUSTOM CTA EVALUATION TOOL DATA:\n\`\`\`json\n${JSON.stringify(scan.custom_cta_results, null, 2)}\n\`\`\`\n`;
    }

    if (scan.custom_rules_validation) {
        prompt += `\n📋 CUSTOM RULES DATA:\n\`\`\`json\n${JSON.stringify(scan.custom_rules_validation, null, 2)}\n\`\`\`\n`;
    }

    prompt += `\n¿Por qué el tool está infiriendo o fallando en este caso y cómo podemos solucionarlo en la lógica del tool o patrones de app.py?\n`;
    prompt += `</USER_REQUEST>`;

    return prompt;
}

async function updateToolBugsBadge() {
    if (!toolBugsBadge) return;
    try {
        const res = await fetch('/api/tool-bugs');
        const data = await res.json();
        if (data.success && Array.isArray(data.data)) {
            const count = data.data.length;
            toolBugsBadge.textContent = count;
            toolBugsBadge.style.display = count > 0 ? 'inline-block' : 'none';
        }
    } catch (e) {
        console.warn('Failed to update tool bugs badge:', e);
    }
}

if (reportToolBugBtn && reportBugModal) {
    reportToolBugBtn.addEventListener('click', () => {
        const activeData = window.lastScanData || (typeof lastScanData !== 'undefined' ? lastScanData : null);
        const activeUrl = activeData?.url || document.getElementById('url-input')?.value || '';
        if (reportBugTargetUrl) reportBugTargetUrl.value = activeUrl;
        if (reportBugCommentInput) reportBugCommentInput.value = '';
        reportBugModal.style.display = 'flex';
    });
}

if (closeReportBugBtn && reportBugModal) {
    closeReportBugBtn.addEventListener('click', () => {
        reportBugModal.style.display = 'none';
    });
}
if (cancelReportBugBtn && reportBugModal) {
    cancelReportBugBtn.addEventListener('click', () => {
        reportBugModal.style.display = 'none';
    });
}
if (reportBugModal) {
    reportBugModal.addEventListener('click', (e) => {
        if (e.target === reportBugModal) reportBugModal.style.display = 'none';
    });
}

if (submitReportBugBtn) {
    submitReportBugBtn.addEventListener('click', async () => {
        const rawUrl = (reportBugTargetUrl ? reportBugTargetUrl.value : '').trim() || (document.getElementById('url-input')?.value || '').trim();
        const comment = (reportBugCommentInput ? reportBugCommentInput.value : '').trim();

        if (!rawUrl) {
            alert('Please perform or enter a target URL before reporting a bug.');
            return;
        }

        const activeData = window.lastScanData || (typeof lastScanData !== 'undefined' ? lastScanData : null);
        const caseId = (document.getElementById('case-number-input')?.value || activeData?.case_id || '').trim() || `CASE-${Date.now().toString().slice(-6)}`;
        let pathStr = '';
        try { pathStr = new URL(rawUrl).pathname; } catch(e) { pathStr = rawUrl; }

        const scanPayload = activeData || { url: rawUrl, case_id: caseId };
        
        const tempBugObj = {
            case_id: caseId,
            url: rawUrl,
            path: pathStr,
            title: scanPayload.page_title || (document.getElementById('expected-title-input')?.value || '').trim(),
            user_comment: comment,
            full_scan_data: scanPayload
        };

        const debugPrompt = buildAiDebugPrompt(tempBugObj);

        submitReportBugBtn.disabled = true;
        submitReportBugBtn.textContent = 'Submitting...';

        try {
            const res = await fetch('/api/report-bug', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...tempBugObj,
                    debug_prompt: debugPrompt
                })
            });

            const data = await res.json();
            if (data.success) {
                submitReportBugBtn.textContent = 'Submitted!';
                submitReportBugBtn.style.backgroundColor = '#4caf50';
                setTimeout(() => {
                    reportBugModal.style.display = 'none';
                    submitReportBugBtn.disabled = false;
                    submitReportBugBtn.textContent = 'Submit Bug Report';
                    submitReportBugBtn.style.backgroundColor = '#ff9800';
                    updateToolBugsBadge();
                }, 1200);
            } else {
                alert('Error submitting report: ' + (data.error || data.message));
                submitReportBugBtn.disabled = false;
                submitReportBugBtn.textContent = 'Submit Bug Report';
            }
        } catch(err) {
            console.error('Failed to submit tool bug report:', err);
            alert('Failed to connect to server.');
            submitReportBugBtn.disabled = false;
            submitReportBugBtn.textContent = 'Submit Bug Report';
        }
    });
}

if (toolBugsBtn && toolBugsModal) {
    toolBugsBtn.addEventListener('click', () => {
        toolBugsModal.style.display = 'flex';
        loadAndRenderToolBugs();
    });
}

if (closeToolBugsBtn && toolBugsModal) {
    closeToolBugsBtn.addEventListener('click', () => {
        toolBugsModal.style.display = 'none';
        if (toolBugsSearch) toolBugsSearch.value = '';
    });
}

if (toolBugsModal) {
    toolBugsModal.addEventListener('click', (e) => {
        if (e.target === toolBugsModal) {
            toolBugsModal.style.display = 'none';
            if (toolBugsSearch) toolBugsSearch.value = '';
        }
    });
}

if (toolBugsSearch) {
    toolBugsSearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = allReportedToolBugs.filter(item => {
            const idMatch = item.id && item.id.toLowerCase().includes(query);
            const caseMatch = item.case_id && item.case_id.toLowerCase().includes(query);
            const urlMatch = item.url && item.url.toLowerCase().includes(query);
            const commentMatch = item.user_comment && item.user_comment.toLowerCase().includes(query);
            return idMatch || caseMatch || urlMatch || commentMatch;
        });
        renderToolBugsList(filtered);
    });
}

async function loadAndRenderToolBugs() {
    if (!toolBugsListContainer) return;
    toolBugsListContainer.innerHTML = '<div style="text-align:center; color:#aaa; padding: 2rem;">Loading reported tool bugs...</div>';

    try {
        const res = await fetch('/api/tool-bugs');
        const data = await res.json();
        allReportedToolBugs = (data.success && Array.isArray(data.data)) ? data.data : [];
        renderToolBugsList(allReportedToolBugs);
        updateToolBugsBadge();
    } catch(err) {
        console.error('Failed to load tool bugs:', err);
        toolBugsListContainer.innerHTML = '<div style="text-align:center; color:#ff6b6b; padding: 2rem;">Failed to load reported bugs.</div>';
    }
}

function renderToolBugsList(items) {
    if (!toolBugsListContainer) return;

    if (!items || items.length === 0) {
        toolBugsListContainer.innerHTML = `
            <div style="text-align: center; padding: 3rem 1rem; color: #888;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🎉</div>
                <p style="margin: 0; font-size: 0.95rem;">No reported tool bugs found!</p>
                <p style="font-size: 0.8rem; color: #666; margin-top: 0.3rem;">If you notice any wrong inventory matching or CTA evaluation, click "🐛 Report Tool Error" on the audit page.</p>
            </div>
        `;
        return;
    }

    toolBugsListContainer.innerHTML = '';
    items.forEach(bug => {
        const card = document.createElement('div');
        card.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid rgba(255, 152, 0, 0.3); border-radius: 8px; padding: 1rem; position: relative; display: flex; flex-direction: column; gap: 0.6rem;';

        const d = bug.timestamp ? new Date(bug.timestamp * 1000) : new Date();
        const timeStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const scan = bug.full_scan_data || {};
        const inv = scan.inventory_validation || {};

        let invSnippet = '';
        if (inv && (inv.status || inv.recommendation)) {
            invSnippet = `
                <div style="background: rgba(0,0,0,0.3); padding: 0.5rem 0.8rem; border-radius: 6px; font-size: 0.78rem; font-family: monospace; color: #ffcc80;">
                    <div>⚠️ <strong>Validation:</strong> ${inv.status || 'N/A'} | ${inv.recommendation || inv.match_type || ''}</div>
                    <div>🚙 <strong>Vehicles:</strong> Current Page: ${inv.current_vehicles ?? 'N/A'} vs Target Filter: ${inv.target_vehicles ?? 'N/A'}</div>
                    ${inv.target_filter_url ? `<div style="word-break: break-all;">🔗 <strong>Target Filter:</strong> ${inv.target_filter_url}</div>` : ''}
                </div>
            `;
        }

        const debugPromptText = bug.debug_prompt || buildAiDebugPrompt(bug);

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
                <div>
                    <span style="font-weight: 700; color: #ffb74d; font-size: 0.95rem; margin-right: 0.6rem;">📁 Case: ${escapeHtml(bug.case_id || 'N/A')}</span>
                    <span style="font-size: 0.8rem; color: #888;">${timeStr}</span>
                </div>
                <div style="display: flex; gap: 0.4rem; align-items: center;">
                    <button class="view-bug-case-btn secondary-btn" style="padding: 2px 8px; font-size: 0.78rem; border: 1px solid #4fc3f7; color: #4fc3f7; border-radius: 4px;" title="Ver y cargar este caso abajo en el tool">
                        🔍 Ver en Tool
                    </button>
                    <button class="delete-bug-btn icon-btn" style="color: #ff6b6b; padding: 2px 6px;" title="Delete bug report">🗑️</button>
                </div>
            </div>

            <div style="font-size: 0.85rem; word-break: break-all;">
                <a href="${escapeHtml(bug.url)}" target="_blank" style="color: #4fc3f7; text-decoration: none; font-weight: 500;">
                    🔗 ${escapeHtml(bug.url)}
                </a>
            </div>

            ${bug.user_comment ? `
                <div style="background: rgba(255, 152, 0, 0.08); border-left: 3px solid #ff9800; padding: 0.5rem 0.8rem; border-radius: 0 4px 4px 0; font-size: 0.85rem; color: #eee;">
                    <strong>💬 Reported Issue:</strong> ${escapeHtml(bug.user_comment)}
                </div>
            ` : ''}

            ${invSnippet}

            <div style="display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 0.4rem;">
                <button class="view-bug-case-btn-bottom secondary-btn" style="font-size: 0.82rem; padding: 0.4rem 0.8rem; border-radius: 6px; border: 1px solid #4fc3f7; color: #4fc3f7; display: flex; align-items: center; gap: 0.3rem;">
                    🔍 Cargar Caso en el Tool
                </button>
                <button class="copy-ai-prompt-btn primary-btn" style="background: linear-gradient(135deg, #7c4dff, #651fff); color: white; font-weight: 600; font-size: 0.82rem; padding: 0.4rem 0.8rem; border-radius: 6px; display: flex; align-items: center; gap: 0.4rem;">
                    📋 Copiar Info para AI
                </button>
            </div>
        `;

        const handleViewCase = () => {
            if (toolBugsModal) toolBugsModal.style.display = 'none';
            const caseInput = document.getElementById('case-number-input');
            const urlInput = document.getElementById('url-input');
            const titleInput = document.getElementById('expected-title-input');
            if (bug.case_id && caseInput) caseInput.value = bug.case_id;
            if (bug.url && urlInput) urlInput.value = bug.url;
            if (bug.title && titleInput) titleInput.value = bug.title;

            const fnRender = window.renderResults;
            const scanData = bug.full_scan_data;
            if (scanData && scanData.url && fnRender) {
                fnRender(scanData);
                const resultsArea = document.getElementById('results-area');
                if (resultsArea) {
                    resultsArea.style.display = 'block';
                    resultsArea.scrollIntoView({ behavior: 'smooth' });
                }
            } else if (urlInput && urlInput.value) {
                const submitBtn = document.getElementById('submit-btn');
                if (submitBtn) submitBtn.click();
            }
        };

        const viewBtns = card.querySelectorAll('.view-bug-case-btn, .view-bug-case-btn-bottom');
        viewBtns.forEach(btn => btn.addEventListener('click', handleViewCase));

        const copyBtn = card.querySelector('.copy-ai-prompt-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(debugPromptText).then(() => {
                    const origText = copyBtn.innerHTML;
                    copyBtn.innerHTML = '✅ ¡Copiado para la AI!';
                    copyBtn.style.background = '#2e7d32';
                    setTimeout(() => {
                        copyBtn.innerHTML = origText;
                        copyBtn.style.background = 'linear-gradient(135deg, #7c4dff, #651fff)';
                    }, 2200);
                }).catch(err => {
                    console.error('Clipboard error:', err);
                    alert('Failed to copy to clipboard.');
                });
            });
        }

        const deleteBtn = card.querySelector('.delete-bug-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', async () => {
                if (!confirm('Are you sure you want to delete this bug report?')) return;
                try {
                    const res = await fetch(`/api/tool-bugs?id=${encodeURIComponent(bug.id)}`, { method: 'DELETE' });
                    const resData = await res.json();
                    if (resData.success) {
                        card.remove();
                        allReportedToolBugs = allReportedToolBugs.filter(b => b.id !== bug.id);
                        updateToolBugsBadge();
                        if (allReportedToolBugs.length === 0) renderToolBugsList([]);
                    }
                } catch(e) {
                    console.error('Failed to delete bug report:', e);
                }
            });
        }

        toolBugsListContainer.appendChild(card);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    updateToolBugsBadge();
});
updateToolBugsBadge();
