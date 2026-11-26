/** 场次状态与日期的展示文案；历史页和会话标题共用，避免两处写法不一致。 */
export const STATUS_LABELS: Record<string, string> = {
  ready: "待继续",
  running: "练习中",
  scoring: "评分中",
  completed: "已完成",
};

export const formatDate = (value: string) =>
  new Date(value).toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
