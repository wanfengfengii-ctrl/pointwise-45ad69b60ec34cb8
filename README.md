# 澄川测尺交班

澄川工装试制车间用多把直线测尺核对同一试件的具名标记。各尺有独立零点和摆向。晚班在测读站关闭后，使用白班移交的固定件核对共同摆放和有向位移，班长据签报登记确定位移，将未定项留待复测。

## 运行

使用 Python 3.11 标准库。项目运行器提供 `check_project.py`。在项目根目录执行完整回归和交班演示。

```sh
python3 -B check_project.py
python3 -B demo.py
```

直接运行 unittest 的等价命令为 `python3 -B -m unittest discover -s tests -t . -v`。演示和测试使用自动清理的临时目录，分别打开测读站、固定件目录和签报账。

## 一天的交班

1. 白班按试件工单登记试件号、测尺名册和标记名册。
2. 逐尺提交具名整数毫米读数和测读单行号，得到一份测读修订。
3. 遇错抄时指定底稿另建勘误，冻结本次选定的修订。
4. 按冻结修订发行固定件，关闭测读站，将固定件交给晚班。
5. 晚班按固定件号选件，指定一件为参考尺，提交有序标记对。
6. 复核所有共点和闭环，按项核定终点减起点的毫米差值。
7. 相容时提交签报和首执，班长按项登记或安排复测。冲突时保留原账。
8. 次班可从指定旧底稿另发勘误件，用新选件重新复核。
9. 重开签报账，按旧号领取当时的报告和首执，核对原件和逐点出处。

## Python 接口

- `intake.station.open_station(path)` 打开并初始化站库。`registry.catalog.register(station.registry, number, scales, marks)` 返回 `Specimen`。同一试件号、相同名册内容的重复登记返回原身份，名册比较与输入顺序无关。名称是非空字符串，禁止首尾空白和 NUL。名册至少各有一项且名称唯一。
- `intake.readings.record(station, number, scale, positions, origins, *, base_revision=None)` 返回 `Revision`。`positions` 和 `origins` 是以标记名为键的映射，至少含一项且键相同。位置必须为整数，支持零和负值，布尔值无效。每项出处为 `intake.origins.ReadingOrigin(sheet, line)`，单号非空，行号为正整数。勘误以明确指定的同试件、同尺修订为底，仅替换本次提交的读数和出处。`station.load_revision(number, scale, revision_id)` 可领取完整原修订。`intake.station.freeze(station, number, scale, revision_id)` 返回原修订号，可重复调用。
- `issue.catalog.open_packet_catalog(path)` 打开独立目录。`issue.publish.issue(station, catalog, number, scale, revision_id)` 从指定冻结修订发行 `Packet`。`catalog.get(packet_id)` 按号领取。`issue.codec.encode_packet(packet)` 和 `decode_packet(text)` 用 JSON 交换固定件。`catalog.save(packet)` 可导入独立构造或解码的合法件，同号同内容可重复导入，同号异内容拒绝。独立合法件可用 `issue.shape.ScaleShape(anchor, offsets)` 和 `issue.envelope.make_packet(number, scale, revision_id, shape, origins, packet_id=...)` 构造，`offsets` 为 `(标记, 有向偏移)` 元组序列，`origins` 为包含所有这些标记的 `PacketOrigin(mark, sheet, line)` 序列。
- `report.ledger.open_report_ledger(path)` 打开独立账库。`review.decisions.review(catalog, ledger, packet_ids, reference_packet_id, pairs)` 接受一至三份不同编号的固定件和形如 `[('P', 'R'), ('Q', 'Q')]` 的有序请求。参考尺用选中的固定件号指定。返回 `Assessment`，`status` 为 `signed` 时带 `report` 和 `receipt`，为 `conflict` 时两者为空。签报逐项结果的 `millimeters` 为整数或 `None`，分别表示确认或未定。
- `report.readback.read(ledger, report_id)` 返回 `(SignedReport, SuccessReceipt)`，未知号返回 `None`。报告持有所选件号、尺号、修订号、参考件号、有序结果和逐件逐点出处。读取只需要签报账。

三个开库函数可在同一路径上重复调用，各自返回可用于 `with` 或显式 `close()` 的对象。应为三个职责使用不同的数据库文件。无效输入、归属错配、未冻结发行、混单、参考件未选中及未知端点抛出 `ValueError`。未知试件、修订或固定件抛出 `LookupError`。SQLite 写入及提交错误沿原异常返回，操作回滚后可重试。调用方应由业务入口管理每次事务。

## 固定件和计算规则

V1 固定件外层含 `version`、`packet_id`、`specimen`、`scale`、`revision_id` 和 `body`。正文记录局部锚点、全部具名有向偏移和逐标记出处。发行选择字典序首个已测标记作锚。交换编码使用 Python `hex` 形式的精确整数文本，包含负号和 `0x` 前缀。站内原测读坐标留在站库。不同名但同位的标记各自保留，名册中未测的标记没有读数。

每个固定件提供一次整尺测读。参考件的尺固定正向，其余件各自选整把正向或反向。每把尺在一次摆放中使用同一个整数平移。同试件同名点必须重合。无共点的各部分可独立平移。因此自对确认为 0，跨独立部分的差值未定。收到空请求仍核对选件和共同摆放，相容时可签发零项结果。未知端点拒绝。计算由固定件内容、参考尺和请求次序确定。跨次运行的业务编号独立生成，同次签报与首执以原编号绑定。

样例中 A 尺固定 P=0、Q=1，B 尺令 R 处于 0 或 2，初版 C 尺令 R 处于 −2 或 2。参考 A 的共同摆法只允许 P→R 为 +2 mm。把 C 尺的 P 从 1 勘误为 0 后，C 只允许 R 为 −1 或 1，这时交班冲突。按旧号领取仍得到初版 +2 mm 和原出处。
