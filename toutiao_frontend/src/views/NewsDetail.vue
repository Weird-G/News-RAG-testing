<template>
  <div class="news-detail">
    <van-nav-bar
      title="新闻详情"
      left-text="返回"
      left-arrow
      @click-left="onClickLeft"
      fixed
    >
      <template #right>
        <van-icon name="service" size="20" class="share-ai-icon" @click="shareToAI" />
      </template>
    </van-nav-bar>
    
    <div class="detail-content" v-if="newsStore.newsDetail.id">
      <div class="title-container">
        <h1 class="title">{{ newsStore.newsDetail.title }}</h1>
        <van-button 
          class="favorite-btn" 
          :icon="isFavorite ? 'star' : 'star-o'" 
          :class="{ 'is-favorite': isFavorite }"
          @click="toggleFavorite"
        />
      </div>
      
      <div class="info">
        <span>{{ newsStore.newsDetail.author }}</span>
        <span>{{ newsStore.newsDetail.publishTime }}</span>
        <span>{{ newsStore.newsDetail.views }} 阅读</span>
      </div>

      <div class="ai-share-banner" @click="shareToAI">
        <div class="ai-share-left">
          <div class="ai-share-icon">🤖</div>
          <div class="ai-share-text">
            <div class="ai-share-title">让AI分析这篇新闻</div>
            <div class="ai-share-desc">总结、提取关键信息、生成追问...</div>
          </div>
        </div>
        <van-button type="primary" size="small" round>AI分析 →</van-button>
      </div>
      
      <div class="cover" v-if="newsStore.newsDetail.image">
        <img :src="newsStore.newsDetail.image" :alt="newsStore.newsDetail.title">
      </div>
      
      <div class="content">
        <p v-for="(paragraph, index) in contentParagraphs" :key="index">
          {{ paragraph }}
        </p>
      </div>
      
      <div class="related-news" v-if="newsStore.newsDetail.relatedNews?.length">
        <h3>相关推荐</h3>
        <div class="related-list">
          <div 
            class="related-item" 
            v-for="item in newsStore.newsDetail.relatedNews" 
            :key="item.id"
            @click="goToRelatedNews(item.id)"
          >
            <div class="related-image">
              <img :src="item.image" :alt="item.title">
            </div>
            <div class="related-title">{{ item.title }}</div>
          </div>
        </div>
      </div>
    </div>
    
    <van-empty v-else description="加载中..." />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNewsStore } from '../store/modules/news'
import { useHistoryStore } from '../store/modules/history'
import { useFavoriteStore } from '../store/modules/favorite'
import { useUserStore } from '../store/user'
import { showToast } from 'vant'
import { shareNewsToAI } from '../utils/request'
import { useAiShareStore } from '../store/modules/aiShare'

const route = useRoute()
const router = useRouter()
const newsStore = useNewsStore()
const historyStore = useHistoryStore()
const favoriteStore = useFavoriteStore()
const userStore = useUserStore()
const aiShareStore = useAiShareStore()

// 获取路由参数中的新闻ID
const newsId = computed(() => Number(route.params.id))

// 将内容拆分为段落
const contentParagraphs = computed(() => {
  if (!newsStore.newsDetail.content) return []
  return newsStore.newsDetail.content.split('\n\n').filter(p => p.trim())
})

// 返回上一页
const onClickLeft = () => {
  router.back()
}

// 跳转到相关新闻
const goToRelatedNews = (id) => {
  router.push(`/news/detail/${id}`)
}

// 分享新闻给AI
const shareToAI = async () => {
  if (!newsStore.newsDetail.id) return
  
  showToast({ message: '正在分析新闻...', position: 'bottom', forbidClick: true, duration: 0 })
  
  try {
    const result = await shareNewsToAI(
      newsStore.newsDetail.id,
      newsStore.newsDetail.title,
      newsStore.newsDetail.content
    )
    
    showToast.closeAll()
    
    if (result.code === 200 && result.data) {
      const data = result.data
      // 存储新闻完整数据到store，供AI对话框继续使用
      aiShareStore.setSharedNews({
        newsId: data.news_id,
        newsTitle: data.news_title,
        newsContent: newsStore.newsDetail.content
      })
      
      router.push({
        path: '/ai-chat',
        query: {
          share_news: '1',
          news_id: data.news_id,
          news_title: encodeURIComponent(data.news_title),
          skill_results: encodeURIComponent(JSON.stringify(data.skill_results)),
          formatted_text: encodeURIComponent(data.formatted_text),
          skill_choices: encodeURIComponent(JSON.stringify(data.skill_choices || []))
        }
      })
    } else {
      showToast({ message: '分析失败，请重试', position: 'bottom' })
    }
  } catch (error) {
    console.error('分享AI失败:', error)
    showToast.closeAll()
    showToast({ message: '网络错误，请重试', position: 'bottom' })
  }
}

// 判断当前新闻是否已收藏
const isFavorite = computed(() => {
  return favoriteStore.isFavorite(newsId.value)
})

// 切换收藏状态
const toggleFavorite = async () => {
  // 判断用户是否已登录
  if (!userStore.getLoginStatus) {
    // 未登录则跳转到登录页
    showToast({
      message: '请先登录后再收藏',
      position: 'bottom',
    })
    router.push('/login')
    return
  }
  
  // 已登录则调用API切换收藏状态
  const status = await favoriteStore.toggleFavorite(newsStore.newsDetail)
  
  if (status === true) {
    showToast({
      message: '已添加到收藏',
      position: 'bottom',
    })
  } else if (status === false) {
    showToast({
      message: '已取消收藏',
      position: 'bottom',
    })
  } else {
    // status为null表示操作失败
    showToast({
      message: '操作失败，请稍后重试',
      position: 'bottom',
    })
  }
}

// 加载新闻详情、收藏状态等数据（抽取为函数，供 watch 和 onMounted 共用）
const loadPageData = async (id) => {
  if (!id) return
  
  // 重置旧数据
  newsStore.newsDetail = {}
  
  // 加载新闻详情
  await newsStore.getNewsDetail(id)
  
  if (newsStore.newsDetail.id) {
    // 记录浏览历史
    if (userStore.getLoginStatus) {
      try {
        await historyStore.addHistoryApi(newsStore.newsDetail.id);
      } catch (error) {
        console.error('记录浏览历史API失败:', error);
      }
    }
    
    // 加载收藏数据
    favoriteStore.loadFavorites()
    
    // 检查文章收藏状态
    if (userStore.getLoginStatus) {
      const result = await favoriteStore.checkFavoriteStatusApi(newsStore.newsDetail.id)
      if (result.success && !result.isLocal) {
        if (result.isFavorite && !favoriteStore.isFavorite(newsStore.newsDetail.id)) {
          favoriteStore.addFavorite(newsStore.newsDetail)
        } else if (!result.isFavorite && favoriteStore.isFavorite(newsStore.newsDetail.id)) {
          favoriteStore.removeFavorite(newsStore.newsDetail.id)
        }
      }
    }
  }
}

// 监听路由参数变化，实现相关推荐点击跳转后重新加载数据
watch(newsId, (newId) => {
  if (newId) loadPageData(newId)
})

// 组件首次挂载时加载数据
onMounted(() => {
  loadPageData(newsId.value)
})
</script>

<style scoped>
.news-detail {
  padding-top: 46px;
  background-color: #fff;
  min-height: 100vh;
}

.share-ai-icon {
  color: #667eea;
  cursor: pointer;
}

.ai-share-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  cursor: pointer;
  transition: transform 0.2s;
}

.ai-share-banner:active {
  transform: scale(0.98);
}

.ai-share-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-share-icon {
  font-size: 28px;
}

.ai-share-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.ai-share-desc {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}

.detail-content {
  padding: 16px;
}

.title-container {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.title {
  font-size: 22px;
  font-weight: bold;
  line-height: 1.4;
  margin: 0;
  flex: 1;
}

.favorite-btn {
  flex-shrink: 0;
  margin-left: 10px;
  padding: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
}

.favorite-btn.is-favorite {
  color: #ff9500;
}

.info {
  display: flex;
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
}

.info span {
  margin-right: 12px;
}

.cover {
  margin-bottom: 16px;
}

.cover img {
  width: 100%;
  border-radius: 4px;
}

.content {
  font-size: 16px;
  line-height: 1.8;
  color: #333;
}

.content p {
  margin-bottom: 16px;
  text-align: justify;
}

.related-news {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 8px solid #f5f5f5;
}

.related-news h3 {
  font-size: 18px;
  margin: 0 0 16px;
}

.related-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.related-item {
  display: flex;
  align-items: center;
}

.related-image {
  width: 80px;
  height: 60px;
  margin-right: 12px;
  flex-shrink: 0;
}

.related-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
}

.related-title {
  font-size: 14px;
  line-height: 1.4;
  flex: 1;
}
</style>