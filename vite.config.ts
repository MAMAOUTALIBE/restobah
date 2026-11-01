import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

// STC_API_TARGET and STC_WEB_PORT let scripts/e2e.py run an isolated copy next to `npm run dev:all`.
const apiTarget=process.env.STC_API_TARGET||'http://127.0.0.1:8000';
const webPort=Number(process.env.STC_WEB_PORT||5173);

export default defineConfig({
  plugins:[react()],
  server:{
    host:'127.0.0.1',port:webPort,strictPort:true,
    proxy:Object.fromEntries(['/api','/admin','/crm','/static','/media'].map(path=>[path,{target:apiTarget,changeOrigin:false}])),
  },
  preview:{host:'127.0.0.1',port:4173,strictPort:true},
});
