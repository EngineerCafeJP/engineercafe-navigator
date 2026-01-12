import { NextRequest, NextResponse } from 'next/server';

// バックエンドAPI URL
const BACKEND_API_URL = process.env.BACKEND_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { action, question, sessionId, language, text, fromLanguage, toLanguage } = body;

    // バックエンドAPIにプロキシ
    const backendUrl = `${BACKEND_API_URL}/api/chat`;
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: question || text,
        session_id: sessionId,
        language: language || 'ja',
      }),
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const result = await response.json();

    return NextResponse.json({
      success: true,
      answer: result.answer,
      emotion: result.emotion,
      metadata: result.metadata,
    });
  } catch (error) {
    console.error('Q&A API error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action');

    switch (action) {
      case 'question_categories':
        const categories = [
          {
            id: 'pricing',
            name: 'Pricing & Membership',
            nameJa: '料金・会員制度',
            description: 'Questions about pricing plans and membership options',
            descriptionJa: '料金プランや会員制度に関する質問',
          },
          {
            id: 'facilities',
            name: 'Facilities & Equipment',
            nameJa: '施設・設備',
            description: 'Questions about workspace facilities and available equipment',
            descriptionJa: 'ワークスペースの施設や利用可能な設備に関する質問',
          },
          {
            id: 'access',
            name: 'Access & Location',
            nameJa: 'アクセス・所在地',
            description: 'Questions about location, hours, and access methods',
            descriptionJa: '場所、営業時間、アクセス方法に関する質問',
          },
          {
            id: 'events',
            name: 'Events & Community',
            nameJa: 'イベント・コミュニティ',
            description: 'Questions about events, networking, and community activities',
            descriptionJa: 'イベント、ネットワーキング、コミュニティ活動に関する質問',
          },
          {
            id: 'membership',
            name: 'Membership & Registration',
            nameJa: '会員登録・手続き',
            description: 'Questions about membership registration and processes',
            descriptionJa: '会員登録や手続きに関する質問',
          },
          {
            id: 'technical',
            name: 'Technical Support',
            nameJa: '技術サポート',
            description: 'Questions about internet, equipment, and technical support',
            descriptionJa: 'インターネット、機器、技術サポートに関する質問',
          },
          {
            id: 'general',
            name: 'General Inquiries',
            nameJa: '一般的なお問い合わせ',
            description: 'General questions about Engineer Cafe services',
            descriptionJa: 'エンジニアカフェのサービスに関する一般的な質問',
          },
        ];

        return NextResponse.json({
          success: true,
          categories,
        });

      case 'sample_questions':
        const sampleQuestions = {
          ja: [
            '料金プランについて教えてください',
            '営業時間は何時から何時までですか？',
            'Wi-Fiの速度はどのくらいですか？',
            '会議室の予約方法を教えてください',
            'コーヒーは無料ですか？',
            'イベントの予定はありますか？',
          ],
          en: [
            'Can you tell me about the pricing plans?',
            'What are your operating hours?',
            'How fast is the Wi-Fi connection?',
            'How can I book a meeting room?',
            'Is coffee complimentary?',
            'Are there any upcoming events?',
          ],
        };

        const language = searchParams.get('language') || 'ja';

        return NextResponse.json({
          success: true,
          questions: sampleQuestions[language as keyof typeof sampleQuestions] || sampleQuestions.ja,
        });

      case 'health':
        return NextResponse.json({
          success: true,
          status: 'healthy',
          backend: BACKEND_API_URL,
        });

      default:
        return NextResponse.json(
          { error: 'Action parameter required' },
          { status: 400 }
        );
    }
  } catch (error) {
    console.error('Q&A API GET error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

// Handle OPTIONS for CORS
export async function OPTIONS(request: NextRequest) {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}
