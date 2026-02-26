/**
 * ISO 8601 形式の日付文字列を YYYY/MM/DD HH:mm 形式に変換
 * バックエンド保存: UTC
 * フロントエンド表示: ブラウザのローカルタイムゾーン（日本時間 JST）
 */
export function isoConvertDate(isoString: string): string {
  const date = new Date(isoString);
  const formatter = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  const parts = formatter.formatToParts(date);
  const year = parts.find((p) => p.type === "year")?.value;
  const month = parts.find((p) => p.type === "month")?.value;
  const day = parts.find((p) => p.type === "day")?.value;
  const hour = parts.find((p) => p.type === "hour")?.value;
  const minute = parts.find((p) => p.type === "minute")?.value;

  return `${year}/${month}/${day} ${hour}:${minute}`;
}
