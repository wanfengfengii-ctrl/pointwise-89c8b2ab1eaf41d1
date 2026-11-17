# 河湾环境实验室：离散观测风险归档

Python 3.11 标准库项目。分析员把设备状态、气象分组与超标标志的完整联合频数交给系统，负责人取得精确的观察性条件风险表。结果口径为 observational_conditional_probability；这些比例描述观测分组中的关联。

## 一天的工作

1. 收件：上游给出数据集 ID、来源 ID、有序变量域和联合赋值计数。
2. 核账：每个联合赋值必须恰有一行；合法候选尚未写入归档。
3. 发布：在一个事务中登记不可变修订、来源和当前指针。
4. 固定：分析员保存任务 ID、确切修订、输出顺序与条件赋值。
5. 计算：按变量名消去隐藏轴，以条件组质量作分母，用 Fraction 精确计算。
6. 交付：校验成果与固定规格一致，原子保存成果并完成任务。
7. 更正：新来源发布新修订，新任务消费更正；旧任务保留旧数据。
8. 复核：关闭重开后读取历史成果和来源，读取不重新计算。

观测次数是整数，概率无量纲。零计数表示显式观测单元，不能以漏行代替。所有计算确定性执行；复现需要固定修订、查询规格和受支持的编码版本。

## 运行

在项目根目录运行：

~~~sh
python3.11 -B verify.py
python3.11 -B -m unittest discover -s tests -p 'test_*.py'
python3.11 -B demo.py --database demo.sqlite3
~~~

verify 执行八个测试文件的完整回归，再在测试临时目录执行发布、更正、重开复核的演示。任何测试或集成断言失败都会返回非零。demo 写入调用者明确指定的数据库，使用稳定数据集、来源及任务 ID；相同内容重跑幂等，已用同 ID 的不同内容报冲突。初始化仅幂等建表及检查版本，不重灌样例、不覆盖用户更正。演示结束前先断言手算比例，再打印实际 POINTWISE_SCENARIO JSON。

## 公开 API 与组合

项目采用命名空间包，无第三方依赖。从项目根目录导入：

~~~python
from observatory.archive.storage import ArchiveDatabase
from observatory.archive.repository import DistributionRepository
from observatory.tasks.repository import TaskRepository
from observatory.tasks.execution import TaskExecutor
from observatory.results.publication import ResultPublisher
from observatory.results.reading import ResultReader

db = ArchiveDatabase.open("laboratory.sqlite3")
try:
    distributions = DistributionRepository(db)
    distributions.initialize()
    tasks = TaskRepository(db, distributions)
    tasks.initialize()
    publisher = ResultPublisher(db, tasks)
    publisher.initialize()
    reader = ResultReader(db, tasks)
    executor = TaskExecutor(distributions, tasks, publisher, reader)

    revision = distributions.put_distribution(
        "river", "daily",
        [("X", [0, 1]), ("Y", [0, 1])],
        [((0, 0), 1), ((0, 1), 1), ((1, 0), 2), ((1, 1), 4)])
    tasks.save_query("risk", "river", revision, ["Y"], {"X": 1})
    result = executor.execute_task("risk")
    assert str(result.rows[0][1]) == "1/3"
    record = reader.read_result("risk", structured=True)
    assert record["rows"][1]["probability"] == [2, 3]
finally:
    db.close()
~~~

所有仓储与执行器共享同一个 ArchiveDatabase。连接面向单进程本地工作流，不要求并发工作者或跨进程执行恢复。

- put_distribution(dataset_id, source_id, variables, rows) 返回数据集内从 1 开始的修订号。variables 是 (name, domain) 有序序列，rows 是 (assignment, count) 序列。assignment 可为对应轴顺序的序列或恰好覆盖全部变量的映射。原行序列在转为映射前检测重复。
- read_distribution(dataset_id, revision) 返回不可变 DistributionRevision；其 to_public_record() 返回独立的可修改字典。current_revision(dataset_id) 返回当前号。
- save_query(task_id, dataset_id, revision, outputs, conditions) 返回不可变 TaskRecord；load(task_id) 读取规格、状态与错误摘要。其 to_public_record() 是独立副本。
- execute_task(task_id) 返回不可变 RiskResult。已有成果时直接读取。pending 与 failed 都可执行。
- read_result(task_id, structured=False) 读取 RiskResult，structured=True 返回独立、JSON 兼容的记录。export_result(result) 返回相同结构的 JSON 字符串。

VariableSpec、FrequencyTable、CandidateDistribution、ProbabilityTable、ObservationalQuery、任务及成果值对象用于计算或持久化边界。入口将合法输入规范化为不可变元组；修改调用方数据或公开字典副本不会改变保存内容。

## 输入与输出规则

变量名为非空唯一字符串。每个域为非空、无重复的有限有序标签序列；标签仅接受字符串或非布尔整数，整数 1 与字符串 "1" 不同。拒绝浮点、None、bool、域外赋值和未知变量。计数为非布尔非负整数，总量必须为正。允许零单元和空变量表；空变量表只有唯一空赋值。

输出变量必须存在、无重复，且不与条件重叠。条件键顺序不影响任务身份，输出轴顺序影响身份。概率行按输出声明顺序和域声明顺序的笛卡尔积排列，保留零概率。空条件表示边际；空输出在正条件质量下为唯一空赋值，概率为 1。

成果具有固定规格、source、revision、interpretation、status、condition_mass 与 rows。computable 的 rows 为完整有序表，所有概率为非负 Fraction，精确求和为 1。zero_condition 的 condition_mass 为 0、rows 为 None，任务正常 completed。结构化输出将每个 Fraction 编码为 [整数分子, 正整数分母]，零条件 rows 为 JSON null；不经浮点数往返。

## 身份、来源与错误

摘要覆盖有序变量、带类型标签、有序域和规范联合赋值顺序的全部计数。输入行重排不改变摘要，声明轴顺序改变属于内容变化。同数据集同来源同内容返回原修订；重放较早来源不会倒退当前指针。来源 ID 按数据集隔离。任务 ID 在数据库内唯一，同 ID 同规格返回既有状态。

非法输入或候选成果抛 ValueError。SourceConflict 和 UnknownRevision 定义于 archive/revisions.py；TaskConflict 和 UnknownTask 定义于 tasks/repository.py；ResultUnavailable 定义于 results/reading.py。同来源不同内容报 SourceConflict；未知确切修订报 UnknownRevision；同任务 ID 不同规格报 TaskConflict；执行未知任务报 UnknownTask；无已发布成果时报 ResultUnavailable。

计算失败或提交前失败会回滚成果和完成标记，保留固定绑定；若独立错误记录事务成功，任务为 failed，重试成功后清除错误。错误记录自身失败仍传播原异常。成果插入与 mark_completed 使用同一连接和同一事务，禁止独立嵌套提交。已有成果不会被重算或替换。

## 模块与回归

intake 的四个模块分别管理变量规则、赋值定位、完整频数及合法候选。archive 的五个模块分别管理连接事务、无损内容编码、来源摘要、修订值对象和修订仓储。analysis 的五个模块分别管理普通概率表、具名投影重排、边缘求和、普通条件化和查询。tasks 的五个模块分别管理规格、固定绑定、无损任务编码、持久状态和执行编排。results 的五个模块分别管理精确编码、规格校验、原子发布、结构化导出和只读成果交付。

tests/test_distribution.py 覆盖完整二元表、类型和大整数编码、版本拒绝；test_intake.py 覆盖整批拒绝；test_sources.py 覆盖重放、冲突与来源隔离；test_query.py 覆盖精确条件、零质量、轴重排、隐藏轴累加、空查询和成果守卫；test_binding.py 覆盖更正后的旧任务及来源；test_publication.py 用测试侧子类在真实写入后、提交前抛异常，核对回滚与重试；test_reading.py 覆盖副本、初始化与重开读取；test_tables.py 使用独立整数枚举核对多个条件表。

fixtures.json 含有限正常输入、手算结果及不执行的离线图。基准计数 [1,1,2,4] 得到 Y|X=1 的 1/3、2/3；更正 [1,1,5,1] 得到 5/6、1/6。二元隐藏 Z、计数 1 至 8 得到 11/26、15/26。三元 Z、计数 1 至 12，输出 (Z,Y) 且 X=1 得到 7/57、10/57、8/57、11/57、9/57、12/57。预期以独立整数加法构造，不调用待验证的表计算函数。
