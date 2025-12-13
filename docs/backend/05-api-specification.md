# API 规范

> 模块: API Specification
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. API 概述

### 1.1 基础信息

| 属性 | 值 |
|------|-----|
| Base URL | `https://api.paimon.fund/v1` |
| 协议 | HTTPS |
| 格式 | JSON |
| 认证 | JWT + 钱包签名 |
| 版本 | v1 |

### 1.2 通用响应格式

```typescript
// 成功响应
interface SuccessResponse<T> {
  success: true;
  data: T;
  timestamp: string;
  requestId: string;
}

// 错误响应
interface ErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, any>;
  };
  timestamp: string;
  requestId: string;
}

// 分页响应
interface PaginatedResponse<T> {
  success: true;
  data: {
    items: T[];
    pagination: {
      total: number;
      page: number;
      pageSize: number;
      totalPages: number;
    };
  };
  timestamp: string;
  requestId: string;
}
```

### 1.3 错误码

| 错误码 | HTTP状态码 | 描述 |
|--------|-----------|------|
| `AUTH_REQUIRED` | 401 | 需要认证 |
| `AUTH_INVALID` | 401 | 认证无效 |
| `AUTH_EXPIRED` | 401 | 认证已过期 |
| `FORBIDDEN` | 403 | 无权限 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `VALIDATION_ERROR` | 400 | 参数验证失败 |
| `CONFLICT` | 409 | 资源冲突 |
| `RATE_LIMITED` | 429 | 请求过于频繁 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
| `SERVICE_UNAVAILABLE` | 503 | 服务不可用 |

---

## 2. 认证

### 2.1 JWT 认证

```http
Authorization: Bearer <jwt_token>
```

### 2.2 钱包签名认证

用于敏感操作，需要钱包签名：

```http
X-Wallet-Address: 0x...
X-Wallet-Signature: 0x...
X-Signature-Timestamp: 1702468800
```

签名消息格式：
```
Paimon Fund Operation
Action: {action}
Timestamp: {timestamp}
Nonce: {nonce}
```

---

## 3. 基金数据 API

### 3.1 获取基金概览

```http
GET /fund/overview
```

**响应:**
```json
{
  "success": true,
  "data": {
    "totalAssets": "12345678000000000000000000",
    "totalSupply": "11728645000000000000000000",
    "sharePrice": "1052300000000000000",
    "nav": "1.0523",
    "aum": "12345678.00",
    "layer1Liquidity": "1234567800000000000000000",
    "layer2Liquidity": "3703703400000000000000000",
    "layer3Value": "7407406800000000000000000",
    "totalRedemptionLiability": "234567000000000000000000",
    "totalLockedShares": "222853000000000000000000",
    "emergencyMode": false,
    "layers": {
      "L1": { "value": "1234567.80", "ratio": "0.10" },
      "L2": { "value": "3703703.40", "ratio": "0.30" },
      "L3": { "value": "7407406.80", "ratio": "0.60" }
    },
    "lastUpdated": "2024-12-13T12:34:56Z"
  }
}
```

### 3.2 获取 NAV 历史

```http
GET /fund/nav/history
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `startDate` | string | 否 | 开始日期 (ISO 8601) |
| `endDate` | string | 否 | 结束日期 (ISO 8601) |
| `interval` | string | 否 | 间隔 (hourly/daily/weekly) |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "timestamp": "2024-12-13T00:00:00Z",
        "nav": "1.0523",
        "totalAssets": "12345678.00",
        "totalSupply": "11728645.00"
      }
    ],
    "change24h": "0.0023",
    "change7d": "0.0156",
    "change30d": "0.0412"
  }
}
```

### 3.3 获取流动性层级详情

```http
GET /fund/liquidity/layers
```

**响应:**
```json
{
  "success": true,
  "data": {
    "L1": {
      "name": "TIER_1_CASH",
      "description": "现金及即时生息资产",
      "value": "1234567.80",
      "ratio": "0.10",
      "target": "0.10",
      "min": "0.05",
      "max": "0.20",
      "deviation": "0.00",
      "status": "normal"
    },
    "L2": {
      "name": "TIER_2_MMF",
      "description": "货币市场基金",
      "value": "3703703.40",
      "ratio": "0.30",
      "target": "0.30",
      "min": "0.20",
      "max": "0.40",
      "deviation": "0.00",
      "status": "normal"
    },
    "L3": {
      "name": "TIER_3_HYD",
      "description": "高收益资产",
      "value": "7407406.80",
      "ratio": "0.60",
      "target": "0.60",
      "min": "0.50",
      "max": "0.70",
      "deviation": "0.00",
      "status": "normal"
    }
  }
}
```

### 3.4 获取资产持仓

```http
GET /fund/assets
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `tier` | string | 否 | 筛选层级 (L1/L2/L3) |
| `active` | boolean | 否 | 是否仅显示活跃资产 |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "token": "0x55d398326f99059fF775485246999027B3197955",
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": 18,
        "tier": "L1",
        "balance": "1234567800000000000000000",
        "price": "1.0000",
        "value": "1234567.80",
        "allocation": "0.10",
        "targetAllocation": "0.10",
        "isActive": true,
        "change24h": "0.00"
      },
      {
        "token": "0x1234...5678",
        "symbol": "RWA-A",
        "name": "RWA Asset A",
        "decimals": 18,
        "tier": "L3",
        "balance": "2000000000000000000000000",
        "price": "1.85",
        "value": "3700000.00",
        "allocation": "0.30",
        "targetAllocation": "0.30",
        "isActive": true,
        "change24h": "+0.50"
      }
    ],
    "summary": {
      "totalAssets": 5,
      "activeAssets": 5,
      "totalValue": "12345678.00"
    }
  }
}
```

### 3.5 获取费用统计

```http
GET /fund/fees
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `startDate` | string | 否 | 开始日期 |
| `endDate` | string | 否 | 结束日期 |

**响应:**
```json
{
  "success": true,
  "data": {
    "accumulated": {
      "managementFees": "12345.67",
      "performanceFees": "23456.78",
      "redemptionFees": "3456.78",
      "total": "39259.23"
    },
    "pending": {
      "managementFees": "1234.56",
      "performanceFees": "2345.67",
      "redemptionFees": "345.67",
      "total": "3925.90"
    },
    "withdrawn": {
      "managementFees": "11111.11",
      "performanceFees": "21111.11",
      "redemptionFees": "3111.11",
      "total": "35333.33"
    },
    "feeRates": {
      "managementFee": "0.50",
      "performanceFee": "10.00",
      "baseRedemptionFee": "0.10",
      "emergencyFeeExtra": "1.00"
    }
  }
}
```

---

## 4. 赎回管理 API

### 4.1 获取赎回列表

```http
GET /redemptions
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `status` | string | 否 | 状态筛选 |
| `channel` | string | 否 | 通道筛选 (STANDARD/EMERGENCY/SCHEDULED) |
| `owner` | string | 否 | 所有者地址 |
| `startDate` | string | 否 | 开始日期 |
| `endDate` | string | 否 | 结束日期 |
| `page` | number | 否 | 页码 (默认1) |
| `pageSize` | number | 否 | 每页数量 (默认20) |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "requestId": "123",
        "owner": "0xabc...def",
        "receiver": "0xabc...def",
        "shares": "100000000000000000000000",
        "grossAmount": "105230000000000000000000",
        "lockedNav": "1052300000000000000",
        "estimatedFee": "105230000000000000000",
        "requestTime": "2024-12-13T10:00:00Z",
        "settlementTime": "2024-12-20T10:00:00Z",
        "status": "PENDING",
        "channel": "STANDARD",
        "requiresApproval": false,
        "windowId": null,
        "txHash": "0x..."
      }
    ],
    "pagination": {
      "total": 150,
      "page": 1,
      "pageSize": 20,
      "totalPages": 8
    }
  }
}
```

### 4.2 获取赎回详情

```http
GET /redemptions/:requestId
```

**响应:**
```json
{
  "success": true,
  "data": {
    "requestId": "123",
    "owner": "0xabc...def",
    "receiver": "0xabc...def",
    "shares": "100000000000000000000000",
    "grossAmount": "105230000000000000000000",
    "lockedNav": "1052300000000000000",
    "estimatedFee": "105230000000000000000",
    "netAmount": "105124770000000000000000",
    "requestTime": "2024-12-13T10:00:00Z",
    "settlementTime": "2024-12-20T10:00:00Z",
    "status": "PENDING",
    "channel": "STANDARD",
    "requiresApproval": false,
    "windowId": null,
    "txHash": "0x...",
    "blockNumber": 12345678,
    "approvalTicket": null,
    "timeline": [
      {
        "event": "REQUESTED",
        "timestamp": "2024-12-13T10:00:00Z",
        "txHash": "0x..."
      }
    ]
  }
}
```

### 4.3 获取待审批赎回

```http
GET /redemptions/pending-approvals
```

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "requestId": "456",
        "owner": "0xdef...abc",
        "grossAmount": "150000000000000000000000",
        "channel": "STANDARD",
        "requestTime": "2024-12-13T11:00:00Z",
        "approvalTicketId": "ticket-123",
        "slaDeadline": "2024-12-14T11:00:00Z",
        "reason": "金额超过 100K USDT"
      }
    ],
    "summary": {
      "totalPending": 3,
      "totalAmount": "450000.00",
      "urgentCount": 1
    }
  }
}
```

### 4.4 批准赎回

```http
POST /redemptions/:requestId/approve
```

**请求头:**
```http
X-Wallet-Address: 0x...
X-Wallet-Signature: 0x...
X-Signature-Timestamp: 1702468800
```

**请求体:**
```json
{
  "reason": "审批通过"
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "requestId": "456",
    "status": "APPROVED",
    "approvedBy": "0x...",
    "approvedAt": "2024-12-13T12:00:00Z",
    "txHash": "0x..."
  }
}
```

### 4.5 拒绝赎回

```http
POST /redemptions/:requestId/reject
```

**请求体:**
```json
{
  "reason": "流动性不足，请选择定期赎回通道"
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "requestId": "456",
    "status": "REJECTED",
    "rejectedBy": "0x...",
    "rejectedAt": "2024-12-13T12:00:00Z",
    "reason": "流动性不足，请选择定期赎回通道",
    "txHash": "0x..."
  }
}
```

### 4.6 手动结算赎回

```http
POST /redemptions/:requestId/settle
```

**响应:**
```json
{
  "success": true,
  "data": {
    "requestId": "123",
    "status": "SETTLED",
    "grossAmount": "105230.00",
    "fee": "105.23",
    "netAmount": "105124.77",
    "settledAt": "2024-12-20T10:00:00Z",
    "txHash": "0x..."
  }
}
```

---

## 5. 调仓 API

### 5.1 获取调仓状态

```http
GET /rebalance/status
```

**响应:**
```json
{
  "success": true,
  "data": {
    "needsRebalance": false,
    "lastRebalance": "2024-12-12T00:00:00Z",
    "nextScheduled": "2024-12-14T00:00:00Z",
    "currentDeviation": {
      "L1": "0.002",
      "L2": "-0.005",
      "L3": "0.003"
    },
    "thresholds": {
      "triggerDeviation": "0.05",
      "minAmount": "10000"
    },
    "pendingPlan": null
  }
}
```

### 5.2 获取调仓历史

```http
GET /rebalance/history
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `startDate` | string | 否 | 开始日期 |
| `endDate` | string | 否 | 结束日期 |
| `trigger` | string | 否 | 触发类型 |
| `page` | number | 否 | 页码 |
| `pageSize` | number | 否 | 每页数量 |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "rebal-001",
        "trigger": "THRESHOLD",
        "createdAt": "2024-12-12T00:00:00Z",
        "executedAt": "2024-12-12T00:05:00Z",
        "status": "COMPLETED",
        "preState": {
          "l1Ratio": "0.08",
          "l2Ratio": "0.32",
          "l3Ratio": "0.60"
        },
        "postState": {
          "l1Ratio": "0.10",
          "l2Ratio": "0.30",
          "l3Ratio": "0.60"
        },
        "actions": [
          {
            "type": "TRANSFER",
            "fromLayer": "L2",
            "toLayer": "L1",
            "amount": "246913.56",
            "txHash": "0x..."
          }
        ],
        "gasCost": "0.05",
        "executedBy": "0x..."
      }
    ],
    "pagination": {
      "total": 50,
      "page": 1,
      "pageSize": 20,
      "totalPages": 3
    }
  }
}
```

### 5.3 预览调仓计划

```http
POST /rebalance/preview
```

**请求体:**
```json
{
  "targetRatios": {
    "L1": "0.10",
    "L2": "0.30",
    "L3": "0.60"
  }
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "planId": "preview-001",
    "preState": {
      "l1Ratio": "0.08",
      "l2Ratio": "0.32",
      "l3Ratio": "0.60"
    },
    "targetState": {
      "l1Ratio": "0.10",
      "l2Ratio": "0.30",
      "l3Ratio": "0.60"
    },
    "actions": [
      {
        "type": "TRANSFER",
        "fromLayer": "L2",
        "toLayer": "L1",
        "amount": "246913.56",
        "estimatedSlippage": "0.001"
      }
    ],
    "estimatedGasCost": "0.05",
    "totalAmount": "246913.56",
    "requiresApproval": true,
    "approvalReason": "金额超过 50K"
  }
}
```

### 5.4 执行调仓

```http
POST /rebalance/execute
```

**请求头:** 需要钱包签名

**请求体:**
```json
{
  "planId": "preview-001"
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "planId": "rebal-002",
    "status": "PENDING_APPROVAL",
    "approvalTicketId": "ticket-456",
    "message": "调仓计划已提交审批"
  }
}
```

---

## 6. 风控 API

### 6.1 获取风险状态

```http
GET /risk/status
```

**响应:**
```json
{
  "success": true,
  "data": {
    "overallLevel": "NORMAL",
    "overallScore": 15,
    "indicators": {
      "liquidity": {
        "status": "normal",
        "indicators": [
          { "name": "L1占比", "value": "10.2%", "threshold": "8%", "status": "normal" },
          { "name": "L1+L2占比", "value": "40.5%", "threshold": "35%", "status": "normal" },
          { "name": "赎回覆盖率", "value": "156%", "threshold": "100%", "status": "normal" }
        ]
      },
      "price": {
        "status": "normal",
        "indicators": [
          { "name": "NAV波动(24h)", "value": "1.2%", "threshold": "5%", "status": "normal" },
          { "name": "价格偏离", "value": "0.5%", "threshold": "3%", "status": "normal" }
        ]
      },
      "concentration": {
        "status": "normal",
        "indicators": [
          { "name": "最大单资产", "value": "18%", "threshold": "25%", "status": "normal" },
          { "name": "前3资产", "value": "48%", "threshold": "60%", "status": "normal" }
        ]
      },
      "redemption": {
        "status": "normal",
        "indicators": [
          { "name": "单日赎回率", "value": "2.1%", "threshold": "5%", "status": "normal" }
        ]
      }
    },
    "lastUpdated": "2024-12-13T12:34:56Z"
  }
}
```

### 6.2 获取风险事件

```http
GET /risk/events
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `severity` | string | 否 | 严重程度 (info/warning/critical) |
| `resolved` | boolean | 否 | 是否已解决 |
| `startDate` | string | 否 | 开始日期 |
| `endDate` | string | 否 | 结束日期 |
| `page` | number | 否 | 页码 |
| `pageSize` | number | 否 | 每页数量 |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "risk-001",
        "type": "LOW_LIQUIDITY",
        "severity": "warning",
        "metricName": "l1_ratio",
        "thresholdValue": "0.08",
        "actualValue": "0.078",
        "message": "L1流动性降至7.8%，低于安全阈值8%",
        "resolved": true,
        "resolvedAt": "2024-12-12T11:30:00Z",
        "createdAt": "2024-12-12T10:00:00Z",
        "duration": 5400
      }
    ],
    "pagination": {
      "total": 25,
      "page": 1,
      "pageSize": 20,
      "totalPages": 2
    }
  }
}
```

### 6.3 获取流动性预测

```http
GET /risk/liquidity-forecast
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `horizon` | string | 否 | 预测范围 (1d/7d/30d)，默认7d |

**响应:**
```json
{
  "success": true,
  "data": {
    "horizon": "7d",
    "currentLiquidity": {
      "L1": "1234567.80",
      "L2": "3703703.40",
      "available": "4938271.20"
    },
    "forecast": {
      "expectedInflow": "125000.00",
      "expectedOutflow": "89000.00",
      "confirmedOutflow": "56000.00",
      "probabilisticOutflow": "33000.00",
      "netFlow": "+36000.00",
      "projectedBalance": "4974271.20"
    },
    "risk": {
      "shortfallProbability": "2.3%",
      "shortfallAmount": "0.00",
      "confidenceInterval": {
        "lower": "4850000.00",
        "upper": "5100000.00"
      }
    },
    "recommendation": {
      "action": "NONE",
      "reason": "流动性充足，无需额外操作"
    },
    "generatedAt": "2024-12-13T12:00:00Z"
  }
}
```

---

## 7. 审批 API

### 7.1 获取待审批列表

```http
GET /approvals
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `status` | string | 否 | 状态筛选 |
| `type` | string | 否 | 类型筛选 |
| `page` | number | 否 | 页码 |
| `pageSize` | number | 否 | 每页数量 |

**响应:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "ticket-001",
        "type": "STANDARD_REDEMPTION",
        "status": "PENDING",
        "referenceType": "REDEMPTION",
        "referenceId": "456",
        "requester": "0xabc...def",
        "amount": "150000000000000000000000",
        "description": "标准赎回审批 - 金额超过100K",
        "createdAt": "2024-12-13T11:00:00Z",
        "slaDeadline": "2024-12-14T11:00:00Z",
        "slaRemaining": 82800,
        "requiredApprovals": 1,
        "currentApprovals": 0
      }
    ],
    "pagination": {
      "total": 5,
      "page": 1,
      "pageSize": 20,
      "totalPages": 1
    }
  }
}
```

### 7.2 审批通过

```http
POST /approvals/:id/approve
```

**请求头:** 需要钱包签名

**请求体:**
```json
{
  "reason": "已核实，批准通过"
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "ticketId": "ticket-001",
    "status": "APPROVED",
    "approvedBy": "0x...",
    "approvedAt": "2024-12-13T12:00:00Z"
  }
}
```

### 7.3 审批拒绝

```http
POST /approvals/:id/reject
```

**请求体:**
```json
{
  "reason": "流动性不足，建议延后"
}
```

---

## 8. 报表 API

### 8.1 获取每日报告

```http
GET /reports/daily
```

**参数:**
| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `date` | string | 否 | 日期 (默认昨天) |

**响应:**
```json
{
  "success": true,
  "data": {
    "date": "2024-12-12",
    "summary": {
      "openingNav": "1.0500",
      "closingNav": "1.0523",
      "navChange": "+0.22%",
      "openingAum": "12000000.00",
      "closingAum": "12345678.00",
      "aumChange": "+2.88%"
    },
    "flows": {
      "deposits": {
        "count": 15,
        "amount": "456789.00"
      },
      "redemptions": {
        "count": 8,
        "amount": "123456.00"
      },
      "netFlow": "+333333.00"
    },
    "liquidity": {
      "l1Ratio": "10.0%",
      "l2Ratio": "30.0%",
      "l3Ratio": "60.0%"
    },
    "risk": {
      "overallLevel": "NORMAL",
      "events": 1
    },
    "operations": {
      "rebalances": 1,
      "approvals": 3
    }
  }
}
```

### 8.2 获取周报

```http
GET /reports/weekly
```

### 8.3 获取月报

```http
GET /reports/monthly
```

---

## 9. 系统 API

### 9.1 健康检查

```http
GET /system/health
```

**响应:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 864000,
    "components": {
      "database": "healthy",
      "redis": "healthy",
      "blockchain": "healthy",
      "eventListener": "healthy"
    },
    "lastBlockProcessed": 12345678,
    "blockLag": 2
  }
}
```

### 9.2 获取系统配置

```http
GET /system/config
```

**响应:**
```json
{
  "success": true,
  "data": {
    "contracts": {
      "vault": "0x...",
      "redemptionManager": "0x...",
      "assetController": "0x..."
    },
    "thresholds": {
      "emergencyApprovalAmount": "30000",
      "standardApprovalAmount": "100000",
      "rebalanceApprovalAmount": "50000"
    },
    "fees": {
      "baseRedemptionFee": "0.10%",
      "emergencyFeeExtra": "1.00%",
      "managementFee": "0.50%",
      "performanceFee": "10.00%"
    }
  }
}
```

---

## 10. WebSocket API

### 10.1 连接

```
wss://api.paimon.fund/v1/ws
```

### 10.2 认证

```json
{
  "type": "auth",
  "token": "<jwt_token>"
}
```

### 10.3 订阅频道

```json
{
  "type": "subscribe",
  "channels": ["fund:overview", "redemption:new", "risk:alert"]
}
```

### 10.4 频道消息格式

```json
{
  "channel": "fund:overview",
  "data": {
    "totalAssets": "12345678.00",
    "nav": "1.0523",
    "timestamp": "2024-12-13T12:34:56Z"
  }
}
```

### 10.5 可用频道

| 频道 | 描述 | 推送频率 |
|------|------|----------|
| `fund:overview` | 基金概览更新 | 每分钟 |
| `fund:nav` | NAV 更新 | 实时 |
| `redemption:new` | 新赎回请求 | 实时 |
| `redemption:settled` | 赎回结算 | 实时 |
| `approval:new` | 新审批工单 | 实时 |
| `approval:resolved` | 审批完成 | 实时 |
| `risk:alert` | 风险告警 | 实时 |
| `rebalance:executed` | 调仓执行 | 实时 |

---

*下一节: [06-database-design.md](./06-database-design.md) - 数据库设计*
