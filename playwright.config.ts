import {defineConfig,devices} from '@playwright/test';
const baseURL=process.env.E2E_BASE_URL||'http://localhost:5173';
export default defineConfig({
 testDir:'./tests',timeout:40_000,expect:{timeout:8_000},fullyParallel:false,workers:2,
 // API contexts send Origin like a browser: Django requires it (or Referer) for HTTPS writes.
 use:{baseURL,extraHTTPHeaders:{Origin:baseURL},trace:'retain-on-failure',screenshot:'only-on-failure'},
 projects:[
  {name:'api',testMatch:'api.spec.ts'},
  {name:'admin',testMatch:'admin.spec.ts',use:{...devices['Desktop Chrome']}},
  {name:'desktop',testIgnore:['api.spec.ts','admin.spec.ts'],use:{...devices['Desktop Chrome']}},
  {name:'tablet',testIgnore:['api.spec.ts','admin.spec.ts'],use:{...devices['Desktop Chrome'],viewport:{width:768,height:1024},hasTouch:true}},
  {name:'mobile',testIgnore:['api.spec.ts','admin.spec.ts'],use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}},
 ],
});
