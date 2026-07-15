# Checklist de homologação beta fechada

## 1. Fluxo principal
- [x] A aplicação sobe sem falhas críticas.
- [x] O endpoint /search responde com 200 e mensagem clara em caso de zero resultados.
- [x] O endpoint /export/excel e /export/csv estão disponíveis para uso.
- [x] A interface permite preencher período, UF e município e disparar a pesquisa.
- [x] A interface exibe mensagem clara quando não há resultados.

## 2. Validação de risco
- [x] Validação de datas e intervalo máximo funcionando.
- [x] Validação de limite e parâmetros obrigatórios funcionando.
- [x] Base estável para pequenas consultas de teste.
- [ ] Validar com 10 escritórios reais em ambiente controlado.
- [ ] Confirmar se os campos exportados atendem às necessidades do time comercial.

## 3. Itens obrigatórios antes do beta
- [x] Mensagens de erro/sem resultado mais claras para o usuário.
- [x] Fluxo de busca e exportação alinhado ao backend real.
- [ ] Definir um processo simples de suporte para os primeiros usuários.
- [ ] Criar um canal de recebimento de bugs e pedidos de ajuste.

## 4. Melhorias para versão 1.1
- [ ] Adicionar paginação real no backend para navegação mais ampla.
- [ ] Melhorar mapeamento de colunas para exportação.
- [ ] Incluir filtros mais completos compatíveis com a base.
- [ ] Adicionar autenticação/controle de acesso para uso comercial.
