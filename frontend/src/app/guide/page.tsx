import CustomerGuideShell from '@/app/components/presentation/CustomerGuideShell';

interface GuidePageProps {
  searchParams: Promise<{
    autoplay?: string;
    lang?: string;
  }>;
}

export default async function GuidePage({ searchParams }: GuidePageProps) {
  const params = await searchParams;
  const language = params.lang === 'en' ? 'en' : 'ja';
  const autoPlay = params.autoplay === '1';

  return <CustomerGuideShell language={language} autoPlay={autoPlay} />;
}
