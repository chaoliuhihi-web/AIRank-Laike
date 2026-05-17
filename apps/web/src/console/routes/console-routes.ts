export type ConsoleRoutePriority = "M1" | "M1.5" | "P2";

export type ConsoleRoute = {
  id: string;
  path: string;
  label: string;
  icon: string;
  sourceImage: string;
  priority: ConsoleRoutePriority;
};

export const consoleRoutes: ConsoleRoute[] = [
  {
    id: "dashboard",
    path: "/console",
    label: "工作台",
    icon: "Home",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_02 (1).png",
    priority: "M1",
  },
  {
    id: "checkup",
    path: "/console/checkup",
    label: "AI 收录体检",
    icon: "BadgeCheck",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_03 (2).png",
    priority: "M1",
  },
  {
    id: "facts",
    path: "/console/facts",
    label: "企业事实库",
    icon: "NotebookTabs",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_03 (3).png",
    priority: "M1",
  },
  {
    id: "questions",
    path: "/console/questions",
    label: "买家问题地图",
    icon: "Map",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_04 (4).png",
    priority: "M1",
  },
  {
    id: "gaps",
    path: "/console/gaps",
    label: "推荐缺口分析",
    icon: "ShieldCheck",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_04 (5).png",
    priority: "M1",
  },
  {
    id: "gap-questions",
    path: "/console/gaps/questions",
    label: "推荐缺口问题",
    icon: "ListChecks",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_07 (1).png",
    priority: "M1",
  },
  {
    id: "assets",
    path: "/console/assets",
    label: "AI 收录包",
    icon: "PackageCheck",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_08 (2).png",
    priority: "M1",
  },
  {
    id: "publishing",
    path: "/console/publishing",
    label: "发布提交",
    icon: "SquarePen",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_08 (3).png",
    priority: "M1.5",
  },
  {
    id: "assistant",
    path: "/console/assistant",
    label: "AI 来客助手",
    icon: "Bot",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_09 (4).png",
    priority: "P2",
  },
  {
    id: "reports",
    path: "/console/reports",
    label: "报表中心",
    icon: "FileChartColumn",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_10 (5).png",
    priority: "M1.5",
  },
  {
    id: "settings",
    path: "/console/settings",
    label: "设置中心",
    icon: "Settings",
    sourceImage: "AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_11 (6).png",
    priority: "M1.5",
  },
];
