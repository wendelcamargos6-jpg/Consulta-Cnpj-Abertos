CREATE TABLE IF NOT EXISTS search_queries (
    id INTEGER PRIMARY KEY,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    uf TEXT,
    municipio TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_data (
    id INTEGER PRIMARY KEY,
    cnpj TEXT NOT NULL,
    razao_social TEXT,
    nome_fantasia TEXT,
    telefone TEXT,
    telefone_secundario TEXT,
    celular TEXT,
    whatsapp TEXT,
    email TEXT,
    website TEXT,
    cep TEXT,
    endereco TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    municipio TEXT,
    situacao TEXT,
    data_situacao TEXT
);

-- Tabelas oficiais separadas
CREATE TABLE IF NOT EXISTS empresas (
    cnpj TEXT,
    razao_social TEXT,
    nome_fantasia TEXT,
    natureza_juridica TEXT,
    capital_social DOUBLE,
    data_constituicao DATE,
    situacao_cadastral TEXT,
    data_situacao DATE,
    uf TEXT,
    municipio TEXT,
    bairro TEXT,
    endereco TEXT,
    numero TEXT,
    complemento TEXT,
    cep TEXT,
    telefone TEXT,
    email TEXT,
    website TEXT,
    cnae_principal TEXT,
    cnae_descricao TEXT,
    porte TEXT,
    matriz BOOLEAN,
    filial BOOLEAN,
    ultima_atualizacao DATE
);

CREATE TABLE IF NOT EXISTS estabelecimentos (
    cnpj TEXT,
    cnpj_basico TEXT,
    razao_social TEXT,
    nome_fantasia TEXT,
    endereco TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    municipio TEXT,
    uf TEXT,
    cep TEXT,
    telefone TEXT,
    email TEXT,
    atividade_principal TEXT,
    natureza_juridica TEXT,
    situacao_cadastral TEXT,
    data_situacao DATE
);

CREATE TABLE IF NOT EXISTS simples (
    cnpj TEXT,
    adesao_simples TEXT,
    data_adesao DATE,
    data_renuncia DATE,
    opcao_simples TEXT
);

CREATE TABLE IF NOT EXISTS cnaes (
    codigo TEXT,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS naturezas (
    codigo TEXT,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS municipios (
    codigo_ibge TEXT,
    nome TEXT,
    uf TEXT
);

-- Índices (idempotentes quando suportado)
CREATE INDEX IF NOT EXISTS idx_empresas_cnpj ON empresas(cnpj);
CREATE INDEX IF NOT EXISTS idx_empresas_cnae ON empresas(cnae_principal);
CREATE INDEX IF NOT EXISTS idx_empresas_uf ON empresas(uf);

CREATE INDEX IF NOT EXISTS idx_estabelecimentos_cnpj ON estabelecimentos(cnpj);
CREATE INDEX IF NOT EXISTS idx_estabelecimentos_municipio ON estabelecimentos(municipio);

CREATE INDEX IF NOT EXISTS idx_simples_cnpj ON simples(cnpj);

CREATE INDEX IF NOT EXISTS idx_cnaes_codigo ON cnaes(codigo);
CREATE INDEX IF NOT EXISTS idx_naturezas_codigo ON naturezas(codigo);
CREATE INDEX IF NOT EXISTS idx_municipios_codigo ON municipios(codigo_ibge);

