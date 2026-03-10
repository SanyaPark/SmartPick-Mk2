import React, { useEffect } from 'react';
import { ChatKit, useChatKit } from '@openai/chatkit-react';
import { findCardIdByName } from './CardCarousel';
import { AgentCard, postAgentChat } from '../lib/api';

interface ChatKitWrapperProps {
  onSpin: () => void;
  onCardSelected: (cardId: string | null) => void;
}

const assistantIntro = 'Hi! Tell me what kind of credit card perks you want and I\'ll highlight a match.';

type ChatKitTextContent = { type: 'input_text'; text: string };
type ChatKitTagContent = { type: 'input_tag'; text: string };

type ChatKitRequest = {
  type: 'threads.create' | 'threads.add_user_message';
  params: {
    thread_id?: string;
    input: {
      content: Array<ChatKitTextContent | ChatKitTagContent>;
      attachments?: string[];
      inference_options?: {
        model?: string | null;
        tool_choice?: { id: string } | null;
      };
      quoted_text?: string | null;
    };
  };
};

type ChatKitOperation = {
  type: string;
  params?: Record<string, unknown>;
};

type ChatKitThreadItem = {
  id: string;
  type: 'user_message' | 'assistant_message';
  thread_id: string;
  created_at: string;
  content: Array<Record<string, unknown>>;
  attachments?: unknown[];
  quoted_text?: string | null;
  inference_options?: Record<string, unknown>;
};

type ChatKitThreadState = {
  id: string;
  created_at: string;
  title: string | null;
  status: { type: 'active' };
  items: ChatKitThreadItem[];
};

const threadState = new Map<string, ChatKitThreadState>();

const createAgentFetch = (
  onSpin: () => void,
  onCardSelected: (cardId: string | null) => void
) => {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const operation = parseChatKitOperation(init.body);
      if (!operation) {
        return buildJsonResponse({});
      }

      if (!isChatKitStreamingRequest(operation)) {
        return handleNonStreamingOperation(operation);
      }

      const request = operation;

      onSpin();

      const userMessage = getUserMessageFromRequest(request);
      const threadId = request.type === 'threads.add_user_message' ? request.params.thread_id : undefined;

      try {
        const data = await postAgentChat({
          message: userMessage,
          threadId,
        });

        const selectedCardId = pickCardId(data.cards);
        onCardSelected(selectedCardId);

        return buildStreamResponse(request, data.reply, data.thread_id);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Agent call failed';
        onCardSelected(null);
        return buildStreamResponse(
          request,
          `Sorry, something went wrong while contacting the agent: ${message}`
        );
      }
    }

    return fetch(input, init);
  };
};

function pickCardId(cards: AgentCard[]): string | null {
  for (const card of cards) {
    const matchedId = findCardIdByName(card.card_name);
    if (matchedId) return matchedId;
  }
  return null;
}

function parseChatKitOperation(body: BodyInit | null | undefined): ChatKitOperation | null {
  if (typeof body !== 'string') {
    return null;
  }

  try {
    const parsed = JSON.parse(body) as ChatKitOperation;
    if (!parsed || typeof parsed.type !== 'string') {
      return null;
    }

    return parsed;
  } catch (error) {
    console.error('Failed to parse ChatKit request body', error);
    return null;
  }
}

function isChatKitStreamingRequest(operation: ChatKitOperation): operation is ChatKitRequest {
  return (
    operation.type === 'threads.create' ||
    operation.type === 'threads.add_user_message'
  );
}

function handleNonStreamingOperation(operation: ChatKitOperation): Response {
  if (operation.type === 'threads.list') {
    const threads = Array.from(threadState.values())
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(thread => ({
        id: thread.id,
        title: thread.title,
        created_at: thread.created_at,
        status: thread.status,
        items: { data: [], has_more: false, after: null },
      }));

    return buildJsonResponse({
      data: threads,
      has_more: false,
      after: null,
    });
  }

  if (operation.type === 'threads.get_by_id') {
    const threadId = readStringParam(operation.params, 'thread_id');
    const thread = threadId ? threadState.get(threadId) : undefined;

    if (!thread) {
      return buildJsonResponse({ detail: 'Thread not found' }, 404);
    }

    return buildJsonResponse({
      id: thread.id,
      title: thread.title,
      created_at: thread.created_at,
      status: thread.status,
      items: {
        data: thread.items,
        has_more: false,
        after: null,
      },
    });
  }

  if (operation.type === 'items.list') {
    const threadId = readStringParam(operation.params, 'thread_id');
    const thread = threadId ? threadState.get(threadId) : undefined;

    return buildJsonResponse({
      data: thread?.items ?? [],
      has_more: false,
      after: null,
    });
  }

  if (operation.type === 'threads.update') {
    const threadId = readStringParam(operation.params, 'thread_id');
    const title = readStringParam(operation.params, 'title');
    const thread = threadId ? threadState.get(threadId) : undefined;

    if (!thread) {
      return buildJsonResponse({ detail: 'Thread not found' }, 404);
    }

    thread.title = title || null;

    return buildJsonResponse({
      id: thread.id,
      title: thread.title,
      created_at: thread.created_at,
      status: thread.status,
      items: { data: [], has_more: false, after: null },
    });
  }

  if (operation.type === 'threads.delete') {
    const threadId = readStringParam(operation.params, 'thread_id');
    if (threadId) {
      threadState.delete(threadId);
    }
    return buildJsonResponse({});
  }

  return buildJsonResponse({});
}

function readStringParam(
  params: Record<string, unknown> | undefined,
  key: string
): string | undefined {
  const value = params?.[key];
  return typeof value === 'string' ? value : undefined;
}

function buildJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

function getUserMessageFromRequest(request: ChatKitRequest): string {
  const content = request.params.input.content || [];
  const textParts = content
    .filter(item => item.type === 'input_text')
    .map(item => item.text)
    .filter(Boolean);

  return textParts.join('\n').trim();
}

function generateId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}_${crypto.randomUUID()}`;
  }

  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function buildStreamResponse(request: ChatKitRequest, text: string, backendThreadId?: string) {
  const fallback = text?.trim() ? text : '죄송합니다. 조건에 맞는 카드를 찾지 못했습니다.';
  const nowIso = new Date().toISOString();
  const isCreate = request.type === 'threads.create';
  const threadId = backendThreadId || (isCreate ? generateId('thread') : request.params.thread_id || generateId('thread'));
  const userItemId = generateId('item_user');
  const assistantItemId = generateId('item_assistant');

  const userItem: ChatKitThreadItem = {
    id: userItemId,
    type: 'user_message',
    thread_id: threadId,
    created_at: nowIso,
    content: request.params.input.content,
    attachments: [],
    quoted_text: request.params.input.quoted_text || null,
    inference_options: request.params.input.inference_options || {},
  };

  const assistantItemBase = {
    id: assistantItemId,
    type: 'assistant_message',
    thread_id: threadId,
    created_at: nowIso,
  } as const;

  const assistantDoneItem: ChatKitThreadItem = {
    ...assistantItemBase,
    content: [
      {
        type: 'output_text',
        text: fallback,
        annotations: [],
      },
    ],
  };

  const existing = threadState.get(threadId);
  const nextItems = [...(existing?.items || []), userItem, assistantDoneItem];
  threadState.set(threadId, {
    id: threadId,
    created_at: existing?.created_at || nowIso,
    title: existing?.title || null,
    status: { type: 'active' },
    items: nextItems,
  });

  const streamEvents: Array<Record<string, unknown>> = [];

  if (isCreate) {
    streamEvents.push({
      type: 'thread.created',
      thread: {
        id: threadId,
        title: null,
        created_at: nowIso,
        status: { type: 'active' },
        items: { data: [], has_more: false, after: null },
      },
    });
  }

  streamEvents.push(
    { type: 'thread.item.done', item: userItem },
    { type: 'stream_options', stream_options: { allow_cancel: true } },
    { type: 'thread.item.added', item: { ...assistantItemBase, content: [] } },
    {
      type: 'thread.item.updated',
      item_id: assistantItemId,
      update: {
        type: 'assistant_message.content_part.added',
        content_index: 0,
        content: {
          type: 'output_text',
          text: '',
          annotations: [],
        },
      },
    }
  );

  const chunks = fallback.split(' ');
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i] + (i < chunks.length - 1 ? ' ' : '');
    streamEvents.push({
      type: 'thread.item.updated',
      item_id: assistantItemId,
      update: {
        type: 'assistant_message.content_part.text_delta',
        content_index: 0,
        delta: chunk,
      },
    });
  }

  streamEvents.push(
    {
      type: 'thread.item.updated',
      item_id: assistantItemId,
      update: {
        type: 'assistant_message.content_part.done',
        content_index: 0,
        content: {
          type: 'output_text',
          text: fallback,
          annotations: [],
        },
      },
    },
    {
      type: 'thread.item.done',
      item: assistantDoneItem,
    }
  );

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      let i = 0;

      const interval = setInterval(() => {
        if (i >= streamEvents.length) {
          clearInterval(interval);
          controller.close();
          return;
        }

        const data = JSON.stringify(streamEvents[i]);

        controller.enqueue(encoder.encode(`data: ${data}\n\n`));
        i++;
      }, 16);
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}

const ChatKitWrapper: React.FC<ChatKitWrapperProps> = ({ onSpin, onCardSelected }) => {
  const { control } = useChatKit({
    api: {
      url: '/mock/api/chat', // Dummy URL
      domainKey: 'dummy-key',
      fetch: createAgentFetch(onSpin, onCardSelected),
    },
    locale: 'en',
    theme: {
        colorScheme: 'dark',
        radius: 'round',
    },
    startScreen: {
        greeting: assistantIntro,
        prompts: [
            { label: "Best Rewards", prompt: "What card has the best rewards?" },
            { label: "Travel Perks", prompt: "I need a card with travel benefits." },
            { label: "Low Interest", prompt: "Which card has the lowest interest rate?" }
        ]
    }
  });

  // Since we need to load the web component script, we should check if it's defined
  useEffect(() => {
    // TODO: Add script loading logic here if not present in global scope
    // <script type="module" src="https://.../chatkit.js"></script>
    // Since we don't have the URL, the user needs to add it.
  }, []);

  return (
    <div className="smartpick-chat w-full h-[420px] sm:h-[520px] lg:h-[560px] rounded-3xl border border-white/10 bg-gradient-to-br from-[#121a38]/95 via-[#101933]/90 to-[#0f162e]/95 backdrop-blur-2xl shadow-[0_20px_60px_rgba(11,14,31,0.6)] overflow-hidden relative flex flex-col transition-all duration-500 ease-[cubic-bezier(.4,0,.2,1)]">
      {/* 
        IMPORTANT: The <openai-chatkit> custom element must be defined for this to work.
        Ensure the script is loaded in your application (e.g., in _document.tsx or via a Script tag).
      */}
      <ChatKit 
        control={control} 
        style={{ 
          width: '100%', 
          height: '100%', 
          border: 'none',
          display: 'flex',
          flex: 1,
        }} 
      />
    </div>
  );
};

export default ChatKitWrapper;
