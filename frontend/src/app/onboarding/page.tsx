import CustomerGuideShell from '@/app/components/presentation/CustomerGuideShell';

interface OnboardingPageProps {
  searchParams: Promise<{
    autoplay?: string;
    lang?: string;
  }>;
}

export default async function OnboardingPage({ searchParams }: OnboardingPageProps) {
  const params = await searchParams;
  const language = params.lang === 'en' ? 'en' : 'ja';
  const autoPlay = params.autoplay === '1';

  return <CustomerGuideShell language={language} autoPlay={autoPlay} />;
}
