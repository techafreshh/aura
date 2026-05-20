import { TextStreamData } from '@livekit/components-core';
const t: TextStreamData = { text: 'a' } as any;
const keys: keyof TextStreamData = "invalid_key_to_trigger_error";