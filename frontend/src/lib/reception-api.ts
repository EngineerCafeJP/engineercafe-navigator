export type ReceptionStage =
  | 'idle'
  | 'welcome'
  | 'camera_ocr'
  | 'text_input'
  | 'greeting'
  | 'purpose_hearing'
  | 'routing'
  | 'completed';

export type ReceptionActiveStage = Exclude<ReceptionStage, 'idle' | 'welcome' | 'camera_ocr' | 'text_input'>;

export interface VisitorIdentity {
  user_id?: number;
  name?: string;
  visit_count?: number;
  last_purpose?: { category: string; detail?: string };
}

export interface StartReceptionRequest {
  session_id: string;
  language: string;
  trigger_type: string;
  visitor_identity?: VisitorIdentity;
}

export interface StartReceptionResponse {
  reception_session_id: string;
  greeting: string;
  stage: ReceptionActiveStage;
}

export interface RespondReceptionRequest {
  session_id: string;
  reception_session_id: string;
  message: string;
}

export interface RespondReceptionResponse {
  response: string;
  stage: ReceptionActiveStage;
  purpose: { category: string; detail?: string } | null;
  next_action: string | null;
}

export interface CompleteReceptionRequest {
  session_id: string;
  reception_session_id: string;
}

export interface CompleteReceptionResponse {
  response_text: string;
  target_agent: string | null;
  requires_staff: boolean;
  purpose_category: string | null;
  action_type: string | null;
  action_data: Record<string, unknown> | null;
}

export interface ReceptionStatusResponse {
  session_id: string;
  stage: ReceptionActiveStage;
  visitor_type: string | null;
  purpose: string | null;
}

export interface SensorStatusResponse {
  triggered: boolean;
  device_id?: string;
  sensor_type?: string;
  distance_mm?: number;
  timestamp?: number;
}

interface ApiErrorPayload {
  error?: string;
  details?: string;
}

async function requestReceptionApi<TResponse>(
  input: RequestInfo,
  init?: RequestInit
): Promise<TResponse> {
  const response = await fetch(input, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  const isJson = response.headers.get('content-type')?.includes('application/json');
  const payload = isJson ? ((await response.json()) as TResponse | ApiErrorPayload) : null;

  if (!response.ok) {
    const apiError = payload as ApiErrorPayload | null;
    const message =
      apiError?.error ?? apiError?.details ?? `Reception API request failed with ${response.status}`;
    throw new Error(message);
  }

  return (payload ?? {}) as TResponse;
}

export async function startReception(
  request: StartReceptionRequest
): Promise<StartReceptionResponse> {
  return requestReceptionApi<StartReceptionResponse>('/api/reception/start', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function respondReception(
  request: RespondReceptionRequest
): Promise<RespondReceptionResponse> {
  return requestReceptionApi<RespondReceptionResponse>('/api/reception/respond', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function completeReception(
  request: CompleteReceptionRequest
): Promise<CompleteReceptionResponse> {
  return requestReceptionApi<CompleteReceptionResponse>('/api/reception/complete', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function getReceptionStatus(
  receptionSessionId: string,
  sessionId: string
): Promise<ReceptionStatusResponse> {
  const search = new URLSearchParams({ session_id: sessionId }).toString();

  return requestReceptionApi<ReceptionStatusResponse>(
    `/api/reception/status/${receptionSessionId}?${search}`,
    { method: 'GET' }
  );
}

export async function getSensorStatus(
  deviceId: string,
  since = 0
): Promise<SensorStatusResponse> {
  const search = new URLSearchParams({
    device_id: deviceId,
    since: String(since),
  }).toString();

  return requestReceptionApi<SensorStatusResponse>(`/api/reception/sensor-status?${search}`, {
    method: 'GET',
    cache: 'no-store',
  });
}
