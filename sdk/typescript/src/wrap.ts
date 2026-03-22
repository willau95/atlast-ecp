/**
 * ATLAST ECP Wrap — transparent LLM client wrapper (Layer 1)
 * 
 * Usage:
 *   import { wrap } from '@atlast/sdk';
 *   const client = wrap(new OpenAI(), { agentId: 'my-agent' });
 *   // All chat.completions.create() calls are now tracked
 */

import { createRecord } from './record';
import { storeRecord } from './storage';
import { loadOrCreateIdentity } from './identity';
import type { ATLASTConfig } from './types';

export interface WrapOptions {
  agentId: string;
  apiUrl?: string;
  autoUpload?: boolean;
}

/**
 * Wrap an OpenAI-compatible client to automatically record ECP evidence.
 * Intercepts chat.completions.create() calls.
 */
export function wrap<T extends object>(client: T, options: WrapOptions): T {
  const identity = loadOrCreateIdentity(options.agentId);

  // Deep proxy to intercept chat.completions.create
  return new Proxy(client, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver);

      if (prop === 'chat' && typeof value === 'object' && value !== null) {
        return new Proxy(value, {
          get(chatTarget, chatProp, chatReceiver) {
            const chatValue = Reflect.get(chatTarget, chatProp, chatReceiver);

            if (chatProp === 'completions' && typeof chatValue === 'object' && chatValue !== null) {
              return new Proxy(chatValue, {
                get(compTarget, compProp, compReceiver) {
                  const compValue = Reflect.get(compTarget, compProp, compReceiver);

                  if (compProp === 'create' && typeof compValue === 'function') {
                    return async function wrappedCreate(...args: unknown[]) {
                      const startTime = Date.now();
                      const params = args[0] as Record<string, unknown>;
                      const inputStr = JSON.stringify(params?.messages || '');

                      let result: unknown;
                      let error: Error | undefined;
                      const flags: string[] = [];

                      try {
                        result = await (compValue as Function).apply(compTarget, args);
                      } catch (e) {
                        error = e as Error;
                        flags.push('error');
                        throw e;
                      } finally {
                        const latencyMs = Date.now() - startTime;
                        const outputStr = error
                          ? `error: ${error.message}`
                          : JSON.stringify((result as Record<string, unknown>)?.choices || '');

                        const usage = (result as Record<string, unknown>)?.usage as Record<string, number> | undefined;

                        const record = createRecord({
                          agentId: options.agentId,
                          action: 'llm_call',
                          model: params?.model as string,
                          input: inputStr,
                          output: outputStr,
                          tokensIn: usage?.prompt_tokens,
                          tokensOut: usage?.completion_tokens,
                          latencyMs,
                          flags,
                          identity,
                        });

                        storeRecord(options.agentId, record);
                      }

                      return result;
                    };
                  }
                  return compValue;
                },
              });
            }
            return chatValue;
          },
        });
      }
      return value;
    },
  });
}
