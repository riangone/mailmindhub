/**
 * MailMindHub AI Chat Assistant
 * 侧边滑出式聊天界面，支持 SSE 流式响应
 */

(function() {
    'use strict';

    // 状态管理
    const state = {
        sessionId: null,
        backend: 'claude',
        isStreaming: false,
        abortController: null,
        messages: [],
        models: []
    };

    // DOM 元素
    let chatPanel, chatMessages, chatInput, chatSendBtn, chatBackendSelect, chatCancelBtn;
    let chatMessagesContainer, chatLoading, chatSessionsList;

    /**
     * 初始化聊天界面
     */
    function initChat() {
        // 获取 DOM 引用（面板已在 HTML 中定义）
        chatPanel = document.getElementById('chat-panel');
        chatMessagesContainer = document.getElementById('chat-messages-container');
        chatMessages = document.getElementById('chat-messages');
        chatInput = document.getElementById('chat-input');
        chatSendBtn = document.getElementById('chat-send-btn');
        chatCancelBtn = document.getElementById('chat-cancel-btn');
        chatBackendSelect = document.getElementById('chat-backend-select');
        chatLoading = document.getElementById('chat-loading');
        chatSessionsList = document.getElementById('chat-sessions-list');

        // 如果面板不存在，跳过初始化
        if (!chatPanel) {
            return;
        }

        // 绑定事件
        bindEvents();

        // 加载模型列表
        loadModels();

        // 加载会话列表
        loadSessions();

        // 从 localStorage 恢复上次使用的 backend
        const savedBackend = localStorage.getItem('mm-chat-backend');
        if (savedBackend && state.models.find(m => m.id === savedBackend)) {
            state.backend = savedBackend;
            if (chatBackendSelect) {
                chatBackendSelect.value = savedBackend;
            }
        }
    }

    /**
     * 绑定事件
     */
    function bindEvents() {
        if (!chatSendBtn || !chatInput || !chatCancelBtn || !chatBackendSelect) return;

        // 发送按钮
        chatSendBtn.addEventListener('click', sendMessage);

        // 取消按钮
        chatCancelBtn.addEventListener('click', cancelStreaming);

        // 输入框事件
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // 自动调整输入框高度
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
        });

        // 模型选择
        chatBackendSelect.addEventListener('change', (e) => {
            state.backend = e.target.value;
            localStorage.setItem('mm-chat-backend', state.backend);
        });
    }

    /**
     * 加载模型列表
     */
    async function loadModels() {
        if (!chatBackendSelect) return;

        try {
            const res = await fetch('/api/chat/models');
            const data = await res.json();
            state.models = data.models || [];

            chatBackendSelect.innerHTML = state.models.map(m =>
                `<option value="${m.id}">${m.name}</option>`
            ).join('');

            // 恢复上次选择的模型
            const savedBackend = localStorage.getItem('mm-chat-backend');
            if (savedBackend && state.models.find(m => m.id === savedBackend)) {
                state.backend = savedBackend;
                chatBackendSelect.value = savedBackend;
            }
        } catch (err) {
            console.error('Failed to load models:', err);
        }
    }

    /**
     * 加载会话列表
     */
    async function loadSessions() {
        if (!chatSessionsList) return;

        try {
            const res = await fetch('/chat/sessions-list?active=0');
            const html = await res.text();
            chatSessionsList.innerHTML = html;
        } catch (err) {
            console.error('Failed to load sessions:', err);
        }
    }

    /**
     * 切换聊天面板
     */
    function toggleChatPanel() {
        if (!chatPanel) return;

        const isVisible = chatPanel.style.display !== 'none';

        if (!isVisible) {
            // Opening - load sessions
            loadSessions();
        }

        chatPanel.style.display = isVisible ? 'none' : 'flex';

        if (!isVisible) {
            // 打开时聚焦输入框
            setTimeout(() => chatInput && chatInput.focus(), 100);
        }
    }

    // 暴露到全局
    window.toggleChatPanel = toggleChatPanel;

    /**
     * 发送消息
     */
    async function sendMessage() {
        const message = chatInput?.value.trim();
        if (!message || state.isStreaming) return;

        // 如果没有会话，创建新会话
        if (!state.sessionId) {
            await createNewSession();
        }

        // 清空输入框
        if (chatInput) {
            chatInput.value = '';
            chatInput.style.height = 'auto';
        }

        // 添加用户消息到 UI
        appendMessage('user', message);

        // 准备接收 AI 响应
        const assistantMessageEl = appendMessage('assistant', '', true);
        const contentEl = assistantMessageEl.querySelector('.chat-message-content');

        // 开始流式请求
        startStreaming(message, contentEl);
    }

    /**
     * 创建新会话
     */
    async function createNewSession() {
        try {
            const formData = new FormData();
            formData.append('name', '新对话');

            const res = await fetch('/chat/new', {
                method: 'POST',
                body: formData,
                redirect: 'manual'  // 不自动跟随重定向
            });

            // 从重定向 URL 提取 session ID
            const location = res.headers.get('location');
            if (location) {
                const match = location.match(/\/chat\/(\d+)/);
                if (match) {
                    state.sessionId = parseInt(match[1]);
                    return;  // 成功获取 session ID
                }
            }

            // 如果从重定向 URL 获取失败，尝试从响应 URL 获取
            if (!state.sessionId && res.url) {
                const match = res.url.match(/\/chat\/(\d+)/);
                if (match) {
                    state.sessionId = parseInt(match[1]);
                    return;
                }
            }

            // 如果仍然失败，尝试通过 API 创建
            console.warn('无法从重定向获取 session ID，尝试备用方案');
            await createNewSessionViaAPI();

        } catch (err) {
            console.error('Failed to create session:', err);
            showError('无法创建会话');
        }
    }

    /**
     * 备用方案：通过 API 创建新会话
     */
    async function createNewSessionViaAPI() {
        try {
            // 先获取最新会话列表
            const res = await fetch('/chat/sessions?limit=1');
            if (res.ok) {
                const sessions = await res.json();
                if (sessions && sessions.length > 0) {
                    state.sessionId = sessions[0].id;
                    return;
                }
            }

            // 如果没有会话，抛出错误
            throw new Error('无法创建或获取会话 ID');
        } catch (err) {
            console.error('备用方案也失败了:', err);
            throw err;
        }
    }

    /**
     * 开始流式请求
     */
    function startStreaming(message, contentEl) {
        state.isStreaming = true;
        state.abortController = new AbortController();

        // 更新 UI 状态
        if (chatSendBtn) chatSendBtn.style.display = 'none';
        if (chatCancelBtn) chatCancelBtn.style.display = 'flex';
        if (chatLoading) chatLoading.style.display = 'flex';
        if (chatInput) chatInput.disabled = true;

        let accumulatedContent = '';

        fetch(`/api/chat/${state.sessionId}/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                backend: state.backend
            }),
            signal: state.abortController.signal
        })
        .then(res => {
            if (!res.ok) throw new Error('Network error');
            return res.body;
        })
        .then(reader => {
            if (!reader) return;

            const decoder = new TextDecoder();
            const pump = async () => {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;

                        const data = line.slice(6);
                        if (data === '[DONE]') {
                            finishStreaming();
                            continue;
                        }

                        try {
                            const event = JSON.parse(data);
                            handleStreamEvent(event, contentEl, () => accumulatedContent, (v) => { accumulatedContent = v; });
                        } catch (e) {
                            console.warn('Failed to parse SSE event:', data, e);
                        }
                    }
                }
            };
            pump().catch(err => {
                if (err.name === 'AbortError') {
                    // Cancelled
                } else {
                    console.error('Stream error:', err);
                    showError('流式响应出错');
                }
            });
        })
        .catch(err => {
            if (err.name === 'AbortError') {
                if (contentEl) contentEl.textContent += '\n\n[已取消]';
            } else {
                console.error('Fetch error:', err);
                showError('请求失败');
            }
            finishStreaming();
        });
    }

    /**
     * 处理流式事件
     */
    function handleStreamEvent(event, contentEl, getContentAccumulator, setContentAccumulator) {
        switch (event.type) {
            case 'start':
                // 开始响应
                break;

            case 'token':
                // 接收 token
                setContentAccumulator(getContentAccumulator() + event.content);
                // 使用 marked 渲染 Markdown
                if (window.marked) {
                    contentEl.innerHTML = window.marked.parse(getContentAccumulator());
                } else {
                    contentEl.textContent = getContentAccumulator();
                }
                // 滚动到底部
                scrollToBottom();
                // 代码高亮
                if (window.hljs) {
                    contentEl.querySelectorAll('pre code').forEach((block) => {
                        window.hljs.highlightElement(block);
                    });
                }
                break;

            case 'error':
                showError(event.message);
                break;

            case 'done':
                // 完成
                break;

            case 'cancelled':
                if (contentEl) contentEl.textContent += '\n\n[已取消]';
                break;
        }
    }

    /**
     * 取消流式请求
     */
    function cancelStreaming() {
        if (state.abortController) {
            state.abortController.abort();
            state.abortController = null;
        }
    }

    /**
     * 结束流式请求
     */
    function finishStreaming() {
        state.isStreaming = false;

        // 恢复 UI 状态
        if (chatSendBtn) chatSendBtn.style.display = 'flex';
        if (chatCancelBtn) chatCancelBtn.style.display = 'none';
        if (chatLoading) chatLoading.style.display = 'none';
        if (chatInput) {
            chatInput.disabled = false;
            chatInput.focus();
        }

        // 刷新会话列表
        loadSessions();
    }

    /**
     * 添加消息到 UI
     */
    function appendMessage(role, content, isLoading = false) {
        if (!chatMessages) return null;

        // 移除空状态
        const emptyState = chatMessages.querySelector('.chat-empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        const el = document.createElement('div');
        el.className = `chat-message chat-message-${role}`;

        const time = new Date().toLocaleTimeString();
        const roleLabel = role === 'user' ? '你' : 'AI';

        el.innerHTML = `
            <div class="chat-message-header">
                <span class="chat-message-role">${roleLabel}</span>
                <span class="chat-message-time">${time}</span>
            </div>
            <div class="chat-message-content">${isLoading ? '<span class="typing-dots"><span></span><span></span><span></span></span>' : escapeHtml(content)}</div>
        `;

        chatMessages.appendChild(el);
        scrollToBottom();

        return el;
    }

    /**
     * 滚动到底部
     */
    function scrollToBottom() {
        if (chatMessagesContainer) {
            chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
        }
    }

    /**
     * 显示错误
     */
    function showError(message) {
        console.error('Chat error:', message);
    }

    /**
     * HTML 转义
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 新对话
     */
    window.newChatSession = async function() {
        state.sessionId = null;
        if (chatMessages) {
            chatMessages.innerHTML = `
                <div class="chat-empty-state">
                    <div class="chat-empty-icon">💬</div>
                    <p>开始与 AI 对话</p>
                    <p class="chat-empty-hint">选择 AI 模型，输入问题，按 Enter 发送</p>
                </div>
            `;
        }
        loadSessions();
        if (chatInput) chatInput.focus();
    };

    /**
     * 选择会话
     */
    window.selectChatSession = async function(sessionId) {
        state.sessionId = sessionId;

        // 加载会话消息
        try {
            const res = await fetch(`/chat/${sessionId}/messages-html`);
            const html = await res.text();
            if (chatMessages) {
                chatMessages.innerHTML = html;

                // 渲染 Markdown 和高亮代码
                if (window.marked) {
                    chatMessages.querySelectorAll('.chat-message-content').forEach(el => {
                        if (!el.dataset.marked) {
                            el.innerHTML = window.marked.parse(el.textContent);
                            el.dataset.marked = 'true';
                        }
                    });
                }
                if (window.hljs) {
                    chatMessages.querySelectorAll('pre code').forEach(block => {
                        window.hljs.highlightElement(block);
                    });
                }

                scrollToBottom();
            }

            // 更新会话列表激活状态
            document.querySelectorAll('.chat-session-item').forEach(item => {
                item.classList.remove('active');
            });
            const activeItem = document.querySelector(`.chat-session-item[data-session-id="${sessionId}"]`);
            if (activeItem) {
                activeItem.classList.add('active');
            }
        } catch (err) {
            console.error('Failed to load messages:', err);
        }
    };

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initChat);
    } else {
        initChat();
    }
})();
