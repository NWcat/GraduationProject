import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import { 
  ElLoading, ElAlert, ElEmpty, ElSelect, ElOption, 
  ElCard, ElForm, ElFormItem, ElInput, ElButton 
} from 'element-plus';

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.use(ElLoading).use(ElAlert).use(ElEmpty)
  .use(ElSelect).use(ElOption).use(ElCard)
  .use(ElForm).use(ElFormItem).use(ElInput).use(ElButton);
  
app.mount('#app')
