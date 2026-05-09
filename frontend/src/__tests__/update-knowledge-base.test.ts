import assert from 'node:assert/strict';
import Module from 'node:module';
import { after, afterEach, test } from 'node:test';

const originalResolveFilename = (Module as any)._resolveFilename;
const originalLoad = (Module as any)._load;
const originalConsoleError = console.error;

(Module as any)._resolveFilename = function resolveFilename(
  request: string,
  parent: unknown,
  isMain: boolean,
  options: unknown
) {
  if (request === 'server-only') {
    return request;
  }

  return originalResolveFilename.call(this, request, parent, isMain, options);
};

(Module as any)._load = function load(request: string, parent: unknown, isMain: boolean) {
  if (request === 'server-only') {
    return {};
  }

  return originalLoad.call(this, request, parent, isMain);
};

afterEach(() => {
  console.error = originalConsoleError;
});

after(() => {
  (Module as any)._resolveFilename = originalResolveFilename;
  (Module as any)._load = originalLoad;
});

async function loadKnowledgeBaseUpdater() {
  const module = await import('../jobs/update-knowledge-base');
  return (module as any).KnowledgeBaseUpdater ?? (module as any).default.KnowledgeBaseUpdater;
}

function createConnpassEvent(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 101,
    title: 'Engineer Cafe Test Event',
    catch: 'Testing event',
    description: 'A deterministic Connpass event used for updater tests.',
    event_url: 'https://engineercafe.connpass.com/event/101/',
    started_at: '2026-06-01T10:00:00+09:00',
    ended_at: '2026-06-01T12:00:00+09:00',
    place: 'Engineer Cafe',
    address: 'Fukuoka',
    limit: 30,
    accepted: 12,
    waiting: 0,
    updated_at: '2026-05-01T09:00:00+09:00',
    ...overrides,
  };
}

function createSupabaseMock(existingByEventId = new Map<string, { id: string }>()) {
  const inserts: Array<Record<string, unknown>> = [];
  const updates: Array<{ id: string; payload: Record<string, unknown> }> = [];
  const selectedEventIds: string[] = [];

  const client = {
    from(table: string) {
      assert.equal(table, 'knowledge_base');

      return {
        select(columns: string) {
          assert.equal(columns, 'id');

          return {
            eq(column: string, value: string) {
              assert.equal(column, 'metadata->>event_id');
              selectedEventIds.push(value);

              return {
                async single() {
                  return { data: existingByEventId.get(value) ?? null, error: null };
                },
              };
            },
          };
        },
        update(payload: Record<string, unknown>) {
          return {
            async eq(column: string, id: string) {
              assert.equal(column, 'id');
              updates.push({ id, payload });
              return { error: null };
            },
          };
        },
        async insert(payload: Record<string, unknown>) {
          inserts.push(payload);
          return { error: null };
        },
      };
    },
  };

  return { client, inserts, updates, selectedEventIds };
}

test(
  'Connpass update embeds rows and writes RAG-visible event category',
  { concurrency: false },
  async () => {
    console.error = () => {};
    const KnowledgeBaseUpdater = await loadKnowledgeBaseUpdater();
    const supabase = createSupabaseMock(new Map([['101', { id: 'existing-row' }]]));
    const embedding = Array.from({ length: 1536 }, (_, index) => index / 1536);
    const embeddingRequests: Array<Record<string, unknown>> = [];
    const connpassClient = {
      async searchEngineerCafeEvents() {
        return [
          createConnpassEvent(),
          createConnpassEvent({
            event_id: 202,
            title: '新しいイベント',
            event_url: 'https://engineercafe.connpass.com/event/202/',
          }),
        ];
      },
    };
    const fetchMock = (async (input, init) => {
      assert.equal(input, 'https://openrouter.ai/api/v1/embeddings');
      assert.equal(init?.method, 'POST');
      assert.equal((init?.headers as Record<string, string>).Authorization, 'Bearer test-openrouter-key');
      embeddingRequests.push(JSON.parse(init?.body as string));

      return new Response(JSON.stringify({ data: [{ embedding }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    const updater = new KnowledgeBaseUpdater({
      connpassClient,
      supabaseAdmin: supabase.client,
      fetch: fetchMock,
      getOpenRouterApiKey: () => 'test-openrouter-key',
    });

    const result = await (updater as any).updateFromConnpass();

    assert.match(result, /^Added 1, updated 1, skipped 0, failed 0 events/);
    assert.equal(embeddingRequests.length, 2);
    assert.deepEqual(
      embeddingRequests.map((request) => ({
        model: request.model,
        dimensions: request.dimensions,
      })),
      [
        { model: 'openai/text-embedding-3-small', dimensions: 1536 },
        { model: 'openai/text-embedding-3-small', dimensions: 1536 },
      ]
    );

    assert.deepEqual(supabase.selectedEventIds, ['101', '202']);
    assert.equal(supabase.updates.length, 1);
    assert.equal(supabase.inserts.length, 1);

    const updatedPayload = supabase.updates[0].payload;
    const insertedPayload = supabase.inserts[0];

    for (const payload of [updatedPayload, insertedPayload]) {
      assert.equal(payload.category, 'event');
      assert.equal(payload.subcategory, 'connpass');
      assert.equal(payload.source, 'connpass');
      assert.equal((payload.content_embedding as number[]).length, 1536);
      assert.equal((payload.metadata as Record<string, unknown>).embedding_model, 'openai/text-embedding-3-small');
      assert.equal((payload.metadata as Record<string, unknown>).embedding_dimensions, 1536);
    }
  }
);

test(
  'Connpass update skips database writes when OPENROUTER_API_KEY is missing',
  { concurrency: false },
  async () => {
    console.error = () => {};
    const KnowledgeBaseUpdater = await loadKnowledgeBaseUpdater();
    let fetchCalled = false;
    let supabaseCalled = false;
    const updater = new KnowledgeBaseUpdater({
      connpassClient: {
        async searchEngineerCafeEvents() {
          return [createConnpassEvent(), createConnpassEvent({ event_id: 202 })];
        },
      },
      supabaseAdmin: {
        from() {
          supabaseCalled = true;
          throw new Error('Supabase should not be called without embeddings');
        },
      },
      fetch: (async () => {
        fetchCalled = true;
        throw new Error('Embedding fetch should not be called without an API key');
      }) as typeof fetch,
      getOpenRouterApiKey: () => undefined,
    });

    const result = await (updater as any).updateFromConnpass();

    assert.match(result, /^Added 0, updated 0, skipped 2, failed 0 events/);
    assert.match(result, /one-time migration to category 'event'/);
    assert.equal(fetchCalled, false);
    assert.equal(supabaseCalled, false);
  }
);

test(
  'Connpass update skips rows when embedding response has the wrong dimensions',
  { concurrency: false },
  async () => {
    console.error = () => {};
    const KnowledgeBaseUpdater = await loadKnowledgeBaseUpdater();
    const supabase = createSupabaseMock();
    const updater = new KnowledgeBaseUpdater({
      connpassClient: {
        async searchEngineerCafeEvents() {
          return [createConnpassEvent()];
        },
      },
      supabaseAdmin: supabase.client,
      fetch: (async () =>
        new Response(JSON.stringify({ data: [{ embedding: [0.1, 0.2] }] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })) as typeof fetch,
      getOpenRouterApiKey: () => 'test-openrouter-key',
    });

    const result = await (updater as any).updateFromConnpass();

    assert.match(result, /^Added 0, updated 0, skipped 1, failed 0 events/);
    assert.equal(supabase.inserts.length, 0);
    assert.equal(supabase.updates.length, 0);
    assert.equal(supabase.selectedEventIds.length, 0);
  }
);
