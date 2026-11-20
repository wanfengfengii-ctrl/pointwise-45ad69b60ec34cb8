# 区间测读交班

README.md 中的精确测读、收发固定件和签报领取继续可用。区间测读适用于只能确认标记读数在闭整数区间内的班次。单位仍为毫米。

## 录入与固定件

新增 `intake.readings.record_ranges(station, specimen, scale, positions, origins, *, base_revision=None)`。`positions` 是具名映射，值可以是整数，或两项列表或元组 `(lower, upper)`。两界均为整数且 `lower <= upper`，布尔值无效。整数等同于两界相同的区间。`origins` 与 `positions` 同键且非空，沿用 `ReadingOrigin(sheet, line)` 和原名册校验。返回值提供 `revision_id`、`specimen`、`scale`、`base_revision` 和 `frozen`，与原入口的同名属性含义一致。

底稿须是指定的同试件同尺修订，可以是 V1 精确修订或区间修订。仅替换本次提交的标记读数和出处，底稿和其他修订保持原样。区间修订后续用 `record_ranges` 勘误。普通 `record` 保持原精确读数契约。

区间修订沿用 `intake.station.freeze` 和 `issue.publish.issue`。从区间录入建立的修订发行 `version == 2` 的件，即使其中各区间均为单点。普通精确修订继续发行 V1。沿用 `encode_packet`、`decode_packet`、`catalog.save` 和 `catalog.get`，可将新版件传到独立目录。新版件沿用件号、试件、尺号、修订号和逐标记出处的含义，正文的联合表示由实现确定。整数须精确往返。每个已测标记各有一条出处。无效件拒收，同号同内容可重复接纳，同号异内容拒绝。

区间件绑定修订和逐点出处，去掉站内绝对坐标后仍保全同尺各点可同时实现的相对位置。将同一尺全部站内读数平移同一个整数，交接的相对位置关系应保持等价。夜班只有固定件，白班发行时无须知道夜班会选择哪些对件。

## 裁决和领取

新增 `review.decisions.review_ranges(catalog, ledger, packet_ids, reference_packet_id, pairs)`。选件和请求的形参沿用 `review`，可使用任何合法的 V1、V2 组合。件号互异，同属一试件，参考件在选件内，端点必须确实出现在选件中。每个 V1 读数按精确关系处理。参考件正向，其余每件各选一个整尺方向。每件在同一次摆放中只有一个整数平移，同名标记在所有选件中同时重合。原 `review` 碰到 V2 件抛 `ValueError`。

返回对象具有 `status`、`report`、`receipt`。没有共同摆法时 `status == 'conflict'`，`report` 和 `receipt` 均为 `None`。空请求仍核对整组是否相容。相容时 `status == 'signed'`，报告每项结果提供 `start`、`end`、`minimum`、`maximum`，按请求原序保留重复项。上下界是全部共同摆法中终点减起点的精确整数极值。每个有界端值须可达，端值之间可有空档。跨独立平移分量时上下界均为 `None`，自对两端均为 `0`。相容的空请求可签零项报告。

区间报告沿用 `report_id`、`specimen`、`reference_packet_id`、`bindings`、`results` 和 `origins`。按选件顺序固定绑定，逐件记录原尺号、原修订及逐点出处。签报和原成功首执共同提交。`report.readback.read(ledger, report_id)` 在只有账库时返回原 `(report, receipt)`，未知报告号仍返回 `None`。旧报告继续返回原单值结果。后续勘误和重开均不改变已签报告。

输入无效、归属不符、未冻发行、混单、未知请求端点和无效件抛 `ValueError`。未知试件、修订或固定件抛 `LookupError`。写入错误按原 SQLite 异常传播。冲突或写入失败时本次报告和首执都不增加，写入失败后可以重试。

## 手算样例与核验

`range_cases.py` 提供输入和按请求原序的期望双界。用其中的 `SPECIMEN`、`SCALES`、`MARKS` 登记试件。每次录入可用下式生成出处，为不同原件选不同的单号。

```python
origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(values, 1)}
revision = record_ranges(station, SPECIMEN, 'A', values, origins)
freeze(station, SPECIMEN, 'A', revision.revision_id)
packet = issue(station, source_catalog, SPECIMEN, 'A', revision.revision_id)
receiving_catalog.save(decode_packet(encode_packet(packet)))
```

- A 分别录 `COUPLED` 或 `INDEPENDENT`。B 用原精确 `record` 录 `COINCIDENT`。冻结、发行并经编码传到独立接收目录。关闭站库和发行目录，用对应 A 件作参考核对 `COINCIDENCE_PAIRS`。两种 A 相对 P 的边际相同，前者始终有 R−Q=1，后者允许 Q、R 同时为零。前组冲突且账库计数不变，后组签 P→R=[0,0]。前组给空请求时仍冲突。
- `TRIPLE_A` 为区间件，`TRIPLE_B`、`TRIPLE_C` 为精确件。以 A 为参考，初版只有 (Q,R)=(1,−1) 或 (3,1) 两种摆法（以 P 为零）。Q→R 恒为 −2，P→R 的两个端值为 −1、1。用 `CORRECTION_A` 勘误 A 时只提交 Q 及新出处，另冻结发行。用新件重做相同请求时 P→R 两端均为 1，P 仍保留初版出处。关闭接收目录及报告账库后，只重开报告账库，按新旧报告号领取各自原绑定、结果、出处和首执。
- 使用初版 `TRIPLE_A`、`TRIPLE_B` 和独立精确件 `ISOLATED_D`，选择 A 作参考，按 `ISOLATED_PAIRS` 核对跨分量无界、自对零和组内有界同时成立。
- 可沿用 `tests/test_history.py` 中 `test_commit_failure_rolls_back_both_rows_and_allows_retry` 的延迟约束夹具。对一组可签区间件，在账库连接上执行原例创建临时表和 `fail_commit` 触发器的三条语句，然后调用 `review_ranges(catalog, ledger, ids, ref, pairs)`。预期提交抛 `sqlite3.IntegrityError`，`ledger.counts()` 与调用前一致。去掉触发器或重开账库再调用，可正常签发。

保留全部原回归。完成后让现有运行清单的 `verify` 核验原业务和新增联合链路，检查失败应以非零状态退出。`demo` 展示实际的断源复核结果和重开领报。清单 `.pointwise-runtime.json` 沿用现有格式，版本 1，类别 `cli`，`setup` 为准备命令的参数数组列表，`verify` 和 `demo` 各为一条命令的参数数组。基线可执行 `python3 -B check_project.py` 与 `python3 -B demo.py` 核验原业务。
