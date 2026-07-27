# DeepSeek Runtime 文档索引

> 适用基线：`develop@0e1e435`
> 文档状态：Open-source Alpha 规划基线
> 原则：PRD 是产品范围与验收标准的唯一事实源；架构、测试和路线图均引用 PRD 能力编号。

## 核心文档

| 文档 | 目的 |
| --- | --- |
| [Code Review](reviews/2026-07-27-code-review.md) | 当前代码质量、安全性、正确性和工程化审查 |
| [产品架构](architecture/product-architecture.md) | 产品定位、用户、能力域、使用链路和边界 |
| [技术架构](architecture/technical-architecture.md) | 当前技术实现、目标架构、数据流、信任边界和非功能约束 |
| [PRD](product/PRD.md) | 产品需求、优先级、验收标准、非目标与发布门禁 |
| [测试计划](testing/test-plan.md) | 测试策略、环境、范围、准入/退出标准 |
| [测试用例](testing/test-cases.md) | 功能、安全、恢复、协议、性能和发布用例 |
| [测试报告](testing/test-report-2026-07-27.md) | 当前基线的测试证据、静态确认结果、阻塞项与发布结论 |
| [开源就绪路线图](roadmap/open-source-readiness-plan.md) | 以真正开源为唯一目标的最小迭代计划 |

## 状态定义

| 状态 | 含义 |
| --- | --- |
| Implemented | 当前代码已存在对应实现，但不等于已通过生产验证 |
| Partial | 存在部分原语或局部实现，端到端能力不完整 |
| Planned | PRD 定义但当前未实现 |
| Blocked | 存在 P0/P1 缺陷，不能作为可承诺能力发布 |
| Verified | 已有可复现自动化测试证据 |
| Static-confirmed | 通过代码控制流或数据流审查确认，尚未执行动态测试 |
| Not-run | 当前环境没有实际执行证据 |

## 文档治理

1. 任何新功能必须先更新 `product/PRD.md`。
2. 任何架构变化必须同步更新技术架构和相关 ADR。
3. 每条 P0/P1 需求必须对应至少一个自动化测试用例。
4. 发布报告只能引用可复现 CI 结果，不能引用“本地口头通过”。
5. README 只承担项目入口职责，不重复定义产品范围。
