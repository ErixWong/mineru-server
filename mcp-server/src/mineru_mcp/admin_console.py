"""
Admin Console HTML Pages

Simple HTML admin console for internal use.
Serves as the UI layer for admin management.

DEPRECATED: The main admin UI has been migrated to the Vue SPA under
`mcp-server/admin-ui/` and is now served from `/admin/*` via built static assets.
This module is retained only as a temporary reference during migration cleanup.
"""

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from mineru_mcp.admin_auth import get_default_admin_username, get_default_admin_password


# Initialize router without prefix (will be mounted under /admin)
router = APIRouter(tags=["admin-console"])


# ========== Page Templates ==========

BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - MinerU Admin Console</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        
        /* Header */
        .header {{ background: #fff; padding: 15px 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .header h1 {{ font-size: 20px; color: #333; }}
        .header .user-info {{ float: right; color: #666; font-size: 14px; }}
        
        /* Navigation */
        .nav {{ background: #fff; padding: 0; margin-bottom: 20px; border-radius: 4px; overflow: hidden; }}
        .nav a {{ display: inline-block; padding: 12px 20px; color: #333; text-decoration: none; border-bottom: 3px solid transparent; }}
        .nav a:hover {{ background: #f0f0f0; }}
        .nav a.active {{ border-bottom-color: #1976d2; color: #1976d2; }}
        
        /* Cards */
        .card {{ background: #fff; border-radius: 4px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card h2 {{ font-size: 16px; margin-bottom: 15px; color: #333; }}
        
        /* Tables */
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f9f9f9; font-weight: 500; color: #666; font-size: 14px; }}
        td {{ font-size: 14px; }}
        
        /* Buttons */
        .btn {{ display: inline-block; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        .btn-primary {{ background: #1976d2; color: #fff; }}
        .btn-primary:hover {{ background: #1565c0; }}
        .btn-danger {{ background: #dc3545; color: #fff; }}
        .btn-danger:hover {{ background: #c82333; }}
        .btn-success {{ background: #28a745; color: #fff; }}
        .btn-success:hover {{ background: #218838; }}
        .btn-sm {{ padding: 4px 8px; font-size: 12px; }}
        
        /* Forms */
        .form-group {{ margin-bottom: 15px; }}
        .form-group label {{ display: block; margin-bottom: 5px; font-size: 14px; color: #666; }}
        .form-group input, .form-group select {{ width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }}
        
        /* Alerts */
        .alert {{ padding: 12px 15px; border-radius: 4px; margin-bottom: 15px; }}
        .alert-error {{ background: #ffebee; color: #c62828; }}
        .alert-success {{ background: #e8f5e9; color: #2e7d32; }}
        .alert-warning {{ background: #fff3e0; color: #ef6c00; }}
        
        /* Status badges */
        .status {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
        .status-pending {{ background: #fff3e0; color: #ef6c00; }}
        .status-processing {{ background: #e3f2fd; color: #1565c0; }}
        .status-completed {{ background: #e8f5e9; color: #2e7d32; }}
        .status-failed {{ background: #ffebee; color: #c62828; }}
        .status-cancelled {{ background: #f5f5f5; color: #666; }}
        
        .disabled {{ color: #999; }}
        
        /* Loading */
        .loading {{ text-align: center; padding: 40px; color: #999; }}
        
        /* Actions */
        .actions {{ display: flex; gap: 8px; }}
        
        /* Modal */
        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }}
        .modal.show {{ display: flex; align-items: center; justify-content: center; }}
        .modal-content {{ background: #fff; border-radius: 4px; padding: 20px; max-width: 500px; width: 90%; }}
        .modal-header {{ font-size: 18px; margin-bottom: 15px; }}
        .modal-footer {{ margin-top: 20px; text-align: right; }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""


def render_page(title: str, content: str) -> str:
    """Render a full page."""
    safe_content = content.replace("{", "{{").replace("}", "}}")
    return BASE_TEMPLATE.format(title=title, content=safe_content)


def inject_common_js(content: str) -> str:
    """Inject shared JS helpers before rendering the page template."""
    return content.replace("{COMMON_JS_HELPERS}", COMMON_JS_HELPERS)


COMMON_JS_HELPERS = """
        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>\"']/g, function(ch) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[ch];
            });
        }

        function escapeAttr(value) {
            return escapeHtml(value);
        }

        function jsString(value) {
            return JSON.stringify(String(value ?? ''));
        }

        function getCookie(name) {
            const prefix = name + '=';
            return document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix))?.slice(prefix.length) || '';
        }

        function csrfHeaders(extraHeaders) {
            const headers = Object.assign({}, extraHeaders || {});
            const csrfToken = getCookie('admin_csrf');
            if (csrfToken) {
                headers['X-CSRF-Token'] = csrfToken;
            }
            return headers;
        }
"""


# Console base path - must match the actual mounted path
CONSOLE_BASE = "/admin"


def get_nav(active: str) -> str:
    """Get navigation HTML."""
    return f'''
    <div class="nav">
        <a href="{CONSOLE_BASE}/" class="{('active' if active == 'dashboard' else '')}">仪表盘</a>
        <a href="{CONSOLE_BASE}/callers" class="{('active' if active == 'callers' else '')}">调用方</a>
        <a href="{CONSOLE_BASE}/tasks" class="{('active' if active == 'tasks' else '')}">任务与交付</a>
        <a href="{CONSOLE_BASE}/settings" class="{('active' if active == 'settings' else '')}">系统设置</a>
    </div>
    '''


# ========== Page Routes ==========

@router.get("/")
async def admin_index(request: Request):
    """Admin dashboard page."""
    # Check if logged in
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Verify session
    from mineru_mcp.admin_auth import get_current_admin
    admin = get_current_admin(session_token)
    if not admin:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Check if password change is required
    if admin.must_change_password:
        return Response(headers={"Location": f"{CONSOLE_BASE}/change-password"}, status_code=302)
    
    content = f'''
    <div class="header">
        <h1>MinerU 管理控制台</h1>
        <span class="user-info">当前用户: {admin.username} | <a href="{CONSOLE_BASE}/logout">退出</a></span>
    </div>
    <div class="container">
        {get_nav('dashboard')}
        <div class="card">
            <h2>欢迎使用 MinerU 管理控制台</h2>
            <p>请从左侧导航选择管理功能。</p>
            <ul style="margin-top: 15px; line-height: 2;">
                <li><strong>调用方</strong> - 管理 API 调用方及其密钥</li>
                <li><strong>任务与交付</strong> - 查看任务状态和结果</li>
                <li><strong>系统设置</strong> - 修改管理员密码、查看全局配置</li>
            </ul>
        </div>
    </div>
    '''
    return HTMLResponse(render_page("仪表盘", content))


@router.get("/login")
async def admin_login_page(request: Request):
    """Admin login page."""
    content = '''
    <div class="container" style="max-width: 400px; margin-top: 100px;">
        <div class="card">
            <h2>MinerU 管理控制台</h2>
            <p style="color: #666; margin-bottom: 20px;">请登录以继续</p>
            <div id="alert"></div>
            <form id="loginForm">
                <div class="form-group">
                    <label>用户名</label>
                    <input type="text" name="username" required value="admin">
                </div>
                <div class="form-group">
                    <label>密码</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">登录</button>
            </form>
        </div>
    </div>
    <script>
        {COMMON_JS_HELPERS}
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = new FormData(e.target);
            try {
                const resp = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(Object.fromEntries(form))
                });
                const data = await resp.json();
                if (data.success) {
                    if (data.must_change_password) {
                        window.location.href = '/admin/change-password';
                    } else {
                        window.location.href = '/admin/';
                    }
                } else {
                    document.getElementById('alert').innerHTML = '<div class="alert alert-error">' + escapeHtml(data.message) + '</div>';
                }
            } catch (err) {
                document.getElementById('alert').innerHTML = '<div class="alert alert-error">登录失败</div>';
            }
        });
    </script>
    '''
    return HTMLResponse(render_page("登录", inject_common_js(content)))


@router.get("/change-password")
async def change_password_page(request: Request):
    """Change password page (required on first login)."""
    content = '''
    <div class="container" style="max-width: 400px; margin-top: 100px;">
        <div class="card">
            <h2>首次登录必须修改密码</h2>
            <div id="alert"></div>
            <form id="pwForm">
                <div class="form-group">
                    <label>当前密码</label>
                    <input type="password" name="old_password" required>
                </div>
                <div class="form-group">
                    <label>新密码</label>
                    <input type="password" name="new_password" required minlength="6">
                </div>
                <div class="form-group">
                    <label>确认新密码</label>
                    <input type="password" name="confirm_password" required minlength="6">
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">修改密码</button>
            </form>
        </div>
    </div>
    <script>
        {COMMON_JS_HELPERS}
        document.getElementById('pwForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = new FormData(e.target);
            if (form.get('new_password') !== form.get('confirm_password')) {
                document.getElementById('alert').innerHTML = '<div class="alert alert-error">两次输入的密码不一致</div>';
                return;
            }
            try {
                const resp = await fetch('/api/admin/change-password', {
                    method: 'POST',
                    headers: csrfHeaders({'Content-Type': 'application/json'}),
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        old_password: form.get('old_password'),
                        new_password: form.get('new_password')
                    })
                });
                const data = await resp.json();
                if (data.success) {
                    alert('密码修改成功，请重新登录');
                    window.location.href = '/admin/logout';
                } else {
                    document.getElementById('alert').innerHTML = '<div class="alert alert-error">' + escapeHtml(data.message) + '</div>';
                }
            } catch (err) {
                document.getElementById('alert').innerHTML = '<div class="alert alert-error">修改密码失败</div>';
            }
        });
    </script>
    '''
    return HTMLResponse(render_page("修改密码", inject_common_js(content)))


@router.get("/logout")
async def admin_logout_page(request: Request):
    """Admin logout page - calls API to invalidate session server-side."""
    content = '''
    <script>
        async function logout() {
            try {
                await fetch('/api/admin/logout', { method: 'POST', headers: csrfHeaders(), credentials: 'same-origin' });
            } catch (e) {
                // Ignore errors
            }
            document.cookie = 'admin_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            document.cookie = 'admin_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            window.location.href = '/admin/login';
        }
        logout();
    </script>
    '''
    return HTMLResponse(content)


@router.get("/callers")
async def admin_callers_page(request: Request):
    """Caller management page."""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    from mineru_mcp.admin_auth import get_current_admin
    admin = get_current_admin(session_token)
    if not admin:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Check if password change is required
    if admin.must_change_password:
        return Response(headers={"Location": f"{CONSOLE_BASE}/change-password"}, status_code=302)
    
    content = f'''
    <div class="header">
        <h1>MinerU 管理控制台</h1>
        <span class="user-info">当前用户: {admin.username} | <a href="{CONSOLE_BASE}/logout">退出</a></span>
    </div>
    <div class="container">
        {get_nav('callers')}
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2>调用方管理</h2>
                <button class="btn btn-primary" onclick="showCreateModal()">新建调用方</button>
            </div>
            <div id="callersList" class="loading">加载中...</div>
        </div>
    </div>
    
    <!-- Create Modal -->
    <div id="createModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">新建调用方</div>
            <div id="createAlert"></div>
            <form id="createForm">
                <div class="form-group">
                    <label>名称</label>
                    <input type="text" name="name" required placeholder="例如: MyApp">
                </div>
                <div class="form-group">
                    <label>有效期 (可选)</label>
                    <input type="datetime-local" name="expires_at">
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn" onclick="closeModal()">取消</button>
                    <button type="submit" class="btn btn-primary">创建</button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        {COMMON_JS_HELPERS}
        console.log('Caller page loaded, calling loadCallers...');
        
        function fmtTime(str) {{
            if (!str) return '-';
            if (str.indexOf(' ') > -1) return new Date(str.replace(' ', 'T') + 'Z').toLocaleString();
            return new Date(str).toLocaleString();
        }}
        
        async function loadCallers() {{
            console.log('loadCallers started');
            try {{
                const resp = await fetch('/api/admin/callers?include_disabled=true', {{ credentials: 'same-origin' }});
                console.log('Response status:', resp.status);
                if (!resp.ok) {{
                    const err = await resp.json();
                    console.error('API error:', err);
                    document.getElementById('callersList').innerHTML = '<div class="alert alert-error">加载失败: ' + escapeHtml(err.message || resp.statusText) + '</div>';
                    return;
                }}
                const callers = await resp.json();
                if (callers.length === 0) {{
                    document.getElementById('callersList').innerHTML = '<p style="color: #999;">暂无调用方</p>';
                    return;
                }}
                let html = '<table><thead><tr><th>名称</th><th>API Key</th><th>有效期</th><th>状态</th><th>最近使用</th><th>近7天统计</th><th>操作</th></tr></thead><tbody>';
                for (const c of callers) {{
                    const status = c.disabled ? '<span class="status status-failed">已禁用</span>' : '<span class="status status-completed">启用</span>';
                    const expires = fmtTime(c.expires_at) || '永久';
                    const lastUsed = fmtTime(c.last_used_at) || '从未';
                    const stats = c.stats_last_7_days;
                    const safeName = escapeHtml(c.name);
                    const safeApiKey = escapeHtml(c.api_key || c.api_key_prefix + '****' + c.api_key_suffix);
                    const safeApiKeyAttr = escapeAttr(c.api_key || '');
                    const safeCallerId = escapeAttr(c.caller_id);
                    html += '<tr class="' + (c.disabled ? 'disabled' : '') + '">' +
                        '<td>' + safeName + '</td>' +
                        '<td><code style="font-size:12px;max-width:280px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle;" title="' + safeApiKeyAttr + '">' + safeApiKey + '</code>' +
                        ' <button class="btn btn-sm copy-key" data-api-key="' + safeApiKeyAttr + '" style="padding:2px 6px;font-size:11px;">复制</button></td>' +
                        '<td>' + expires + '</td>' +
                        '<td>' + status + '</td>' +
                        '<td>' + lastUsed + '</td>' +
                        '<td>总计: ' + stats.total + ' / 失败: ' + stats.failed + '</td>' +
                        '<td class="actions">' +
                        (c.disabled ? 
                            '<button class="btn btn-success btn-sm toggle-caller" data-caller-id="' + safeCallerId + '" data-disabled="false">启用</button>' :
                            '<button class="btn btn-danger btn-sm toggle-caller" data-caller-id="' + safeCallerId + '" data-disabled="true">禁用</button>') +
                        '<button class="btn btn-primary btn-sm reset-key" data-caller-id="' + safeCallerId + '">重置</button>' +
                        '<button class="btn btn-danger btn-sm delete-caller" data-caller-id="' + safeCallerId + '">删除</button>' +
                        '</td></tr>';
                }}
                html += '</tbody></table>';
                document.getElementById('callersList').innerHTML = html;
            }} catch (err) {{
                document.getElementById('callersList').innerHTML = '<div class="alert alert-error">加载失败</div>';
            }}
        }}
        
        function showCreateModal() {{
            document.getElementById('createModal').classList.add('show');
        }}
        
        function closeModal() {{
            document.getElementById('createModal').classList.remove('show');
            document.getElementById('createAlert').innerHTML = '';
        }}

        function showApiKey(key) {{
            var overlay = document.createElement('div');
            overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:9999;';
            overlay.onclick = function(e) {{ if (e.target === overlay) overlay.remove(); }};
            var card = document.createElement('div');
            card.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;padding:24px;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.2);z-index:10000;min-width:450px;';
            card.innerHTML = '<h4 style="margin:0 0 12px 0;">API Key（只显示一次，请立即复制保存）</h4>' +
                '<input readonly id="apiKeyInput" value="' + key.replace(/"/g, '&quot;') + '" style="width:100%;padding:8px;font-family:monospace;border:1px solid #ddd;border-radius:4px;margin-bottom:12px;box-sizing:border-box;" onclick="this.select()">' +
                '<button id="copyKeyBtn" class="btn btn-primary" style="margin-right:8px;">复制</button>' +
                '<button class="btn" onclick="this.parentElement.parentElement.remove()">关闭</button>';
            overlay.appendChild(card);
            document.body.appendChild(overlay);
            document.getElementById('copyKeyBtn').onclick = function() {{
                document.getElementById('apiKeyInput').select();
                navigator.clipboard.writeText(key);
                this.textContent = '已复制';
            }};
        }}

        function copyKey(btn, key) {{
            navigator.clipboard.writeText(key);
            btn.textContent = '已复制';
            setTimeout(function() {{ btn.textContent = '复制'; }}, 1500);
        }}

        document.addEventListener('click', function(e) {{
            if (e.target.classList.contains('copy-key')) {{
                copyKey(e.target, e.target.getAttribute('data-api-key') || '');
            }}
            if (e.target.classList.contains('toggle-caller')) {{
                toggleCaller(e.target.getAttribute('data-caller-id'), e.target.getAttribute('data-disabled') === 'true');
            }}
            if (e.target.classList.contains('reset-key')) {{
                resetKey(e.target.getAttribute('data-caller-id'));
            }}
            if (e.target.classList.contains('delete-caller')) {{
                deleteCaller(e.target.getAttribute('data-caller-id'));
            }}
        }});
        
        document.getElementById('createForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const form = new FormData(e.target);
            const data = {{ name: form.get('name') }};
            if (form.get('expires_at')) {{
                data.expires_at = new Date(form.get('expires_at')).toISOString();
            }}
            try {{
                const resp = await fetch('/api/admin/callers', {{
                    method: 'POST',
                    headers: csrfHeaders({{'Content-Type': 'application/json'}}),
                    body: JSON.stringify(data),
                    credentials: 'same-origin'
                }});
                const result = await resp.json();
                if (result.api_key) {{
                    closeModal();
                    loadCallers();
                    showApiKey(result.api_key);
                }} else {{
                    document.getElementById('createAlert').innerHTML = '<div class="alert alert-error">创建失败</div>';
                }}
            }} catch (err) {{
                document.getElementById('createAlert').innerHTML = '<div class="alert alert-error">创建失败</div>';
            }}
        }});
        
        async function toggleCaller(id, disabled) {{
            try {{
                await fetch('/api/admin/callers/' + id, {{
                    method: 'PATCH',
                    headers: csrfHeaders({{'Content-Type': 'application/json'}}),
                    body: JSON.stringify({{ disabled: disabled }}),
                    credentials: 'same-origin'
                }});
                loadCallers();
            }} catch (err) {{
                alert('操作失败');
            }}
        }}
        
        async function resetKey(id) {{
            if (!confirm('确定要重置 API Key 吗？')) return;
            try {{
                const resp = await fetch('/api/admin/callers/' + id + '/reset-key', {{
                    method: 'POST',
                    headers: csrfHeaders(),
                    credentials: 'same-origin'
                }});
                const result = await resp.json();
                if (result.api_key) {{
                    loadCallers();
                    showApiKey(result.api_key);
                }} else {{
                    alert('重置失败');
                }}
            }} catch (err) {{
                alert('重置失败');
            }}
        }}

        async function deleteCaller(id) {{
            if (!confirm('确定要删除此调用方吗？此操作不可撤销。')) return;
            try {{
                const resp = await fetch('/api/admin/callers/' + id, {{
                    method: 'DELETE',
                    headers: csrfHeaders(),
                    credentials: 'same-origin'
                }});
                if (resp.ok) {{
                    loadCallers();
                }} else {{
                    alert('删除失败');
                }}
            }} catch (err) {{
                alert('删除失败');
            }}
        }}
        
        loadCallers();
    </script>
    '''
    return HTMLResponse(render_page("调用方管理", inject_common_js(content)))


@router.get("/tasks")
async def admin_tasks_page(request: Request):
    """Task list page."""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    from mineru_mcp.admin_auth import get_current_admin
    admin = get_current_admin(session_token)
    if not admin:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Check if password change is required
    if admin.must_change_password:
        return Response(headers={"Location": f"{CONSOLE_BASE}/change-password"}, status_code=302)
    
    content = f'''
    <div class="header">
        <h1>MinerU 管理控制台</h1>
        <span class="user-info">当前用户: {admin.username} | <a href="{CONSOLE_BASE}/logout">退出</a></span>
    </div>
    <div class="container">
        {get_nav('tasks')}
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2>任务列表</h2>
                <button class="btn btn-primary" onclick="showUploadModal()">新建任务</button>
            </div>
            <!-- Upload Modal -->
            <div id="uploadModal" class="modal">
                <div class="modal-content">
                    <div class="modal-header">新建任务</div>
                    <div id="uploadAlert"></div>
                    <form id="uploadForm">
                        <div class="form-group">
                            <label>选择文件 (PDF)</label>
                            <input type="file" name="file" accept=".pdf" required>
                        </div>
                        <div class="form-group">
                            <label>后端</label>
                            <select name="backend">
                                <option value="">默认</option>
                                <option value="pipeline">pipeline</option>
                                <option value="vlm-auto-engine">vlm-auto-engine</option>
                                <option value="vlm-http-client">vlm-http-client</option>
                                <option value="hybrid-auto-engine">hybrid-auto-engine</option>
                                <option value="hybrid-http-client">hybrid-http-client</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>语言</label>
                            <select name="lang">
                                <option value="ch">中文</option>
                                <option value="en">英文</option>
                                <option value="ja">日文</option>
                                <option value="ko">韩文</option>
                                <option value="fr">法文</option>
                                <option value="de">德文</option>
                            </select>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn" onclick="closeUploadModal()">取消</button>
                            <button type="submit" class="btn btn-primary">提交</button>
                        </div>
                    </form>
                </div>
            </div>
            <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
                <input type="text" id="filterCaller" placeholder="调用方ID" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <input type="text" id="filterKey" placeholder="API Key" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <select id="filterStatus" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                    <option value="">全部状态</option>
                    <option value="pending">排队中</option>
                    <option value="processing">处理中</option>
                    <option value="completed">已完成</option>
                    <option value="failed">失败</option>
                    <option value="cancelled">已取消</option>
                </select>
                <input type="date" id="filterStartDate" placeholder="开始日期" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <input type="date" id="filterEndDate" placeholder="结束日期" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <input type="text" id="filterTaskId" placeholder="Task ID" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <button class="btn btn-primary" onclick="loadTasks()">筛选</button>
            </div>
            <div id="tasksList" class="loading">加载中...</div>
        </div>
    </div>
    
    <script>
        {COMMON_JS_HELPERS}
        const CONSOLE_BASE = '/admin';
        
        function fmtTime(str) {{
            if (!str) return '-';
            if (str.indexOf(' ') > -1) return new Date(str.replace(' ', 'T') + 'Z').toLocaleString();
            return new Date(str).toLocaleString();
        }}
        
        // Restore filter values from URL on page load
        function restoreFilters() {{
            const params = new URLSearchParams(window.location.search);
            if (params.has('caller_id')) document.getElementById('filterCaller').value = params.get('caller_id');
            if (params.has('key')) document.getElementById('filterKey').value = params.get('key');
            if (params.has('status')) document.getElementById('filterStatus').value = params.get('status');
            if (params.has('start_date')) document.getElementById('filterStartDate').value = params.get('start_date');
            if (params.has('end_date')) document.getElementById('filterEndDate').value = params.get('end_date');
            if (params.has('task_id')) document.getElementById('filterTaskId').value = params.get('task_id');
        }}
        
        // Copy task_id to clipboard
        function copyTaskId(taskId) {{
            navigator.clipboard.writeText(taskId).then(function() {{
                alert('Task ID 已复制: ' + taskId);
            }}, function() {{
                alert('复制失败，请手动复制');
            }});
        }}
        
        async function loadTasks() {{
            const callerId = document.getElementById('filterCaller').value;
            const key = document.getElementById('filterKey').value;
            const status = document.getElementById('filterStatus').value;
            const startDate = document.getElementById('filterStartDate').value;
            const endDate = document.getElementById('filterEndDate').value;
            const taskId = document.getElementById('filterTaskId').value;
            
            let url = '/api/admin/tasks?limit=50';
            if (callerId) url += '&caller_id=' + encodeURIComponent(callerId);
            // Note: key is sent as-is; backend will hash it before using
            // This keeps API backward compatible while protecting the key from appearing in most logs
            if (key) url += '&key=' + encodeURIComponent(key);
            if (status) url += '&status=' + encodeURIComponent(status);
            if (startDate) url += '&start_date=' + encodeURIComponent(startDate);
            if (endDate) url += '&end_date=' + encodeURIComponent(endDate);
            if (taskId) url += '&task_id=' + encodeURIComponent(taskId);
            
            // Update URL without reload to preserve filter state
            const newUrl = url.replace('/api/admin/tasks?', '?');
            history.replaceState(Object(), '', window.location.pathname + newUrl);
            
            try {{
                const resp = await fetch(url, {{ credentials: 'same-origin' }});
                const data = await resp.json();
                const tasks = data.tasks;
                if (tasks.length === 0) {{
                    document.getElementById('tasksList').innerHTML = '<p style="color: #999;">暂无任务</p>';
                    return;
                }}
                let html = '<table><thead><tr><th>Task ID</th><th>状态</th><th>文件名</th><th>调用方</th><th>处理摘要</th><th>创建时间</th><th>完成时间</th><th>操作</th></tr></thead><tbody>';
                for (const t of tasks) {{
                    const statusClass = 'status-' + t.status;
                    const statusText = {{pending: '排队中', processing: '处理中', completed: '已完成', failed: '失败', cancelled: '已取消'}}[t.status];
                    const created = fmtTime(t.created_at);
                    const completed = fmtTime(t.completed_at);
                    
                    // Build summary: result_summary > message > error
                    // For failed tasks, show error in red
                    let summary = '';
                    let summaryStyle = '';
                    if (t.result_summary) {{
                        summary = t.result_summary.length > 50 ? t.result_summary.substring(0, 50) + '...' : t.result_summary;
                    }} else if (t.status === 'failed' && t.error) {{
                        summary = t.error.length > 50 ? t.error.substring(0, 50) + '...' : t.error;
                        summaryStyle = 'color: #c62828; font-weight: 500;';
                    }} else if (t.message) {{
                        summary = t.message.length > 50 ? t.message.substring(0, 50) + '...' : t.message;
                    }}
                    
                    const safeTaskId = escapeAttr(t.task_id);
                    const safeInputFilename = escapeHtml(t.input_filename);
                    const safeCallerName = escapeHtml(t.caller_name || '-');
                    const titleValue = t.result_summary || t.message || t.error || '';
                    const safeTitle = escapeAttr(titleValue);
                    const safeSummary = escapeHtml(summary);
                    // Use data attribute to avoid inline JS escaping issues
                    html += '<tr>' +
                        '<td style="font-family: monospace; font-size: 12px;" title="' + safeTaskId + '">' + escapeHtml(t.task_id.substring(0, 12)) + '... <a href="#" data-task-id="' + safeTaskId + '" class="copy-task-id" style="color: #1976d2; text-decoration: none; font-size: 10px;">复制</a></td>' +
                        '<td><span class="status ' + statusClass + '">' + statusText + '</span></td>' +
                        '<td>' + safeInputFilename + '</td>' +
                        '<td>' + safeCallerName + '</td>' +
                        '<td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' + summaryStyle + '" title="' + safeTitle + '">' + safeSummary + '</td>' +
                        '<td>' + created + '</td>' +
                        '<td>' + completed + '</td>' +
                        '<td><a href="' + CONSOLE_BASE + '/tasks/' + encodeURIComponent(t.task_id) + '" class="btn btn-primary btn-sm">详情</a> <button class="btn btn-danger btn-sm" data-delete-task="' + safeTaskId + '">删除</button></td></tr>';
                }}
                html += '</tbody></table>';
                document.getElementById('tasksList').innerHTML = html;
            }} catch (err) {{
                document.getElementById('tasksList').innerHTML = '<div class="alert alert-error">加载失败</div>';
            }}
        }}
        
        // Add event listener for copy task id links (using event delegation)
        document.addEventListener('click', function(e) {{
            if (e.target.classList.contains('copy-task-id')) {{
                e.preventDefault();
                const taskId = e.target.getAttribute('data-task-id');
                copyTaskId(taskId);
            }}
            if (e.target.hasAttribute('data-delete-task')) {{
                const taskId = e.target.getAttribute('data-delete-task');
                deleteTask(taskId);
            }}
        }});
        
        async function deleteTask(id) {{
            if (!confirm('确定要删除此任务吗？')) return;
            try {{
                const resp = await fetch('/api/admin/tasks/' + id, {{
                    method: 'DELETE',
                    headers: csrfHeaders(),
                    credentials: 'same-origin'
                }});
                if (resp.ok) {{
                    loadTasks();
                }} else {{
                    alert('删除失败');
                }}
            }} catch (err) {{
                alert('删除失败');
            }}
        }}
        
        // Restore filters first, then load tasks with restored filter values
        restoreFilters();
        loadTasks();
        
        function showUploadModal() {{
            document.getElementById('uploadModal').classList.add('show');
        }}
        
        function closeUploadModal() {{
            document.getElementById('uploadModal').classList.remove('show');
            document.getElementById('uploadAlert').innerHTML = '';
            document.getElementById('uploadForm').reset();
        }}
        
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const btn = e.target.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.textContent = '提交中...';
            
            const formData = new FormData(e.target);
            try {{
                const resp = await fetch('/api/admin/tasks', {{
                    method: 'POST',
                    headers: csrfHeaders(),
                    body: formData,
                    credentials: 'same-origin'
                }});
                const result = await resp.json();
                if (result.status === 'ok') {{
                    closeUploadModal();
                    loadTasks();
                }} else {{
                    document.getElementById('uploadAlert').innerHTML = '<div class="alert alert-error">创建失败</div>';
                }}
            }} catch (err) {{
                    document.getElementById('uploadAlert').innerHTML = '<div class="alert alert-error">创建失败: ' + escapeHtml(err.message) + '</div>';
            }} finally {{
                btn.disabled = false;
                btn.textContent = '提交';
            }}
        }});
    </script>
    '''
    return HTMLResponse(render_page("任务列表", inject_common_js(content)))


@router.get("/tasks/{task_id}")
async def admin_task_detail_page(request: Request, task_id: str):
    """Task detail page."""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    from mineru_mcp.admin_auth import get_current_admin
    admin = get_current_admin(session_token)
    if not admin:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Check if password change is required
    if admin.must_change_password:
        return Response(headers={"Location": f"{CONSOLE_BASE}/change-password"}, status_code=302)
    
    content = f'''
    <div class="header">
        <h1>MinerU 管理控制台</h1>
        <span class="user-info">当前用户: {admin.username} | <a href="{CONSOLE_BASE}/logout">退出</a></span>
    </div>
    <div class="container" style="max-width:100%;">
        {get_nav('tasks')}
        <div class="card" style="margin-bottom: 12px;">
            <a href="{CONSOLE_BASE}/tasks" style="color: #1976d2; text-decoration: none;">&larr; 返回任务列表</a>
        </div>
        <div id="taskDetail" class="loading" style="min-height: 200px;">加载中...</div>
    </div>
    
    <script>
        {COMMON_JS_HELPERS}
        function fmtTime(str) {{
            if (!str) return '-';
            if (str.indexOf(' ') > -1) return new Date(str.replace(' ', 'T') + 'Z').toLocaleString();
            return new Date(str).toLocaleString();
        }}
        
        async function loadTaskDetail() {{
            try {{
                const resp = await fetch('/api/admin/tasks/{task_id}', {{ credentials: 'same-origin' }});
                if (!resp.ok) {{
                    document.getElementById('taskDetail').innerHTML = '<div class="card"><p style="color:#999;">任务不存在</p></div>';
                    return;
                }}
                const t = await resp.json();
                const statusLabel = {{pending:'排队中',processing:'处理中',completed:'已完成',failed:'失败',cancelled:'已取消'}}[t.status] || t.status;
                const statusColor = t.status === 'completed' ? '#28a745' : t.status === 'failed' ? '#dc3545' : t.status === 'processing' ? '#ffc107' : '#6c757d';
                const created = fmtTime(t.created_at);
                const started = fmtTime(t.started_at);
                const completed = fmtTime(t.completed_at);
                
                let html = '';
                
                // Top row: info + deliverables side by side
                html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">';
                
                // Left: task info
                html += '<div class="card"><h2 style="margin-top:0;">任务详情</h2>';
                html += '<table style="width:100%;">';
                html += '<tr><td style="width:80px;color:#666;padding:4px 0;">Task ID</td><td style="font-family:monospace;font-size:13px;padding:4px 0;">' + escapeHtml(t.task_id) + '</td></tr>';
                html += '<tr><td style="color:#666;padding:4px 0;">状态</td><td style="padding:4px 0;"><span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:500;color:white;background:' + statusColor + ';">' + statusLabel + '</span></td></tr>';
                html += '<tr><td style="color:#666;padding:4px 0;">文件名</td><td style="padding:4px 0;">' + escapeHtml(t.input_filename) + '</td></tr>';
                html += '<tr><td style="color:#666;padding:4px 0;">Backend</td><td style="padding:4px 0;">' + escapeHtml(t.backend || '-') + '</td></tr>';
                html += '<tr><td style="color:#666;padding:4px 0;">调用方</td><td style="padding:4px 0;">' + escapeHtml(t.caller_name || '-') + '</td></tr>';
                html += '<tr><td style="color:#666;padding:4px 0;">创建</td><td style="padding:4px 0;">' + created + '</td></tr>';
                if (started !== '-') html += '<tr><td style="color:#666;padding:4px 0;">开始</td><td style="padding:4px 0;">' + started + '</td></tr>';
                if (completed !== '-') html += '<tr><td style="color:#666;padding:4px 0;">完成</td><td style="padding:4px 0;">' + completed + '</td></tr>';
                html += '</table>';
                if (t.status === 'completed') {{
                    html += '<div style="margin-top: 8px;"><a href="/api/admin/tasks/{task_id}/source?name=' + encodeURIComponent(t.input_filename) + '" class="btn btn-primary btn-sm" target="_blank">下载原始文件</a></div>';
                }}
                html += '</div>';
                
                // Right: deliverables
                html += '<div class="card"><h2 style="margin-top:0;">附件</h2>';
                if (t.status === 'completed') {{
                    html += '<div id="deliverablesList" style="color:#999;">加载中...</div>';
                }} else {{
                    html += '<p style="color:#999;">任务完成后可见</p>';
                }}
                html += '</div>';
                
                html += '</div>';
                
                // Error card
                if (t.error) {{
                    html += '<div class="card" style="border-left:4px solid #dc3545;margin-bottom:12px;"><h2 style="color:#dc3545;margin-top:0;">错误信息</h2><pre id="taskErrorOutput" style="background:#fff5f5;padding:12px;border-radius:4px;font-family:monospace;font-size:12px;color:#c62828;white-space:pre-wrap;word-break:break-all;margin:0;"></pre></div>';
                }}
                
                // Bottom row: raw result
                if (t.result_raw) {{
                    html += '<div class="card"><h2 style="margin-top:0;">解析结果</h2><pre id="resultOutput" style="background:#f8f9fa;padding:16px;border-radius:4px;font-family:Consolas,monospace;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all;max-height:70vh;overflow:auto;margin:0;"></pre></div>';
                }}
                
                document.getElementById('taskDetail').innerHTML = html;
                
                // Fill raw result via textContent
                if (t.result_raw) {{
                    document.getElementById('resultOutput').textContent = t.result_raw;
                }}
                if (t.error) {{
                    document.getElementById('taskErrorOutput').textContent = t.error;
                }}
                
                // Load deliverables
                if (t.status === 'completed') {{
                    fetch('/api/admin/tasks/{task_id}/deliverables')
                        .then(r => r.json())
                        .then(data => {{
                            if (data.artifacts && data.artifacts.length > 0) {{
                                 let dhtml = '<table style="width:100%;"><thead><tr><th>文件名</th><th style="width:60px;">大小</th></tr></thead><tbody>';
                                 for (const a of data.artifacts) {{
                                     var sizeStr = a.size ? (a.size / 1024).toFixed(1) + ' KB' : '-';
                                    dhtml += '<tr><td style="font-family:monospace;font-size:12px;"><a href="/api/admin/tasks/{task_id}/deliverables/download?download_key=' + encodeURIComponent(a.download_key) + '" target="_blank" style="text-decoration:none;color:#1976d2;">' + escapeHtml(a.filename) + '</a></td><td style="font-size:12px;color:#666;">' + escapeHtml(sizeStr) + '</td></tr>';
                                 }}
                                dhtml += '</tbody></table>';
                                document.getElementById('deliverablesList').innerHTML = dhtml;
                            }} else {{
                                document.getElementById('deliverablesList').innerHTML = '<p style="color:#999;">暂无交付物</p>';
                            }}
                        }})
                        .catch(function() {{ document.getElementById('deliverablesList').innerHTML = '<p style="color:#999;">加载失败</p>'; }});
                }}
            }} catch (err) {{
                document.getElementById('taskDetail').innerHTML = '<div class="card"><p style="color:#c62828;">加载失败: ' + escapeHtml(err.message) + '</p></div>';
            }}
        }}
        
        loadTaskDetail();
    </script>
    '''
    return HTMLResponse(render_page("任务详情", inject_common_js(content)))


@router.get("/settings")
async def admin_settings_page(request: Request):
    """Settings page."""
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    from mineru_mcp.admin_auth import get_current_admin
    admin = get_current_admin(session_token)
    if not admin:
        return Response(headers={"Location": f"{CONSOLE_BASE}/login"}, status_code=302)
    
    # Check if password change is required
    if admin.must_change_password:
        return Response(headers={"Location": f"{CONSOLE_BASE}/change-password"}, status_code=302)
    
    content = f'''
    <div class="header">
        <h1>MinerU 管理控制台</h1>
        <span class="user-info">当前用户: {admin.username} | <a href="{CONSOLE_BASE}/logout">退出</a></span>
    </div>
    <div class="container">
        {get_nav('settings')}
        <div class="card">
            <h2>修改密码</h2>
            <div id="passwordAlert"></div>
            <form id="passwordForm">
                <div class="form-group">
                    <label>当前密码</label>
                    <input type="password" name="old_password" required>
                </div>
                <div class="form-group">
                    <label>新密码</label>
                    <input type="password" name="new_password" required minlength="6">
                </div>
                <div class="form-group">
                    <label>确认新密码</label>
                    <input type="password" name="confirm_password" required minlength="6">
                </div>
                <button type="submit" class="btn btn-primary">修改密码</button>
            </form>
        </div>
        <div class="card">
            <h2>管理员安全</h2>
            <div id="securityInfo" class="loading">加载中...</div>
        </div>
        <div class="card">
            <h2>全局运行配置</h2>
            <div id="runtimeInfo" class="loading">加载中...</div>
        </div>
    </div>
    
    <script>
        {COMMON_JS_HELPERS}
        document.getElementById('passwordForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const form = new FormData(e.target);
            if (form.get('new_password') !== form.get('confirm_password')) {{
                document.getElementById('passwordAlert').innerHTML = '<div class="alert alert-error">两次输入的密码不一致</div>';
                return;
            }}
            try {{
                const resp = await fetch('/api/admin/change-password', {{
                    method: 'POST',
                    headers: csrfHeaders({{'Content-Type': 'application/json'}}),
                    body: JSON.stringify({{
                        old_password: form.get('old_password'),
                        new_password: form.get('new_password')
                    }}),
                    credentials: 'same-origin'
                }});
                const data = await resp.json();
                if (data.success) {{
                    document.getElementById('passwordAlert').innerHTML = '<div class="alert alert-success">密码修改成功</div>';
                    e.target.reset();
                }} else {{
                    document.getElementById('passwordAlert').innerHTML = '<div class="alert alert-error">' + escapeHtml(data.message) + '</div>';
                }}
            }} catch (err) {{
                document.getElementById('passwordAlert').innerHTML = '<div class="alert alert-error">修改密码失败</div>';
            }}
        }});
        
        async function loadSettings() {{
            try {{
                const resp = await fetch('/api/admin/settings/runtime', {{ credentials: 'same-origin' }});
                const data = await resp.json();
                
                // Security info
                let secHtml = '<table>';
                secHtml += '<tr><td style="width: 150px; color: #666;">用户名</td><td>{{{{default_admin}}}}</td></tr>'.replace('{{default_admin}}', escapeHtml(data.admin_security.default_username));
                if (data.admin_security.default_password_in_use) {{
                    secHtml += '<tr><td style="color: #666;">密码状态</td><td><span class="alert alert-warning" style="display: inline-block; padding: 5px 10px;">警告: 仍在使用默认密码</span></td></tr>';
                }} else {{
                    secHtml += '<tr><td style="color: #666;">密码状态</td><td><span class="status status-completed">已修改</span></td></tr>';
                }}
                secHtml += '</table>';
                document.getElementById('securityInfo').innerHTML = secHtml;
                
                // Runtime info
                let runHtml = '<table>';
                runHtml += '<tr><td style="width: 150px; color: #666;">最大并发数</td><td>' + escapeHtml(data.max_concurrent) + '</td></tr>';
                runHtml += '<tr><td style="color: #666;">配置来源</td><td>' + escapeHtml(data.max_concurrent_source) + '</td></tr>';
                runHtml += '<tr><td style="color: #666;">说明</td><td>' + escapeHtml(data.max_concurrent_note) + '</td></tr>';
                runHtml += '</table>';
                document.getElementById('runtimeInfo').innerHTML = runHtml;
            }} catch (err) {{
                document.getElementById('securityInfo').innerHTML = '<div class="alert alert-error">加载失败</div>';
                document.getElementById('runtimeInfo').innerHTML = '<div class="alert alert-error">加载失败</div>';
            }}
        }}
        
        loadSettings();
    </script>
    '''
    return HTMLResponse(render_page("系统设置", inject_common_js(content)))


# Create the console router
console_router = router
