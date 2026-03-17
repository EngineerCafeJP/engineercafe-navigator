'use client';

import { startTransition, useState } from 'react';

import {
  completeReception as completeReceptionRequest,
  respondReception,
  startReception as startReceptionRequest,
  type CompleteReceptionResponse,
  type ReceptionStage,
} from '@/lib/reception-api';

export interface ReceptionMessage {
  id: string;
  role: 'assistant' | 'visitor';
  text: string;
}

export interface UseReceptionOptions {
  sessionId: string;
  language?: string;
  triggerType?: string;
}

interface UseReceptionResult {
  stage: ReceptionStage;
  responseText: string | null;
  purpose: string | null;
  error: string | null;
  isLoading: boolean;
  receptionSessionId: string | null;
  completion: CompleteReceptionResponse | null;
  messages: ReceptionMessage[];
  startReception: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  completeReception: () => Promise<CompleteReceptionResponse>;
  resetReception: () => void;
}

function createMessage(role: ReceptionMessage['role'], text: string): ReceptionMessage {
  return {
    id: `${role}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
    role,
    text,
  };
}

export function useReception({
  sessionId,
  language = 'ja',
  triggerType = 'button_press',
}: UseReceptionOptions): UseReceptionResult {
  const [stage, setStage] = useState<ReceptionStage>('idle');
  const [responseText, setResponseText] = useState<string | null>(null);
  const [purpose, setPurpose] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [receptionSessionId, setReceptionSessionId] = useState<string | null>(null);
  const [completion, setCompletion] = useState<CompleteReceptionResponse | null>(null);
  const [messages, setMessages] = useState<ReceptionMessage[]>([]);

  const resetReception = () => {
    setStage('idle');
    setResponseText(null);
    setPurpose(null);
    setError(null);
    setIsLoading(false);
    setReceptionSessionId(null);
    setCompletion(null);
    setMessages([]);
  };

  const startReception = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await startReceptionRequest({
        session_id: sessionId,
        language,
        trigger_type: triggerType,
      });

      startTransition(() => {
        setReceptionSessionId(result.reception_session_id);
        setStage(result.stage);
        setResponseText(result.greeting);
        setPurpose(null);
        setCompletion(null);
        setMessages([createMessage('assistant', result.greeting)]);
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to start reception');
    } finally {
      setIsLoading(false);
    }
  };

  const sendMessage = async (message: string) => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || !receptionSessionId) {
      return;
    }

    setIsLoading(true);
    setError(null);
    setMessages((currentMessages) => [...currentMessages, createMessage('visitor', trimmedMessage)]);

    try {
      const result = await respondReception({
        session_id: sessionId,
        reception_session_id: receptionSessionId,
        message: trimmedMessage,
      });

      startTransition(() => {
        setStage(result.stage);
        setResponseText(result.response);
        setPurpose(result.purpose);
        setMessages((currentMessages) => [
          ...currentMessages,
          createMessage('assistant', result.response),
        ]);
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to send message');
    } finally {
      setIsLoading(false);
    }
  };

  const completeReception = async (): Promise<CompleteReceptionResponse> => {
    if (!receptionSessionId) {
      throw new Error('Reception session has not started');
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await completeReceptionRequest({
        session_id: sessionId,
        reception_session_id: receptionSessionId,
      });

      startTransition(() => {
        setStage('completed');
        setResponseText(result.response_text);
        setPurpose((currentPurpose) => currentPurpose ?? result.purpose_category);
        setCompletion(result);
        setMessages((currentMessages) => [
          ...currentMessages,
          createMessage('assistant', result.response_text),
        ]);
      });

      return result;
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : 'Failed to complete reception';
      setError(message);
      throw new Error(message);
    } finally {
      setIsLoading(false);
    }
  };

  return {
    stage,
    responseText,
    purpose,
    error,
    isLoading,
    receptionSessionId,
    completion,
    messages,
    startReception,
    sendMessage,
    completeReception,
    resetReception,
  };
}
