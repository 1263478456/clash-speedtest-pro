/**
 * ClashSpeedTest Pro - 前端逻辑
 */

// ========== 状态管理 ==========
let token = localStorage.getItem('token');
let currentUser = null;
let pollTimer = null;
let isRunning = false;
let selectedResults = new Set();
let uploadedYamlTempFile = null;

// ========== DOM 元素 ==========
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ========== API 调用 ==========
async function api(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();
    
    if (res.status === 401) {
        logout();
        throw new Error('认证失败，请重新登录');
    }
    
    if (!res.ok) {
        throw new Error(data.detail || '请求失败');
    }
    
    return data;
}

async function apiForm(url, formData) {
    const headers = {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const res = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
    });
    const data = await res.json();
    
    if (res.status === 401) {
        logout();
        throw new Error('认证失败');
    }
    
    if (!res.ok) {
        throw new Error(data.detail || '请求失败');
    }
    
    return data;
}

// ========== 认证 ==========
async function login(username, password) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    const data = await apiForm('/api/auth/login', formData);
    token = data.access_token;
    localStorage.setItem('token', token);
    currentUser = data.username;
    showMainPage();
}

function logout() {
    token = null;
    currentUser = null;
    localStorage.removeItem('token');
    showLoginPage();
}

async function checkAuth() {
    if (!token) {
        showLoginPage();
        return;
    }
    try {
        const data = await api('/api/auth/me');
        currentUser = data.username;
        showMainPage();
    } catch (e) {
        showLoginPage();
    }
}

function showLoginPage() {
    $('#login-page').classList.remove('hidden');
    $('#main-page').classList.add('hidden');
}

function showMainPage() {
    $('#login-page').classList.add('hidden');
    $('#main-page').classList.remove('hidden');
    $('#username-display').textContent = currentUser;
    loadSubscriptions();
    loadTheme();
    loadLogLevel();
    loadHistory();
    loadSchedules();
    
    // 检查是否有正在运行的测速
    checkRunningTest();
}

// ========== 主题 (默认浅色) ==========
function getSavedTheme() {
    return localStorage.getItem('theme') || 'light';
}

function applyTheme(theme) {
    if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        $('#theme-icon').textContent = '☀️';
    } else {
        document.documentElement.removeAttribute('data-theme');
        $('#theme-icon').textContent = '🌙';
    }
    localStorage.setItem('theme', theme);
}

async function loadTheme() {
    try {
        const data = await api('/api/theme');
        applyTheme(data.theme);
    } catch (e) {
        applyTheme(getSavedTheme());
    }
}

function toggleTheme() {
    const current = getSavedTheme();
    const newTheme = current === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
    api('/api/theme', {
        method: 'POST',
        body: JSON.stringify({ theme: newTheme }),
    }).catch(() => {});
}

// ========== 日志等级 ==========
async function loadLogLevel() {
    try {
        const data = await api('/api/log-level');
        $('#log-level').value = data.level;
    } catch (e) {}
}

async function syncLogLevel() {
    const level = $('#log-level').value;
    try {
        await api('/api/log-level', {
            method: 'POST',
            body: JSON.stringify({ level }),
        });
    } catch (e) {}
}

// ========== 订阅管理 ==========
let subscriptions = [];

async function loadSubscriptions() {
    try {
        const data = await api('/api/subscriptions');
        subscriptions = data.subscriptions;
        renderSubscriptions();
        updateSubscriptionSelects();
    } catch (e) {}
}

function renderSubscriptions() {
    const list = $('#subscriptions-list');
    if (subscriptions.length === 0) {
        list.innerHTML = '<p style="color:var(--text-dim)">暂无订阅</p>';
        return;
    }
    
    list.innerHTML = subscriptions.map(sub => `
        <div class="list-item">
            <div class="list-item-info">
                <h3>${escapeHtml(sub.name)}</h3>
                <p>${escapeHtml(sub.url)} • ${sub.node_count} 个节点</p>
                ${sub.last_used_at ? `<p>上次使用: ${formatDate(sub.last_used_at)}</p>` : ''}
            </div>
            <div class="list-item-actions">
                <button class="btn btn-small btn-secondary" onclick="editSubscription(${sub.id})" title="编辑订阅">✏️ 编辑</button>
                <button class="btn btn-small btn-primary" onclick="refreshSubscription(${sub.id})" title="刷新订阅获取最新节点">🔄 刷新</button>
                <button class="btn btn-small btn-danger" onclick="deleteSubscription(${sub.id})">🗑️ 删除</button>
            </div>
        </div>
    `).join('');
}

function updateSubscriptionSelects() {
    const options = '<option value="">-- 选择已保存的订阅 --</option>' +
        subscriptions.map(s => `<option value="${s.id}">${escapeHtml(s.name)} (${s.node_count}节点)</option>`).join('');
    $('#subscription-select').innerHTML = options;
    
    const scheduleOptions = subscriptions.map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
    $('#schedule-subscription').innerHTML = scheduleOptions;
}

async function addSubscription() {
    const name = $('#sub-name').value.trim();
    const url = $('#sub-url').value.trim();
    
    if (!name || !url) {
        alert('请输入名称和链接');
        return;
    }
    
    try {
        await api('/api/subscriptions', {
            method: 'POST',
            body: JSON.stringify({ name, url }),
        });
        $('#sub-name').value = '';
        $('#sub-url').value = '';
        loadSubscriptions();
    } catch (e) {
        alert('添加失败: ' + e.message);
    }
}

async function deleteSubscription(id) {
    if (!confirm('确定删除此订阅？')) return;
    
    try {
        await api(`/api/subscriptions/${id}`, { method: 'DELETE' });
        loadSubscriptions();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function refreshSubscription(id) {
    const sub = subscriptions.find(s => s.id === id);
    if (!sub) return;
    
    if (!confirm(`确定刷新订阅 "${sub.name}"？\n这将重新拉取订阅内容并更新节点数。`)) return;
    
    try {
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = '⏳ 刷新中...';
        
        const data = await api(`/api/subscriptions/${id}/refresh`, { method: 'POST' });
        alert(`刷新成功！当前节点数: ${data.subscription.node_count}`);
        loadSubscriptions();
    } catch (e) {
        alert('刷新失败: ' + e.message);
    } finally {
        const btn = event.target;
        btn.disabled = false;
        btn.textContent = '🔄 刷新';
    }
}

async function editSubscription(id) {
    const sub = subscriptions.find(s => s.id === id);
    if (!sub) return;
    
    const newName = prompt('请输入新的订阅名称:', sub.name);
    if (newName === null) return; // 用户取消
    
    const newUrl = prompt('请输入新的订阅链接:', sub.url);
    if (newUrl === null) return; // 用户取消
    
    if (!newName.trim() || !newUrl.trim()) {
        alert('名称和链接不能为空');
        return;
    }
    
    try {
        await api(`/api/subscriptions/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ name: newName.trim(), url: newUrl.trim() }),
        });
        alert('订阅更新成功');
        loadSubscriptions();
    } catch (e) {
        alert('更新失败: ' + e.message);
    }
}

// ========== 测速 ==========
async function checkRunningTest() {
    try {
        const data = await api('/api/status');
        if (data.test_running || data.progress.status === 'running') {
            isRunning = true;
            $('#btn-start').classList.add('hidden');
            $('#btn-stop').classList.remove('hidden');
            $('#progress-section').classList.remove('hidden');
            $('#results-section').classList.remove('hidden');
            startPolling();
        }
    } catch (e) {}
}

async function startTest() {
    const subscriptionId = $('#subscription-select').value;
    const tempUrl = $('#temp-url').value.trim();
    
    // 检查是否使用上传的 YAML
    if (uploadedYamlTempFile) {
        try {
            const data = await api('/api/start-test-yaml', {
                method: 'POST',
                body: JSON.stringify({
                    temp_file: uploadedYamlTempFile,
                    test_streaming: $('#test-streaming').checked,
                    theme: $('#image-theme').value,
                }),
            });
            isRunning = true;
            $('#btn-start').classList.add('hidden');
            $('#btn-stop').classList.remove('hidden');
            $('#progress-section').classList.remove('hidden');
            $('#results-section').classList.remove('hidden');
            $('#results-body').innerHTML = '';
            startPolling();
            return;
        } catch (e) {
            alert('启动失败: ' + e.message);
            return;
        }
    }
    
    if (!subscriptionId && !tempUrl) {
        alert('请选择订阅、输入链接或上传 YAML 文件');
        return;
    }
    
    const body = {
        test_streaming: $('#test-streaming').checked,
        theme: $('#image-theme').value,
    };
    
    if (subscriptionId) {
        body.subscription_id = parseInt(subscriptionId);
    } else {
        body.url = tempUrl;
    }
    
    try {
        await api('/api/start-test', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        
        isRunning = true;
        $('#btn-start').classList.add('hidden');
        $('#btn-stop').classList.remove('hidden');
        $('#progress-section').classList.remove('hidden');
        $('#results-section').classList.remove('hidden');
        $('#complete-section').classList.add('hidden');
        $('#results-body').innerHTML = '';
        
        startPolling();
    } catch (e) {
        alert('启动失败: ' + e.message);
    }
}

async function stopTest() {
    try {
        await api('/api/stop-test', { method: 'POST' });
    } catch (e) {}
    
    isRunning = false;
    stopPolling();
    $('#btn-start').classList.remove('hidden');
    $('#btn-stop').classList.add('hidden');
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 1000);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function pollStatus() {
    try {
        const data = await api('/api/status');
        const progress = data.progress;
        
        const percent = progress.total > 0 ? (progress.completed / progress.total * 100) : 0;
        $('#progress-fill').style.width = percent + '%';
        $('#progress-text').textContent = progress.message;
        $('#progress-count').textContent = `${progress.completed}/${progress.total}`;
        $('#progress-current').textContent = progress.current_node ? `当前: ${progress.current_node}` : '';
        
        // 更新实时结果
        if (data.results_count > 0) {
            updateLiveResults();
        }
        
        if (progress.status === 'completed' || progress.status === 'error' || progress.status === 'stopped') {
            isRunning = false;
            stopPolling();
            $('#btn-start').classList.remove('hidden');
            $('#btn-stop').classList.add('hidden');
            
            if (progress.status === 'completed' || progress.status === 'stopped') {
                $('#complete-section').classList.remove('hidden');
                $('#complete-summary').textContent = progress.message;
                loadHistory();
            }
        }
    } catch (e) {}
}

async function updateLiveResults() {
    try {
        const data = await api('/api/live-results');
        if (data.results && data.results.length > 0) {
            renderLiveResults(data.results);
        }
    } catch (e) {}
}

function renderLiveResults(results) {
    const tbody = $('#results-body');
    if (!results || results.length === 0) return;
    
    tbody.innerHTML = results.map((n, i) => `
        <tr>
            <td>${i + 1}</td>
            <td title="${escapeHtml(n.name)}">${escapeHtml(n.name)}</td>
            <td>${n.type || ''}</td>
            <td class="${getSpeedClass(n.speed_mb_per_sec)}">${formatSpeed(n.speed_mb_per_sec)}</td>
            <td class="${getSpeedClass(n.upload_speed_mb_per_sec)}">${formatSpeed(n.upload_speed_mb_per_sec)}</td>
            <td class="${getSpeedClass(n.max_speed_mb_per_sec)}">${formatSpeed(n.max_speed_mb_per_sec)}</td>
            <td>${(n.traffic_mb || 0).toFixed(2)} MB</td>
            <td>${n.tls_rtt ? n.tls_rtt.toFixed(0) + 'ms' : '-'}</td>
            <td>${n.https_ping ? n.https_ping.toFixed(0) + 'ms' : '-'}</td>
            <td class="${getStatusClass(n.streaming?.Netflix)}">${n.streaming?.Netflix || '-'}</td>
            <td class="${getStatusClass(n.streaming?.YouTube)}">${n.streaming?.YouTube || '-'}</td>
            <td class="${getStatusClass(n.streaming?.Bilibili)}">${n.streaming?.Bilibili || '-'}</td>
            <td class="${getStatusClass(n.streaming?.['Disney+'])}">${n.streaming?.['Disney+'] || '-'}</td>
            <td class="${getStatusClass(n.streaming?.TikTok)}">${n.streaming?.TikTok || '-'}</td>
            <td class="${getStatusClass(n.streaming?.ChatGPT)}">${n.streaming?.ChatGPT || '-'}</td>
        </tr>
    `).join('');
}

function formatSpeed(mbPerSec) {
    if (!mbPerSec || mbPerSec <= 0) return '0.00 MB/s';
    if (mbPerSec >= 1000) return (mbPerSec / 1000).toFixed(2) + ' GB/s';
    return mbPerSec.toFixed(2) + ' MB/s';
}

function getSpeedClass(mbPerSec) {
    if (mbPerSec >= 10) return 'speed-fast';
    if (mbPerSec >= 2) return 'speed-medium';
    if (mbPerSec >= 0.5) return 'speed-slow';
    return 'speed-very-slow';
}

function getStatusClass(status) {
    if (status && status.includes('解锁')) return 'status-unlock';
    if (status === '未解锁') return 'status-block';
    return 'status-unknown';
}

// ========== 历史记录 ==========
async function loadHistory() {
    try {
        selectedResults.clear();
        const data = await api('/api/results');
        renderHistory(data.results);
    } catch (e) {}
}

function renderHistory(results) {
    const list = $('#history-list');
    if (results.length === 0) {
        list.innerHTML = '<p style="color:var(--text-dim)">暂无历史记录</p>';
        return;
    }
    
    const hasRunning = results.some(r => r.status === 'running');
    
    list.innerHTML = `
        <div class="history-toolbar">
            <label class="checkbox-label">
                <input type="checkbox" id="select-all" onchange="toggleSelectAll(this.checked)">
                <span>全选</span>
            </label>
            <button class="btn btn-small btn-danger" id="btn-batch-delete" onclick="batchDeleteResults()" style="display:none">
                🗑️ 批量删除 (<span id="selected-count">0</span>)
            </button>
            ${hasRunning ? '<button class="btn btn-small btn-warning" onclick="stopAllRunningTests()">⏹️ 停止所有测速</button>' : ''}
        </div>
        ${results.map(r => `
            <div class="list-item ${r.status === 'running' ? 'list-item-running' : ''}">
                <label class="checkbox-label history-checkbox">
                    <input type="checkbox" data-id="${r.id}" onchange="toggleResultSelect(${r.id}, this.checked)" ${r.status === 'running' ? 'disabled' : ''}>
                </label>
                <div class="list-item-info">
                    <h3>${escapeHtml(r.subscription_name || '未知订阅')}</h3>
                    <p>${r.tested_nodes}/${r.total_nodes} 节点 • 流量: ${(r.total_traffic_mb || 0).toFixed(2)} MB</p>
                    <p>${formatDate(r.created_at)} <span class="badge badge-${r.status === 'completed' ? 'success' : r.status === 'running' ? 'info' : 'warning'}">${translateStatus(r.status)}</span></p>
                </div>
                <div class="list-item-actions">
                    ${r.status === 'running' ? `<button class="btn btn-small btn-warning" onclick="stopRunningTest(${r.id})">⏹️ 停止</button>` : ''}
                    ${r.image_path ? `<button class="btn btn-small btn-primary" onclick="viewImage('${r.image_path}')">📸 图片</button>` : ''}
                    <button class="btn btn-small btn-secondary" onclick="viewHistoryDetail(${r.id})">📊 详情</button>
                    <button class="btn btn-small btn-danger" onclick="deleteResult(${r.id})">🗑️</button>
                </div>
            </div>
        `).join('')}
    `;
}

function translateStatus(status) {
    const map = {
        'completed': '已完成',
        'running': '运行中',
        'stopped': '已停止',
        'failed': '失败',
        'error': '错误'
    };
    return map[status] || status;
}

function toggleSelectAll(checked) {
    const checkboxes = $$('#history-list input[type="checkbox"][data-id]:not(:disabled)');
    checkboxes.forEach(cb => {
        cb.checked = checked;
        const id = parseInt(cb.dataset.id);
        if (checked) {
            selectedResults.add(id);
        } else {
            selectedResults.delete(id);
        }
    });
    updateBatchDeleteBtn();
}

function toggleResultSelect(id, checked) {
    if (checked) {
        selectedResults.add(id);
    } else {
        selectedResults.delete(id);
    }
    updateBatchDeleteBtn();
}

function updateBatchDeleteBtn() {
    const btn = $('#btn-batch-delete');
    const count = $('#selected-count');
    if (btn && count) {
        if (selectedResults.size > 0) {
            btn.style.display = 'inline-flex';
            count.textContent = selectedResults.size;
        } else {
            btn.style.display = 'none';
        }
    }
}

async function batchDeleteResults() {
    if (selectedResults.size === 0) return;
    if (!confirm(`确定删除选中的 ${selectedResults.size} 条记录？`)) return;
    
    try {
        for (const id of selectedResults) {
            await api(`/api/results/${id}`, { method: 'DELETE' });
        }
        selectedResults.clear();
        loadHistory();
    } catch (e) {
        alert('批量删除失败: ' + e.message);
    }
}

async function stopRunningTest(resultId) {
    if (!confirm('确定停止此测速任务？')) return;
    try {
        await api('/api/stop-test', { method: 'POST' });
        setTimeout(() => loadHistory(), 500);
    } catch (e) {
        alert('停止失败: ' + e.message);
    }
}

async function stopAllRunningTests() {
    if (!confirm('确定停止所有正在运行的测速？')) return;
    try {
        await api('/api/stop-test', { method: 'POST' });
        setTimeout(() => loadHistory(), 500);
    } catch (e) {
        alert('停止失败: ' + e.message);
    }
}

// ========== 历史详情弹窗 ==========
async function viewHistoryDetail(resultId) {
    try {
        const data = await api(`/api/results/${resultId}`);
        const result = data.result;
        const nodes = data.nodes;
        
        // 更新弹窗标题
        $('#detail-modal-title').textContent = `${result.subscription_name} - ${formatDate(result.created_at)}`;
        
        // 更新统计信息
        const speedNodes = nodes.filter(n => n.speed_mb_per_sec > 0);
        const avgSpeed = speedNodes.length > 0 
            ? speedNodes.reduce((sum, n) => sum + n.speed_mb_per_sec, 0) / speedNodes.length 
            : 0;
        const maxSpeed = Math.max(...nodes.map(n => n.max_speed_mb_per_sec || 0));
        
        $('#detail-stats').innerHTML = `
            <span>总节点: ${result.total_nodes}</span>
            <span>已测试: ${result.tested_nodes}</span>
            <span>有速度: ${speedNodes.length}</span>
            <span>平均速度: ${formatSpeed(avgSpeed)}</span>
            <span>最高速度: ${formatSpeed(maxSpeed)}</span>
            <span>总流量: ${(result.total_traffic_mb || 0).toFixed(2)} MB</span>
        `;
        
        // 填充表格
        $('#detail-body').innerHTML = nodes.map((n, i) => `
            <tr>
                <td>${i + 1}</td>
                <td title="${escapeHtml(n.name)}">${escapeHtml(n.name)}</td>
                <td>${n.type || ''}</td>
                <td class="${getSpeedClass(n.speed_mb_per_sec)}">${formatSpeed(n.speed_mb_per_sec)}</td>
                <td class="${getSpeedClass(n.upload_speed_mb_per_sec)}">${formatSpeed(n.upload_speed_mb_per_sec)}</td>
                <td class="${getSpeedClass(n.max_speed_mb_per_sec)}">${formatSpeed(n.max_speed_mb_per_sec)}</td>
                <td>${(n.traffic_mb || 0).toFixed(2)} MB</td>
                <td>${n.tls_rtt ? n.tls_rtt.toFixed(0) + 'ms' : '-'}</td>
                <td class="${getStatusClass(n.streaming?.Netflix)}">${n.streaming?.Netflix || '-'}</td>
                <td class="${getStatusClass(n.streaming?.YouTube)}">${n.streaming?.YouTube || '-'}</td>
                <td class="${getStatusClass(n.streaming?.ChatGPT)}">${n.streaming?.ChatGPT || '-'}</td>
            </tr>
        `).join('');
        
        // 显示弹窗
        $('#detail-modal').classList.remove('hidden');
    } catch (e) {
        alert('加载详情失败: ' + e.message);
    }
}

function closeDetailModal() {
    $('#detail-modal').classList.add('hidden');
}

async function deleteResult(resultId) {
    if (!confirm('确定删除此结果？')) return;
    
    try {
        await api(`/api/results/${resultId}`, { method: 'DELETE' });
        loadHistory();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function viewImage(imagePath) {
    $('#modal-image').src = '/' + imagePath;
    $('#image-modal').classList.remove('hidden');
}

function closeImageModal() {
    $('#image-modal').classList.add('hidden');
    $('#modal-image').src = '';
}

// ========== 定时任务 ==========
async function loadSchedules() {
    try {
        const data = await api('/api/schedules');
        renderSchedules(data.tasks);
    } catch (e) {}
}

function renderSchedules(tasks) {
    const list = $('#schedules-list');
    if (tasks.length === 0) {
        list.innerHTML = '<p style="color:var(--text-dim)">暂无定时任务</p>';
        return;
    }
    
    const typeNames = { daily: '每天', weekly: '每周', monthly: '每月' };
    const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    
    list.innerHTML = tasks.map(t => {
        const config = t.schedule_config;
        let timeDesc = typeNames[t.schedule_type] || t.schedule_type;
        if (t.schedule_type === 'weekly' && config.weekday !== undefined) {
            timeDesc = `每${weekdayNames[config.weekday]}`;
        }
        timeDesc += ` ${String(config.hour || 0).padStart(2, '0')}:${String(config.minute || 0).padStart(2, '0')}`;
        
        return `
            <div class="list-item">
                <div class="list-item-info">
                    <h3>${escapeHtml(t.name)} <span class="badge ${t.enabled ? 'badge-success' : 'badge-warning'}">${t.enabled ? '启用' : '禁用'}</span></h3>
                    <p>${timeDesc} • ${t.test_streaming ? '含流媒体检测' : '不含流媒体检测'}</p>
                    ${t.last_run_at ? `<p>上次运行: ${formatDate(t.last_run_at)}</p>` : ''}
                </div>
                <div class="list-item-actions">
                    <button class="btn btn-small btn-secondary" onclick="toggleSchedule(${t.id}, ${!t.enabled})">${t.enabled ? '⏸️ 禁用' : '▶️ 启用'}</button>
                    <button class="btn btn-small btn-danger" onclick="deleteSchedule(${t.id})">🗑️ 删除</button>
                </div>
            </div>
        `;
    }).join('');
}

async function toggleSchedule(taskId, enabled) {
    try {
        await api(`/api/schedules/${taskId}`, {
            method: 'PUT',
            body: JSON.stringify({ enabled }),
        });
        loadSchedules();
    } catch (e) {
        alert('操作失败: ' + e.message);
    }
}

async function deleteSchedule(taskId) {
    if (!confirm('确定删除此任务？')) return;
    
    try {
        await api(`/api/schedules/${taskId}`, { method: 'DELETE' });
        loadSchedules();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function saveSchedule() {
    const name = $('#schedule-name').value.trim();
    const subscriptionId = $('#schedule-subscription').value;
    const scheduleType = $('#schedule-type').value;
    const hour = parseInt($('#schedule-hour').value);
    const minute = parseInt($('#schedule-minute').value);
    const testStreaming = $('#schedule-streaming').checked;
    
    if (!name) {
        alert('请输入任务名称');
        return;
    }
    
    if (!subscriptionId) {
        alert('请选择订阅');
        return;
    }
    
    const config = { hour, minute };
    if (scheduleType === 'weekly') {
        config.weekday = parseInt($('#schedule-weekday').value);
    } else if (scheduleType === 'monthly') {
        config.day = parseInt($('#schedule-day').value);
    }
    
    try {
        await api('/api/schedules', {
            method: 'POST',
            body: JSON.stringify({
                name,
                subscription_id: parseInt(subscriptionId),
                schedule_type: scheduleType,
                schedule_config: config,
                test_streaming: testStreaming,
                theme: $('#image-theme').value,
            }),
        });
        
        closeScheduleModal();
        loadSchedules();
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ========== 设置 ==========
async function changeUsername() {
    const newUsername = $('#new-username').value.trim();
    if (!newUsername || newUsername.length < 3) {
        alert('用户名至少 3 位');
        return;
    }
    
    try {
        await api('/api/auth/change-username', {
            method: 'POST',
            body: JSON.stringify({ new_username: newUsername }),
        });
        currentUser = newUsername;
        $('#username-display').textContent = newUsername;
        $('#new-username').value = '';
        alert('用户名修改成功');
    } catch (e) {
        alert('修改失败: ' + e.message);
    }
}

async function changePassword() {
    const oldPassword = $('#old-password').value;
    const newPassword = $('#new-password').value;
    
    if (!oldPassword || !newPassword) {
        alert('请输入旧密码和新密码');
        return;
    }
    
    if (newPassword.length < 6) {
        alert('新密码至少 6 位');
        return;
    }
    
    try {
        await api('/api/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
        });
        $('#old-password').value = '';
        $('#new-password').value = '';
        alert('密码修改成功');
    } catch (e) {
        alert('修改失败: ' + e.message);
    }
}

// ========== 工具函数 ==========
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

// ========== 弹窗控制 ==========
function showSettingsModal() {
    $('#settings-modal').classList.remove('hidden');
}

function closeSettingsModal() {
    $('#settings-modal').classList.add('hidden');
}

function showScheduleModal() {
    // 初始化时间选择器
    initTimeSelects();
    $('#schedule-modal').classList.remove('hidden');
}

function closeScheduleModal() {
    $('#schedule-modal').classList.add('hidden');
}

function closeImageModal() {
    $('#image-modal').classList.add('hidden');
}

// ========== 初始化 ==========
function initTimeSelects() {
    const hourSelect = $('#schedule-hour');
    const minuteSelect = $('#schedule-minute');
    const daySelect = $('#schedule-day');
    
    if (hourSelect && hourSelect.options.length === 0) {
        for (let i = 0; i < 24; i++) {
            hourSelect.add(new Option(String(i).padStart(2, '0'), i));
        }
    }
    
    if (minuteSelect && minuteSelect.options.length === 0) {
        for (let i = 0; i < 60; i += 5) {
            minuteSelect.add(new Option(String(i).padStart(2, '0'), i));
        }
    }
    
    if (daySelect && daySelect.options.length === 0) {
        for (let i = 1; i <= 31; i++) {
            daySelect.add(new Option(i + '日', i));
        }
    }
}

function initScheduleTypeChange() {
    const typeSelect = $('#schedule-type');
    if (typeSelect) {
        typeSelect.addEventListener('change', function() {
            const weekdayGroup = $('#schedule-weekday-group');
            const dayGroup = $('#schedule-day-group');
            weekdayGroup.classList.toggle('hidden', this.value !== 'weekly');
            dayGroup.classList.toggle('hidden', this.value !== 'monthly');
        });
    }
}

// ========== 事件绑定 ==========
document.addEventListener('DOMContentLoaded', function() {
    // 登录表单
    const loginForm = $('#login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const username = $('#login-username').value;
            const password = $('#login-password').value;
            try {
                await login(username, password);
            } catch (e) {
                $('#login-error').textContent = e.message;
                $('#login-error').classList.remove('hidden');
            }
        });
    }
    
    // 主题切换
    const themeToggle = $('#theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // 用户菜单
    const userBtn = $('#user-btn');
    if (userBtn) {
        userBtn.addEventListener('click', function() {
            $('#user-dropdown').classList.toggle('hidden');
        });
    }
    
    // 设置按钮
    const settingsBtn = $('#settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', function(e) {
            e.preventDefault();
            showSettingsModal();
            $('#user-dropdown').classList.add('hidden');
        });
    }
    
    // 退出按钮
    const logoutBtn = $('#logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    }
    
    // 标签页切换
    $$('.tab').forEach(tab => {
        tab.addEventListener('click', function() {
            $$('.tab').forEach(t => t.classList.remove('active'));
            $$('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            $(`#tab-${this.dataset.tab}`).classList.add('active');
        });
    });
    
    // 添加订阅
    const btnAddSub = $('#btn-add-sub');
    if (btnAddSub) {
        btnAddSub.addEventListener('click', addSubscription);
    }
    
    // 上传 YAML
    let uploadedYamlTempFile = null;
    const btnUploadYaml = $('#btn-upload-yaml');
    const yamlFileInput = $('#yaml-file');
    if (btnUploadYaml && yamlFileInput) {
        btnUploadYaml.addEventListener('click', () => yamlFileInput.click());
        yamlFileInput.addEventListener('change', async function() {
            if (!this.files[0]) return;
            const file = this.files[0];
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                $('#upload-status').textContent = '⏳ 上传中...';
                const data = await apiForm('/api/upload-yaml', formData);
                uploadedYamlTempFile = data.temp_file;
                $('#upload-status').textContent = `✅ ${data.message}`;
                $('#upload-preview').classList.remove('hidden');
                $('#upload-info').textContent = `已解析 ${data.node_count} 个节点`;
                $('#upload-nodes-preview').innerHTML = data.nodes.map(n => 
                    `<span class="node-tag">${escapeHtml(n.name)} (${n.type})</span>`
                ).join(' ');
            } catch (e) {
                $('#upload-status').textContent = `❌ ${e.message}`;
                uploadedYamlTempFile = null;
            }
        });
    }
    
    // 测速按钮
    const btnStart = $('#btn-start');
    if (btnStart) {
        btnStart.addEventListener('click', startTest);
    }
    
    const btnStop = $('#btn-stop');
    if (btnStop) {
        btnStop.addEventListener('click', stopTest);
    }
    
    // 日志等级
    const logLevel = $('#log-level');
    if (logLevel) {
        logLevel.addEventListener('change', syncLogLevel);
    }
    
    // 设置弹窗关闭
    const closeSettings = $('#close-settings');
    if (closeSettings) {
        closeSettings.addEventListener('click', closeSettingsModal);
    }
    
    const btnSaveUsername = $('#btn-change-username');
    if (btnSaveUsername) {
        btnSaveUsername.addEventListener('click', changeUsername);
    }
    
    const btnSavePassword = $('#btn-change-password');
    if (btnSavePassword) {
        btnSavePassword.addEventListener('click', changePassword);
    }
    
    // 定时任务
    const btnAddSchedule = $('#btn-add-schedule');
    if (btnAddSchedule) {
        btnAddSchedule.addEventListener('click', showScheduleModal);
    }
    
    const closeSchedule = $('#close-schedule');
    if (closeSchedule) {
        closeSchedule.addEventListener('click', closeScheduleModal);
    }
    
    const btnSaveSchedule = $('#btn-save-schedule');
    if (btnSaveSchedule) {
        btnSaveSchedule.addEventListener('click', saveSchedule);
    }
    
    // 图片弹窗
    const closeImage = $('#close-image');
    if (closeImage) {
        closeImage.addEventListener('click', closeImageModal);
    }
    
    // 详情弹窗
    const closeDetail = $('#close-detail');
    if (closeDetail) {
        closeDetail.addEventListener('click', closeDetailModal);
    }
    
    // 初始化
    initScheduleTypeChange();
    checkAuth();
    
    // 点击弹窗外部关闭
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal')) {
            e.target.classList.add('hidden');
        }
    });
    
    // 应用默认主题
    applyTheme(getSavedTheme());
});
