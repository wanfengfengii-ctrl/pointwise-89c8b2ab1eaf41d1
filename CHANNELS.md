# 已知误分类通道下的真实条件风险

## 业务与现有能力

README.md 所述正常观察性归档、全部原接口和 tests 原文件保持有效。本增量用于已知测量误分类通道下的部分识别，不估计通道、不作因果干预、不输出抽样置信区间。已有修订、事务、重试和重开读取设施可以复用。新增分析、任务规格和范围成果尚未实现；channel_examples.py 只提供输入、手算预期和外部核验。

## 保存与执行

新增 TaskRepository.save_channel_query(task_id, dataset_id, revision, latent_variables, channel, event, condition)，返回沿用 TaskRecord 的任务记录；通过既有 TaskExecutor.execute_task(task_id) 执行，通过 ResultReader.read_result(task_id, structured=False) 或 structured=True 读取。

latent_variables 使用 V1 variables 的有序变量域声明及同样的标签规则。观测域来自指定数据集的确切修订；两边的联合笛卡尔积各有 1 至 8 个单元，空变量表仍有唯一空赋值。最后一个轴变化最快。潜在变量名与观测变量名无须相同。超出本入口规模或其他非法输入抛 ValueError 且不保存任务。

channel 是有序行序列，每行是有序 Fraction 序列。行对应观测联合赋值、列对应潜在联合赋值；矩阵大小必须完全匹配，元素必须是非负 Fraction，每列精确和为 1；不接纳浮点或整数元素。event 和 condition 均为潜在变量的部分赋值映射，标签与变量须合法；空映射表示全集，二者可重叠，矛盾时交集为空。它们表示事件而非输出轴，不能套用 V1 的输出与条件不得重叠限制。

保存时复制并规范化全部输入。映射键插入顺序不影响任务身份；潜在轴顺序、域顺序、矩阵位置、事件、条件、观测修订均属于任务规格。相同 ID 相同规格幂等，相同 ID 不同规格抛 TaskConflict；与观察性任务共用 ID 空间，跨任务种类同 ID 也冲突。未知修订沿用 UnknownRevision。

## 分析语义

观测概率 p 按固定修订的完整频数精确归一化。真实分布的相容集合为 Q={q:q>=0, sum(q)=1, Cq=p}。允许秩亏、相容冗余和零单元，不能选择一个逆解替代全部相容分布。

先判定 Q：空集合返回 incompatible；否则，只要存在 q 使条件质量 Pq(condition)=0，就返回 undefined_condition；仅当全部相容 q 的条件质量严格为正时返回 bounded，给出 Pq(event 且 condition)/Pq(condition) 在 Q 上的精确最小值 lower 与最大值 upper。前两种状态的 lower、upper 均为 None；三种都是正常 completed 成果。分子与分母必须属于同一个 q，不能分别取界相除。极小正条件质量不得当作零。允许全量重算、有限顶点枚举，不设性能优化目标。

## 成果与历史

execute_task 返回的新增成果须不可变，提供 spec、status、lower、upper、interpretation 和 to_public_record()。spec 包含固定任务身份、观测修订及来源、观测域、潜在域、完整通道、事件与条件；具体内部类和表示由实现选择。interpretation 固定为 channel_conditional_risk_range。bounded 时 lower、upper 为 Fraction，满足 0<=lower<=upper<=1；其他状态两项为 None，不伪造概率表。

新增成果的 to_public_record() 及 structured=True 记录均含 task_id、dataset_id、revision、source、variables、latent_variables、channel、event、condition、interpretation、status、lower、upper。variables 是观测域，两个域均按 V1 的 [[name, domain], ...] 形式；event、condition 为字典，channel 为嵌套列表。to_public_record() 保留 Fraction；structured=True 与 export_result 的 JSON 中，所有 Fraction（通道及端点）均编码为 [分子, 正分母]，无范围用 null。返回记录修改不得影响任务、成果或后续读取。

新增任务和成果须无损持久化；保存后修改调用方输入、发布观测更正、关闭重开，均不得改变旧绑定和成果。读取及重复执行已有成果不重算。原观察性接口、旧编码读取、重放冲突及发布失败回滚重试保持原行为。沿用真实成果发布事务：成果与 completed 共同提交，提交前异常不留下半份成果，原绑定可重试，错误记录不能遮蔽原异常。成果守卫须拒绝与固定规格不符、错误口径或状态、非 Fraction/越界/倒置端点及无范围状态携带端点的候选；无需在读取或守卫中重新求极值。

## 交付与核验入口

提供分析、固定任务和成果交付的联动实现及简短交接说明，保留全部原测试字节。沿现有 .pointwise-runtime.json 接通原回归和新增联合核验，演示有歧义范围及更正后重开旧任务；运行清单既有 version、kind、setup、verify、demo 字段及 argv 形式保持兼容。

channel_examples.py 的无参数或 --fixtures 模式只展示非答案输入；实现后运行 python3.11 -B channel_examples.py --verify，以手算案例验证公开状态、精确范围、持久绑定、守卫及回滚重试；演示使用 python3.11 -B channel_examples.py --demo --database channel-demo.sqlite3。已有 verify.py 及完整 unittest 回归仍须执行。可补充独立核账，不规定实现算法或新增文件名。

手算例中四潜在单元顺序为 (G,Y)=00,01,10,11，观测三单元计数为 [3,2,0]，通道三行为 [1,0,0,1]、[0,0,1,0]、[0,1,0,0]，元素均转 Fraction。事件 Y=1、条件 G=1，必有 q01=0、q10=2/5、q00+q11=3/5，风险范围为 [0,3/5]。这完全使用部分赋值入口。其他可直接运行的手算数据见 channel_examples.py。
