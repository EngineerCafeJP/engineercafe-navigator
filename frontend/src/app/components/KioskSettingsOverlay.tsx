'use client';

import { cn } from '@/lib/cn';
import { overlayLabels } from '@/lib/kiosk-labels';
import {
  type KioskMicMode,
  type KioskTriggerMode,
  writeKioskMicMode,
  writeKioskTriggerMode,
} from '@/lib/kiosk-constants';
import type { CSSProperties, Dispatch, SetStateAction } from 'react';
import SettingsPanel, { type SettingsPanelPropsFromSource } from './SettingsPanel';
import type { ConversationHistoryItem } from './ConversationHistoryEffects';
import type { VoiceInterfaceRenderProps } from './VoiceInterface';

type KioskSettingsOverlayProps = {
  open: boolean;
  settingsPanelProps: SettingsPanelPropsFromSource | null;
  showSlideMode: boolean;
  screenPadding: CSSProperties;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  conversationHistory: ConversationHistoryItem[];
  voice: VoiceInterfaceRenderProps;
  triggerMode: KioskTriggerMode;
  micInputMode: KioskMicMode;
  setCurrentLanguage: Dispatch<SetStateAction<'ja' | 'en'>>;
  setTriggerMode: Dispatch<SetStateAction<KioskTriggerMode>>;
  setMicInputMode: Dispatch<SetStateAction<KioskMicMode>>;
  onClose: () => void;
  onOpenSlides: () => void;
  onCloseSlides: () => void;
};

export function KioskSettingsOverlay({
  open,
  settingsPanelProps,
  showSlideMode,
  screenPadding,
  labels,
  conversationHistory,
  voice,
  triggerMode,
  micInputMode,
  setCurrentLanguage,
  setTriggerMode,
  setMicInputMode,
  onClose,
  onOpenSlides,
  onCloseSlides,
}: KioskSettingsOverlayProps) {
  if (!open || !settingsPanelProps || showSlideMode) {
    return null;
  }

  return (
    <div className="absolute inset-0 z-40 pointer-events-none" aria-hidden={!open}>
      <div
        className="pointer-events-auto absolute top-0 flex max-h-full justify-end"
        style={{ top: screenPadding.paddingTop, right: screenPadding.paddingRight }}
      >
        <SettingsPanel
          {...settingsPanelProps}
          kiosk_language={voice.currentLanguage}
          kiosk_trigger_mode={triggerMode}
          kiosk_mic_mode={micInputMode}
          on_kiosk_language_change={setCurrentLanguage}
          on_kiosk_trigger_mode_change={(mode) => {
            setTriggerMode(mode);
            writeKioskTriggerMode(mode);
          }}
          on_kiosk_mic_mode_change={(mode) => {
            setMicInputMode(mode);
            writeKioskMicMode(mode);
          }}
          volume={Math.round(voice.volume * 100)}
          is_muted={voice.isMuted}
          on_volume_change={(value) => {
            voice.setVolume(value / 100);
          }}
          on_mute_toggle={() => {
            voice.setMuted(!voice.isMuted);
          }}
          tts_speed={voice.ttsSpeed}
          on_tts_speed_change={(value) => {
            voice.setTtsSpeed(value);
          }}
          show_close_button
          on_close={onClose}
          extra_tab={{
            label: voice.currentLanguage === 'ja' ? '会話履歴' : 'Conversation',
            content: (
              <div className="space-y-2 overflow-y-auto pr-1">
                {conversationHistory.length === 0 ? (
                  <p className="text-sm text-gray-600">{labels.helperPrompt}</p>
                ) : (
                  conversationHistory.map((item) => (
                    <div
                      key={item.id}
                      className={cn(
                        'rounded-2xl px-3 py-2 text-sm leading-6',
                        item.role === 'user' ? 'bg-gray-100 text-gray-800' : 'bg-blue-50 text-gray-800',
                      )}
                    >
                      <p className="text-xs font-medium text-gray-500">
                        {item.role === 'user'
                          ? voice.currentLanguage === 'ja'
                            ? 'あなた'
                            : 'You'
                          : 'Navigator'}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap">{item.text}</p>
                    </div>
                  ))
                )}
              </div>
            ),
          }}
          slide_mode_open={showSlideMode}
          on_open_slides={onOpenSlides}
          on_close_slides={onCloseSlides}
          open_slides_label={labels.openSlides}
          close_slides_label={labels.closeSlides}
        />
      </div>
    </div>
  );
}
