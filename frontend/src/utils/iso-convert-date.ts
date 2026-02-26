/**
 * ISO 8601 形式の日付文字列を YYYY/MM/DD HH:mm 形式に変換
 * バックエンド保存: UTC
 * フロントエンド表示: ブラウザのローカルタイムゾーン（日本時間 JST）
 */
export function isoConvertDate(isoString: string): string {
  const date = new Date(isoString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}/${month}/${day} ${hours}:${minutes}`;
}
