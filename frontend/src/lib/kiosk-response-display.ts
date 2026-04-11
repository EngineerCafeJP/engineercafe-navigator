export type KioskResponseSessionState = 'idle' | 'listening' | 'processing' | 'speaking';

export function getKioskResponseDisplayState({
  response,
  sessionState,
  responseVisibleUntil,
  defaultPromptVisibleUntil,
  now,
  defaultPrompt,
}: {
  response: string;
  sessionState: KioskResponseSessionState;
  responseVisibleUntil: number;
  defaultPromptVisibleUntil: number;
  now: number;
  defaultPrompt: string;
}): {
  text: string;
  showBubble: boolean;
  isLiveResponse: boolean;
} {
  const isLiveResponse =
    response.length > 0 &&
    (sessionState === 'speaking' || responseVisibleUntil > now);
  const isDefaultPrompt =
    sessionState === 'idle' &&
    defaultPromptVisibleUntil > now &&
    !isLiveResponse;

  if (isLiveResponse) {
    return {
      text: response,
      showBubble: true,
      isLiveResponse: true,
    };
  }

  if (isDefaultPrompt) {
    return {
      text: defaultPrompt,
      showBubble: true,
      isLiveResponse: false,
    };
  }

  return {
    text: '',
    showBubble: false,
    isLiveResponse: false,
  };
}
