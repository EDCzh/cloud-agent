<template>
  <div class="chat-container">
    <el-container class="app-shell">
      <el-aside width="280px" class="sidebar">
        <div class="sidebar-header">
          <div class="brand">
            <div class="brand-logo">CA</div>
            <div>
              <h1>Cloud Agent</h1>
              <p>智能云服务助手</p>
            </div>
          </div>
          <el-tooltip content="新建对话" placement="right">
            <el-button type="primary" :icon="Plus" circle @click="createNewSession" />
          </el-tooltip>
        </div>

        <div class="session-list">
          <button
            v-for="session in sessions"
            :key="session.id"
            type="button"
            :class="['session-item', { active: currentSessionId === session.id }]"
            @click="switchSession(session.id)"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span class="session-name">{{ session.name }}</span>
            <el-tooltip content="重命名" placement="right">
              <el-button
                class="session-action"
                :icon="EditPen"
                text
                circle
                @click.stop="renameSession(session.id)"
              />
            </el-tooltip>
            <el-tooltip content="删除" placement="right">
              <el-button
                class="session-action danger"
                :icon="Delete"
                text
                circle
                @click.stop="deleteSession(session.id)"
              />
            </el-tooltip>
          </button>
        </div>

        <div class="user-info">
          <div class="mini-avatar user-avatar">U</div>
          <span class="username">user_1001</span>
        </div>
      </el-aside>

      <el-main class="chat-main">
        <header class="chat-header">
          <div>
            <div class="header-title">{{ currentSession?.name || '未命名对话' }}</div>
            <div class="header-subtitle">Multi-Agent · Billing · Promotion · FinOps</div>
          </div>
          <el-tooltip content="清空当前对话" placement="left">
            <el-button
              class="clear-session-btn"
              :icon="Delete"
              text
              :disabled="messages.length === 0 || isLoading"
              @click="clearCurrentSession"
            >
              清空
            </el-button>
          </el-tooltip>
        </header>

        <div ref="messageListRef" class="message-list">
          <section v-if="messages.length === 0" class="empty-state">
            <el-icon size="58" color="#2563eb"><Service /></el-icon>
            <h2 class="welcome-title">欢迎使用云平台智能客服</h2>
            <p class="welcome-desc">可以直接提问，也可以从下面的典型场景开始。</p>

            <div class="scenario-container">
              <article v-for="scenario in scenarios" :key="scenario.title" class="scenario-card">
                <div class="card-header">
                  <el-icon><component :is="scenario.icon" /></el-icon>
                  <span>{{ scenario.title }}</span>
                </div>
                <button
                  v-for="item in scenario.items"
                  :key="item"
                  type="button"
                  class="scenario-item"
                  @click="sendQuery(item)"
                >
                  {{ item }}
                </button>
              </article>
            </div>
          </section>

          <div
            v-for="(msg, index) in messages"
            :key="`${currentSessionId}-${index}`"
            :class="['message-row', msg.role]"
          >
            <div :class="['msg-avatar', msg.role === 'user' ? 'user-avatar' : 'ai-avatar']">
              {{ msg.role === 'user' ? 'U' : 'AI' }}
            </div>
            <div class="message-bubble" v-html="renderMarkdown(msg.content)"></div>
          </div>

          <div v-if="isLoading" class="message-row assistant">
            <div class="msg-avatar ai-avatar">AI</div>
            <div class="message-bubble loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              正在思考与调用工具...
            </div>
          </div>
        </div>

        <div class="input-area">
          <el-input
            v-model="inputQuery"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="请输入您的问题，Shift + Enter 换行，Enter 发送"
            :disabled="isLoading"
            @keydown.enter.prevent="handleEnter"
          />
          <el-button
            type="primary"
            class="send-btn"
            :icon="Position"
            :loading="isLoading"
            :disabled="!inputQuery.trim()"
            @click="sendQuery(inputQuery)"
          >
            发送
          </el-button>
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  DataLine,
  Delete,
  EditPen,
  List,
  Loading,
  Monitor,
  Plus,
  Position,
  Service,
  Share,
} from '@element-plus/icons-vue'
import { marked } from 'marked'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Session {
  id: string
  name: string
  messages: Message[]
  createdAt: number
}

const STORAGE_KEY = 'cloud-agent-chat-sessions'
const CURRENT_SESSION_KEY = 'cloud-agent-current-session'
const DEFAULT_SESSION_NAME = '默认对话'

const inputQuery = ref('')
const isLoading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const currentSessionId = ref('session_default_1')
const sessions = ref<Session[]>([
  {
    id: 'session_default_1',
    name: DEFAULT_SESSION_NAME,
    messages: [],
    createdAt: Date.now(),
  },
])

const scenarios = [
  {
    title: '产品咨询与推荐',
    icon: Monitor,
    items: ['云服务器 ECS 有哪些基础属性？', '我是 Java 接口服务 + MySQL，推荐什么实例规格？'],
  },
  {
    title: '账单与实例查询',
    icon: List,
    items: ['帮我查一下最近的订单记录', '查询我名下所有运行中的实例'],
  },
  {
    title: '资源优化与降本',
    icon: DataLine,
    items: ['获取近 7 天 CPU、内存、带宽数据，并给出降本建议', '服务器利用率低，怎么省钱？'],
  },
  {
    title: '产品推广活动',
    icon: Share,
    items: ['我想推广云服务器 ECS，有海报吗？', '帮我生成一张 c7 计算型实例的推广海报'],
  },
]

const currentSession = computed(() => sessions.value.find((session) => session.id === currentSessionId.value))
const messages = computed(() => currentSession.value?.messages ?? [])

onMounted(() => {
  restoreSessions()
})

watch(
  sessions,
  (value) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  },
  { deep: true },
)

watch(currentSessionId, (value) => {
  localStorage.setItem(CURRENT_SESSION_KEY, value)
})

const restoreSessions = () => {
  const storedSessions = localStorage.getItem(STORAGE_KEY)
  if (storedSessions) {
    try {
      const parsed = JSON.parse(storedSessions) as Session[]
      if (Array.isArray(parsed) && parsed.length > 0) {
        sessions.value = parsed.map((session) => ({
          ...session,
          messages: Array.isArray(session.messages) ? session.messages : [],
          createdAt: session.createdAt || Date.now(),
        }))
      }
    } catch {
      ElMessage.warning('本地会话数据读取失败，已创建新的默认对话')
    }
  }

  const storedCurrentSession = localStorage.getItem(CURRENT_SESSION_KEY)
  if (storedCurrentSession && sessions.value.some((session) => session.id === storedCurrentSession)) {
    currentSessionId.value = storedCurrentSession
  } else {
    currentSessionId.value = sessions.value[0]?.id || 'session_default_1'
  }
}

const askSessionName = async (title: string, defaultValue = '') => {
  const { value } = await ElMessageBox.prompt('请输入对话名称', title, {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: defaultValue,
    inputPlaceholder: '例如：ECS 规格咨询',
    inputPattern: /\S/,
    inputErrorMessage: '对话名称不能为空',
  })

  return String(value).trim()
}

const createNewSession = async () => {
  try {
    const name = await askSessionName('新建对话')
    const newSession: Session = {
      id: `session_${Date.now()}`,
      name,
      messages: [],
      createdAt: Date.now(),
    }

    sessions.value.unshift(newSession)
    currentSessionId.value = newSession.id
    inputQuery.value = ''
    await scrollToBottom()
  } catch {
    // User cancelled the dialog.
  }
}

const renameSession = async (id: string) => {
  const session = sessions.value.find((item) => item.id === id)
  if (!session) return

  try {
    session.name = await askSessionName('重命名对话', session.name)
  } catch {
    // User cancelled the dialog.
  }
}

const deleteSession = async (id: string) => {
  const session = sessions.value.find((item) => item.id === id)
  if (!session) return

  try {
    await ElMessageBox.confirm(`确定删除“${session.name}”吗？该对话的本地历史也会被删除。`, '删除对话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    })

    const nextSessions = sessions.value.filter((item) => item.id !== id)
    if (nextSessions.length === 0) {
      const fallbackSession: Session = {
        id: `session_${Date.now()}`,
        name: DEFAULT_SESSION_NAME,
        messages: [],
        createdAt: Date.now(),
      }
      sessions.value = [fallbackSession]
      currentSessionId.value = fallbackSession.id
      inputQuery.value = ''
      return
    }

    const nextCurrentSession = nextSessions[0]!
    sessions.value = nextSessions
    if (currentSessionId.value === id) {
      currentSessionId.value = nextCurrentSession.id
      inputQuery.value = ''
      await scrollToBottom()
    }
  } catch {
    // User cancelled the dialog.
  }
}

const clearCurrentSession = async () => {
  const session = currentSession.value
  if (!session || session.messages.length === 0) return

  try {
    await ElMessageBox.confirm(`确定清空“${session.name}”的所有消息吗？`, '清空对话', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    })

    session.messages = []
    inputQuery.value = ''
    await scrollToBottom()
  } catch {
    // User cancelled the dialog.
  }
}

const switchSession = async (id: string) => {
  if (currentSessionId.value === id) return
  currentSessionId.value = id
  inputQuery.value = ''
  await scrollToBottom()
}

const renderMarkdown = (text: string) => {
  return marked.parse(text)
}

const scrollToBottom = async () => {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

const handleEnter = (e: KeyboardEvent) => {
  if (e.shiftKey) return
  if (inputQuery.value.trim() && !isLoading.value) {
    sendQuery(inputQuery.value)
  }
}

const sendQuery = async (query: string) => {
  const session = currentSession.value
  if (!query.trim() || !session) return

  const text = query.trim()
  const sessionId = session.id
  inputQuery.value = ''

  session.messages.push({ role: 'user', content: text })
  scrollToBottom()

  isLoading.value = true

  const assistantMessage: Message = { role: 'assistant', content: '' }
  session.messages.push(assistantMessage)
  const currentMsgIndex = session.messages.length - 1

  try {
    const response = await fetch('http://localhost:5000/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: text,
        user_id: 'user_1001',
        session_id: sessionId,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder('utf-8')
    isLoading.value = false

    if (reader) {
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          const dataStr = line.slice(6).trim()
          if (!dataStr || dataStr === '[DONE]') continue

          try {
            const data = JSON.parse(dataStr)
            const activeSession = sessions.value.find((item) => item.id === sessionId)
            if (data.content && activeSession?.messages[currentMsgIndex]) {
              activeSession.messages[currentMsgIndex].content += data.content
              scrollToBottom()
            }
            if (data.error && activeSession?.messages[currentMsgIndex]) {
              activeSession.messages[currentMsgIndex].content = `请求失败：${data.error}`
            }
          } catch (error) {
            console.error('Error parsing SSE data:', error, dataStr)
          }
        }
      }
    }
  } catch (error) {
    console.error('API Error:', error)
    if (session.messages[currentMsgIndex]) {
      session.messages[currentMsgIndex].content =
        '请求失败，请检查后端服务是否已启动（FastAPI port 5000）。'
    }
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}
</script>

<style scoped>
.chat-container {
  width: 100vw;
  height: 100vh;
  padding: 16px;
  overflow: hidden;
  background: #eef4fb;
}

.app-shell {
  height: 100%;
  overflow: hidden;
  background: #fff;
  border: 1px solid #dfe7f2;
  border-radius: 8px;
  box-shadow: 0 20px 50px rgba(15, 35, 95, 0.08);
}

.sidebar {
  display: flex;
  flex-direction: column;
  background: #101828;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.brand {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 10px;
}

.brand-logo,
.mini-avatar,
.msg-avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-weight: 700;
}

.brand-logo {
  width: 32px;
  height: 32px;
  color: #fff;
  font-size: 12px;
  border-radius: 8px;
  background: #2563eb;
}

.brand h1 {
  margin: 0;
  color: #f8fafc;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
}

.brand p {
  margin: 2px 0 0;
  color: #94a3b8;
  font-size: 12px;
}

.session-list {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 44px;
  padding: 8px 8px 8px 10px;
  margin-bottom: 8px;
  color: #dbeafe;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  transition:
    background-color 0.2s,
    border-color 0.2s;
}

.session-item:hover,
.session-item.active {
  background: rgba(37, 99, 235, 0.22);
  border-color: rgba(147, 197, 253, 0.3);
}

.session-name {
  flex: 1;
  min-width: 0;
  margin-left: 10px;
  overflow: hidden;
  color: inherit;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-action {
  opacity: 0;
  color: #bfdbfe;
}

.session-action.danger {
  color: #fecaca;
}

.session-item:hover .session-action,
.session-item.active .session-action {
  opacity: 1;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.username {
  color: #e2e8f0;
  font-weight: 600;
}

.mini-avatar {
  width: 28px;
  height: 28px;
  font-size: 11px;
  border-radius: 7px;
}

.chat-main {
  display: flex;
  flex-direction: column;
  padding: 0;
  background: #f8fbff;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 72px;
  padding: 16px 28px;
  background: rgba(255, 255, 255, 0.86);
  border-bottom: 1px solid #e4ebf5;
}

.clear-session-btn {
  flex-shrink: 0;
  color: #64748b;
}

.header-title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
}

.header-subtitle {
  margin-top: 3px;
  color: #64748b;
  font-size: 13px;
}

.message-list {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 32px;
  color: #64748b;
  background: #fff;
  border: 1px solid #e4ebf5;
  border-radius: 8px;
}

.welcome-title {
  margin: 14px 0 6px;
  color: #1e293b;
  font-size: 24px;
  font-weight: 700;
}

.welcome-desc {
  margin: 0 0 28px;
  font-size: 15px;
}

.scenario-container {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
  max-width: 880px;
  gap: 16px;
}

.scenario-card {
  min-width: 0;
  padding: 18px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  color: #334155;
  font-size: 15px;
  font-weight: 700;
}

.card-header .el-icon {
  color: #2563eb;
  font-size: 20px;
}

.scenario-item {
  display: block;
  width: 100%;
  padding: 10px 12px;
  margin-top: 10px;
  color: #475569;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  transition:
    background-color 0.2s,
    border-color 0.2s,
    color 0.2s;
}

.scenario-item:hover {
  color: #1d4ed8;
  background: #eff6ff;
  border-color: #93c5fd;
}

.message-row {
  display: flex;
  align-items: flex-start;
  max-width: 86%;
  gap: 12px;
  margin-bottom: 18px;
}

.message-row.user {
  flex-direction: row-reverse;
  margin-left: auto;
}

.msg-avatar {
  width: 34px;
  height: 34px;
  font-size: 12px;
  border-radius: 8px;
}

.user-avatar {
  color: #eff6ff;
  background: #2563eb;
}

.ai-avatar {
  color: #f8fafc;
  background: #0284c7;
}

.message-bubble {
  min-width: 0;
  padding: 13px 16px;
  color: #1e293b;
  font-size: 15px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  background: #fff;
  border: 1px solid #e4ebf5;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 35, 95, 0.05);
}

.message-row.user .message-bubble {
  color: #fff;
  background: #2563eb;
  border-color: rgba(37, 99, 235, 0.35);
}

.loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.message-bubble :deep(p) {
  margin: 0 0 10px;
}

.message-bubble :deep(p:last-child) {
  margin-bottom: 0;
}

.message-bubble :deep(img) {
  max-width: 100%;
  margin-top: 10px;
  border-radius: 8px;
}

.message-bubble :deep(pre) {
  padding: 10px;
  overflow-x: auto;
  background: #f4f4f5;
  border-radius: 6px;
}

.message-bubble :deep(code) {
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 28px 20px;
  background: #fff;
  border-top: 1px solid #e4ebf5;
}

.send-btn {
  align-self: flex-end;
  width: 108px;
  border-radius: 8px;
}

@media (max-width: 860px) {
  .chat-container {
    padding: 0;
  }

  .app-shell {
    border-radius: 0;
  }

  .sidebar {
    width: 220px !important;
  }

  .scenario-container {
    grid-template-columns: 1fr;
  }

  .message-row {
    max-width: 100%;
  }
}
</style>
