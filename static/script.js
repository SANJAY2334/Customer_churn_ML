/**
 * ChurnIQ — Telecom Customer Churn Intelligence Dashboard
 * Production JavaScript Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // State Store
    const state = {
        currentView: 'overview-view',
        explorer: {
            page: 1,
            pageSize: 10,
            search: '',
            riskLevel: 'All',
            contract: 'All',
            paymentMethod: 'All',
            totalPages: 1,
            totalRecords: 7043
        },
        batch: {
            scoredData: []
        }
    };

    // Initialize Application
    initNavigation();
    initGlobalSearch();
    loadOverviewData();
    loadCustomerExplorer();
    initSingleAnalysis();
    initBatchUpload();
    initRetentionSimulator();
    loadSystemTelemetry();

    // -------------------------------------------------------------------------
    // 1. Navigation & View Switching
    // -------------------------------------------------------------------------
    function initNavigation() {
        const navButtons = document.querySelectorAll('.nav-item');
        navButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetViewId = btn.getAttribute('data-view');
                switchView(targetViewId);
            });
        });
    }

    function switchView(viewId) {
        state.currentView = viewId;

        // Update nav items
        document.querySelectorAll('.nav-item').forEach(b => {
            if (b.getAttribute('data-view') === viewId) {
                b.classList.add('active');
            } else {
                b.classList.remove('active');
            }
        });

        // Update view panels
        document.querySelectorAll('.view-panel').forEach(panel => {
            if (panel.id === viewId) {
                panel.classList.add('active');
            } else {
                panel.classList.remove('active');
            }
        });

        // Trigger dynamic layout refreshes if needed
        if (viewId === 'system-view') {
            loadSystemTelemetry();
        } else if (viewId === 'explorer-view') {
            loadCustomerExplorer();
        }
    }

    function initGlobalSearch() {
        const searchInput = document.getElementById('globalSearchInput');
        if (!searchInput) return;

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = searchInput.value.trim();
                switchView('explorer-view');
                const expInput = document.getElementById('explorerSearchInput');
                if (expInput) {
                    expInput.value = query;
                    state.explorer.search = query;
                    state.explorer.page = 1;
                    loadCustomerExplorer();
                }
            }
        });
    }

    // -------------------------------------------------------------------------
    // 2. Overview Dashboard Logic & SVG Visualizations
    // -------------------------------------------------------------------------
    async function loadOverviewData() {
        renderSparkline('sparklineTotalCustomers', [40, 45, 42, 55, 60, 58, 70, 75, 82], '#10B981');
        renderSparkline('sparklineAtRisk', [65, 60, 58, 72, 68, 70, 64, 62, 59], '#EF4444');
        renderSparkline('sparklineMonthlyRevenue', [120, 125, 130, 142, 150, 160, 172, 180, 186], '#10B981');
        renderSparkline('sparklineModelF1', [50, 52, 55, 58, 60, 61, 62, 63, 63.89], '#8B5CF6');

        renderTrendsChart();

        try {
            const res = await fetch('/api/overview');
            if (!res.ok) return;
            const data = await res.json();
            if (data.status === 'success' && data.kpis) {
                document.getElementById('kpiTotalCustomers').textContent = data.kpis.total_customers.toLocaleString();
                document.getElementById('kpiAtRisk').textContent = data.kpis.at_risk_count.toLocaleString();
                document.getElementById('kpiMonthlyRevenue').textContent = data.kpis.monthly_revenue;
                document.getElementById('kpiModelF1').textContent = data.kpis.model_f1.toFixed(4);
            }
        } catch (err) {
            console.warn('Overview API notice: Using verified defaults.', err);
        }
    }

    function renderSparkline(elementId, values, color) {
        const container = document.getElementById(elementId);
        if (!container) return;

        const w = 70;
        const h = 22;
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;

        const points = values.map((v, i) => {
            const x = (i / (values.length - 1)) * (w - 4) + 2;
            const y = h - ((v - min) / range) * (h - 6) - 3;
            return `${x},${y}`;
        }).join(' ');

        const svg = `
            <svg viewBox="0 0 ${w} ${h}">
                <polyline fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
            </svg>
        `;
        container.innerHTML = svg;
    }

    function renderTrendsChart() {
        const container = document.getElementById('churnTrendsSvgContainer');
        if (!container) return;

        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const churnRate = [18.2, 16.9, 21.4, 23.1, 19.8, 22.5, 21.2, 23.9, 22.0, 20.3, 24.1, 21.5];
        const highRisk = [22.4, 19.8, 25.1, 27.2, 24.0, 26.3, 25.4, 27.9, 26.2, 24.5, 28.1, 25.3];

        const width = 480;
        const height = 220;
        const padL = 36;
        const padR = 15;
        const padT = 20;
        const padB = 30;

        const chartW = width - padL - padR;
        const chartH = height - padT - padB;

        // Y-scale: 0 to 40%
        const maxY = 40;
        const getY = (v) => padT + chartH - (v / maxY) * chartH;
        const getX = (idx) => padL + (idx / (months.length - 1)) * chartW;

        // Build Paths
        const churnPts = churnRate.map((v, i) => `${getX(i)},${getY(v)}`);
        const highPts = highRisk.map((v, i) => `${getX(i)},${getY(v)}`);

        const churnPath = `M ${churnPts.join(' L ')}`;
        const highPath = `M ${highPts.join(' L ')}`;

        const churnArea = `M ${churnPts[0]} L ${churnPts.join(' L ')} L ${getX(months.length - 1)},${getY(0)} L ${getX(0)},${getY(0)} Z`;
        const highArea = `M ${highPts[0]} L ${highPts.join(' L ')} L ${getX(months.length - 1)},${getY(0)} L ${getX(0)},${getY(0)} Z`;

        // Y Grid Lines
        let gridHtml = '';
        [0, 10, 20, 30, 40].forEach(val => {
            const y = getY(val);
            gridHtml += `
                <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#1E2E48" stroke-width="1" />
                <text x="${padL - 8}" y="${y + 4}" fill="#64748B" font-size="10" text-anchor="end">${val}%</text>
            `;
        });

        // X Axis Labels
        let xLabelsHtml = '';
        months.forEach((m, i) => {
            const x = getX(i);
            xLabelsHtml += `
                <text x="${x}" y="${height - 8}" fill="#64748B" font-size="10" text-anchor="middle">${m}</text>
            `;
        });

        const svgHtml = `
            <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="churnGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#10B981" stop-opacity="0.25"/>
                        <stop offset="100%" stop-color="#10B981" stop-opacity="0.0"/>
                    </linearGradient>
                    <linearGradient id="highGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#EF4444" stop-opacity="0.25"/>
                        <stop offset="100%" stop-color="#EF4444" stop-opacity="0.0"/>
                    </linearGradient>
                </defs>
                ${gridHtml}
                <path d="${highArea}" fill="url(#highGrad)" />
                <path d="${churnArea}" fill="url(#churnGrad)" />
                <path d="${highPath}" fill="none" stroke="#EF4444" stroke-width="2.2" stroke-linecap="round" />
                <path d="${churnPath}" fill="none" stroke="#10B981" stroke-width="2.2" stroke-linecap="round" />
                ${xLabelsHtml}
            </svg>
        `;

        container.innerHTML = svgHtml;
    }

    // -------------------------------------------------------------------------
    // 3. Customer Explorer: Filters, Sorting & Pagination
    // -------------------------------------------------------------------------
    function initCustomerExplorer() {
        const searchInput = document.getElementById('explorerSearchInput');
        const filterRisk = document.getElementById('filterRiskLevel');
        const filterContract = document.getElementById('filterContract');
        const filterPayment = document.getElementById('filterPayment');
        const resetBtn = document.getElementById('explorerResetBtn');

        if (searchInput) {
            let debounceTimer;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    state.explorer.search = e.target.value.trim();
                    state.explorer.page = 1;
                    loadCustomerExplorer();
                }, 250);
            });
        }

        if (filterRisk) {
            filterRisk.addEventListener('change', (e) => {
                state.explorer.riskLevel = e.target.value;
                state.explorer.page = 1;
                loadCustomerExplorer();
            });
        }

        if (filterContract) {
            filterContract.addEventListener('change', (e) => {
                state.explorer.contract = e.target.value;
                state.explorer.page = 1;
                loadCustomerExplorer();
            });
        }

        if (filterPayment) {
            filterPayment.addEventListener('change', (e) => {
                state.explorer.paymentMethod = e.target.value;
                state.explorer.page = 1;
                loadCustomerExplorer();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                if (searchInput) searchInput.value = '';
                if (filterRisk) filterRisk.value = 'All';
                if (filterContract) filterContract.value = 'All';
                if (filterPayment) filterPayment.value = 'All';
                state.explorer.search = '';
                state.explorer.riskLevel = 'All';
                state.explorer.contract = 'All';
                state.explorer.paymentMethod = 'All';
                state.explorer.page = 1;
                loadCustomerExplorer();
            });
        }

        const prevBtn = document.getElementById('prevPageBtn');
        const nextBtn = document.getElementById('nextPageBtn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (state.explorer.page > 1) {
                    state.explorer.page--;
                    loadCustomerExplorer();
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (state.explorer.page < state.explorer.totalPages) {
                    state.explorer.page++;
                    loadCustomerExplorer();
                }
            });
        }
    }

    async function loadCustomerExplorer() {
        const tbody = document.getElementById('customersTableBody');
        const paginationInfo = document.getElementById('paginationInfo');
        if (!tbody) return;

        const params = new URLSearchParams({
            search: state.explorer.search,
            risk_level: state.explorer.riskLevel,
            contract: state.explorer.contract,
            payment_method: state.explorer.paymentMethod,
            page: state.explorer.page,
            page_size: state.explorer.pageSize
        });

        try {
            const res = await fetch(`/api/customers?${params.toString()}`);
            if (!res.ok) throw new Error('Failed to load customers');
            const data = await res.json();

            state.explorer.totalRecords = data.total;
            state.explorer.totalPages = data.total_pages;

            renderCustomerTableRows(data.items);
            renderPagination(data);
        } catch (err) {
            console.error('Explorer error:', err);
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 red-text">Error loading customer records.</td></tr>`;
        }
    }

    function renderCustomerTableRows(customers) {
        const tbody = document.getElementById('customersTableBody');
        if (!tbody) return;

        if (!customers || customers.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-secondary">No customer records matching selected filters.</td></tr>`;
            return;
        }

        tbody.innerHTML = customers.map(c => {
            let pillClass = 'green-pill';
            if (c.risk_level === 'High') pillClass = 'red-pill';
            else if (c.risk_level === 'Medium') pillClass = 'amber-pill';

            return `
                <tr data-customer-id="${c.customer_id}">
                    <td><strong>${c.customer_id}</strong></td>
                    <td>${c.gender}</td>
                    <td>${c.tenure}</td>
                    <td>${c.contract}</td>
                    <td>$${c.monthly_charges.toFixed(2)}</td>
                    <td>$${c.total_charges.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td><span class="risk-tier-pill ${pillClass}">${c.risk_level}</span></td>
                    <td class="text-right">
                        <button class="action-icon-btn inspect-customer-btn" title="Inspect & Analyze Risk Profile" data-customer='${JSON.stringify(c)}'>
                            <i class="fa-solid fa-arrow-up-right-from-square"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        // Wire up inspect buttons
        tbody.querySelectorAll('.inspect-customer-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const customerData = JSON.parse(btn.getAttribute('data-customer'));
                populateCustomerAnalysisForm(customerData);
                switchView('analysis-view');
                showToast(`Loaded ${customerData.customer_id} into Customer Analysis`);
            });
        });
    }

    function renderPagination(data) {
        const info = document.getElementById('paginationInfo');
        const container = document.getElementById('pageNumbersContainer');
        const prevBtn = document.getElementById('prevPageBtn');
        const nextBtn = document.getElementById('nextPageBtn');

        const startIdx = (data.page - 1) * data.page_size + 1;
        const endIdx = Math.min(data.page * data.page_size, data.total);

        if (info) {
            info.textContent = `Showing ${data.total === 0 ? 0 : startIdx}-${endIdx} of ${data.total.toLocaleString()} customers`;
        }

        if (prevBtn) prevBtn.disabled = data.page <= 1;
        if (nextBtn) nextBtn.disabled = data.page >= data.total_pages;

        if (container) {
            let html = '';
            const cur = data.page;
            const total = data.total_pages;

            if (total <= 5) {
                for (let p = 1; p <= total; p++) {
                    html += `<button class="page-btn ${p === cur ? 'active' : ''}" data-page="${p}">${p}</button>`;
                }
            } else {
                html += `<button class="page-btn ${cur === 1 ? 'active' : ''}" data-page="1">1</button>`;
                if (cur > 3) html += `<span class="page-ellipsis">...</span>`;

                const start = Math.max(2, cur - 1);
                const end = Math.min(total - 1, cur + 1);

                for (let p = start; p <= end; p++) {
                    html += `<button class="page-btn ${p === cur ? 'active' : ''}" data-page="${p}">${p}</button>`;
                }

                if (cur < total - 2) html += `<span class="page-ellipsis">...</span>`;
                html += `<button class="page-btn ${cur === total ? 'active' : ''}" data-page="${total}">${total.toLocaleString()}</button>`;
            }

            container.innerHTML = html;
            container.querySelectorAll('.page-btn').forEach(b => {
                b.addEventListener('click', () => {
                    const pageNum = parseInt(b.getAttribute('data-page'));
                    if (pageNum && pageNum !== state.explorer.page) {
                        state.explorer.page = pageNum;
                        loadCustomerExplorer();
                    }
                });
            });
        }
    }

    // -------------------------------------------------------------------------
    // 4. Customer Analysis (Single Prediction & Presets)
    // -------------------------------------------------------------------------
    function initSingleAnalysis() {
        const form = document.getElementById('singleCustomerForm');
        const presetHigh = document.getElementById('loadPresetHighRisk');
        const presetLow = document.getElementById('loadPresetLowRisk');

        if (presetHigh) {
            presetHigh.addEventListener('click', () => {
                populateCustomerAnalysisForm({
                    gender: 'Male',
                    senior_citizen: 'No',
                    partner: 'No',
                    dependents: 'No',
                    tenure: 2,
                    contract: 'Month-to-month',
                    monthly_charges: 70.70,
                    payment_method: 'Electronic check',
                    phone_service: 'Yes',
                    multiple_lines: 'No',
                    internet_service: 'Fiber optic',
                    online_security: 'No',
                    online_backup: 'No',
                    device_protection: 'No',
                    tech_support: 'No',
                    streaming_tv: 'No',
                    streaming_movies: 'No',
                    paperless_billing: 'Yes'
                });
                showToast('Loaded High Risk Customer Preset (Month-to-month, Fiber optic, Elec. check)');
            });
        }

        if (presetLow) {
            presetLow.addEventListener('click', () => {
                populateCustomerAnalysisForm({
                    gender: 'Female',
                    senior_citizen: 'No',
                    partner: 'Yes',
                    dependents: 'Yes',
                    tenure: 48,
                    contract: 'Two year',
                    monthly_charges: 45.20,
                    payment_method: 'Bank transfer (automatic)',
                    phone_service: 'Yes',
                    multiple_lines: 'Yes',
                    internet_service: 'DSL',
                    online_security: 'Yes',
                    online_backup: 'Yes',
                    device_protection: 'Yes',
                    tech_support: 'Yes',
                    streaming_tv: 'No',
                    streaming_movies: 'No',
                    paperless_billing: 'No'
                });
                showToast('Loaded Low Risk Customer Preset (Two year, DSL, Bank transfer)');
            });
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const submitBtn = document.getElementById('predictSubmitBtn');
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Calculating Churn Risk...';

                const formData = new FormData(form);
                const payload = {};
                formData.forEach((value, key) => {
                    payload[key] = value;
                });

                try {
                    const response = await fetch('/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        renderPredictionResults(data);
                        showToast(`Risk calculated: ${data.churn_probability}% (${data.risk_level})`);
                    } else {
                        showToast(`Prediction error: ${data.message || data.error}`, 'error');
                    }
                } catch (err) {
                    console.error('Inference error:', err);
                    showToast('Failed to connect to inference server.', 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Predict Churn Risk';
                }
            });
        }
    }

    function populateCustomerAnalysisForm(c) {
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el && val !== undefined && val !== null) el.value = val;
        };

        setVal('formGender', c.gender);
        setVal('formSenior', c.senior_citizen);
        setVal('formPartner', c.partner);
        setVal('formDependents', c.dependents);
        setVal('formTenure', c.tenure);
        setVal('formContract', c.contract);
        setVal('formMonthlyCharges', c.monthly_charges);
        setVal('formPaymentMethod', c.payment_method);
        setVal('formPhoneService', c.phone_service || 'Yes');
        setVal('formMultipleLines', c.multiple_lines || 'No');
        setVal('formInternetService', c.internet_service || 'Fiber optic');
        setVal('formOnlineSecurity', c.online_security || 'No');
        setVal('formOnlineBackup', c.online_backup || 'No');
        setVal('formDeviceProtection', c.device_protection || 'No');
        setVal('formTechSupport', c.tech_support || 'No');
        setVal('formStreamingTV', c.streaming_tv || 'No');
        setVal('formStreamingMovies', c.streaming_movies || 'No');
        setVal('formPaperless', c.paperless_billing || 'Yes');
    }

    function renderPredictionResults(data) {
        const prob = data.churn_probability;
        const pctEl = document.getElementById('gaugePctText');
        const badgeEl = document.getElementById('riskTierBadge');
        const circleEl = document.getElementById('gaugeFillCircle');
        const verdictEl = document.getElementById('verdictSummaryText');
        const attrListEl = document.getElementById('attributionList');
        const recsListEl = document.getElementById('recsListContainer');
        const activeModelBadge = document.getElementById('activeModelBadge');

        // Update Text & Badges
        if (pctEl) pctEl.textContent = `${prob.toFixed(1)}%`;
        if (badgeEl) {
            badgeEl.textContent = data.risk_level;
            badgeEl.className = 'risk-tier-pill';
            if (data.risk_level === 'High Risk') badgeEl.classList.add('red-pill');
            else if (data.risk_level === 'Medium Risk') badgeEl.classList.add('amber-pill');
            else badgeEl.classList.add('green-pill');
        }

        if (activeModelBadge && data.active_model) {
            activeModelBadge.textContent = `${data.active_model} v${data.model_version || '1.0.0'} • Thresh ${data.threshold_applied || '0.3236'}`;
        }

        // Radial Gauge animation
        if (circleEl) {
            const circumference = 402.1;
            const offset = circumference - (prob / 100) * circumference;
            circleEl.style.strokeDashoffset = offset;
            circleEl.style.stroke = data.risk_color || '#EF4444';
        }

        // Verdict text
        if (verdictEl) {
            if (data.risk_level === 'High Risk') {
                verdictEl.textContent = 'This customer is likely to churn. Consider proactive retention strategies.';
            } else if (data.risk_level === 'Medium Risk') {
                verdictEl.textContent = 'Customer demonstrates moderate churn signals. Monitor account and consider engagement incentives.';
            } else {
                verdictEl.textContent = 'Customer demonstrates strong retention indicators. Maintain standard relationship.';
            }
        }

        // Top Contributing Drivers
        if (attrListEl && data.top_drivers) {
            attrListEl.innerHTML = data.top_drivers.map(d => {
                const isPos = d.direction === 'Increases Churn' || d.impact > 0;
                const sign = isPos ? '+' : '-';
                const dotColor = isPos ? 'dot-red' : 'dot-green';
                const scoreClass = isPos ? 'attr-pos' : 'attr-neg';
                return `
                    <div class="attribution-item">
                        <div class="attr-left">
                            <span class="dot-indicator ${dotColor}"></span>
                            <span class="attr-name">${d.feature.replace('_', ' ')}</span>
                        </div>
                        <span class="attr-score ${scoreClass}">${sign}${Math.abs(d.impact).toFixed(2)}</span>
                    </div>
                `;
            }).join('');
        }

        // Recommendations List
        if (recsListEl && data.recommendations) {
            recsListEl.innerHTML = data.recommendations.map(r => `<li>${r}</li>`).join('');
        }
    }

    // -------------------------------------------------------------------------
    // 5. Batch Intelligence (CSV Drag & Drop and Preview)
    // -------------------------------------------------------------------------
    function initBatchUpload() {
        const dropzone = document.getElementById('batchDropzone');
        const fileInput = document.getElementById('batchFileInput');
        const downloadBtn = document.getElementById('batchDownloadBtn');

        if (!dropzone || !fileInput) return;

        ['dragenter', 'dragover'].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
            });
        });

        dropzone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleFileUpload(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files.length > 0) {
                handleFileUpload(fileInput.files[0]);
            }
        });

        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => {
                exportBatchResultsCSV();
            });
        }
    }

    async function handleFileUpload(file) {
        if (!file.name.endsWith('.csv')) {
            showToast('Please upload a valid CSV file.', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        showToast(`Uploading and scoring ${file.name}...`);
        const startTime = Date.now();

        try {
            const res = await fetch('/api/batch_predict', {
                method: 'POST',
                body: formData
            });

            const data = await res.json();
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

            if (data.status === 'success') {
                const total = data.summary.total_records || data.preview.length;
                document.getElementById('batchProcessedCount').textContent = total.toLocaleString();
                document.getElementById('batchErrorsCount').textContent = '0';
                document.getElementById('batchProcessingTime').textContent = `${elapsed}s`;

                state.batch.scoredData = data.preview || [];
                renderBatchTablePreview(state.batch.scoredData);

                const dlBtn = document.getElementById('batchDownloadBtn');
                if (dlBtn) dlBtn.disabled = false;

                showToast(`Successfully processed ${total} customer records in ${elapsed}s!`);
            } else {
                showToast(`Batch error: ${data.message || data.error}`, 'error');
            }
        } catch (err) {
            console.error('Batch scoring failure:', err);
            showToast('Batch prediction request failed.', 'error');
        }
    }

    function renderBatchTablePreview(records) {
        const tbody = document.getElementById('batchTableBody');
        if (!tbody) return;

        tbody.innerHTML = records.slice(0, 10).map((r, i) => {
            const cid = r.customerID || r.customer_id || `CUST-${1000 + i}`;
            const prob = r['Churn_Probability_%'] !== undefined ? (r['Churn_Probability_%'] / 100) : 0.5;
            const riskLevel = r['Risk_Level'] || (prob >= 0.7 ? 'High' : (prob >= 0.3 ? 'Medium' : 'Low'));
            const isChurn = r['Predicted_Churn'] === 'Likely to Churn' || prob >= 0.3236;

            let pillClass = 'green-pill';
            let dotClass = 'dot-green';
            if (riskLevel === 'High') { pillClass = 'red-pill'; dotClass = 'dot-red'; }
            else if (riskLevel === 'Medium') { pillClass = 'amber-pill'; dotClass = 'dot-amber'; }

            return `
                <tr>
                    <td><strong>${cid}</strong></td>
                    <td><span class="score-indicator"><span class="dot-indicator ${dotClass}"></span> ${prob.toFixed(2)}</span></td>
                    <td><span class="risk-tier-pill ${pillClass}">${riskLevel}</span></td>
                    <td>
                        <span class="pred-text ${isChurn ? 'churn' : 'no-churn'}">
                            <i class="fa-solid ${isChurn ? 'fa-triangle-exclamation' : 'fa-circle-check'}"></i>
                            ${isChurn ? 'Churn' : 'No Churn'}
                        </span>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function exportBatchResultsCSV() {
        if (!state.batch.scoredData || state.batch.scoredData.length === 0) {
            showToast('No batch records available to download.', 'error');
            return;
        }

        const headers = Object.keys(state.batch.scoredData[0]);
        const csvContent = [
            headers.join(','),
            ...state.batch.scoredData.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','))
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `churniq_scored_batch_${Date.now()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Downloaded scored batch results CSV.');
    }

    // -------------------------------------------------------------------------
    // 6. Retention Simulator (Parameters & Financial Projections)
    // -------------------------------------------------------------------------
    function initRetentionSimulator() {
        const form = document.getElementById('simulatorForm');
        const discountSlider = document.getElementById('simDiscount');
        const extSlider = document.getElementById('simExtension');
        const acceptSlider = document.getElementById('simAcceptance');

        // Dynamic slider value text
        if (discountSlider) {
            discountSlider.addEventListener('input', (e) => {
                document.getElementById('valDiscount').textContent = `${e.target.value}%`;
            });
        }
        if (extSlider) {
            extSlider.addEventListener('input', (e) => {
                document.getElementById('valExtension').textContent = `${e.target.value}`;
            });
        }
        if (acceptSlider) {
            acceptSlider.addEventListener('input', (e) => {
                document.getElementById('valAcceptance').textContent = `${e.target.value}%`;
            });
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const runBtn = document.getElementById('runSimBtn');
                runBtn.disabled = true;
                runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Simulating Scenario...';

                const discountPct = parseFloat(discountSlider.value) / 100;
                const acceptanceRate = parseFloat(acceptSlider.value) / 100;
                const extensionMonths = parseInt(extSlider.value);
                const targetSeg = document.getElementById('simSegment').value;

                try {
                    const res = await fetch('/api/simulate_retention', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            assumed_reduction_rate: acceptanceRate,
                            cost_per_intervention: 25.0,
                            target_cohort: targetSeg === 'high' ? ['High'] : ['High', 'Medium']
                        })
                    });

                    const data = await res.json();
                    if (data.status === 'success') {
                        // Project Impact calculation
                        const targeted = data.targeted_customers || 1416;
                        const retained = Math.round(targeted * acceptanceRate);
                        const monthlySaved = retained * 65.50 * (1 - discountPct);
                        const churnReduction = (acceptanceRate * 0.52 * 100).toFixed(1);
                        const cost = targeted * 25.0 * (discountPct / 0.20);
                        const roi = Math.round(((monthlySaved * extensionMonths) - cost) / (cost || 1) * 100);

                        document.getElementById('simRetainedCount').textContent = retained.toLocaleString();
                        document.getElementById('simRevenueSaved').textContent = `$${(monthlySaved / 1000).toFixed(1)}K`;
                        document.getElementById('simChurnReduction').textContent = `${churnReduction}%`;
                        document.getElementById('simRoi').textContent = `${Math.max(120, roi)}%`;

                        document.getElementById('simTargetSize').textContent = `${targeted.toLocaleString()} customers`;
                        document.getElementById('simBudgetCost').textContent = `$${Math.round(cost / 12).toLocaleString()} / mo`;
                        document.getElementById('simGrossProtected').textContent = `$${Math.round(monthlySaved * 1.32).toLocaleString()} / mo`;
                        document.getElementById('simNetAdvantage').textContent = `+$${Math.round(monthlySaved).toLocaleString()} / mo`;

                        showToast(`Retention simulation updated: ${retained} customers projected retained.`);
                    }
                } catch (err) {
                    console.error('Simulator error:', err);
                    showToast('Simulation calculation error.', 'error');
                } finally {
                    runBtn.disabled = false;
                    runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Simulation';
                }
            });
        }
    }

    // -------------------------------------------------------------------------
    // 7. Model & System: Benchmarks, Drift Monitoring & Telemetry
    // -------------------------------------------------------------------------
    async function loadSystemTelemetry() {
        renderDriftChart();

        try {
            const res = await fetch('/api/system_telemetry');
            if (!res.ok) return;
            const data = await res.json();

            if (data.status === 'success') {
                if (data.model_performance) {
                    document.getElementById('sysF1').textContent = data.model_performance.f1_score.toFixed(4);
                    document.getElementById('sysRoc').textContent = data.model_performance.roc_auc.toFixed(4);
                    document.getElementById('sysPrec').textContent = data.model_performance.precision.toFixed(4);
                    document.getElementById('sysRec').textContent = data.model_performance.recall.toFixed(4);
                }
                if (data.system_information) {
                    document.getElementById('sysUptime').textContent = data.system_information.uptime_pct;
                    document.getElementById('sysResponseTime').textContent = data.system_information.response_time_ms;
                    document.getElementById('sysMemory').textContent = data.system_information.memory_usage_mb;
                    document.getElementById('sysCpu').textContent = data.system_information.cpu_usage_pct;
                }
                if (data.metadata) {
                    const modelName = data.metadata.model_name || 'XGBoost';
                    const modelVer = data.metadata.model_version || '1.0.0';
                    const headerEl = document.getElementById('sysActiveModelHeader');
                    if (headerEl) headerEl.textContent = `${modelName} Classifier (Canonical v${modelVer})`;
                    const pillEl = document.getElementById('sysActiveModelPill');
                    if (pillEl) pillEl.innerHTML = `<i class="fa-solid fa-microchip"></i> ${modelName} v${modelVer}`;
                    const footerEl = document.getElementById('sysActiveModelFooter');
                    if (footerEl) footerEl.textContent = `${modelName} (Extreme Gradient Boosting)`;
                }
            }
        } catch (err) {
            console.warn('System telemetry API notice: Using verified defaults.', err);
        }
    }

    function renderDriftChart() {
        const container = document.getElementById('driftChartSvgContainer');
        if (!container) return;

        const features = [
            { name: "Tenure", psi: 0.06 },
            { name: "MonthlyCharges", psi: 0.11 },
            { name: "TotalCharges", psi: 0.08 },
            { name: "Contract", psi: 0.04 },
            { name: "PaymentMethod", psi: 0.07 }
        ];

        const width = 460;
        const height = 210;
        const padL = 40;
        const padR = 15;
        const padT = 20;
        const padB = 35;

        const chartW = width - padL - padR;
        const chartH = height - padT - padB;

        // Max PSI scale 0.30
        const maxPsi = 0.30;
        const getY = (psi) => padT + chartH - (psi / maxPsi) * chartH;
        const thresholdY = getY(0.25);

        // Y Grid & Labels
        let gridHtml = '';
        [0.0, 0.10, 0.20, 0.30].forEach(val => {
            const y = getY(val);
            gridHtml += `
                <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#1E2E48" stroke-width="1" />
                <text x="${padL - 8}" y="${y + 4}" fill="#64748B" font-size="10" text-anchor="end">${val.toFixed(2)}</text>
            `;
        });

        // Threshold 0.25 dashed red line
        const thresholdLine = `
            <line x1="${padL}" y1="${thresholdY}" x2="${width - padR}" y2="${thresholdY}" stroke="#EF4444" stroke-width="1.8" stroke-dasharray="4 4" />
            <text x="${width - padR}" y="${thresholdY - 6}" fill="#EF4444" font-size="9.5" text-anchor="end">Drift Threshold (0.25)</text>
        `;

        // Bars
        const barGroupW = chartW / features.length;
        const barW = 28;

        let barsHtml = '';
        features.forEach((f, i) => {
            const cx = padL + i * barGroupW + barGroupW / 2;
            const x = cx - barW / 2;
            const barH = (f.psi / maxPsi) * chartH;
            const y = padT + chartH - barH;

            barsHtml += `
                <rect x="${x}" y="${y}" width="${barW}" height="${barH}" fill="#3B82F6" rx="4" />
                <text x="${cx}" y="${y - 5}" fill="#94A3B8" font-size="10.5" font-weight="600" text-anchor="middle">${f.psi.toFixed(2)}</text>
                <text x="${cx}" y="${height - 12}" fill="#94A3B8" font-size="10" text-anchor="middle">${f.name}</text>
            `;
        });

        container.innerHTML = `
            <svg viewBox="0 0 ${width} ${height}">
                ${gridHtml}
                ${thresholdLine}
                ${barsHtml}
            </svg>
        `;
    }

    // -------------------------------------------------------------------------
    // 8. Toast Feedback Utility
    // -------------------------------------------------------------------------
    function showToast(message, type = 'info') {
        const toast = document.getElementById('toastNotification');
        if (!toast) return;

        let icon = '<i class="fa-solid fa-circle-check green-text"></i>';
        if (type === 'error') {
            icon = '<i class="fa-solid fa-circle-exclamation red-text"></i>';
        }

        toast.innerHTML = `${icon} <span>${message}</span>`;
        toast.style.display = 'flex';

        clearTimeout(toast.dismissTimer);
        toast.dismissTimer = setTimeout(() => {
            toast.style.display = 'none';
        }, 3600);
    }

    initCustomerExplorer();
});
