// DDC Keyword & Metadata Inspector - Global Script
(function () {
    let currentAuditData = null;
    let currentBatchData = null;
    let lastInspectedUrl = null;

    // --- Helper Functions ---
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.innerText = str;
        return div.innerHTML;
    }

    function highlightText(text, keyword, caseSensitive) {
        if (!text || !keyword) return escapeHtml(text || '');
        const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const flags = caseSensitive ? 'g' : 'gi';
        const regex = new RegExp(`(${escaped})`, flags);
        const escapedText = escapeHtml(text);
        return escapedText.replace(regex, '<mark class="highlight-kw">$1</mark>');
    }

    function setButtonLoading(btn, isLoading) {
        if (!btn) return;
        const textSpan = btn.querySelector('.btn-text');
        const spinner = btn.querySelector('.btn-spinner');
        if (isLoading) {
            btn.disabled = true;
            if (spinner) spinner.style.display = 'inline-block';
            if (textSpan) textSpan.style.opacity = '0.7';
        } else {
            btn.disabled = false;
            if (spinner) spinner.style.display = 'none';
            if (textSpan) textSpan.style.opacity = '1';
        }
    }

    function updateBadge(badgeEl, count) {
        if (!badgeEl) return;
        if (count === 0) {
            badgeEl.className = 'badge clean';
            badgeEl.textContent = '0 matches';
        } else {
            badgeEl.className = 'badge alert';
            badgeEl.textContent = `${count} ${count === 1 ? 'match' : 'matches'}`;
        }
    }

    // --- Main Single Audit Trigger (Exposed Globally) ---
    window.triggerAudit = async function (e) {
        if (e && e.preventDefault) e.preventDefault();

        const targetUrlInput = document.getElementById('target-url');
        const searchKeywordInput = document.getElementById('search-keyword');
        const caseToggle = document.getElementById('case-sensitive-toggle');
        const submitBtn = document.getElementById('submit-btn');
        const loadingIndicator = document.getElementById('loading-indicator');
        const loadingSubtext = document.getElementById('loading-subtext');
        const resultsSection = document.getElementById('results-section');

        const scopeTitle = document.getElementById('scope-title');
        const scopeMetadata = document.getElementById('scope-metadata');
        const scopeContent = document.getElementById('scope-content');
        const scopeImages = document.getElementById('scope-images');
        const scopeLinks = document.getElementById('scope-links');

        const url = targetUrlInput ? targetUrlInput.value.trim() : '';
        const keyword = searchKeywordInput ? searchKeywordInput.value.trim() : '';
        const caseSensitive = caseToggle ? caseToggle.checked : false;

        if (!url) {
            if (targetUrlInput) targetUrlInput.focus();
            alert('⚠️ Por favor ingresa la URL de la página DDC que deseas auditar.');
            return;
        }

        if (!keyword) {
            if (searchKeywordInput) searchKeywordInput.focus();
            alert('⚠️ Por favor ingresa la palabra a buscar (ej: Bubba).');
            return;
        }

        console.log('[DDC Auditor] Starting audit:', { url, keyword, caseSensitive });

        // Save history
        saveRecentKeyword(keyword);

        // UI Loading
        setButtonLoading(submitBtn, true);
        if (loadingIndicator) loadingIndicator.style.display = 'block';
        if (resultsSection) resultsSection.style.display = 'none';
        if (loadingSubtext) loadingSubtext.textContent = `Scanning "${url}" via robust DoH for "${keyword}"...`;

        try {
            const payload = {
                url: url,
                keyword: keyword,
                case_sensitive: caseSensitive,
                include_title: scopeTitle ? scopeTitle.checked : true,
                include_metadata: scopeMetadata ? scopeMetadata.checked : true,
                include_content: scopeContent ? scopeContent.checked : true,
                include_images: scopeImages ? scopeImages.checked : false,
                include_links: scopeLinks ? scopeLinks.checked : false
            };

            const response = await fetch('/api/audit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                alert(`Error en Auditoría: ${result.error || 'Fallo de conexión al servidor'}`);
                return;
            }

            console.log('[DDC Auditor] Results received:', result.data);
            currentAuditData = result.data;
            renderSingleAuditResults(result.data);

            if (resultsSection) {
                resultsSection.style.display = 'block';
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

        } catch (err) {
            console.error('[DDC Auditor] Network error:', err);
            alert(`Error de red al consultar el servidor local: ${err.message}`);
        } finally {
            setButtonLoading(submitBtn, false);
            if (loadingIndicator) loadingIndicator.style.display = 'none';
        }
    };

    // --- Render Single Audit Results ---
    function renderSingleAuditResults(data) {
        const kw = data.keyword;
        const isCase = data.case_sensitive;
        const total = data.total_matches;
        const scope = data.scope || {
            title: true,
            metadata: true,
            content: true,
            images: false,
            links: false
        };

        const verdictBanner = document.getElementById('verdict-banner');
        const verdictIcon = document.getElementById('verdict-icon');
        const verdictTitle = document.getElementById('verdict-title');
        const verdictSubtitle = document.getElementById('verdict-subtitle');
        const verdictKw = document.getElementById('verdict-kw');
        const metricTotalMatches = document.getElementById('metric-total-matches');
        const metricResponseTime = document.getElementById('metric-response-time');

        if (verdictKw) verdictKw.textContent = kw;
        if (metricTotalMatches) metricTotalMatches.textContent = total;
        if (metricResponseTime) metricResponseTime.textContent = `${data.elapsed_sec}s`;

        if (verdictBanner) {
            if (total === 0) {
                verdictBanner.className = 'verdict-banner clean';
                if (verdictIcon) verdictIcon.textContent = '✅';
                if (verdictTitle) verdictTitle.textContent = 'Page is Clean!';
                if (verdictSubtitle) verdictSubtitle.innerHTML = `No occurrences of "<span class="highlight-target-kw">${escapeHtml(kw)}</span>" found in active sections.`;
            } else {
                verdictBanner.className = 'verdict-banner detected';
                if (verdictIcon) verdictIcon.textContent = '⚠️';
                if (verdictTitle) verdictTitle.textContent = `Legacy Data Detected! (${total} ${total === 1 ? 'Match' : 'Matches'})`;
                if (verdictSubtitle) verdictSubtitle.innerHTML = `Found occurrences of "<span class="highlight-target-kw">${escapeHtml(kw)}</span>" in active sections. Review details below.`;
            }
        }

        // Card elements
        const cardTitle = document.getElementById('card-title');
        const cardMetadata = document.getElementById('card-metadata');
        const cardHeadings = document.getElementById('card-headings');
        const cardContent = document.getElementById('card-content');
        const cardImages = document.getElementById('card-images');
        const cardLinks = document.getElementById('card-links');

        if (cardTitle) cardTitle.style.display = scope.title ? 'flex' : 'none';
        if (cardMetadata) cardMetadata.style.display = scope.metadata ? 'flex' : 'none';
        if (cardHeadings) cardHeadings.style.display = scope.content ? 'flex' : 'none';
        if (cardContent) cardContent.style.display = scope.content ? 'flex' : 'none';
        if (cardImages) cardImages.style.display = scope.images ? 'flex' : 'none';
        if (cardLinks) cardLinks.style.display = scope.links ? 'flex' : 'none';

        // 1. Title
        if (scope.title) {
            const badgeTitle = document.getElementById('badge-title');
            const textTitle = document.getElementById('text-title');
            const titleData = data.title || {};
            updateBadge(badgeTitle, titleData.matches || 0);
            if (textTitle) {
                if (titleData.value) {
                    textTitle.innerHTML = highlightText(titleData.value, kw, isCase);
                } else {
                    textTitle.innerHTML = '<em style="color: var(--text-muted);">&lt;No title tag present&gt;</em>';
                }
            }
        }

        // 2. Metadata & OpenGraph
        if (scope.metadata) {
            const badgeMetadata = document.getElementById('badge-metadata');
            const listMetadata = document.getElementById('list-metadata');
            const metaData = data.metadata || { matches: 0, items: [] };
            const jsonLdData = data.json_ld || { matches: 0, items: [] };
            const totalMetaMatches = (metaData.matches || 0) + (jsonLdData.matches || 0);
            updateBadge(badgeMetadata, totalMetaMatches);

            if (listMetadata) {
                listMetadata.innerHTML = '';
                if (totalMetaMatches === 0) {
                    listMetadata.innerHTML = `<div class="empty-findings">✓ No matches found in &lt;meta&gt; description, og:*, canonical, or schema.</div>`;
                } else {
                    (metaData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">${escapeHtml(item.tag)}</span>
                                <span class="finding-count">${item.matches} ${item.matches === 1 ? 'match' : 'matches'}</span>
                            </div>
                            <div class="finding-snippet">${highlightText(item.content, kw, isCase)}</div>
                        `;
                        listMetadata.appendChild(div);
                    });

                    (jsonLdData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">&lt;script type="application/ld+json"&gt;</span>
                                <span class="finding-count">${item.matches} matches</span>
                            </div>
                            <div class="finding-snippet" style="font-family: var(--font-code); font-size: 0.8rem;">
                                ${highlightText(item.snippet, kw, isCase)}
                            </div>
                        `;
                        listMetadata.appendChild(div);
                    });
                }
            }
        }

        // 3. Headings & 4. SEO Content
        if (scope.content) {
            const badgeHeadings = document.getElementById('badge-headings');
            const listHeadings = document.getElementById('list-headings');
            const headingData = data.headings || { matches: 0, items: [] };
            updateBadge(badgeHeadings, headingData.matches || 0);

            if (listHeadings) {
                listHeadings.innerHTML = '';
                if (headingData.matches === 0) {
                    listHeadings.innerHTML = `<div class="empty-findings">✓ No matches found in headings (&lt;h1&gt; - &lt;h6&gt;).</div>`;
                } else {
                    (headingData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">&lt;${item.level.toLowerCase()}&gt;</span>
                                <span class="finding-count">${item.matches} match</span>
                            </div>
                            <div class="finding-snippet">${highlightText(item.text, kw, isCase)}</div>
                        `;
                        listHeadings.appendChild(div);
                    });
                }
            }

            const badgeContent = document.getElementById('badge-content');
            const listContent = document.getElementById('list-content');
            const contentData = data.seo_content || { matches: 0, items: [] };
            updateBadge(badgeContent, contentData.matches || 0);

            if (listContent) {
                listContent.innerHTML = '';
                if (contentData.matches === 0) {
                    listContent.innerHTML = `<div class="empty-findings">✓ No matches in body text or DDC content widgets.</div>`;
                } else {
                    (contentData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">Widget: ${escapeHtml(item.widget)}</span>
                                <span class="finding-count">${item.matches} matches</span>
                            </div>
                            <div class="finding-snippet">${highlightText(item.snippet, kw, isCase)}</div>
                        `;
                        listContent.appendChild(div);
                    });
                }
            }
        }

        // 5. Images
        if (scope.images) {
            const badgeImages = document.getElementById('badge-images');
            const listImages = document.getElementById('list-images');
            const imgData = data.images || { matches: 0, items: [] };
            updateBadge(badgeImages, imgData.matches || 0);

            if (listImages) {
                listImages.innerHTML = '';
                if (imgData.matches === 0) {
                    listImages.innerHTML = `<div class="empty-findings">✓ No matches found in image alt or title attributes.</div>`;
                } else {
                    (imgData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        let details = '';
                        if (item.alt_matches > 0) details += `<div><strong>alt:</strong> ${highlightText(item.alt, kw, isCase)}</div>`;
                        if (item.title_matches > 0) details += `<div><strong>title:</strong> ${highlightText(item.title, kw, isCase)}</div>`;
                        
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">&lt;img src="${escapeHtml(item.src ? item.src.slice(0, 40) + '...' : '')}"&gt;</span>
                                <span class="finding-count">${item.total} match</span>
                            </div>
                            <div class="finding-snippet">${details}</div>
                        `;
                        listImages.appendChild(div);
                    });
                }
            }
        }

        // 6. Links / CTAs
        if (scope.links) {
            const badgeLinks = document.getElementById('badge-links');
            const listLinks = document.getElementById('list-links');
            const linkData = data.links || { matches: 0, items: [] };
            updateBadge(badgeLinks, linkData.matches || 0);

            if (listLinks) {
                listLinks.innerHTML = '';
                if (linkData.matches === 0) {
                    listLinks.innerHTML = `<div class="empty-findings">✓ No matches found in links, buttons or CTAs.</div>`;
                } else {
                    (linkData.items || []).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'finding-item';
                        div.innerHTML = `
                            <div class="finding-header">
                                <span class="finding-tag">&lt;${item.tag || 'a'} href="${escapeHtml((item.href || '').slice(0, 40))}"&gt;</span>
                                <span class="finding-count">${item.matches} match</span>
                            </div>
                            <div class="finding-snippet">
                                <strong>Text:</strong> ${highlightText(item.anchor_text, kw, isCase)}
                            </div>
                        `;
                        listLinks.appendChild(div);
                    });
                }
            }
        }
    }

    // --- Batch Audit Trigger (Exposed Globally) ---
    window.triggerBatchAudit = async function (e) {
        if (e && e.preventDefault) e.preventDefault();

        const batchUrlsInput = document.getElementById('batch-urls');
        const batchKeywordInput = document.getElementById('batch-keyword');
        const batchCaseToggle = document.getElementById('batch-case-toggle');
        const batchSubmitBtn = document.getElementById('batch-submit-btn');
        const loadingIndicator = document.getElementById('loading-indicator');
        const loadingSubtext = document.getElementById('loading-subtext');
        const batchResultsSection = document.getElementById('batch-results-section');

        const batchScopeTitle = document.getElementById('batch-scope-title');
        const batchScopeMetadata = document.getElementById('batch-scope-metadata');
        const batchScopeContent = document.getElementById('batch-scope-content');
        const batchScopeImages = document.getElementById('batch-scope-images');
        const batchScopeLinks = document.getElementById('batch-scope-links');

        const urlsRaw = batchUrlsInput ? batchUrlsInput.value.trim() : '';
        const keyword = batchKeywordInput ? batchKeywordInput.value.trim() : '';
        const caseSensitive = batchCaseToggle ? batchCaseToggle.checked : false;

        if (!urlsRaw) {
            if (batchUrlsInput) batchUrlsInput.focus();
            alert('⚠️ Por favor pega al menos una URL de Dealer.com.');
            return;
        }

        if (!keyword) {
            if (batchKeywordInput) batchKeywordInput.focus();
            alert('⚠️ Por favor ingresa la palabra a buscar.');
            return;
        }

        const urls = urlsRaw.split('\n').map(u => u.trim()).filter(u => u.length > 0);
        if (urls.length === 0) {
            alert('⚠️ No se encontraron URLs válidas en el texto.');
            return;
        }

        saveRecentKeyword(keyword);

        setButtonLoading(batchSubmitBtn, true);
        if (loadingIndicator) loadingIndicator.style.display = 'block';
        if (batchResultsSection) batchResultsSection.style.display = 'none';
        if (loadingSubtext) loadingSubtext.textContent = `Auditing ${urls.length} URLs in batch for "${keyword}"...`;

        try {
            const response = await fetch('/api/audit-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    urls: urls,
                    keyword: keyword,
                    case_sensitive: caseSensitive,
                    include_title: batchScopeTitle ? batchScopeTitle.checked : true,
                    include_metadata: batchScopeMetadata ? batchScopeMetadata.checked : true,
                    include_content: batchScopeContent ? batchScopeContent.checked : true,
                    include_images: batchScopeImages ? batchScopeImages.checked : false,
                    include_links: batchScopeLinks ? batchScopeLinks.checked : false
                })
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                alert(`Error en auditoría en lote: ${result.error || 'Server error'}`);
                return;
            }

            currentBatchData = result;
            renderBatchResults(result);
            if (batchResultsSection) {
                batchResultsSection.style.display = 'block';
                batchResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

        } catch (err) {
            alert(`Error running batch audit: ${err.message}`);
        } finally {
            setButtonLoading(batchSubmitBtn, false);
            if (loadingIndicator) loadingIndicator.style.display = 'none';
        }
    };

    // --- Return to Batch View Helper (Exposed Globally) ---
    window.returnToBatchView = function () {
        console.log('[DDC Auditor] Returning to batch view...');
        const singleTab = document.getElementById('single-mode-tab');
        const batchTab = document.getElementById('batch-mode-tab');
        const singleForm = document.getElementById('audit-form');
        const batchForm = document.getElementById('batch-form');
        const resultsSection = document.getElementById('results-section');
        const batchResultsSection = document.getElementById('batch-results-section');
        const batchBackNav = document.getElementById('batch-back-nav');
        const bottomBackToBatchBtn = document.getElementById('bottom-back-to-batch-btn');

        if (batchBackNav) batchBackNav.style.display = 'none';
        if (bottomBackToBatchBtn) bottomBackToBatchBtn.style.display = 'none';

        if (batchTab) batchTab.classList.add('active');
        if (singleTab) singleTab.classList.remove('active');
        if (singleForm) singleForm.style.display = 'none';
        if (batchForm) batchForm.style.display = 'block';
        if (resultsSection) resultsSection.style.display = 'none';

        if (batchResultsSection && currentBatchData) {
            batchResultsSection.style.display = 'block';

            // Highlight the inspected row in the table
            if (lastInspectedUrl) {
                const rows = document.querySelectorAll('#batch-table-body tr');
                let foundRow = null;
                rows.forEach(r => {
                    const cell = r.querySelector('.url-cell');
                    if (cell && cell.textContent.trim() === lastInspectedUrl.trim()) {
                        r.classList.add('row-inspected');
                        foundRow = r;
                    } else {
                        r.classList.remove('row-inspected');
                    }
                });
                if (foundRow) {
                    foundRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                } else {
                    batchResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            } else {
                batchResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    };

    function renderBatchResults(batchData) {
        const tbody = document.getElementById('batch-table-body');
        const summaryBadge = document.getElementById('batch-summary-badge');
        if (!tbody) return;
        tbody.innerHTML = '';

        const results = batchData.results || [];
        if (summaryBadge) summaryBadge.textContent = `${results.length} Pages Scanned`;

        results.forEach(item => {
            const tr = document.createElement('tr');
            if (item.status === 'error') {
                tr.innerHTML = `
                    <td><span class="status-tag flagged">❌ Error</span></td>
                    <td class="url-cell" title="${escapeHtml(item.url)}">${escapeHtml(item.url)}</td>
                    <td colspan="5" style="color: var(--accent-rose); font-size: 0.8rem;">${escapeHtml(item.error)}</td>
                    <td>-</td>
                `;
            } else {
                const d = item.data;
                const isClean = d.total_matches === 0;
                
                tr.innerHTML = `
                    <td>
                        <span class="status-tag ${isClean ? 'clean' : 'flagged'}">
                            ${isClean ? '✓ Clean' : '⚠️ Matches'}
                        </span>
                    </td>
                    <td class="url-cell" title="${escapeHtml(d.url)}">${escapeHtml(d.url)}</td>
                    <td>
                        <span class="match-pill ${d.total_matches > 0 ? 'positive' : 'zero'}">
                            ${d.total_matches}
                        </span>
                    </td>
                    <td>
                        <span class="match-pill ${(d.title && d.title.matches) > 0 ? 'positive' : 'zero'}">
                            ${d.title ? d.title.matches : 0}
                        </span>
                    </td>
                    <td>
                        <span class="match-pill ${(d.metadata && d.metadata.matches) > 0 ? 'positive' : 'zero'}">
                            ${d.metadata ? d.metadata.matches : 0}
                        </span>
                    </td>
                    <td>
                        <span class="match-pill ${(d.seo_content && d.seo_content.matches) > 0 ? 'positive' : 'zero'}">
                            ${d.seo_content ? d.seo_content.matches : 0}
                        </span>
                    </td>
                    <td>
                        <span class="match-pill ${(d.images && d.images.matches) > 0 ? 'positive' : 'zero'}">
                            ${d.images ? d.images.matches : 0}
                        </span>
                    </td>
                    <td>
                        <button type="button" class="chip-item inspect-row-btn">Inspect</button>
                    </td>
                `;

                const inspectBtn = tr.querySelector('.inspect-row-btn');
                if (inspectBtn) {
                    inspectBtn.addEventListener('click', () => {
                        lastInspectedUrl = d.url;

                        // Show Back to Batch banner and action button
                        const batchBackNav = document.getElementById('batch-back-nav');
                        const bottomBackToBatchBtn = document.getElementById('bottom-back-to-batch-btn');
                        if (batchBackNav) batchBackNav.style.display = 'flex';
                        if (bottomBackToBatchBtn) bottomBackToBatchBtn.style.display = 'inline-flex';

                        const singleTab = document.getElementById('single-mode-tab');
                        const batchTab = document.getElementById('batch-mode-tab');
                        const singleForm = document.getElementById('audit-form');
                        const batchForm = document.getElementById('batch-form');
                        const targetUrlInput = document.getElementById('target-url');
                        const searchKeywordInput = document.getElementById('search-keyword');
                        const resultsSection = document.getElementById('results-section');
                        const batchResultsSection = document.getElementById('batch-results-section');

                        if (targetUrlInput) targetUrlInput.value = d.url;
                        if (searchKeywordInput) searchKeywordInput.value = d.keyword;

                        currentAuditData = d;
                        renderSingleAuditResults(d);

                        if (singleTab) singleTab.classList.add('active');
                        if (batchTab) batchTab.classList.remove('active');
                        if (singleForm) singleForm.style.display = 'block';
                        if (batchForm) batchForm.style.display = 'none';
                        if (batchResultsSection) batchResultsSection.style.display = 'none';

                        if (resultsSection) {
                            resultsSection.style.display = 'block';
                            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                    });
                }
            }
            tbody.appendChild(tr);
        });
    }

    // --- History Management ---
    function saveRecentKeyword(kw) {
        if (!kw) return;
        try {
            let list = JSON.parse(localStorage.getItem('ddc_recent_keywords') || '[]');
            list = list.filter(item => item.toLowerCase() !== kw.toLowerCase());
            list.unshift(kw);
            list = list.slice(0, 5);
            localStorage.setItem('ddc_recent_keywords', JSON.stringify(list));
            renderRecentChips(list);
        } catch (e) {}
    }

    function renderRecentChips(list) {
        const historyContainer = document.getElementById('history-container');
        const recentChips = document.getElementById('recent-chips');
        if (!historyContainer || !recentChips) return;
        if (!list || list.length === 0) {
            historyContainer.style.display = 'none';
            return;
        }
        historyContainer.style.display = 'flex';
        recentChips.innerHTML = '';
        list.forEach(item => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'chip-item';
            chip.textContent = item;
            chip.addEventListener('click', () => {
                const searchKeywordInput = document.getElementById('search-keyword');
                const batchKeywordInput = document.getElementById('batch-keyword');
                if (searchKeywordInput) searchKeywordInput.value = item;
                if (batchKeywordInput) batchKeywordInput.value = item;
            });
            recentChips.appendChild(chip);
        });
    }

    // --- DOMContentLoaded Initialization ---
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[DDC Auditor] Initializing DOM listeners...');

        // Mode tabs
        const singleTab = document.getElementById('single-mode-tab');
        const batchTab = document.getElementById('batch-mode-tab');
        const singleForm = document.getElementById('audit-form');
        const batchForm = document.getElementById('batch-form');
        const resultsSection = document.getElementById('results-section');
        const batchResultsSection = document.getElementById('batch-results-section');

        const backToBatchBtn = document.getElementById('back-to-batch-btn');
        const bottomBackToBatchBtn = document.getElementById('bottom-back-to-batch-btn');
        const batchBackNav = document.getElementById('batch-back-nav');

        if (backToBatchBtn) backToBatchBtn.addEventListener('click', window.returnToBatchView);
        if (bottomBackToBatchBtn) bottomBackToBatchBtn.addEventListener('click', window.returnToBatchView);

        if (singleTab && batchTab) {
            singleTab.addEventListener('click', () => {
                singleTab.classList.add('active');
                batchTab.classList.remove('active');
                if (singleForm) singleForm.style.display = 'block';
                if (batchForm) batchForm.style.display = 'none';
                if (batchResultsSection) batchResultsSection.style.display = 'none';
                if (currentAuditData && resultsSection) resultsSection.style.display = 'block';
            });

            batchTab.addEventListener('click', () => {
                batchTab.classList.add('active');
                singleTab.classList.remove('active');
                if (singleForm) singleForm.style.display = 'none';
                if (batchForm) batchForm.style.display = 'block';
                if (resultsSection) resultsSection.style.display = 'none';
                if (batchBackNav) batchBackNav.style.display = 'none';
                if (bottomBackToBatchBtn) bottomBackToBatchBtn.style.display = 'none';

                // Automatically restore batch results if they were already loaded!
                if (currentBatchData && batchResultsSection) {
                    batchResultsSection.style.display = 'block';
                }
            });
        }

        // Quick chip "Bubba"
        const chipBubba = document.getElementById('chip-bubba');
        const searchKeywordInput = document.getElementById('search-keyword');
        if (chipBubba && searchKeywordInput) {
            chipBubba.addEventListener('click', () => {
                searchKeywordInput.value = 'Bubba';
                searchKeywordInput.focus();
            });
        }

        // Scope checkboxes & Presets
        const scopeTitle = document.getElementById('scope-title');
        const scopeMetadata = document.getElementById('scope-metadata');
        const scopeContent = document.getElementById('scope-content');
        const scopeImages = document.getElementById('scope-images');
        const scopeLinks = document.getElementById('scope-links');

        const presetSeoOnly = document.getElementById('preset-seo-only');
        const presetAll = document.getElementById('preset-all');

        const batchScopeTitle = document.getElementById('batch-scope-title');
        const batchScopeMetadata = document.getElementById('batch-scope-metadata');
        const batchScopeContent = document.getElementById('batch-scope-content');
        const batchScopeImages = document.getElementById('batch-scope-images');
        const batchScopeLinks = document.getElementById('batch-scope-links');

        if (presetSeoOnly && presetAll) {
            presetSeoOnly.addEventListener('click', () => {
                presetSeoOnly.classList.add('active');
                presetAll.classList.remove('active');
                if (scopeTitle) scopeTitle.checked = true;
                if (scopeMetadata) scopeMetadata.checked = true;
                if (scopeContent) scopeContent.checked = true;
                if (scopeImages) scopeImages.checked = false;
                if (scopeLinks) scopeLinks.checked = false;

                if (batchScopeTitle) batchScopeTitle.checked = true;
                if (batchScopeMetadata) batchScopeMetadata.checked = true;
                if (batchScopeContent) batchScopeContent.checked = true;
                if (batchScopeImages) batchScopeImages.checked = false;
                if (batchScopeLinks) batchScopeLinks.checked = false;
            });

            presetAll.addEventListener('click', () => {
                presetAll.classList.add('active');
                presetSeoOnly.classList.remove('active');
                if (scopeTitle) scopeTitle.checked = true;
                if (scopeMetadata) scopeMetadata.checked = true;
                if (scopeContent) scopeContent.checked = true;
                if (scopeImages) scopeImages.checked = true;
                if (scopeLinks) scopeLinks.checked = true;

                if (batchScopeTitle) batchScopeTitle.checked = true;
                if (batchScopeMetadata) batchScopeMetadata.checked = true;
                if (batchScopeContent) batchScopeContent.checked = true;
                if (batchScopeImages) batchScopeImages.checked = true;
                if (batchScopeLinks) batchScopeLinks.checked = true;
            });
        }

        [scopeTitle, scopeMetadata, scopeContent, scopeImages, scopeLinks].filter(Boolean).forEach(chk => {
            chk.addEventListener('change', () => {
                if (!presetAll || !presetSeoOnly) return;
                const hasMedia = (scopeImages && scopeImages.checked) || (scopeLinks && scopeLinks.checked);
                if (hasMedia) {
                    presetAll.classList.add('active');
                    presetSeoOnly.classList.remove('active');
                } else {
                    presetSeoOnly.classList.add('active');
                    presetAll.classList.remove('active');
                }
            });
        });

        // Form submits
        if (singleForm) {
            singleForm.addEventListener('submit', window.triggerAudit);
        }
        if (batchForm) {
            batchForm.addEventListener('submit', window.triggerBatchAudit);
        }

        // Action buttons
        const copyReportBtn = document.getElementById('copy-report-btn');
        const openPageBtn = document.getElementById('open-page-btn');

        if (copyReportBtn) {
            copyReportBtn.addEventListener('click', () => {
                if (!currentAuditData) return;
                const d = currentAuditData;
                const scope = d.scope || {};
                
                let report = `=== DDC KEYWORD & METADATA AUDIT REPORT ===\n`;
                report += `URL: ${d.url}\n`;
                report += `Searched Keyword: "${d.keyword}" (Case-sensitive: ${d.case_sensitive ? 'Yes' : 'No'})\n`;
                report += `Status: ${d.total_matches === 0 ? 'CLEAN (0 matches)' : `FOUND ${d.total_matches} MATCHES`}\n`;
                report += `Response Time: ${d.elapsed_sec}s\n\n`;

                if (scope.title && d.title) {
                    report += `[1] PAGE TITLE (${d.title.matches} matches):\n`;
                    report += `    "${d.title.value || 'N/A'}"\n\n`;
                }

                if (scope.metadata && d.metadata) {
                    report += `[2] HEAD METADATA & OPENGRAPH (${d.metadata.matches} matches):\n`;
                    if ((d.metadata.items || []).length === 0) {
                        report += `    Clean - No matches\n`;
                    } else {
                        d.metadata.items.forEach(item => {
                            report += `    - ${item.tag}: "${item.content}"\n`;
                        });
                    }
                    report += `\n`;
                }

                if (scope.content) {
                    report += `[3] HEADINGS (${(d.headings && d.headings.matches) || 0} matches):\n`;
                    if (!d.headings || (d.headings.items || []).length === 0) {
                        report += `    Clean - No matches\n`;
                    } else {
                        d.headings.items.forEach(item => {
                            report += `    - <${item.level.toLowerCase()}>: "${item.text}"\n`;
                        });
                    }
                    report += `\n`;

                    report += `[4] SEO CONTENT & DDC WIDGETS (${(d.seo_content && d.seo_content.matches) || 0} matches):\n`;
                    if (!d.seo_content || (d.seo_content.items || []).length === 0) {
                        report += `    Clean - No matches\n`;
                    } else {
                        d.seo_content.items.forEach(item => {
                            report += `    - [${item.widget}]: "${item.snippet}"\n`;
                        });
                    }
                    report += `\n`;
                }

                if (scope.images && d.images && d.images.matches > 0) {
                    report += `[5] IMAGES (${d.images.matches} matches):\n`;
                    d.images.items.forEach(item => {
                        report += `    - src="${item.src}" | alt="${item.alt}" | title="${item.title}"\n`;
                    });
                    report += `\n`;
                }

                if (scope.links && d.links && d.links.matches > 0) {
                    report += `[6] CTAs & LINKS (${d.links.matches} matches):\n`;
                    d.links.items.forEach(item => {
                        report += `    - href="${item.href}" | text="${item.anchor_text}"\n`;
                    });
                    report += `\n`;
                }

                navigator.clipboard.writeText(report).then(() => {
                    const orig = copyReportBtn.innerHTML;
                    copyReportBtn.innerHTML = '<span>✅</span> Copied Report!';
                    setTimeout(() => { copyReportBtn.innerHTML = orig; }, 2000);
                }).catch(() => {
                    alert('Reporte copiado al portapapeles.');
                });
            });
        }

        if (openPageBtn) {
            openPageBtn.addEventListener('click', () => {
                if (currentAuditData && currentAuditData.url) {
                    window.open(currentAuditData.url, '_blank');
                }
            });
        }

        // Load recent keywords
        try {
            const raw = localStorage.getItem('ddc_recent_keywords');
            const list = raw ? JSON.parse(raw) : ['Bubba'];
            renderRecentChips(list);
        } catch (e) {
            renderRecentChips(['Bubba']);
        }

        console.log('[DDC Auditor] Ready!');
    });
})();
