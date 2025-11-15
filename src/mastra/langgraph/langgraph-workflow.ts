/**
 * LangGraph統合ワークフロー
 * 
 * 既存のMastraエージェントをLangGraphのグラフ構造で統合し、
 * より柔軟で拡張可能なAIエージェントシステムを構築します。
 */

import { StateGraph, START, END } from '@langchain/langgraph';
import { BaseMessage, HumanMessage, AIMessage } from '@langchain/core/messages';
import { RouterAgent } from '@/mastra/agents/router-agent';
import { BusinessInfoAgent } from '@/mastra/agents/business-info-agent';
import { FacilityAgent } from '@/mastra/agents/facility-agent';
import { MemoryAgent } from '@/mastra/agents/memory-agent';
import { EventAgent } from '@/mastra/agents/event-agent';
import { GeneralKnowledgeAgent } from '@/mastra/agents/general-knowledge-agent';
import { ClarificationAgent } from '@/mastra/agents/clarification-agent';
import { SimplifiedMemorySystem } from '@/lib/simplified-memory';
import { UnifiedAgentResponse } from '@/mastra/types/unified-response';

/**
 * LangGraphワークフローの状態定義
 */
export interface LangGraphState {
  messages: BaseMessage[];
  query: string;
  sessionId: string;
  language: string;
  routedTo?: string;
  answer?: string;
  emotion?: string;
  metadata?: any;
  context?: Record<string, any>;
}

/**
 * LangGraph統合ワークフロー
 * 
 * 既存のエージェントをLangGraphのグラフ構造で統合し、
 * より柔軟なルーティングと状態管理を実現します。
 */
export class LangGraphWorkflow {
  private routerAgent: RouterAgent;
  private businessInfoAgent: BusinessInfoAgent;
  private facilityAgent: FacilityAgent;
  private memoryAgent: MemoryAgent;
  private eventAgent: EventAgent;
  private generalKnowledgeAgent: GeneralKnowledgeAgent;
  private clarificationAgent: ClarificationAgent;
  private memorySystem: SimplifiedMemorySystem;
  private graph: StateGraph<LangGraphState>;

  constructor(config: any) {
    // Initialize all agents
    this.routerAgent = new RouterAgent(config);
    this.businessInfoAgent = new BusinessInfoAgent(config);
    this.facilityAgent = new FacilityAgent(config);
    this.memoryAgent = new MemoryAgent(config);
    this.eventAgent = new EventAgent(config);
    this.generalKnowledgeAgent = new GeneralKnowledgeAgent(config);
    this.clarificationAgent = new ClarificationAgent(config);
    this.memorySystem = new SimplifiedMemorySystem('langgraph');

    // Build LangGraph workflow
    this.graph = this.buildGraph();
  }

  /**
   * LangGraphのグラフ構造を構築
   */
  private buildGraph() {
    const workflow = new StateGraph<LangGraphState>({
      channels: {
        messages: {
          reducer: (x: BaseMessage[], y: BaseMessage[]) => x.concat(y),
          default: () => [],
        },
        query: {
          reducer: (x: string, y: string) => y || x,
          default: () => '',
        },
        sessionId: {
          reducer: (x: string, y: string) => y || x,
          default: () => '',
        },
        language: {
          reducer: (x: string, y: string) => y || x,
          default: () => 'ja',
        },
        routedTo: null,
        answer: null,
        emotion: null,
        metadata: {
          reducer: (x: any, y: any) => ({ ...x, ...y }),
          default: () => ({}),
        },
        context: {
          reducer: (x: Record<string, any>, y: Record<string, any>) => ({ ...x, ...y }),
          default: () => ({}),
        },
      },
    });

    // Add nodes
    workflow
      .addNode('memory', this.memoryNode.bind(this))
      .addNode('router', this.routerNode.bind(this))
      .addNode('clarification', this.clarificationNode.bind(this))
      .addNode('businessInfo', this.businessInfoNode.bind(this))
      .addNode('facility', this.facilityNode.bind(this))
      .addNode('event', this.eventNode.bind(this))
      .addNode('generalKnowledge', this.generalKnowledgeNode.bind(this))
      .addNode('formatResponse', this.formatResponseNode.bind(this));

    // Define edges
    workflow
      .addEdge(START, 'memory')
      .addEdge('memory', 'router')
      .addConditionalEdges('router', this.routeDecision.bind(this), {
        clarification: 'clarification',
        businessInfo: 'businessInfo',
        facility: 'facility',
        event: 'event',
        generalKnowledge: 'generalKnowledge',
      })
      .addEdge('clarification', 'formatResponse')
      .addEdge('businessInfo', 'formatResponse')
      .addEdge('facility', 'formatResponse')
      .addEdge('event', 'formatResponse')
      .addEdge('generalKnowledge', 'formatResponse')
      .addEdge('formatResponse', END);

    return workflow.compile();
  }

  /**
   * Memory node: 会話履歴とコンテキストを取得
   */
  private async memoryNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const memoryContext = await this.memorySystem.getContext(
        state.sessionId,
        state.query
      );
      
      return {
        context: {
          ...state.context,
          memory: memoryContext,
        },
      };
    } catch (error) {
      console.error('[LangGraph] Memory node error:', error);
      return { context: state.context || {} };
    }
  }

  /**
   * Router node: クエリを適切なエージェントにルーティング
   */
  private async routerNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.routerAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        routedTo: result.metadata?.routedTo || 'generalKnowledge',
        metadata: {
          ...state.metadata,
          routing: result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] Router node error:', error);
      return {
        routedTo: 'generalKnowledge',
      };
    }
  }

  /**
   * Route decision: ルーターの決定に基づいて次のノードを選択
   */
  private routeDecision(state: LangGraphState): string {
    return state.routedTo || 'generalKnowledge';
  }

  /**
   * Clarification node: 曖昧なクエリを明確化
   */
  private async clarificationNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.clarificationAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        answer: result.answer,
        emotion: result.emotion,
        metadata: {
          ...state.metadata,
          agent: 'clarification',
          ...result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] Clarification node error:', error);
      return {
        answer: '申し訳ございませんが、もう少し詳しく教えていただけますか？',
        emotion: 'neutral',
      };
    }
  }

  /**
   * BusinessInfo node: 営業情報を処理
   */
  private async businessInfoNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.businessInfoAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        answer: result.answer,
        emotion: result.emotion,
        metadata: {
          ...state.metadata,
          agent: 'businessInfo',
          ...result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] BusinessInfo node error:', error);
      return {
        answer: '営業情報の取得中にエラーが発生しました。',
        emotion: 'neutral',
      };
    }
  }

  /**
   * Facility node: 施設情報を処理
   */
  private async facilityNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.facilityAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        answer: result.answer,
        emotion: result.emotion,
        metadata: {
          ...state.metadata,
          agent: 'facility',
          ...result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] Facility node error:', error);
      return {
        answer: '施設情報の取得中にエラーが発生しました。',
        emotion: 'neutral',
      };
    }
  }

  /**
   * Event node: イベント情報を処理
   */
  private async eventNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.eventAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        answer: result.answer,
        emotion: result.emotion,
        metadata: {
          ...state.metadata,
          agent: 'event',
          ...result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] Event node error:', error);
      return {
        answer: 'イベント情報の取得中にエラーが発生しました。',
        emotion: 'neutral',
      };
    }
  }

  /**
   * GeneralKnowledge node: 一般的な知識を処理
   */
  private async generalKnowledgeNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    try {
      const result = await this.generalKnowledgeAgent.process({
        query: state.query,
        sessionId: state.sessionId,
        language: state.language,
        context: state.context,
      });

      return {
        answer: result.answer,
        emotion: result.emotion,
        metadata: {
          ...state.metadata,
          agent: 'generalKnowledge',
          ...result.metadata,
        },
      };
    } catch (error) {
      console.error('[LangGraph] GeneralKnowledge node error:', error);
      return {
        answer: '情報の取得中にエラーが発生しました。',
        emotion: 'neutral',
      };
    }
  }

  /**
   * FormatResponse node: 最終的な応答をフォーマット
   */
  private async formatResponseNode(state: LangGraphState): Promise<Partial<LangGraphState>> {
    // Save to memory
    if (state.query && state.answer) {
      await this.memorySystem.save(
        state.sessionId,
        state.query,
        state.answer
      );
    }

    return {
      messages: [
        ...state.messages,
        new HumanMessage(state.query),
        new AIMessage(state.answer || ''),
      ],
    };
  }

  /**
   * ワークフローを実行
   */
  async invoke(input: {
    query: string;
    sessionId: string;
    language?: string;
    context?: Record<string, any>;
  }): Promise<UnifiedAgentResponse> {
    const initialState: LangGraphState = {
      messages: [],
      query: input.query,
      sessionId: input.sessionId,
      language: input.language || 'ja',
      context: input.context || {},
    };

    const result = await this.graph.invoke(initialState);

    return {
      answer: result.answer || '回答を生成できませんでした。',
      emotion: result.emotion || 'neutral',
      metadata: {
        ...result.metadata,
        routedTo: result.routedTo,
        language: result.language,
        sessionId: result.sessionId,
      },
    };
  }

  /**
   * ストリーミング実行（将来の拡張用）
   */
  async stream(input: {
    query: string;
    sessionId: string;
    language?: string;
    context?: Record<string, any>;
  }): Promise<AsyncIterable<LangGraphState>> {
    const initialState: LangGraphState = {
      messages: [],
      query: input.query,
      sessionId: input.sessionId,
      language: input.language || 'ja',
      context: input.context || {},
    };

    return this.graph.stream(initialState);
  }
}

