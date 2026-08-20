import axios from 'axios';
import { apiConfig } from '../config/api.js';

/**
 * axios 封装：
 * 1. 统一 baseURL 与超时
 * 2. 请求拦截自动携带 Token（从 localStorage 的 userStore 读取）
 * 3. 响应拦截：统一解包 code/data，返回 Promise.reject 时附带 message，便于前端 toast
 */

const service = axios.create({
  baseURL: apiConfig.baseURL,
  timeout: 60000
});

service.interceptors.request.use(
  (config) => {
    // 修复6: 请求自动带 Authorization
    try {
      // Pinia 默认把 userStore 序列化成 JSON 存到 localStorage 里（persistedstate 插件）
      const raw = localStorage.getItem('user');
      if (raw) {
        const store = JSON.parse(raw);
        const token = store?.token || store?.user?.token;
        if (token) {
          config.headers = config.headers || {};
          config.headers.Authorization = `Bearer ${token}`;
        }
      }
    } catch (_e) {
      // 解析失败不影响请求发送
    }
    return config;
  },
  (error) => Promise.reject(error)
);

service.interceptors.response.use(
  (response) => {
    // 直接返回后端原始 data（前端习惯 .code / .data / .message 的格式）
    return response.data;
  },
  (error) => {
    // 401 未授权 → 清理本地登录态并跳转登录
    if (error.response?.status === 401) {
      localStorage.removeItem('user');
      if (window.location.hash !== '#/login') {
        window.location.hash = '#/login';
      }
    }
    return Promise.reject(error);
  }
);

// ---- AI / 业务快捷方法 ----
export async function ragChat(question, history = []) {
  // 调用统一聊天接口：RAG优先，无相关新闻则回退普通对话
  return service.post('/api/ai/unified_chat', { question, history });
}

export async function syncNewsToVector() {
  return service.post('/api/ai/sync_news_to_vector');
}

// ---- 新闻Agent Skill ----
export async function getNewsSkills() {
  return service.get('/api/ai/news_skills');
}

export async function shareNewsToAI(newsId, title, content) {
  return service.post('/api/ai/news_share', {
    news_id: newsId,
    news_title: title,
    news_content: content
  });
}

export async function processNewsWithSkills(newsText, newsTitle, skills) {
  return service.post('/api/ai/news_process', {
    news_text: newsText,
    news_title: newsTitle,
    skills
  });
}

export default service;
