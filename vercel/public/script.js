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
        const TYPE_CLASS = { 'Critical': 'badge-critical', 'Failed': 'badge-failed', 'Opportunity': 'badge-opportunity' };

        currentBugs.forEach((bug, i) => {
            const row = document.createElement('div');
            row.className = `bug-row ${bug.isEditing ? 'editing' : 'viewing'}`;

            if (bug.isEditing) {
                // Edit Mode
                row.innerHTML = `
                    <div class="bug-edit-container">
                        <div class="edit-grid">
                            <div class="edit-field">
                                <label>Platform</label>
                                <input type="text" value="${escapeHTML(bug.platform)}" onchange="updateBugField(${i}, 'platform', this.value)">
                            </div>
                            <div class="edit-field">
                                <label>Priority</label>
                                <select onchange="updateBugField(${i}, 'type', this.value)">
                                    <option value="Critical" ${bug.type === 'Critical' ? 'selected' : ''}>Critical</option>
                                    <option value="Failed" ${bug.type === 'Failed' ? 'selected' : ''}>Failed</option>
                                    <option value="Opportunity" ${bug.type === 'Opportunity' ? 'selected' : ''}>Opportunity</option>
                                </select>
                            </div>
                            <div class="edit-field">
                                <label>Category</label>
                                <input type="text" value="${escapeHTML(bug.category)}" onchange="updateBugField(${i}, 'category', this.value)">
                            </div>
                        </div>
                        <div class="edit-field">
                            <label>Message</label>
                            <textarea onchange="updateBugField(${i}, 'message', this.value)">${escapeHTML(bug.message)}</textarea>
                        </div>
                        <div class="edit-field">
                            <label>Screenshot Link (prnt.sc/...)</label>
                            <input type="text" value="${escapeHTML(bug.screenshot_link)}" onchange="updateBugField(${i}, 'screenshot_link', this.value)">
                        </div>
                        <div class="edit-actions">
                            <button class="done-btn" onclick="toggleEditBug(${i})">Done</button>
                            <button class="delete-btn-text" onclick="deleteBug(${i})">Delete Entry</button>
                        </div>
                    </div>
                `;
            } else {
                // View Mode (Premium Card)
                const typeClass = TYPE_CLASS[bug.type] || 'badge-failed';
                const catColor = CAT_COLORS[bug.category] || '#94a3b8';
                const hasScreenshot = bug.screenshot_link && bug.screenshot_link.length > 5;

                row.innerHTML = `
                    <div class="bug-view-header">
                        <div class="header-badges">
                            <span class="bug-idx">#${i + 1}</span>
                            <span class="bug-badge small">${escapeHTML(bug.platform)}</span>
                            <span class="bug-badge ${typeClass}">${escapeHTML(bug.type)}</span>
                            <span class="bug-badge small" style="color:${catColor}">${escapeHTML(bug.category)}</span>
                            ${hasScreenshot ? '<span class="bug-badge screenshot-tag">📸 Image Added</span>' : ''}
                        </div>
                        <div class="header-actions">
                            <button class="icon-btn copy-bug-btn" title="Copy for Smartsheet">📋</button>
                            <button class="icon-btn edit-bug-btn" onclick="toggleEditBug(${i})" title="Edit Bug">✏️</button>
                            <button class="icon-btn delete-bug-btn" onclick="deleteBug(${i})" title="Delete Bug">🗑️</button>
                        </div>
                    </div>
                    <div class="bug-view-content">
                        <p class="bug-message-text">${escapeHTML(bug.message)}</p>
                        ${bug.img ? `
                            <div style="margin-top: 10px;">
                                <a href="${escapeHTML(bug.img)}" target="_blank" style="display: inline-block;">
                                    <img 
                                        src="${escapeHTML(bug.img)}" 
                                        style="max-height: 120px; max-width: 100%; border-radius: 4px; border: 1px solid var(--border-color); cursor: pointer; display: block;" 
                                        onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-block';"
                                    >
                                    <span style="display:none; font-size: 0.78rem; color: #64b5f6; word-break: break-all;">${escapeHTML(bug.img)}</span>
                                </a>
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

                const blob = await resp.blob();
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = caseNum ? `${caseNum}.pdf` : 'Bug-Report.pdf';
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
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
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
        historyList.innerHTML = '<li style="text-align:center; color:var(--text-muted);">Loading history...</li>';
        
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            allHistoryData = Array.isArray(data) ? data : [];
            renderHistory(allHistoryData);
        } catch (e) {
            console.error(e);
            historyList.innerHTML = '<li style="text-align:center; color:#ff7b72;">Failed to load history.</li>';
        }
    });

    closeHistoryBtn.addEventListener('click', () => {
        historyModal.style.display = 'none';
        historySearch.value = '';
    });

    // Close on overlay click
    historyModal.addEventListener('click', (e) => {
        if (e.target === historyModal) {
            historyModal.style.display = 'none';
            historySearch.value = '';
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
                return idMatch || titleMatch || pathMatch;
            });
            renderHistory(filtered);
        });
    }
}

function renderHistory(items) {
    if (!historyList) return;
    if (!items || items.length === 0) {
        historyList.innerHTML = '<li style="text-align:center; color:var(--text-muted);">No matching history records found.</li>';
        return;
    }

    historyList.innerHTML = '';
    items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'history-item';
        
        // Format timestamp
        let timeStr = '';
        if (item.timestamp) {
            const d = new Date(item.timestamp * 1000);
            timeStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        li.innerHTML = `
            <span class="history-title">${item.title || 'Unknown Title'}</span>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="history-id">${item.id || 'N/A'}</span>
                    <span style="font-size:0.75rem; color:var(--text-muted);">${timeStr}</span>
                </div>
            </div>
            <span class="history-path">${item.path || ''}</span>
        `;
        
        // Optional: click to auto-fill case ID and Title
        li.addEventListener('click', () => {
            const caseInput = document.getElementById('case-number-input');
            const titleInput = document.getElementById('expected-title-input');
            
            if(caseInput && item.id) caseInput.value = item.id;
            if(titleInput && item.title) titleInput.value = item.title;
            
            historyModal.style.display = 'none';
        });

        historyList.appendChild(li);
    });
}
