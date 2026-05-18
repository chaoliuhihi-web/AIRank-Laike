window.AIRANK_CONFIG = {
  siteOrigin: "https://airank.net.cn",
  siteName: "智界问道 AIRank 来客",
  companyName: "北京智界问道科技有限公司",
  contactPhone: "4001108776",
  contactPhoneDisplay: "400-110-8776",
  // Vercel 默认使用 /api/leads；Netlify 会通过 netlify.toml 重写到 /.netlify/functions/leads。
  leadEndpoint: "/api/leads",
  leadFallbackEndpoint: "/.netlify/functions/leads",
  diagnosisPath: "/diagnosis/",
  requestTimeout: 10000,
  successRedirect: "/thank-you/",
  enableRedirectAfterSubmit: true
};
