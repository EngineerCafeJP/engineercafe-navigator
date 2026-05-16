export function getMemberCardPhase2ReceptionMessage(
  memberNumber: number,
  language: string,
): string {
  if (language === 'ja') {
    return (
      `会員番号 ${memberNumber} を読み取りました。` +
      '現在は会員番号の確認まで対応しています。' +
      '会員情報に基づく座席の提案や個別案内は、フェーズ2以降で対応予定です。' +
      'ご用件をお聞かせください。'
    );
  }

  return (
    `Read member number ${memberNumber}. ` +
    'For now, this kiosk can confirm the member number only. ' +
    'Seat suggestions and personalized guidance based on member records are planned for Phase 2 or later. ' +
    'How can I help you today?'
  );
}
