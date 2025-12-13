# 权限管理设计

> 模块: Permission Management
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 权限体系概述

### 1.1 双层权限架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Permission Architecture                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    链上权限 (On-chain)                             │  │
│  │  • 由智能合约 AccessControl 管理                                   │  │
│  │  • 控制链上操作 (调仓、审批、紧急模式等)                           │  │
│  │  • 角色: ADMIN_ROLE, OPERATOR_ROLE, REBALANCER_ROLE, VIP_APPROVER │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    链下权限 (Off-chain)                            │  │
│  │  • 由后端系统 RBAC 管理                                            │  │
│  │  • 控制 API 访问、仪表板功能、报表查看                             │  │
│  │  • 角色: super_admin, admin, operator, viewer                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 角色映射

| 链上角色 | 链下角色 | 说明 |
|----------|----------|------|
| `DEFAULT_ADMIN_ROLE` | `super_admin` | 超级管理员，管理其他角色 |
| `ADMIN_ROLE` | `admin` | 管理员，配置和紧急操作 |
| `REBALANCER_ROLE` | `operator` | 操作员，执行调仓 |
| `VIP_APPROVER_ROLE` | `admin` | 审批人，审批赎回 |
| - | `viewer` | 只读访问 |

---

## 2. 链上权限 (Smart Contract)

### 2.1 合约角色定义

```solidity
// 来自合约代码
bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
bytes32 public constant REBALANCER_ROLE = keccak256("REBALANCER_ROLE");
bytes32 public constant VIP_APPROVER_ROLE = keccak256("VIP_APPROVER_ROLE");
```

### 2.2 角色权限矩阵

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    On-chain Role Permission Matrix                          │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  操作                        │ ADMIN │ OPERATOR │ REBALANCER │ VIP_APPROVER│
│  ─────────────────────────────────────────────────────────────────────────  │
│  PNGYVault                                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  pause/unpause              │   ✓   │    -     │     -      │      -       │
│  setEmergencyMode           │   ✓   │    -     │     -      │      -       │
│  setAssetController         │   ✓   │    -     │     -      │      -       │
│  lockShares                 │   -   │    ✓     │     -      │      -       │
│  unlockShares               │   -   │    ✓     │     -      │      -       │
│  burnLockedShares           │   -   │    ✓     │     -      │      -       │
│  addRedemptionLiability     │   -   │    ✓     │     -      │      -       │
│  removeRedemptionLiability  │   -   │    ✓     │     -      │      -       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  RedemptionManager                                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  pause/unpause              │   ✓   │    -     │     -      │      -       │
│  approveRedemption          │   -   │    -     │     -      │      ✓       │
│  rejectRedemption           │   -   │    -     │     -      │      ✓       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  AssetController                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  addAsset                   │   ✓   │    -     │     -      │      -       │
│  removeAsset                │   ✓   │    -     │     -      │      -       │
│  updateAssetAllocation      │   ✓   │    -     │     -      │      -       │
│  setFeeRecipient            │   ✓   │    -     │     -      │      -       │
│  collectFees                │   ✓   │    -     │     -      │      -       │
│  allocateToLayer            │   -   │    -     │     ✓      │      -       │
│  purchaseAsset              │   -   │    -     │     ✓      │      -       │
│  redeemAsset                │   -   │    -     │     ✓      │      -       │
│  executeWaterfallLiquidation│   -   │    -     │     ✓      │      -       │
│  rebalanceBuffer            │   -   │    -     │     ✓      │      -       │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 多签钱包配置

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from decimal import Decimal


@dataclass
class GnosisSafeWallet:
    type: Literal['gnosis-safe'] = 'gnosis-safe'
    address: str = ''
    threshold: int = 2
    owners: list[str] = field(default_factory=list)


@dataclass
class EOAWallet:
    type: Literal['eoa'] = 'eoa'
    address: str = ''
    daily_limit: Decimal = Decimal('500000')


@dataclass
class RebalancerWallets:
    hot: EOAWallet
    warm: GnosisSafeWallet


@dataclass
class VIPApprover:
    address: str
    name: str


@dataclass
class MultisigConfig:
    # 超级管理员 (合约升级、角色管理)
    super_admin: GnosisSafeWallet

    # 管理员 (资产配置、费用管理)
    admin: GnosisSafeWallet

    # 调仓执行 (日常操作)
    rebalancer: RebalancerWallets

    # 审批人
    vip_approvers: list[VIPApprover]


# 配置示例
multisig_config = MultisigConfig(
    super_admin=GnosisSafeWallet(
        address='0x...',
        threshold=3,  # 3/5 多签
        owners=['0x...', '0x...', '0x...', '0x...', '0x...'],
    ),
    admin=GnosisSafeWallet(
        address='0x...',
        threshold=2,  # 2/3 多签
        owners=['0x...', '0x...', '0x...'],
    ),
    rebalancer=RebalancerWallets(
        hot=EOAWallet(address='0x...', daily_limit=Decimal('500000')),
        warm=GnosisSafeWallet(
            address='0x...',
            threshold=2,
            owners=['0x...', '0x...', '0x...'],
        ),
    ),
    vip_approvers=[
        VIPApprover(address='0x...', name='Approver 1'),
        VIPApprover(address='0x...', name='Approver 2'),
    ],
)
```

---

## 3. 链下权限 (Backend RBAC)

### 3.1 角色定义

```python
from enum import Enum
from dataclasses import dataclass
from typing import Literal


class Role(str, Enum):
    SUPER_ADMIN = 'super_admin'  # 超级管理员
    ADMIN = 'admin'              # 管理员
    OPERATOR = 'operator'        # 操作员
    VIEWER = 'viewer'            # 只读用户


@dataclass
class Permission:
    resource: str
    action: Literal['create', 'read', 'update', 'delete', 'execute', '*']


# 角色权限映射
ROLE_PERMISSIONS: dict[Role, list[Permission]] = {
    Role.SUPER_ADMIN: [
        Permission(resource='*', action='*'),  # 所有权限
    ],

    Role.ADMIN: [
        # 基金管理
        Permission(resource='fund', action='read'),
        Permission(resource='fund:config', action='update'),

        # 赎回管理
        Permission(resource='redemption', action='read'),
        Permission(resource='redemption', action='execute'),  # 审批

        # 调仓管理
        Permission(resource='rebalance', action='read'),
        Permission(resource='rebalance', action='execute'),

        # 资产管理
        Permission(resource='asset', action='read'),
        Permission(resource='asset', action='create'),
        Permission(resource='asset', action='update'),
        Permission(resource='asset', action='delete'),

        # 风控
        Permission(resource='risk', action='read'),
        Permission(resource='risk:emergency', action='execute'),

        # 审批
        Permission(resource='approval', action='read'),
        Permission(resource='approval', action='execute'),

        # 报表
        Permission(resource='report', action='read'),

        # 系统
        Permission(resource='system', action='read'),
        Permission(resource='system:config', action='update'),
    ],

    Role.OPERATOR: [
        # 基金 (只读)
        Permission(resource='fund', action='read'),

        # 赎回 (只读 + 结算)
        Permission(resource='redemption', action='read'),
        Permission(resource='redemption:settle', action='execute'),

        # 调仓 (执行)
        Permission(resource='rebalance', action='read'),
        Permission(resource='rebalance', action='execute'),

        # 资产 (只读)
        Permission(resource='asset', action='read'),

        # 风控 (只读)
        Permission(resource='risk', action='read'),

        # 报表 (只读)
        Permission(resource='report', action='read'),
    ],

    Role.VIEWER: [
        Permission(resource='fund', action='read'),
        Permission(resource='redemption', action='read'),
        Permission(resource='rebalance', action='read'),
        Permission(resource='asset', action='read'),
        Permission(resource='risk', action='read'),
        Permission(resource='report', action='read'),
    ],
}
```

### 3.2 用户模型

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: str
    wallet_address: str          # 主键，钱包地址
    role: Role
    name: Optional[str] = None
    email: Optional[str] = None

    # 链上角色映射
    on_chain_roles: list[str] = field(default_factory=list)  # ['ADMIN_ROLE', 'VIP_APPROVER_ROLE']

    # 权限覆盖 (可选)
    additional_permissions: Optional[list[Permission]] = None
    denied_permissions: Optional[list[Permission]] = None

    # 状态
    is_active: bool = True
    last_login_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

### 3.3 权限检查中间件

```python
# FastAPI 依赖注入示例
from functools import wraps
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services.user import UserService

security = HTTPBearer()


class PermissionChecker:
    """权限检查依赖"""

    def __init__(self, required_permissions: list[Permission]):
        self.required_permissions = required_permissions

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        user_service: UserService = Depends(),
    ) -> User:
        # 获取当前用户
        user = request.state.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        # 如果没有权限要求，直接返回用户
        if not self.required_permissions:
            return user

        # 检查权限
        has_permission = await user_service.check_permissions(
            user, self.required_permissions
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user


def require_permissions(permissions: list[Permission]) -> Callable:
    """权限检查装饰器"""
    return Depends(PermissionChecker(permissions))


# 使用示例
from fastapi import APIRouter, Body

router = APIRouter(prefix="/rebalance", tags=["rebalance"])


@router.post("/execute")
async def execute_rebalance(
    dto: ExecuteRebalanceDto = Body(...),
    user: User = require_permissions([
        Permission(resource='rebalance', action='execute'),
    ]),
):
    """执行调仓"""
    # ...
    pass


# 权限服务实现
class UserService:
    """用户服务"""

    async def check_permissions(
        self, user: User, required_permissions: list[Permission]
    ) -> bool:
        """检查用户权限"""
        # 获取用户角色权限
        role_permissions = ROLE_PERMISSIONS.get(user.role, [])

        # 添加额外权限
        all_permissions = list(role_permissions)
        if user.additional_permissions:
            all_permissions.extend(user.additional_permissions)

        # 移除被拒绝的权限
        denied = set()
        if user.denied_permissions:
            for p in user.denied_permissions:
                denied.add((p.resource, p.action))

        # 检查每个所需权限
        for required in required_permissions:
            if (required.resource, required.action) in denied:
                return False

            # 检查是否有通配符权限
            has_wildcard = any(
                p.resource == '*' and p.action == '*'
                for p in all_permissions
            )
            if has_wildcard:
                continue

            # 检查具体权限
            has_permission = any(
                (p.resource == required.resource or p.resource == '*') and
                (p.action == required.action or p.action == '*')
                for p in all_permissions
            )

            if not has_permission:
                return False

        return True
```

---

## 4. 认证机制

### 4.1 JWT 认证流程

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        JWT Authentication Flow                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. 请求挑战                                                              │
│     Client → POST /auth/challenge { walletAddress }                       │
│     Server → { challenge: "Sign this message: nonce=abc123...", nonce }   │
│                                                                           │
│  2. 签名验证                                                              │
│     Client → POST /auth/verify { walletAddress, signature, nonce }        │
│     Server → 验证签名 → 查找/创建用户 → 生成 JWT                          │
│     Server → { accessToken, refreshToken, expiresIn }                     │
│                                                                           │
│  3. API 访问                                                              │
│     Client → GET /api/v1/... { Authorization: Bearer <accessToken> }      │
│     Server → 验证 JWT → 检查权限 → 处理请求                               │
│                                                                           │
│  4. Token 刷新                                                            │
│     Client → POST /auth/refresh { refreshToken }                          │
│     Server → { accessToken, refreshToken, expiresIn }                     │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 JWT 配置

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class TokenConfig:
    secret: str
    expires_in: str
    algorithm: Literal['RS256', 'HS256'] = 'RS256'


@dataclass
class JWTPayload:
    sub: str              # 用户ID (钱包地址)
    role: str             # 角色
    on_chain_roles: list[str]  # 链上角色
    iat: int              # 签发时间
    exp: int              # 过期时间


@dataclass
class JWTConfig:
    # Access Token
    access_token: TokenConfig

    # Refresh Token
    refresh_token: TokenConfig


# 配置示例
jwt_config = JWTConfig(
    access_token=TokenConfig(
        secret='<strong-secret>',
        expires_in='15m',     # 15分钟
        algorithm='RS256',
    ),
    refresh_token=TokenConfig(
        secret='<strong-secret>',
        expires_in='7d',      # 7天
        algorithm='RS256',
    ),
)
```

### 4.3 钱包签名验证

```python
from datetime import datetime
from eth_account.messages import encode_defunct
from web3 import Web3


def verify_wallet_signature(
    wallet_address: str,
    message: str,
    signature: str,
) -> bool:
    """验证钱包签名"""
    try:
        # 编码消息
        message_encoded = encode_defunct(text=message)

        # 恢复签名者地址
        w3 = Web3()
        recovered_address = w3.eth.account.recover_message(
            message_encoded, signature=signature
        )

        # 比较地址 (忽略大小写)
        return recovered_address.lower() == wallet_address.lower()
    except Exception:
        return False


def generate_challenge_message(nonce: str) -> str:
    """生成挑战消息"""
    return f"""Sign this message to authenticate with Paimon Fund Admin.

Nonce: {nonce}
Timestamp: {datetime.utcnow().isoformat()}

This signature will not trigger any blockchain transaction."""
```

---

## 5. 敏感操作二次验证

### 5.1 需要二次验证的操作

| 操作 | 验证方式 | 说明 |
|------|----------|------|
| 审批赎回 | 钱包签名 | 每次操作都需签名 |
| 执行调仓 | 钱包签名 | 金额>10K需签名 |
| 修改资产配置 | 钱包签名 + 多签 | 链上多签 |
| 提取费用 | 钱包签名 + 多签 | 链上多签 |
| 切换紧急模式 | 钱包签名 + 多签 | 链上多签 |
| 修改用户角色 | 钱包签名 | 仅super_admin |

### 5.2 签名验证中间件

```python
import time
from fastapi import Depends, HTTPException, Request, status


class SignatureChecker:
    """签名验证依赖"""

    async def __call__(self, request: Request) -> bool:
        # 验证签名
        wallet_address = request.headers.get('x-wallet-address')
        signature = request.headers.get('x-wallet-signature')
        timestamp = request.headers.get('x-signature-timestamp')

        if not wallet_address or not signature or not timestamp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing signature headers",
            )

        # 检查时间戳 (5分钟有效期)
        try:
            signature_time = int(timestamp) * 1000
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp",
            )

        current_time = int(time.time() * 1000)
        if current_time - signature_time > 5 * 60 * 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signature expired",
            )

        # 构建签名消息
        action = f"{request.method} {request.url.path}"
        body = await request.json() if request.method in ('POST', 'PUT', 'PATCH') else {}
        nonce = body.get('nonce', 'none')

        message = f"""Paimon Fund Operation
Action: {action}
Timestamp: {timestamp}
Nonce: {nonce}"""

        # 验证签名
        is_valid = verify_wallet_signature(wallet_address, message, signature)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

        # 验证签名者是否为当前用户
        user = request.state.user
        if wallet_address.lower() != user.wallet_address.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signature address mismatch",
            )

        return True


def require_signature():
    """签名验证装饰器"""
    return Depends(SignatureChecker())


# 使用示例
from fastapi import APIRouter, Body

router = APIRouter()


@router.post("/approve")
async def approve_redemption(
    dto: ApproveDto = Body(...),
    _: bool = require_signature(),
    user: User = require_permissions([
        Permission(resource='approval', action='execute'),
    ]),
):
    """审批赎回"""
    # ...
    pass
```

---

## 6. 服务账户管理

### 6.1 后端服务账户

```python
from dataclasses import dataclass, field
from typing import Literal
from decimal import Decimal


@dataclass
class WalletLimits:
    per_transaction: Decimal
    daily: Decimal


@dataclass
class HotWalletConfig:
    address: str
    private_key_path: str  # KMS/HSM 路径
    roles: list[str] = field(default_factory=lambda: ['REBALANCER_ROLE'])
    limits: WalletLimits = None
    allowed_functions: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.limits is None:
            self.limits = WalletLimits(
                per_transaction=Decimal('100000'),  # 10万 USDT
                daily=Decimal('500000'),            # 50万 USDT
            )
        if not self.allowed_functions:
            self.allowed_functions = [
                'allocateToLayer',
                'purchaseAsset',
                'redeemAsset',
                'rebalanceBuffer',
            ]


@dataclass
class WarmWalletConfig:
    address: str  # 多签地址
    type: Literal['gnosis-safe'] = 'gnosis-safe'
    threshold: int = 2
    roles: list[str] = field(default_factory=lambda: ['REBALANCER_ROLE'])
    allowed_functions: list[str] = field(default_factory=lambda: ['executeWaterfallLiquidation'])


@dataclass
class ServiceAccount:
    hot: HotWalletConfig
    warm: WarmWalletConfig
```

### 6.2 密钥管理

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Key Management Architecture                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                        AWS KMS / HashiCorp Vault                   │   │
│  │                                                                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │   │
│  │  │  Hot Wallet │  │ Warm Wallet │  │  Cold Wallet│               │   │
│  │  │  Private Key│  │   Signers   │  │   Recovery  │               │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               │   │
│  │         │                │                │                       │   │
│  │         │     HSM 加密存储, 不可导出      │                       │   │
│  │         │                │                │                       │   │
│  └─────────┼────────────────┼────────────────┼───────────────────────┘   │
│            │                │                │                           │
│            ▼                ▼                ▼                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                        Signing Service                             │   │
│  │                                                                    │   │
│  │  • 接收签名请求                                                    │   │
│  │  • 验证请求权限                                                    │   │
│  │  • 调用 KMS 签名                                                   │   │
│  │  • 记录审计日志                                                    │   │
│  │  • 返回签名 (不暴露私钥)                                           │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  访问控制:                                                                │
│  • IP 白名单 (仅后端服务器)                                              │
│  • IAM 角色 (最小权限)                                                   │
│  • 请求速率限制                                                          │
│  • 异常检测告警                                                          │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.3 签名服务实现

```python
import structlog
from typing import Literal, Any
from decimal import Decimal
from dataclasses import dataclass

import boto3
from botocore.config import Config

from app.services.audit import AuditService

logger = structlog.get_logger()


@dataclass
class TransactionRequest:
    to: str
    value: Decimal = Decimal(0)
    data: bytes = b''
    gas: int = 0
    gas_price: int = 0


class SigningService:
    """签名服务"""

    def __init__(
        self,
        kms_client: boto3.client,
        audit_service: AuditService,
        service_account: ServiceAccount,
    ):
        self.kms_client = kms_client
        self.audit_service = audit_service
        self.service_account = service_account
        self._daily_usage: dict[str, Decimal] = {}

    async def sign_transaction(
        self,
        wallet: Literal['hot', 'warm'],
        transaction: TransactionRequest,
    ) -> str:
        """签名交易"""
        # 1. 验证限额
        await self._check_limits(wallet, transaction)

        # 2. 调用 KMS 签名
        key_id = self._get_key_id(wallet)
        serialized = self._serialize_transaction(transaction)

        response = self.kms_client.sign(
            KeyId=key_id,
            Message=serialized,
            SigningAlgorithm='ECDSA_SHA_256',
        )

        signature = response['Signature']

        # 3. 记录审计日志
        await self.audit_service.log({
            'action': 'SIGN_TRANSACTION',
            'wallet': wallet,
            'transaction': {
                'to': transaction.to,
                'value': str(transaction.value),
                'data': transaction.data[:10].hex() if transaction.data else '',  # 仅记录函数选择器
            },
        })

        return signature.hex()

    async def _check_limits(
        self, wallet: str, tx: TransactionRequest
    ) -> None:
        """检查交易限额"""
        limits = self._get_limits(wallet)
        value = tx.value

        # 单笔限额
        if value > limits.per_transaction:
            raise ValueError(
                f"Transaction exceeds per-tx limit: {limits.per_transaction}"
            )

        # 日限额
        daily_usage = await self._get_daily_usage(wallet)
        if daily_usage + value > limits.daily:
            raise ValueError(
                f"Transaction exceeds daily limit: {limits.daily}"
            )

    def _get_limits(self, wallet: str) -> WalletLimits:
        """获取钱包限额"""
        if wallet == 'hot':
            return self.service_account.hot.limits
        return WalletLimits(
            per_transaction=Decimal('500000'),
            daily=Decimal('2000000'),
        )

    def _get_key_id(self, wallet: str) -> str:
        """获取 KMS 密钥 ID"""
        return self.service_account.hot.private_key_path if wallet == 'hot' else ''

    async def _get_daily_usage(self, wallet: str) -> Decimal:
        """获取今日使用量"""
        return self._daily_usage.get(wallet, Decimal(0))

    def _serialize_transaction(self, tx: TransactionRequest) -> bytes:
        """序列化交易"""
        # 简化实现，实际需要 RLP 编码
        return b''
```

---

## 7. 审计与合规

### 7.1 审计日志

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Any


@dataclass
class AuditActor:
    type: Literal['user', 'service', 'system']
    id: str
    wallet_address: Optional[str] = None
    role: Optional[str] = None
    ip: Optional[str] = None


@dataclass
class AuditChange:
    field: str
    old_value: Any
    new_value: Any


@dataclass
class AuditLog:
    id: str
    timestamp: datetime

    # 操作者
    actor: AuditActor

    # 操作
    action: str
    resource: str
    resource_id: Optional[str] = None

    # 详情
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None
    changes: Optional[list[AuditChange]] = None

    # 结果
    success: bool = True
    error_message: Optional[str] = None

    # 风险标记
    risk_level: Optional[Literal['low', 'medium', 'high']] = None
    risk_reason: Optional[str] = None
```

### 7.2 必须审计的操作

| 操作 | 风险级别 | 审计内容 |
|------|----------|----------|
| 用户登录/登出 | Low | 时间、IP、成功/失败 |
| 角色变更 | High | 变更前后角色 |
| 赎回审批 | Medium | 审批人、金额、原因 |
| 调仓执行 | High | 完整调仓计划和结果 |
| 资产配置变更 | High | 变更前后配置 |
| 紧急模式切换 | High | 操作人、原因 |
| 费用提取 | High | 金额、接收地址 |
| API 调用失败 | Low | 错误详情 |
| 权限拒绝 | Medium | 请求的资源和权限 |

### 7.3 审计日志保留策略

| 风险级别 | 保留时间 | 存储位置 |
|----------|----------|----------|
| Low | 90天 | PostgreSQL |
| Medium | 1年 | PostgreSQL + S3 |
| High | 7年 | PostgreSQL + S3 + 归档 |

---

## 8. 配置参考

### 8.1 环境变量

```bash
# JWT 配置
JWT_ACCESS_SECRET=<strong-secret>
JWT_ACCESS_EXPIRES=15m
JWT_REFRESH_SECRET=<strong-secret>
JWT_REFRESH_EXPIRES=7d

# AWS KMS
AWS_KMS_KEY_ID_HOT=arn:aws:kms:...
AWS_KMS_KEY_ID_WARM=arn:aws:kms:...
AWS_REGION=ap-southeast-1

# 限额配置
WALLET_HOT_PER_TX_LIMIT=100000
WALLET_HOT_DAILY_LIMIT=500000
WALLET_WARM_PER_TX_LIMIT=500000
WALLET_WARM_DAILY_LIMIT=2000000
```

---

*下一节: [08-deployment.md](./08-deployment.md) - 部署与运维*
