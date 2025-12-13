# Product Specification - Paimon Prime Fund Backend

> Version: 1.0.0
> Status: Complete
> Source: docs/backend/00-overview.md

## 1. Product Overview

### 1.1 Business Context

Paimon Prime Fund is an **actively managed RWA index fund** deployed on BSC chain:

- **Tokenized Fund Shares**: Users purchase PPT tokens via USDT at current NAV
- **Three-Tier Liquidity**: L1 (Cash) + L2 (Money Market Funds) + L3 (High-Yield RWA)
- **Multi-Channel Redemption**: Standard (T+7) / Emergency (T+1) / Scheduled (Quarterly)
- **Tiered Approval**: Multi-level approval based on amount and liquidity ratio

### 1.2 Backend System Positioning

The backend system handles five core responsibilities:

| Responsibility | Description | Priority |
|----------------|-------------|----------|
| **Chain Monitoring** | Real-time contract event listening, sync chain state | Critical |
| **Rebalancing Execution** | Auto/manual asset rebalancing based on strategy | Critical |
| **Risk Control** | Risk indicator monitoring, alerts and responses | Critical |
| **Approval Workflow** | Process operations requiring manual approval | High |
| **Data Aggregation** | Aggregate chain data, provide queries and reports | Normal |

### 1.3 System Boundaries

**Backend System IS responsible for:**
- Listening to on-chain events
- Executing rebalancing transactions
- Risk monitoring and alerts
- Approval workflow management
- Data statistics and reports
- Admin dashboard

**Backend System IS NOT responsible for:**
- User wallet management
- User subscription/redemption UI
- Contract upgrades/deployment
- Private key custody
- Compliance audit reports
- User frontend interface

## 2. User Stories

### 2.1 Chain Monitoring

**US-001**: As a system operator, I need to monitor all contract events in real-time so that I can sync chain state accurately.

**Acceptance Criteria:**
- Event processing delay < 30 seconds
- No events lost (idempotent processing)
- Automatic reconnection on network failure
- Support checkpoint-based resumption

### 2.2 Redemption Management

**US-002**: As an admin, I need to view and manage redemption requests so that I can process approvals and settlements.

**Acceptance Criteria:**
- View redemption list with filters (status, channel, date)
- View redemption details with timeline
- Approve/reject redemptions requiring approval
- Manual settlement trigger

### 2.3 Rebalancing

**US-003**: As a fund manager, I need to execute asset rebalancing so that liquidity tiers stay within target ranges.

**Acceptance Criteria:**
- View current deviation from targets
- Preview rebalancing plan before execution
- Execute rebalancing with approval workflow
- View rebalancing history

### 2.4 Risk Monitoring

**US-004**: As a risk officer, I need real-time risk alerts so that I can respond to anomalies quickly.

**Acceptance Criteria:**
- Dashboard showing risk indicators
- Alert notifications (Slack/Telegram)
- Risk event history
- Liquidity forecasting

### 2.5 Approval Workflow

**US-005**: As an approver, I need to review and approve pending operations so that sensitive operations are properly authorized.

**Acceptance Criteria:**
- View pending approval list
- See approval details with risk assessment
- Approve/reject with reason
- SLA tracking and escalation

### 2.6 Reporting

**US-006**: As a stakeholder, I need daily/weekly/monthly reports so that I can track fund performance.

**Acceptance Criteria:**
- Daily report (NAV change, flows, risk)
- Weekly summary
- Monthly comprehensive report
- Export to PDF/Excel

## 3. Functional Requirements

### 3.1 API Endpoints

See `docs/backend/05-api-specification.md` for complete API specification.

**Key API Groups:**
- `/fund/*` - Fund data (overview, NAV history, assets, fees)
- `/redemptions/*` - Redemption management
- `/rebalance/*` - Rebalancing operations
- `/risk/*` - Risk monitoring
- `/approvals/*` - Approval workflow
- `/reports/*` - Reports
- `/system/*` - Health check, config

### 3.2 WebSocket Channels

Real-time push via WebSocket:
- `fund:overview` - Fund overview updates (every minute)
- `fund:nav` - NAV updates (real-time)
- `redemption:new` - New redemption requests
- `risk:alert` - Risk alerts
- `approval:new` - New approval tickets

### 3.3 Event Processing

See `docs/backend/01-event-listener.md` for complete event list.

**Critical Events:**
- `EmergencyModeChanged` - Trigger emergency protocol
- `LowLiquidityAlert` - Trigger liquidity warning
- `CriticalLiquidityAlert` - Pause new redemptions

### 3.4 Scheduled Tasks

- Daily 00:00 UTC: Check tier deviation
- Weekly Monday: Check asset allocation weights
- Every 5 minutes: Update risk metrics
- Hourly: Generate snapshots

## 4. Non-Functional Requirements

### 4.1 Performance

| Metric | Target |
|--------|--------|
| API P99 Response | < 500ms |
| Event Processing Delay | < 30s |
| System Availability | > 99.9% |
| Data Consistency | < 1 min delay |

### 4.2 Security

- JWT + Wallet Signature dual authentication
- RBAC fine-grained permissions
- Full HTTPS/TLS transport
- Encrypted storage for sensitive data
- Complete audit logging
- HSM/KMS key management

### 4.3 Observability

| Dimension | Implementation |
|-----------|----------------|
| Logging | Structured JSON + ELK |
| Metrics | Prometheus + Grafana |
| Tracing | OpenTelemetry |
| Alerting | PagerDuty / Slack |

## 5. Development Roadmap

### Phase 1: Infrastructure (Week 1-2)
- Project initialization (FastAPI structure)
- CI/CD pipeline
- Database schema (SQLAlchemy + Alembic)
- Chain interaction layer (web3.py)
- Auth module

### Phase 2: Core Features (Week 3-5)
- Event listener service
- Data sync service
- Redemption management
- Approval workflow

### Phase 3: Rebalancing & Risk (Week 6-8)
- Rebalancing strategy engine
- Rebalancing execution service
- Risk monitoring module
- Liquidity forecasting

### Phase 4: Dashboard & Reports (Week 9-10)
- Admin dashboard API
- Report generation service
- WebSocket real-time push

### Phase 5: Hardening & Launch (Week 11-12)
- Security audit
- Penetration testing
- Load testing
- Canary release

## 6. Glossary

| Term | Definition |
|------|------------|
| AUM | Assets Under Management |
| NAV | Net Asset Value per share |
| PPT | Paimon Prime Token (fund share token) |
| L1/L2/L3 | Three liquidity tiers |
| RWA | Real World Assets |
| Waterfall Liquidation | Priority-based asset liquidation |

---

## 7. Risk Management (Research Round 2)

> Validated: 2024-12-13

### 7.1 Risk Matrix

| Risk Category | Probability | Impact | Level | Status |
|---------------|-------------|--------|-------|--------|
| Chain Interaction | Medium | High | 🔴 Critical | Mitigated |
| Data Consistency | Medium | High | 🔴 Critical | Mitigated |
| System Availability | Low | High | 🟡 High | Mitigated |
| Performance | Low | Medium | 🟢 Medium | Mitigated |
| Fund Security | Low | Very High | 🔴 Critical | Mitigated |
| Audit Compliance | Low | High | 🟡 High | Mitigated |
| Operational | Medium | Medium | 🟡 High | Mitigated |
| Third-party Dependency | Medium | High | 🔴 Critical | Partially |

### 7.2 Critical Risks & Mitigations

**R1: Chain Interaction Risk**
- Existing: WebSocket + Polling, checkpoint resumption, deduplication
- Recommended: Multi-RPC auto-failover, health check & circuit breaker

**R2: Data Consistency Risk**
- Existing: Snapshot + incremental events, idempotent design
- Recommended: Reorg detection, periodic consistency validation

**R3: Fund Security Risk**
- Existing: eth_call simulation, multi-sig wallets, tiered approval
- Recommended: Flashbots for MEV protection, transaction amount limits

**R4: Third-party Dependency Risk**
- Existing: Multiple RPC alternatives
- Recommended: Multi-oracle aggregation, cross-region KMS backup

### 7.3 Risk Monitoring

See `docs/backend/03-risk-control.md` for detailed risk indicator system:
- Liquidity Risk: L1 ratio, coverage ratio
- Price Risk: NAV volatility, oracle staleness
- Concentration Risk: Single asset, top 3 assets
- Redemption Pressure: Daily rate, velocity

---

**Reference Documents:**
- `docs/backend/00-overview.md` - System overview
- `docs/backend/03-risk-control.md` - Risk control design
- `docs/backend/05-api-specification.md` - API specification
- `docs/backend/06-database-design.md` - Database design
