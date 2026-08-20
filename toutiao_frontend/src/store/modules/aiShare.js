import { defineStore } from 'pinia'

export const useAiShareStore = defineStore('aiShare', {
  state: () => ({
    sharedNews: null
  }),
  actions: {
    setSharedNews(data) {
      this.sharedNews = data
    },
    clearSharedNews() {
      this.sharedNews = null
    }
  }
})