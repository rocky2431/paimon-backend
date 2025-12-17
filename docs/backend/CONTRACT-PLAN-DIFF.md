# 合约与计划对比分析报告

> 日期: 2024-12-17
> 版本: 1.0
> 状态: 待修订

---

## 概述

本报告对比 `docs/backend/` 计划文档与 `contract-support/` 最新合约代码，识别需要修改的内容。

**核心发现**: 部分功能现在完全在链下实现，部分功能完全在链上实现，需要明确后端职责边界。

---

## 1. 审批阈值差异 [HIGH PRIORITY]

### 计划文档 (04-approval-workflow.md:42-43)
```
紧急赎回审批: >30K 或 >10% L1
标准赎回审批: >100K 或 >5% (L1+L2)
```

### 实际合约 (PPTTypes.sol:32-36)
```solidity
uint256 constant STANDARD_APPROVAL_AMOUNT = 50_000e18;    // 50K USDT (非 100K)
uint256 constant STANDARD_APPROVAL_QUOTA_RATIO = 2000;    // 20% 动态配额 (非 5%)
uint256 constant EMERGENCY_APPROVAL_AMOUNT = 30_000e18;   // 30K USDT ✓
uint256 constant EMERGENCY_APPROVAL_QUOTA_RATIO = 2000;   // 20% 紧急配额 (非 10%)
```

### 需要修改
- [ ] 更新 `04-approval-workflow.md` 审批阈值矩阵
- [ ] 标准赎回: 50K (非100K), 20%动态配额 (非5% L1+L2)
- [ ] 紧急赎回: 30K ✓, 20%紧急配额 (非10% L1)

---

## 2. 赎回费率差异 [HIGH PRIORITY]

### 计划文档假设
- 基础费率: 0.1%
- 紧急溢价: 1%

### 实际合约 (RedemptionManager.sol:177-178)
```solidity
baseRedemptionFeeBps = 100; // 1% (非 0.1%)
emergencyPenaltyFeeBps = 100; // 1%
// 紧急赎回总费率: 2%
```

### 注意
PPTTypes.sol 中的常量 `BASE_REDEMPTION_FEE = 10` (0.1%) 是旧值，实际初始化为 1%。

### 需要修改
- [ ] 更新所有文档中的费率说明
- [ ] 基础费率: 1% (可配置)
- [ ] 紧急费率: 2% (1% + 1%, 可配置)

---

## 3. 赎回取消功能已禁用 [CRITICAL]

### 计划文档 (01-event-listener.md:52)
```
RedemptionCancelled: 更新赎回状态
```

### 实际合约 (RedemptionManager.sol:316-319)
```solidity
function cancelRedemption(uint256 requestId) external override nonReentrant {
    // Redemption cancellation feature is disabled
    revert CancellationDisabled();
}
```

### 需要修改
- [ ] 删除或标记 `cancelRedemption` 相关的计划
- [ ] 用户提交赎回后无法取消，只能等待结算或被拒绝
- [ ] 更新 API 文档，移除取消端点

---

## 4. NFT Voucher 系统 (完全遗漏) [HIGH PRIORITY]

### 计划文档
未提及 NFT Voucher 机制

### 实际合约 (RedemptionManager.sol:85-88, 256-298)
```solidity
IRedemptionVoucher public redemptionVoucher;
uint256 public voucherThreshold; // 默认 7 天

// 当结算延迟 > voucherThreshold 时自动铸造 NFT
// NFT 持有人可交易转让赎回权
// 结算时只有 NFT 持有人可调用 settleWithVoucher(tokenId)
```

### 需要添加
- [ ] 新增 RedemptionVoucher 合约事件监听
- [ ] 事件: `VoucherMinted(requestId, tokenId, owner)`
- [ ] 跟踪 NFT 所有权变更 (ERC721 Transfer 事件)
- [ ] 更新 API 支持查询用户的 Voucher
- [ ] 添加 Voucher 到期提醒通知

---

## 5. 新增事件 (未在计划中) [HIGH PRIORITY]

### RedemptionManager 新事件
| 事件 | 描述 | 优先级 |
|------|------|--------|
| `DailyLiabilityAdded` | 每日负债记录 | Normal |
| `LiabilityRemoved` | 负债清除 | Normal |
| `SettlementWaterfallTriggered` | 结算瀑布清算触发 | High |
| `VoucherMinted` | NFT 凭证铸造 | High |
| `VoucherThresholdUpdated` | NFT 阈值变更 | Normal |
| `RedemptionVoucherUpdated` | NFT 合约地址变更 | Normal |
| `BaseRedemptionFeeUpdated` | 基础费率变更 | High |
| `EmergencyPenaltyFeeUpdated` | 紧急费率变更 | High |
| `AssetSchedulerUpdated` | 调度器地址变更 | Normal |
| `AssetControllerUpdated` | 资产控制器地址变更 | Normal |

### 需要修改
- [ ] 更新 `01-event-listener.md` 事件清单
- [ ] 添加对应的 Handler 实现

---

## 6. 审批流程: 链上执行 (非纯后端) [CRITICAL]

### 计划文档假设
审批是纯后端 DB 状态更新

### 实际合约 (RedemptionManager.sol:426-436)
```solidity
// VIP_APPROVER_ROLE 必须调用链上函数
function approveRedemption(uint256 requestId) external override onlyRole(VIP_APPROVER_ROLE);
function approveRedemptionWithDate(uint256 requestId, uint256 customSettlementTime) external onlyRole(VIP_APPROVER_ROLE);
function rejectRedemption(uint256 requestId, string calldata reason) external override onlyRole(VIP_APPROVER_ROLE);
```

### 实际流程
```
1. 用户调用 requestRedemption() → 链上
2. 后端监听 RedemptionRequested 事件 (requiresApproval=true)
3. 后端创建内部审批工单
4. 人工审批决策
5. 后端调用 approveRedemption() 或 rejectRedemption() → 链上交易
6. 后端监听 RedemptionApproved/RedemptionRejected 事件
```

### 需要修改
- [ ] 更新 `04-approval-workflow.md` 流程图
- [ ] 添加 BlockchainService 调用说明
- [ ] 明确后端需要持有 VIP_APPROVER_ROLE 的私钥

---

## 7. 自定义结算日期 (新功能) [MEDIUM]

### 计划文档
未提及可自定义结算日期

### 实际合约 (RedemptionManager.sol:434-439)
```solidity
/// @notice 审批时可指定自定义结算日期
/// @param customSettlementTime 0 表示使用默认延迟
function approveRedemptionWithDate(
    uint256 requestId,
    uint256 customSettlementTime
) external onlyRole(VIP_APPROVER_ROLE);
```

### 需要添加
- [ ] 更新审批 API 支持 `customSettlementTime` 参数
- [ ] 添加审批 UI 日期选择器

---

## 8. 负债追踪系统 (新模块) [HIGH PRIORITY]

### 计划文档
仅简单提及 liability，未详细说明

### 实际合约 (RedemptionManager.sol:74-78, 867-940)
```solidity
// 按日追踪负债
mapping(uint256 => uint256) public dailyLiability; // dayIndex => amount
uint256 public overdueLiability; // 逾期负债

// 后端需定期调用
function processOverdueLiabilityBatch(uint256 daysBack) external;
function getSevenDayLiability() public view returns (uint256 total);
function getOverdueLiability() public view returns (uint256);
function getDailyLiability(uint256 dayIndex) public view returns (uint256);
```

### 需要添加
- [ ] 新增 `03-liability-tracking.md` 文档
- [ ] 添加定时任务: 每日调用 `processOverdueLiabilityBatch(30)`
- [ ] 添加负债监控仪表板 API

---

## 9. 动态配额计算 (链上) [IMPORTANT]

### 计划文档
未详细说明配额计算

### 实际合约 (PPT.sol - getStandardChannelQuota)
```solidity
// 标准通道动态配额计算 (链上完成)
// 公式: (L1 + L2) × 70% - emergencyQuota - fees - lockedMint - overdue - sevenDay
function getStandardChannelQuota() external view returns (uint256);
```

### 需要修改
- [ ] 更新 `03-risk-control.md` 添加配额计算说明
- [ ] 后端只需调用链上函数获取，无需自行计算

---

## 10. 结算瀑布清算 (链上自动) [IMPORTANT]

### 计划文档
瀑布清算由后端触发

### 实际合约 (RedemptionManager.sol:697-712)
```solidity
// 结算时自动触发瀑布清算 (链上完成)
if (availableCash < payoutAmount) {
    uint256 deficit = payoutAmount - availableCash;
    if (address(assetController) != address(0)) {
        uint256 funded = assetController.executeWaterfallLiquidation(
            deficit,
            PPTTypes.LiquidityTier.TIER_1_CASH  // 只清算 L1 收益资产
        );
        emit SettlementWaterfallTriggered(request.requestId, deficit, funded);
    }
}
```

### 需要修改
- [ ] 更新 `02-rebalance-engine.md` 说明瀑布清算是链上自动的
- [ ] 后端只监听 `SettlementWaterfallTriggered` 事件

---

## 11. PendingApprovalShares 概念 (新) [IMPORTANT]

### 计划文档
仅有 lockedShares

### 实际合约 (PPT.sol, RedemptionManager.sol)
```solidity
// 待审批份额 (不影响 NAV，但限制转账)
mapping(address => uint256) public pendingApprovalSharesOf;

// 流程:
// 1. 需要审批时: addPendingApprovalShares() - 不锁定，不影响NAV
// 2. 审批通过后: convertPendingToLocked() - 转为锁定，影响NAV
// 3. 审批拒绝时: removePendingApprovalShares() - 移除标记
```

### 需要添加
- [ ] 更新数据模型添加 `pending_approval_shares` 字段
- [ ] 更新 API 返回用户的各类份额状态

---

## 12. 链上 vs 链下职责边界 [CRITICAL]

### 完全链上 (后端只监听)
| 功能 | 合约 | 说明 |
|------|------|------|
| 份额锁定/解锁 | PPT | 自动完成 |
| 负债计算 | PPT/RM | 自动完成 |
| 费用计算 | RM | 自动完成 |
| 配额计算 | PPT | 自动完成 |
| 瀑布清算 | RM/AC | 结算时自动 |
| NFT 铸造 | RM | 审批时自动 |

### 后端触发链上
| 功能 | 说明 |
|------|------|
| 审批/拒绝赎回 | 调用 approveRedemption/rejectRedemption |
| 资产购买/赎回 | 调用 AssetController |
| 费用提取 | 调用 withdrawRedemptionFees |
| 配置变更 | 调用各种 set* 函数 |

### 纯链下
| 功能 | 说明 |
|------|------|
| 审批决策 | 人工决定，后端执行 |
| 风险计算 | 后端计算各种风险指标 |
| 调仓策略 | 后端计算最优方案 |
| 通知发送 | 完全后端 |
| 报表生成 | 完全后端 |
| 负债处理 | 后端调用 processOverdueLiabilityBatch |

---

## 13. 待办事项汇总

### P0 - 必须立即修改
- [ ] 更新审批阈值 (50K/20% vs 100K/5%)
- [ ] 添加审批流程的链上调用说明
- [ ] 删除赎回取消功能
- [ ] 添加 NFT Voucher 事件监听

### P1 - 高优先级
- [ ] 添加新事件到事件清单
- [ ] 添加负债追踪模块
- [ ] 更新费率说明 (1%/2%)
- [ ] 添加 pendingApprovalShares 概念

### P2 - 中优先级
- [ ] 添加自定义结算日期支持
- [ ] 更新动态配额说明
- [ ] 更新瀑布清算说明

### P3 - 低优先级
- [ ] 完善链上/链下职责边界文档
- [ ] 添加合约角色说明 (VIP_APPROVER_ROLE, ADMIN_ROLE, OPERATOR)

---

## 14. 合约角色说明 (补充)

### RedemptionManager 角色
```solidity
ADMIN_ROLE:
  - setAssetScheduler, setAssetController
  - setBaseRedemptionFee, setEmergencyPenaltyFee
  - setRedemptionVoucher, setVoucherThreshold
  - adjustOverdueLiability, adjustDailyLiability
  - pause/unpause

VIP_APPROVER_ROLE:
  - approveRedemption, approveRedemptionWithDate
  - rejectRedemption
```

### PPT (Vault) 角色
```solidity
OPERATOR:
  - lockShares, unlockShares, burnLockedShares
  - addRedemptionLiability, removeRedemptionLiability
  - addRedemptionFee, reduceRedemptionFee
  - transferAssetTo, approveAsset
  - addPendingApprovalShares, removePendingApprovalShares, convertPendingToLocked
  - reduceEmergencyQuota, restoreEmergencyQuota, refreshEmergencyQuota
```

**后端需要的角色**: `VIP_APPROVER_ROLE` (用于审批), `OPERATOR` 角色通常分配给 RedemptionManager 合约

---

*本报告应作为更新计划文档的指南。建议逐条核对并更新相应文档。*
