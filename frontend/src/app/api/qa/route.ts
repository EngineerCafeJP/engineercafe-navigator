import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { action, question, sessionId, language, text, fromLanguage, toLanguage, visitorId } = body;

    const query = (question || text || '').trim();
    if (!query) {
      return NextResponse.json(
        { error: '質問を入力してください', success: false },
        { status: 400 }
      );
    }

    const response = await backendFetch<{
      answer?: string;
      emotion?: string;
      metadata?: { vrm_control?: unknown } & Record<string, unknown>;
      vrm_control?: { name: string; duration: number; keyframes: unknown[] } | null;
    }>('/api/chat', {
      body: {
        query,
        session_id: sessionId,
        language: language || 'ja',
        visitor_id: visitorId,
      },
    });

    if (!response.ok) {
      return createBackendErrorResponse(response);
    }

    if (!response.data) {
      throw new Error('Backend API returned an empty response');
    }

    return NextResponse.json({
      success: true,
      answer: response.data.answer,
      emotion: response.data.emotion,
      metadata: response.data.metadata,
      vrm_control:
        response.data.vrm_control ??
        (response.data.metadata as { vrm_control?: unknown } | undefined)?.vrm_control ??
        null,
    });
  } catch (error) {
    console.error('Q&A API error:', error);
    return createInternalServerErrorResponse(error);
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
          backend: 'connected',
        });

      default:
        return NextResponse.json(
          { error: 'Action parameter required' },
          { status: 400 }
        );
    }
  } catch (error) {
    console.error('Q&A API GET error:', error);
    return createInternalServerErrorResponse(error);
  }
}
