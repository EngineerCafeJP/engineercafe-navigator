'use client';

import {
  useEffect,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from 'react';

export type ConversationHistoryItem = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

export function ConversationHistoryEffects({
  transcript,
  response,
  lastTranscriptRef,
  lastResponseRef,
  setConversationHistory,
}: {
  transcript: string;
  response: string;
  lastTranscriptRef: MutableRefObject<string>;
  lastResponseRef: MutableRefObject<string>;
  setConversationHistory: Dispatch<SetStateAction<ConversationHistoryItem[]>>;
}) {
  useEffect(() => {
    if (transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'user',
          text: transcript,
        },
      ]);
    }
  }, [lastTranscriptRef, setConversationHistory, transcript]);

  useEffect(() => {
    if (response && response !== lastResponseRef.current) {
      lastResponseRef.current = response;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'assistant',
          text: response,
        },
      ]);
    }
  }, [lastResponseRef, response, setConversationHistory]);

  return null;
}
