import { createClient } from '@supabase/supabase-js'

// Database types (後で supabase gen types typescript で生成可能)
export interface Database {
  public: {
    Tables: {
      conversation_sessions: {
        Row: {
          id: string
          visitor_id: string | null
          language: 'ja' | 'en'
          mode: string
          started_at: string
          ended_at: string | null
          status: string
          metadata: Record<string, any>
          created_at: string
          updated_at: string
        }
        Insert: Omit<Database['public']['Tables']['conversation_sessions']['Row'], 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Database['public']['Tables']['conversation_sessions']['Insert']>
      }
      conversation_history: {
        Row: {
          id: string
          session_id: string
          role: 'user' | 'assistant' | 'system'
          content: string
          audio_url: string | null
          metadata: Record<string, any>
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['conversation_history']['Row'], 'id' | 'created_at'>
        Update: Partial<Database['public']['Tables']['conversation_history']['Insert']>
      }
      knowledge_base: {
        Row: {
          id: string
          content: string
          content_embedding: number[] | null
          category: string | null
          subcategory: string | null
          language: 'ja' | 'en'
          source: string | null
          metadata: Record<string, any>
          created_at: string
          updated_at: string
        }
        Insert: Omit<Database['public']['Tables']['knowledge_base']['Row'], 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Database['public']['Tables']['knowledge_base']['Insert']>
      }
      agent_memory: {
        Row: {
          id: string
          agent_name: string
          key: string
          value: Record<string, any>
          expires_at: string | null
          created_at: string
          updated_at: string
        }
        Insert: Omit<Database['public']['Tables']['agent_memory']['Row'], 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Database['public']['Tables']['agent_memory']['Insert']>
      }
    }
  }
}

// Create Supabase client (lazy init for build-time safety)
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? ''
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ''

// Public client (for client-side operations)
// When env vars are empty (CI/build), creates a null placeholder that is never called at build time
export const supabase = supabaseUrl
  ? createClient<Database>(supabaseUrl, supabaseAnonKey)
  : (null as unknown as ReturnType<typeof createClient<Database>>)

// Service client (for server-side operations with full access)
// Uses lazy init + Proxy to avoid build-time errors while keeping backward-compatible exports
let _supabaseAdmin: ReturnType<typeof createClient<Database>> | null = null

export function getSupabaseAdmin(): ReturnType<typeof createClient<Database>> {
  if (!_supabaseAdmin) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY
    if (!url || !key) {
      throw new Error(
        'Supabase config missing: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required'
      )
    }
    _supabaseAdmin = createClient<Database>(url, key, {
      auth: { persistSession: false },
    })
  }
  return _supabaseAdmin
}

export const supabaseAdmin = new Proxy({} as ReturnType<typeof createClient<Database>>, {
  get(_, prop) {
    return Reflect.get(getSupabaseAdmin(), prop)
  },
})
