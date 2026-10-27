# Cadastro com WCDA ausente — 23/10/2026

Checkout: PRM-remocao-cargos; branch fix/remocao-autorizacao-cargos. Sem commits/push.

O bloqueio vinha de metadata_field em store_document_update.py, chamado por wcda_state em store_registration_plan.py. O cadastro agora distingue absent, first_inclusion, append e blocked. A validação estrita dos outros consumidores permanece intacta.

Quando absent, a execução usa prepare_document_update com allow_absent explícito. O PUT contém somente meta_data com key e value, sem ID inventado. A lista contém documentos reais retornados pelo upload. O WooCommerce atribui o ID; a releitura verifica conteúdo e unicidade. Campos comerciais não são enviados.

Contrato confirmado no histórico d0ac3f4: label, url, filename e filesize. As classificações e regras de datasheet PRM/fornecedor existentes não foram alteradas. Isso confirma o formato versionado do PRM, não constitui homologação real do plugin.

Duplicidade e formato inválido continuam bloqueados. Snapshot protege mudanças entre prévia e envio e antes do PUT. Hashes, permissões, aprovação e confirmação são preservados. Recuperação de um campo recém-criado restaura lista vazia, mantendo o ID alocado e as mídias; não apaga metadados.

Refazer o Dry Run antigo é obrigatório para retirar o blocker e assinar a nova prévia. Rever e aprovar novamente antes de confirmar um único SKU.

Testes: 144 focados iniciais; suíte completa 759 passaram / 28 ignorados (fixtures privadas e ferramentas ausentes); 3 testes JavaScript passaram. Após ajuste da mensagem da interface, rebuild e 45 testes do cadastro passaram. Todos os testes de lojas usaram mocks e container sem rede.

Deploy concluído: somente api e worker-registration recriados e saudáveis, imagem prm:wcda-absent-test (manifest 5783f237abf3ad7e915892c73379bb379fdfe8c7274b26c1ae5f84631074553e). Ambiente comparado sem diferenças e sem exposição de segredos. Nenhuma escrita pendente antes do deploy; nenhum lote confirmado pelo agente. Banco, volumes e worker de remoção não recriados. Implementação validada com mocks; reconhecimento visual do plugin depende do teste manual autorizado pelo usuário.

Overlay compose.wcda-ausente.yaml muda somente api e worker-registration. Rollback operacional: recriar esses dois serviços usando apenas os overlays anteriores (imagem prm:cadastro-remocao-cargos-20261023b). Não reverter filas nem banco. Nenhum lote será confirmado pelo agente.
