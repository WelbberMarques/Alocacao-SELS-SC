-- Executar no SQL Editor do Supabase
-- Adiciona tabelas para whitelist de dispositivos e IP real

-- Adiciona ip_real na tabela sessoes
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS ip_real TEXT;

-- Adiciona ip_real e maquina na tabela tentativas_login
ALTER TABLE tentativas_login ADD COLUMN IF NOT EXISTS ip_real TEXT;
ALTER TABLE tentativas_login ADD COLUMN IF NOT EXISTS maquina TEXT;

-- Tabela de dispositivos aprovados (whitelist)
CREATE TABLE IF NOT EXISTS dispositivos_aprovados (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,
    ip TEXT,
    ip_real TEXT,
    maquina TEXT,
    cidade TEXT,
    status TEXT DEFAULT 'pendente' CHECK (status IN ('pendente','aprovado','bloqueado')),
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE dispositivos_aprovados ENABLE ROW LEVEL SECURITY;
CREATE POLICY "block_anon_dispositivos" ON dispositivos_aprovados
    FOR ALL TO anon USING (false);

CREATE INDEX IF NOT EXISTS idx_disp_usuario
    ON dispositivos_aprovados(usuario_id, status);
CREATE INDEX IF NOT EXISTS idx_disp_ip
    ON dispositivos_aprovados(ip, ip_real);
