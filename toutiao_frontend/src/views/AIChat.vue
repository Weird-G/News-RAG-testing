<template>
  <div class="ai-chat-container">
    <van-nav-bar title="AI问答" fixed />
    
    <div class="chat-content">
      <div class="messages-container" ref="messagesContainer">
        <div 
          v-for="(message, index) in messages" 
          :key="index" 
          :class="['message', message.role === 'user' ? 'user-message' : 'ai-message']"
        >
          <div class="message-content">
            <div v-if="message.role === 'assistant' && message.loading" class="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>

            <!-- 新闻分享卡片 -->
            <div v-else-if="message.role === 'assistant' && message.type === 'news_share'" class="news-share-card">
              <div class="news-share-header">
                <span class="news-share-icon">📰</span>
                <span class="news-share-title">{{ message.news_title }}</span>
              </div>
              <div class="skill-results">
                <div v-for="(skill, si) in message.skill_results" :key="si" class="skill-result-item">
                  <div class="skill-result-header">
                    <span class="skill-icon">{{ getSkillIcon(skill.skill_name) }}</span>
                    <span class="skill-name">{{ getSkillDisplayName(skill.skill_name) }}</span>
                    <van-tag v-if="skill.status === 'success'" type="success" size="medium">完成</van-tag>
                    <van-tag v-else type="danger" size="medium">失败</van-tag>
                  </div>
                  <div v-if="skill.status === 'success'" class="skill-result-body">
                    <template v-if="skill.skill_name === 'news_summarize'">
                      <div class="sr-row"><span class="sr-label">标题:</span> {{ skill.result.title }}</div>
                      <div class="sr-row"><span class="sr-label">核心:</span> {{ skill.result.core_event }}</div>
                      <div class="sr-row"><span class="sr-label">要点:</span>
                        <ul class="sr-list">
                          <li v-for="(p, i) in skill.result.key_points" :key="i">{{ p }}</li>
                        </ul>
                      </div>
                      <div class="sr-row">
                        <van-tag size="small">{{ skill.result.emotion_tone }}</van-tag>
                        <span class="sr-source">{{ skill.result.source_hint }}</span>
                      </div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_extract'">
                      <div class="sr-row"><span class="sr-label">时间:</span> {{ skill.result.event_time }}</div>
                      <div class="sr-row"><span class="sr-label">地点:</span> {{ skill.result.location }}</div>
                      <div class="sr-row" v-if="skill.result.person_list?.length">
                        <span class="sr-label">人物:</span>
                        <van-tag v-for="(p, i) in skill.result.person_list" :key="i" size="small" type="primary" style="margin-right:4px">{{ p }}</van-tag>
                      </div>
                      <div class="sr-row" v-if="skill.result.organization_list?.length">
                        <span class="sr-label">机构:</span>
                        <van-tag v-for="(o, i) in skill.result.organization_list" :key="i" size="small" type="warning" style="margin-right:4px">{{ o }}</van-tag>
                      </div>
                      <div class="sr-row" v-if="skill.result.important_numbers?.length">
                        <span class="sr-label">关键数据:</span>
                        <van-tag v-for="(n, i) in skill.result.important_numbers" :key="i" size="small" type="danger" style="margin-right:4px">{{ n }}</van-tag>
                      </div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_question_gen'">
                      <div class="sr-row"><span class="sr-label">💡 建议追问:</span></div>
                      <div class="question-chips">
                        <van-chip 
                          v-for="(q, qi) in skill.result.follow_questions" 
                          :key="qi" 
                          type="primary" 
                          size="large"
                          @click="askQuestion(q)"
                        >
                          {{ q }}
                        </van-chip>
                      </div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_opinion'">
                      <div class="sr-row"><span class="sr-label">📋 客观事实:</span>
                        <ul class="sr-list"><li v-for="(f, i) in skill.result.fact_content" :key="i">{{ f }}</li></ul>
                      </div>
                      <div class="sr-row"><span class="sr-label">💬 观点主张:</span>
                        <ul class="sr-list"><li v-for="(o, i) in skill.result.opinion_content" :key="i">{{ o }}</li></ul>
                      </div>
                      <div v-if="skill.result.conflict_view?.length" class="sr-row">
                        <span class="sr-label">⚡ 争议焦点:</span>
                        <ul class="sr-list"><li v-for="(c, i) in skill.result.conflict_view" :key="i">{{ c }}</li></ul>
                      </div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_risk_check'">
                      <div class="sr-row">
                        <span class="sr-label">风险等级:</span>
                        <van-tag :type="skill.result.risk_level === 'high' ? 'danger' : skill.result.risk_level === 'middle' ? 'warning' : 'success'" size="medium">
                          {{ skill.result.risk_level === 'low' ? '🟢 低风险' : skill.result.risk_level === 'middle' ? '🟡 中风险' : '🔴 高风险' }}
                        </van-tag>
                      </div>
                      <div class="sr-row"><span class="sr-label">风险类型:</span> {{ skill.result.risk_type?.join('、') || '无' }}</div>
                      <div class="sr-row"><span class="sr-label">判断依据:</span> {{ skill.result.risk_reason }}</div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_rewrite'">
                      <div class="sr-row"><span class="sr-label">📱 简讯:</span> {{ skill.result.short_bulletin }}</div>
                      <div class="sr-row"><span class="sr-label">📖 通俗版:</span> {{ skill.result.popular_version }}</div>
                      <div class="sr-row"><span class="sr-label">📌 备选标题:</span>
                        <div class="candidate-titles">
                          <div v-for="(t, ti) in skill.result.candidate_titles" :key="ti" class="candidate-title">{{ ti + 1 }}. {{ t }}</div>
                        </div>
                      </div>
                    </template>
                    <template v-else-if="skill.skill_name === 'news_compare'">
                      <div class="sr-row"><span class="sr-label">✔️ 相同点:</span>
                        <ul class="sr-list"><li v-for="(s, i) in skill.result.same_points" :key="i">{{ s }}</li></ul>
                      </div>
                      <div class="sr-row"><span class="sr-label">❌ 差异点:</span>
                        <ul class="sr-list"><li v-for="(d, i) in skill.result.diff_points" :key="i">{{ d }}</li></ul>
                      </div>
                      <div class="sr-row"><span class="sr-label">📊 角度总结:</span> {{ skill.result.angle_summary }}</div>
                    </template>
                  </div>
                  <div v-else class="skill-result-body error-body">
                    {{ skill.msg || '处理失败' }}
                  </div>
                </div>
              </div>

              <!-- Skill选择卡片 -->
              <div v-if="message.skill_choices?.length" class="skill-choices">
                <div class="skill-choices-title">🤖 你还可以试试:</div>
                <div class="skill-choices-list">
                  <van-chip 
                    v-for="choice in message.skill_choices" 
                    :key="choice.skill"
                    :type="message.executed_skills?.includes(choice.skill) ? 'default' : 'primary'"
                    :disabled="message.executed_skills?.includes(choice.skill) || message.processing_skills?.includes(choice.skill)"
                    size="large"
                    @click="executeSkill(message, choice.skill)"
                  >
                    {{ choice.icon }} {{ choice.label }}
                  </van-chip>
                </div>
              </div>
            </div>

            <!-- 普通消息 -->
            <div v-else>
              <div v-if="message.role === 'assistant' && message.is_rag" class="mode-indicator">
                <van-tag type="primary" size="medium">📰 新闻知识</van-tag>
              </div>
              <div v-else-if="message.role === 'assistant'" class="mode-indicator">
                <van-tag type="success" size="medium">💬 AI对话</van-tag>
              </div>
              <div v-html="formatMessage(message.content)"></div>
              <div v-if="message.reference_news && message.reference_news.length > 0" class="reference-news">
                <div class="reference-title">📎 参考新闻来源：</div>
                <div class="reference-list">
                  <span v-for="(news, i) in message.reference_news" :key="i" class="reference-tag">{{ news }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="fixed-input-container">
      <van-field
        v-model="userInput"
        rows="1"
        autosize
        type="textarea"
        placeholder="输入问题，AI会结合新闻知识库回答..."
        class="chat-input"
        @keypress.enter.prevent="sendMessage"
      />
      <van-button 
        type="primary" 
        class="send-button" 
        :disabled="isLoading || !userInput.trim()" 
        @click="sendMessage"
      >
        发送
      </van-button>
    </div>
    
    <tab-bar />
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import TabBar from '../components/TabBar.vue';
import { showToast } from 'vant';
import * as marked from 'marked';
import DOMPurify from 'dompurify';
import { ragChat, shareNewsToAI, processNewsWithSkills } from '../utils/request';
import { useAiShareStore } from '../store/modules/aiShare';

const route = useRoute();
const aiShareStore = useAiShareStore();
const messages = ref([
  { 
    role: 'assistant', 
    content: '你好！我是新闻智能助手。你可以问我任何问题，也可以在新闻详情页点击「🤖 AI分析」让我帮你总结、提取关键信息、生成追问等。' 
  }
]);
const userInput = ref('');
const messagesContainer = ref(null);
const isLoading = ref(false);
const sharedNews = ref(null);

const SKILL_META = {
  news_summarize: { icon: '📝', name: '新闻摘要总结' },
  news_extract: { icon: '🔍', name: '关键信息抽取' },
  news_opinion: { icon: '⚖️', name: '新闻观点提炼' },
  news_risk_check: { icon: '⚠️', name: '新闻风险提示' },
  news_rewrite: { icon: '✏️', name: '新闻改写' },
  news_question_gen: { icon: '❓', name: '关联提问生成' },
  news_compare: { icon: '🔀', name: '多新闻对比分析' },
};

const getSkillIcon = (skillName) => SKILL_META[skillName]?.icon || '⚙️';
const getSkillDisplayName = (skillName) => SKILL_META[skillName]?.name || skillName;

const formatMessage = (content) => {
  if (!content) return '';
  return DOMPurify.sanitize(marked.parse(content));
};

const askQuestion = async (question) => {
  userInput.value = question;
  await sendMessage();
};

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
};

const handleSharedNews = () => {
  if (route.query.share_news !== '1') return;
  
  const newsId = route.query.news_id;
  const newsTitle = decodeURIComponent(route.query.news_title || '');
  const skillResults = route.query.skill_results ? JSON.parse(decodeURIComponent(route.query.skill_results)) : [];
  const skillChoices = route.query.skill_choices ? JSON.parse(decodeURIComponent(route.query.skill_choices)) : [];
  
  // 从store恢复完整新闻数据
  const storeData = aiShareStore.sharedNews;
  sharedNews.value = storeData ? {
    id: storeData.newsId,
    title: storeData.newsTitle,
    content: storeData.newsContent
  } : { id: newsId, title: newsTitle, content: '' };
  
  const executedSkills = skillResults.map(r => r.skill_name);
  const filteredChoices = skillChoices.filter(c => !executedSkills.includes(c.skill));
  
  messages.value.push({
    role: 'user',
    content: `请帮我分析新闻《${newsTitle}》`
  });
  
  messages.value.push({
    role: 'assistant',
    type: 'news_share',
    news_id: newsId,
    news_title: newsTitle,
    skill_results: skillResults,
    skill_choices: filteredChoices,
    executed_skills: executedSkills,
    processing_skills: []
  });
  
  nextTick(scrollToBottom);
};

const executeSkill = async (message, skillName) => {
  if (!sharedNews.value || !sharedNews.value.content) return;
  
  if (!message.processing_skills) {
    message.processing_skills = [];
  }
  message.processing_skills.push(skillName);
  
  try {
    const result = await processNewsWithSkills(sharedNews.value.content, sharedNews.value.title, [skillName]);
    
    if (result.code === 200 && result.data) {
      const newResults = result.data.skill_results || [];
      for (const nr of newResults) {
        message.skill_results.push(nr);
      }
      message.executed_skills = message.executed_skills || [];
      message.executed_skills.push(skillName);
      message.skill_choices = message.skill_choices.filter(c => c.skill !== skillName);
    }
  } catch (error) {
    console.error('Skill执行失败:', error);
    showToast({ message: '处理失败，请重试', position: 'bottom' });
  } finally {
    message.processing_skills = message.processing_skills.filter(s => s !== skillName);
  }
};

const sendMessage = async () => {
  if (!userInput.value.trim() || isLoading.value) return;

  const userMessage = userInput.value.trim();
  messages.value.push({ role: 'user', content: userMessage });
  userInput.value = '';
  
  messages.value.push({ role: 'assistant', content: '', is_rag: false, loading: true });
  
  await nextTick();
  scrollToBottom();
  
  isLoading.value = true;
  try {
    const history = messages.value.slice(0, -2).map(msg => ({
      role: msg.role,
      content: msg.content || msg.news_title || ''
    }));
    
    const result = await ragChat(userMessage, history);
    
    messages.value[messages.value.length - 1] = {
      role: 'assistant',
      content: result.answer || '抱歉，我暂时无法回答这个问题。',
      reference_news: result.reference_news || [],
      is_rag: result.is_rag || false
    };
  } catch (error) {
    console.error('AI对话错误:', error);
    messages.value[messages.value.length - 1] = {
      role: 'assistant',
      content: `❌ 出错了：${error.message || '请检查网络连接后重试'}`
    };
  } finally {
    isLoading.value = false;
    await nextTick();
    scrollToBottom();
  }
};

watch(messages, () => {
  nextTick(scrollToBottom);
}, { deep: true });

onMounted(() => {
  handleSharedNews();
  nextTick(scrollToBottom);
});
</script>

<style scoped>
.ai-chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding-top: 46px;
  padding-bottom: 100px;
  box-sizing: border-box;
  background-color: #f5f5f5;
}

.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.message {
  margin-bottom: 10px;
  max-width: 92%;
}

.user-message {
  margin-left: auto;
}

.ai-message {
  margin-right: auto;
}

.message-content {
  padding: 10px 14px;
  border-radius: 14px;
  word-break: break-word;
}

.user-message .message-content {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.ai-message .message-content {
  background-color: #fff;
  color: #333;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.mode-indicator {
  margin-bottom: 6px;
}

.fixed-input-container {
  position: fixed;
  bottom: 50px;
  left: 0;
  right: 0;
  display: flex;
  padding: 10px;
  border-top: 1px solid #eee;
  background-color: #fff;
  z-index: 999;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
}

.chat-input {
  flex: 1;
  margin-right: 10px;
}

.send-button {
  align-self: flex-end;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 20px;
}

.reference-news {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #ddd;
}

.reference-title {
  font-size: 12px;
  color: #999;
  margin-bottom: 5px;
}

.reference-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.reference-tag {
  font-size: 12px;
  color: #1989fa;
  background-color: #e8f4fd;
  padding: 3px 8px;
  border-radius: 4px;
}

.typing-indicator {
  display: flex;
  padding: 5px;
}

.typing-indicator span {
  height: 8px;
  width: 8px;
  background-color: #999;
  border-radius: 50%;
  margin: 0 2px;
  display: inline-block;
  animation: bounce 1.5s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-5px); }
}

/* 新闻分享卡片 */
.news-share-card {
  background: #fff;
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.news-share-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 10px;
}

.news-share-icon {
  font-size: 20px;
}

.news-share-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
  flex: 1;
}

.skill-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skill-result-item {
  background: #f9f9fb;
  border-radius: 10px;
  padding: 10px 12px;
}

.skill-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.skill-icon {
  font-size: 16px;
}

.skill-name {
  font-weight: 600;
  font-size: 13px;
  color: #333;
  flex: 1;
}

.skill-result-body {
  font-size: 13px;
  color: #555;
  line-height: 1.6;
}

.error-body {
  color: #e74c3c;
  font-size: 13px;
}

.sr-row {
  margin-bottom: 6px;
  line-height: 1.6;
}

.sr-label {
  color: #888;
  font-size: 12px;
  margin-right: 4px;
}

.sr-list {
  margin: 4px 0;
  padding-left: 18px;
  font-size: 13px;
}

.sr-list li {
  margin-bottom: 4px;
}

.sr-source {
  color: #667eea;
  font-size: 12px;
}

.question-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.question-chips .van-chip {
  cursor: pointer;
  text-align: left;
  padding: 8px 12px;
}

.candidate-titles {
  margin-top: 6px;
}

.candidate-title {
  font-size: 13px;
  color: #444;
  padding: 4px 0;
}

.skill-choices {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e0e0e0;
}

.skill-choices-title {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.skill-choices-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-choices-list .van-chip {
  cursor: pointer;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 16px;
}

.skill-choices-list .van-chip.van-chip--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

:deep(pre) {
  background-color: #f0f0f0;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}

:deep(code) {
  font-family: monospace;
  background-color: #f0f0f0;
  padding: 2px 4px;
  border-radius: 4px;
}

:deep(p) {
  margin: 8px 0;
}

:deep(ul), :deep(ol) {
  padding-left: 20px;
}

:deep(a) {
  color: #1989fa;
  text-decoration: none;
}
</style>
