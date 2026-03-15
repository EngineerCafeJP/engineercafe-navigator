#!/usr/bin/env tsx

import { config } from 'dotenv';
config();

import { knowledgeBaseUtils, KnowledgeBaseEntry } from '../src/lib/knowledge-base-utils';

// Sample knowledge base entries for Engineer Cafe
const sampleEntries: KnowledgeBaseEntry[] = [
  // Japanese entries
  {
    content: 'エンジニアカフェは福岡市中央区天神にある、ITエンジニア向けの公共施設です。営業時間は9:00-22:00、休館日は毎月最終月曜日（祝日の場合は翌平日）と年末年始（12/29-1/3）です。高速インターネット、電源完備、会議室、イベントスペースなどの設備を無料で提供しています。',
    category: '基本情報',
    subcategory: '概要',
    language: 'ja',
    source: 'official',
    metadata: { title: 'エンジニアカフェとは' }
  },
  {
    content: '月額会員プランは8,000円から。ドロップイン利用は1時間500円、1日最大2,000円。学生割引あり（50%OFF）。法人プランもご用意しています。',
    category: '料金',
    subcategory: '会員プラン',
    language: 'ja',
    source: 'official',
    metadata: { title: '料金プラン' }
  },
  {
    content: '最大20名収容可能な会議室を3室完備。プロジェクター、ホワイトボード、Web会議システム完備。会員は1時間1,000円、非会員は1時間2,000円でご利用いただけます。',
    category: '設備',
    subcategory: '会議室',
    language: 'ja',
    source: 'official',
    metadata: { title: '会議室情報' }
  },
  {
    content: '地下MTGスペース：2名以上から利用可能、ホームページから予約可能（当日予約不可）、2時間区切りでの利用、ミーティングや打ち合わせに最適なスペースです。',
    category: '設備',
    subcategory: '地下MTGスペース',
    language: 'ja',
    source: 'official',
    metadata: { title: '地下MTGスペース' }
  },
  {
    content: '地下集中スペース：6ブース完備、予約不可、おしゃべり禁止、集中作業専用エリア、静かな環境で個人作業に集中できます。',
    category: '設備',
    subcategory: '地下集中スペース',
    language: 'ja',
    source: 'official',
    metadata: { title: '地下集中スペース' }
  },
  {
    content: '地下アンダースペース：予約不可、1Fと同じフリーアドレス形式、拡張画面あり、防音室1つ（1時間区切り）、自由に利用できるワークスペースです。',
    category: '設備',
    subcategory: '地下アンダースペース',
    language: 'ja',
    source: 'official',
    metadata: { title: '地下アンダースペース' }
  },
  {
    content: '地下Makersスペース：3Dプリンタやレーザーカッターが利用可能、初回利用時はHPから初回講習を申し込み必須、ホームページから予約可能（当日予約不可）、ものづくりに最適なスペースです。',
    category: '設備',
    subcategory: '地下Makersスペース',
    language: 'ja',
    source: 'official',
    metadata: { 
      title: '地下Makersスペース',
      duplicateOf: 'メイカースペース',
      note: 'Specific basement location reference for Makers Space'
    }
  },
  {
    content: 'エンジニアカフェでは毎週技術勉強会やハンズオンセミナーを開催。AI、Web開発、モバイル開発、インフラなど幅広いテーマを扱っています。会員は無料で参加可能。',
    category: 'イベント',
    subcategory: '勉強会',
    language: 'ja',
    source: 'official',
    metadata: { title: 'イベント・勉強会' }
  },
  {
    content: '福岡市営地下鉄天神駅から徒歩3分。西鉄福岡（天神）駅から徒歩5分。駐車場はございませんが、近隣にコインパーキングが多数あります。',
    category: 'アクセス',
    subcategory: '交通',
    language: 'ja',
    source: 'official',
    metadata: { title: 'アクセス情報' }
  },
  {
    content: '高速光ファイバー回線（上下1Gbps）を完備。有線LAN、Wi-Fi両方利用可能。VPN接続対応。セキュアな開発環境をご提供します。',
    category: '設備',
    subcategory: 'インターネット',
    language: 'ja',
    source: 'official',
    metadata: { title: 'インターネット環境' }
  },
  {
    content: '3Dプリンター、レーザーカッター、はんだごてなどのメイカースペースを併設。IoTデバイスの試作やプロトタイピングが可能です。利用は予約制。',
    category: '設備',
    subcategory: 'メイカースペース',
    language: 'ja',
    source: 'official',
    metadata: { title: 'メイカースペース' }
  },
  {
    content: '技術書ライブラリーには最新の技術書籍が1000冊以上。オライリー、技術評論社などの定番書籍から最新刊まで。会員は自由に閲覧可能。',
    category: '設備',
    subcategory: 'ライブラリー',
    language: 'ja',
    source: 'official',
    metadata: { title: '技術書ライブラリー' }
  },

  // English entries
  {
    content: 'Engineer Cafe is a coworking space for IT engineers located in Tenjin, Fukuoka. Open 24/7 with high-speed internet, power outlets, free drinks, and more facilities.',
    category: 'General',
    subcategory: 'Overview',
    language: 'en',
    source: 'official',
    metadata: { title: 'About Engineer Cafe' }
  },
  {
    content: 'Monthly membership starts from ¥8,000. Drop-in rate is ¥500/hour, max ¥2,000/day. Student discount available (50% OFF). Corporate plans also available.',
    category: 'Pricing',
    subcategory: 'Membership',
    language: 'en',
    source: 'official',
    metadata: { title: 'Pricing Plans' }
  },
  {
    content: '3 meeting rooms available, each accommodating up to 20 people. Equipped with projectors, whiteboards, and video conferencing systems. Members: ¥1,000/hour, Non-members: ¥2,000/hour.',
    category: 'Facilities',
    subcategory: 'Meeting Rooms',
    language: 'en',
    source: 'official',
    metadata: { title: 'Meeting Room Information' }
  },
  {
    content: 'Basement MTG Space: Available for 2+ people, reservable via website (no same-day booking), 2-hour slots, ideal for meetings and discussions.',
    category: 'Facilities',
    subcategory: 'Basement MTG Space',
    language: 'en',
    source: 'official',
    metadata: { title: 'Basement MTG Space' }
  },
  {
    content: 'Basement Focus Space: 6 booths available, no reservation required, no talking allowed, dedicated area for concentrated individual work in a quiet environment.',
    category: 'Facilities',
    subcategory: 'Basement Focus Space',
    language: 'en',
    source: 'official',
    metadata: { title: 'Basement Focus Space' }
  },
  {
    content: 'Basement Under Space: No reservation required, free address style like 1F, equipped with extended displays, includes 1 soundproof room (1-hour slots), flexible workspace for general use.',
    category: 'Facilities',
    subcategory: 'Basement Under Space',
    language: 'en',
    source: 'official',
    metadata: { title: 'Basement Under Space' }
  },
  {
    content: 'Basement Makers Space: 3D printers and laser cutters available, first-time users must book initial training via website, reservable via website (no same-day booking), perfect for prototyping and creation.',
    category: 'Facilities',
    subcategory: 'Basement Makers Space',
    language: 'en',
    source: 'official',
    metadata: { title: 'Basement Makers Space' }
  },
  {
    content: 'Weekly tech meetups and hands-on seminars covering AI, web development, mobile development, infrastructure, and more. Free for members to attend.',
    category: 'Events',
    subcategory: 'Meetups',
    language: 'en',
    source: 'official',
    metadata: { title: 'Events & Meetups' }
  },
  {
    content: '3-minute walk from Tenjin Station (Fukuoka City Subway). 5-minute walk from Nishitetsu Fukuoka (Tenjin) Station. No parking available, but many coin parking lots nearby.',
    category: 'Access',
    subcategory: 'Transportation',
    language: 'en',
    source: 'official',
    metadata: { title: 'Access Information' }
  },
  {
    content: 'High-speed fiber optic connection (1Gbps up/down). Both wired LAN and Wi-Fi available. VPN-friendly. Secure development environment provided.',
    category: 'Facilities',
    subcategory: 'Internet',
    language: 'en',
    source: 'official',
    metadata: { title: 'Internet Environment' }
  },
  {
    content: 'Maker space with 3D printers, laser cutters, soldering stations, and more. Perfect for IoT device prototyping. Reservation required.',
    category: 'Facilities',
    subcategory: 'Maker Space',
    language: 'en',
    source: 'official',
    metadata: { title: 'Maker Space' }
  },

  // Saino Cafe Location Information
  {
    content: 'sainoカフェは、エンジニアカフェと同じフロア（1階）の階段手前に位置しています。2階ではありません。コーヒー、軽食、デザートなどを提供しており、エンジニアカフェ利用者の休憩や軽食に便利です。',
    category: '設備',
    subcategory: 'sainoカフェ',
    language: 'ja',
    source: 'official',
    metadata: { 
      title: 'sainoカフェの場所',
      importance: 'high',
      tags: ['cafe', 'location', 'same-floor']
    }
  },
  {
    content: 'saino cafe is located on the same floor (1st floor) as Engineer Cafe, near the stairs area. It is NOT on the 2nd floor. The cafe offers coffee, light meals, and desserts, making it convenient for Engineer Cafe users to take breaks and grab refreshments.',
    category: 'Facilities',
    subcategory: 'saino cafe',
    language: 'en',
    source: 'official',
    metadata: { 
      title: 'saino cafe location',
      importance: 'high',
      tags: ['cafe', 'location', 'same-floor']
    }
  },
  // Saino Cafe Operating Hours and Business Days
  {
    content: 'sainoカフェの営業時間は平日10:00〜20:00、土日祝日10:00〜18:00です。定休日は毎週月曜日（月曜日が祝日の場合は翌平日）および年末年始（12/29〜1/3）です。エンジニアカフェと同じフロア（1階）の階段手前に位置しており、コーヒー、軽食、デザートなどを提供しています。',
    category: '設備',
    subcategory: 'sainoカフェ',
    language: 'ja',
    source: 'official',
    metadata: { 
      title: 'sainoカフェの営業時間と定休日',
      importance: 'high',
      tags: ['cafe', 'hours', 'business-days', 'saino', '営業時間', '定休日']
    }
  },
  {
    content: 'saino cafe operating hours are weekdays 10:00-20:00, weekends and holidays 10:00-18:00. Closed every Monday (if Monday is a holiday, closed the following weekday) and during New Year holidays (December 29 - January 3). Located on the same floor (1st floor) as Engineer Cafe near the stairs, offering coffee, light meals, and desserts.',
    category: 'Facilities',
    subcategory: 'saino cafe',
    language: 'en',
    source: 'official',
    metadata: { 
      title: 'saino cafe operating hours and business days',
      importance: 'high',
      tags: ['cafe', 'hours', 'business-days', 'saino', 'operating-hours', 'closed-days']
    }
  },
  {
    content: 'Tech book library with over 1000 latest technical books. From O\'Reilly classics to the latest publications. Free access for all members.',
    category: 'Facilities',
    subcategory: 'Library',
    language: 'en',
    source: 'official',
    metadata: { title: 'Tech Book Library' }
  }
];

async function seedKnowledgeBase() {
  console.log('🌱 Starting knowledge base seeding...\n');

  try {
    // Check current stats
    console.log('📊 Current knowledge base stats:');
    const statsBefore = await knowledgeBaseUtils.getStats();
    console.log(statsBefore);
    console.log('\n');

    // Add sample entries
    console.log(`📝 Adding ${sampleEntries.length} sample entries...`);
    const result = await knowledgeBaseUtils.addEntries(sampleEntries);
    
    console.log(`✅ Successfully added: ${result.successful}`);
    console.log(`❌ Failed to add: ${result.failed}`);
    
    if (result.errors.length > 0) {
      console.log('\n⚠️  Errors:');
      result.errors.forEach(({ index, error }) => {
        console.log(`  - Entry ${index}: ${error}`);
      });
    }

    // Embeddings are now managed by the backend, so this remains a no-op.
    console.log('\n🔄 Skipping frontend embedding backfill...');
    const updateResult = await knowledgeBaseUtils.updateMissingEmbeddings();
    console.log(`✅ Updated: ${updateResult.updated}`);
    console.log(`❌ Failed: ${updateResult.failed}`);

    // Show final stats
    console.log('\n📊 Final knowledge base stats:');
    const statsAfter = await knowledgeBaseUtils.getStats();
    console.log(statsAfter);

    console.log('\n✨ Knowledge base seeding completed!');
  } catch (error) {
    console.error('\n💥 Error seeding knowledge base:', error);
    process.exit(1);
  }
}

// Run the seeding script
seedKnowledgeBase();
