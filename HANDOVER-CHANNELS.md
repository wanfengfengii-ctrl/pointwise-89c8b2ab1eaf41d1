# 交接：已知误分类通道下的真实条件风险

## 范围

在原观察性归档之上新增按潜在变量的部分识别，口径为
`channel_conditional_risk_range`。不估计通道、不作因果解释、不输出抽样区间。
原有 `save_query`、观察性成果、编码与全部原测试保持原样。

## 入口与调用

```python
revision = distributions.put_distribution(dataset, source, observed_variables, rows)
tasks.save_channel_query(task_id, dataset, revision,
                         latent_variables, channel, event, condition)
result = executor.execute_task(task_id)              # 阻塞式、幂等
reader.read_result(task_id)                          # 不可变成果
reader.read_result(task_id, structured=True)         # JSON 兼容副本
export_result(result)                                # 同结构 JSON 文本
```

- `channel`：行对应观测联合赋值，列对应潜在联合赋值，元素必须是 `Fraction`
  且非负，每列和恰为 1。整数/浮点元素被拒绝，不自动转换。
- `event` / `condition`：潜在标量名到标签的部分赋值；空映射为全集，可重叠，
  交集为空即矛盾事件，不会报错。
- 观测与潜在联合域各限 1 至 8 单元；超限抛 `ValueError` 且不落任务。
- 同 ID 同规格幂等；同 ID 不同规格（含跨任务种类）抛 `TaskConflict`；
  未知修订抛 `UnknownRevision`。

## 语义与求解

观测边缘 `p` 由固定修订的完整频数精确归一化。相容集合
`Q = {q ≥ 0 : C q = p}`（列和为 1 使 `sum(q)=1` 自动成立）。求解步骤：

1. 枚举 `Q` 的全部顶点：对通道列的每个子集精确解 `C_B q_B = p`，
   保留非负解并按 q 去重。域至多 8 单元，全量枚举即可。
2. `Q` 为空 → `incompatible`；顶点上条件质量为 0（线性函数极值在顶点取到）
   → `undefined_condition`；否则对每个顶点用同一 q 求
   `Pq(event∩condition)/Pq(condition)`，取精确最小/最大 → `bounded`。
3. 前两种状态 `lower`/`upper` 为 `None`，三者都是正常 `completed`。

纯 `Fraction` 运算，无浮点往返；极小正质量不会被当作零。

## 持久化与安全

- 任务规格新编码 `version=2, kind=channel`，旧 `version=1` 编码照常解码。
- 成果新编码 `version=2, kind=channel`，观察性成果仍为 `version=1`。
- 成果与 `completed` 在同一事务提交；提交前异常回滚，任务转 `failed`，
  原绑定保留，可重试；错误记录失败不遮蔽原异常。
- 读取及重复执行已有成果不重算。发布守卫校验：规格一致、口径正确、
  状态合法、端点为 `Fraction`、落在 `[0,1]`、不倒置、无范围状态不携带端点。
- `to_public_record()` 保留 `Fraction`，修改返回副本不影响存储。

## 联动与核验

```sh
python3.11 -B verify.py                       # 原 8 个测试 + 新增 test_channel + 两个演示
python3.11 -B -m unittest discover -s tests -p 'test_*.py'
python3.11 -B channel_examples.py --fixtures  # 仅输入/手算，不含求解器
python3.11 -B channel_examples.py --verify    # 公开契约、守卫、回滚重试
python3.11 -B channel_examples.py --demo --database channel-demo.sqlite3
python3.11 -B demo.py --database demo.sqlite3
```

`.pointwise-runtime.json` 保留既有 `version`/`kind`/`setup`/`verify`/`demo`
字段及 argv 形式；`verify` 现在同时跑原回归、观察性演示和通道联合核验，
新增 `channel_demo` 字段指向通道演示。`tests/test_channel.py` 用独立构造
（行约束 + 非负激活约束枚举基本解）交叉核对 60 组随机有理通道，覆盖秩亏、
冗余、零单元、空变量表与重叠事件。

## 交接注意

- 通道矩阵的“位置”属于任务身份：潜在轴顺序或矩阵转置都会产生新规格。
- 更正只产生新修订；旧任务继续读取旧修订与旧成果，不要用当前修订重算。
- 若下游需要概率表而非区间，应显式选择点识别口径；本成果只给范围。
