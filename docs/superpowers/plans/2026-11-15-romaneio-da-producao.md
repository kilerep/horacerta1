# Romaneio da produção Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (escolhido: execução direta). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mandar itens do relatório de produção direto para um romaneio de envio, com saldo do que já saiu, e renomear "Nota de envio" para "Romaneio de envio".

**Architecture:** Campo novo `ProductionEntry.production_order`; FK `ShipmentItem.source_entry`; view POST que cria/usa rascunho a partir de itens selecionados; modo Selecionar + menu de botão direito na lista de itens; troca de rótulos.

**Tech Stack:** Django 6, PostgreSQL, templates + JS puro.

**Spec:** `docs/superpowers/specs/2026-11-15-romaneio-da-producao-design.md`

## Global Constraints

- Textos pt-BR; sem "ponto/jornada/batida"; tokens de tema; alvos ≥ 44px.
- Isolamento por dono (404 para item/rascunho de outro).
- URLs existentes (`/nota-envio/<token>/`, `/me/relatorios-producao/notas/...`) continuam.

## Review Focus

- Item de outro dono no POST de criação: ignorado (404 se nenhum válido).
- Rascunho alvo enviado entre a escolha e o POST: não adiciona em nota travada (cria novo).
- Item sem quantidade/desenho: entra com 1 e "-".
- Saldo conta só romaneios SENT; rascunho não reduz saldo.
- Item já 100% enviado selecionado de novo: entra com quantidade 1 (dono ajusta), não 0.

---

### Task 1: Modelos e saldo
**Files:** `production/models.py`, migração, `production/forms.py` (campo no form), test `production/test_romaneio.py`
**Produces:** `ProductionEntry.production_order`; `ShipmentItem.source_entry` (FK null SET_NULL, related_name `shipment_items`); `ProductionEntry.shipped_quantity() -> int`; `ProductionEntry.remaining_quantity() -> int|None` (None se sem quantidade).
- [ ] Testes: `test_shipped_counts_only_sent_notes`, `test_remaining_never_negative`, `test_form_has_production_order`.
- [ ] FAIL → implementar → PASS → commit.

### Task 2: Criar/adicionar romaneio a partir de itens
**Files:** `production/shipment_views.py` (`shipment_from_entries`), `production/urls.py` (`shipment_from_entries` em `me/relatorios-producao/<uuid:sheet_id>/romaneio/`), test.
**Consumes:** Task 1. Rascunho novo herda destino/pessoas do último enviado.
- [ ] Testes: `test_creates_draft_with_remaining_quantity`, `test_adds_to_existing_draft`, `test_sent_target_creates_new_draft`, `test_other_owner_entries_ignored`, `test_entry_without_quantity_or_code`.
- [ ] FAIL → implementar → PASS → commit.

### Task 3: Tela da produção (seleção, botão direito, saldo) e campo OP na lista/PDF/Excel
**Files:** `templates/production/sheet_detail.html`, `_entry_fields.html`, `production/views.py` (contexto: rascunhos), `production/exports.py`.
- [ ] Testes: `test_sheet_detail_has_select_mode_and_drafts`, `test_entry_shows_sent_progress`, `test_exports_include_production_order`.
- [ ] FAIL → implementar → PASS → commit.

### Task 4: Renomear para "Romaneio de envio"
**Files:** templates/production/shipment_*.html, `_production_tabs.html`, `shipment_exports.py`, `shipment_views.py` (mensagens, WhatsApp, avisos), testes que citam "Nota de envio".
- [ ] Teste: `test_visible_name_is_romaneio` (lista, detalhe, público, PDF filename `romaneio-0001-...`, Excel título).
- [ ] FAIL → implementar → PASS → commit.

### Task 5: Verificação e publicação
- [ ] Capturas celular/computador; suíte completa; merge; push; deploy (reiniciar gunicorn e horacerta).
