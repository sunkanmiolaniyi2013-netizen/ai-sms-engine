-- =============================================
-- AI SMS Reactivation Engine — Supabase Schema
-- Run this in your Supabase SQL Editor
-- =============================================

-- Businesses (tenants)
CREATE TABLE IF NOT EXISTS businesses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    ghl_api_key TEXT NOT NULL,
    ghl_location_id TEXT NOT NULL,
    ai_prompt TEXT NOT NULL DEFAULT 'You are a helpful assistant for this business. Reply in a friendly, natural, concise SMS style. Keep replies under 2 sentences.',
    website_url TEXT,
    calendar_link TEXT,
    delay_min INTEGER NOT NULL DEFAULT 60,   -- seconds
    delay_max INTEGER NOT NULL DEFAULT 180,  -- seconds
    ai_model TEXT NOT NULL DEFAULT 'gemini-2.0-flash',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts (one per GHL contact per business)
CREATE TABLE IF NOT EXISTS contacts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    ghl_contact_id TEXT NOT NULL,
    phone TEXT,
    name TEXT,
    website_context TEXT,           -- cached scraped website content
    website_cached_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, ghl_contact_id)
);

-- Conversations (one per contact)
CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
    ghl_contact_id TEXT NOT NULL,
    status TEXT DEFAULT 'active',   -- active | closed
    total_messages INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, ghl_contact_id)
);

-- Messages (full thread history)
CREATE TABLE IF NOT EXISTS messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),  -- user = contact, assistant = AI
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- App users (for dashboard authentication)
CREATE TABLE IF NOT EXISTS app_users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_contacts_business_ghl ON contacts(business_id, ghl_contact_id);
CREATE INDEX IF NOT EXISTS idx_conversations_business ON conversations(business_id);
CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(ghl_contact_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
