-- ============================================================
-- SELS-SC | CPB Alocacao - Setup do banco de dados
-- Execute este SQL no Supabase: SQL Editor > New Query > Run
-- ============================================================

-- Tabela de usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'membro' CHECK (papel IN ('master', 'membro')),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    ultimo_login TIMESTAMPTZ
);

-- Tabela de sessoes (tokens de acesso)
CREATE TABLE IF NOT EXISTS sessoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    ip TEXT,
    nome_maquina TEXT,
    cidade TEXT,
    expira_em TIMESTAMPTZ NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de tentativas de login (seguranca)
CREATE TABLE IF NOT EXISTS tentativas_login (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    username TEXT NOT NULL,
    ip TEXT,
    sucesso BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de historico de processamentos
CREATE TABLE IF NOT EXISTS historico (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id),
    usuario_nome TEXT,
    xmls_processados TEXT[],
    planilha_gerada TEXT,
    divergencias INTEGER DEFAULT 0,
    concluido_em TIMESTAMPTZ DEFAULT NOW(),
    ip TEXT,
    nome_maquina TEXT
);

-- Tabela de configuracoes (so master pode alterar)
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Configuracoes iniciais
INSERT INTO configuracoes (chave, valor) VALUES
    ('cidades_permitidas', '["sao jose","florianopolis","palhoca","biguacu","santo amaro da imperatriz","governador celso ramos","antonio carlos","sao pedro de alcantara","tijucas","brusque","itajai","balneario camboriu","camboriu","itapema","garopaba","paulo lopes","santa catarina"]'),
    ('versao_app', '1.0.0'),
    ('max_tentativas_login', '5'),
    ('bloqueio_minutos', '30'),
    ('notif_email_ativo', 'true')
ON CONFLICT (chave) DO NOTHING;

-- RLS (Row Level Security) - seguranca por linha
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE historico ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE tentativas_login ENABLE ROW LEVEL SECURITY;

-- Politicas: acesso total via service_role (backend), sem acesso anonimo direto
CREATE POLICY "Sem acesso anonimo - usuarios" ON usuarios FOR ALL TO anon USING (false);
CREATE POLICY "Sem acesso anonimo - sessoes" ON sessoes FOR ALL TO anon USING (false);
CREATE POLICY "Sem acesso anonimo - historico" ON historico FOR ALL TO anon USING (false);
CREATE POLICY "Sem acesso anonimo - config" ON configuracoes FOR ALL TO anon USING (false);

-- Indices para performance
CREATE INDEX IF NOT EXISTS idx_sessoes_token ON sessoes(token);
CREATE INDEX IF NOT EXISTS idx_sessoes_usuario ON sessoes(usuario_id);
CREATE INDEX IF NOT EXISTS idx_tentativas_username ON tentativas_login(username, criado_em);
CREATE INDEX IF NOT EXISTS idx_historico_usuario ON historico(usuario_id);

