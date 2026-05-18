'use client';

/**
 * Kiosk: reception PDF from public/reception/engineer-cafe-{ja,en}.pdf.
 * Optional per-page audio: public/reception/audio/{lang}/01.mp3 …
 * Generated narration uses the backend Piper Plus voice path.
 */
import { useKeyboardControls } from '@/app/hooks/useKeyboardControls';
import { receptionGuidePdfUrl } from '@/lib/reception/reception-pdf-constants';
import {
  ReceptionPdfErrorView,
  ReceptionPdfLandscapeView,
  ReceptionPdfLoadingView,
  ReceptionPdfRotatePrompt,
} from './reception-pdf-guide/ReceptionPdfGuideView';
import type { ReceptionPdfGuideProps } from './reception-pdf-guide/types';
import { useLandscapeReady } from './reception-pdf-guide/useLandscapeReady';
import { useReceptionPdfCanvas } from './reception-pdf-guide/useReceptionPdfCanvas';
import { useReceptionPdfPlayback } from './reception-pdf-guide/useReceptionPdfPlayback';
import { useSlideSwipeNavigation } from './reception-pdf-guide/useSlideSwipeNavigation';

export default function ReceptionPdfGuide({
  language,
  rotateLandscapeHint,
  autoStartKey,
  className,
  sessionId = '',
  onVisemeControl,
  onExpressionControl,
  volume = 80,
  onPresentationComplete,
}: ReceptionPdfGuideProps) {
  const landscapeReady = useLandscapeReady();
  const {
    canvasRef,
    wrapRef,
    totalPages,
    currentPage,
    setCurrentPage,
    error,
    setError,
    isLoading,
  } = useReceptionPdfCanvas(receptionGuidePdfUrl(language), landscapeReady);

  const {
    audioPermissionRequired,
    enableAudioAndResume,
    gotoSlide,
    isPlaying,
    nextSlide,
    previousSlide,
    toggleAutoPlay,
  } = useReceptionPdfPlayback({
    autoStartKey,
    currentPage,
    isLoading,
    language,
    landscapeReady,
    onExpressionControl,
    onPresentationComplete,
    onVisemeControl,
    sessionId,
    setCurrentPage,
    setError,
    totalPages,
    volume,
  });

  const {
    onSlidePointerCancel,
    onSlidePointerDown,
    onSlidePointerUp,
  } = useSlideSwipeNavigation(nextSlide, previousSlide);

  useKeyboardControls({
    onPrevious: previousSlide,
    onReset: () => gotoSlide(1),
    onTogglePlay: toggleAutoPlay,
    onNumberKey: (num) => gotoSlide(num),
    enabled: landscapeReady && !isLoading && !error,
  });

  if (isLoading) {
    return <ReceptionPdfLoadingView className={className} language={language} />;
  }

  if (error) {
    return <ReceptionPdfErrorView className={className} error={error} />;
  }

  if (!landscapeReady) {
    return (
      <ReceptionPdfRotatePrompt
        className={className}
        rotateLandscapeHint={rotateLandscapeHint}
      />
    );
  }

  return (
    <ReceptionPdfLandscapeView
      audioPermissionRequired={audioPermissionRequired}
      canvasRef={canvasRef}
      className={className}
      currentPage={currentPage}
      enableAudioAndResume={enableAudioAndResume}
      gotoSlide={gotoSlide}
      isPlaying={isPlaying}
      language={language}
      nextSlide={nextSlide}
      onSlidePointerCancel={onSlidePointerCancel}
      onSlidePointerDown={onSlidePointerDown}
      onSlidePointerUp={onSlidePointerUp}
      previousSlide={previousSlide}
      toggleAutoPlay={toggleAutoPlay}
      totalPages={totalPages}
      wrapRef={wrapRef}
    />
  );
}
