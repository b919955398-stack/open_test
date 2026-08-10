# Heywood BESS Open PSS/E Automation + PSCAD Post-processing

版本：1.7.3

这是按原 Heywood 项目整体章法整理的开放版：外层保留 PSS/E/PSCAD master、报告映射、示例和说明；所有被调用的逻辑统一放在 `src`。PSS/E 执行引擎已开放；PSCAD 已包含 Vslack/TOV SPEC 初始化、结果读取、通用 analysis/clause analysis、replot 接口、appendix 和 report tables 框架，暂不实现 PSCAD launch/project/volley runner。运行时不依赖私有 `Pallet`、已安装的 `gridlink`，也不会导入旧的 `heywoodbess` editable package。

## 目录结构

```text
heywood_psse_native/
├── 001 smib studies/
│   ├── 2_run_pscad_master_native.py  # PSCAD 后处理 master / runner 预留边界
│   └── 4_run_psse_master_native.py   # PSS/E 项目 master
├── 002 report tables/
│   ├── column_mapping_CSR.csv
│   └── column_mapping_DMAT.csv
├── examples/definitions/               # HBESS savdef/initdef/chandef
├── src/
│   ├── hbess_open/                       # Heywood 编排、分析、绘图、附录、表格
│   │   ├── initialisation/                # 开放 Vslack/TOV 两母线计算与缓存
│   │   ├── analysis/clause_analysis/
│   │   ├── analysis/run_analysis_pscad.py # 声明式 PSCAD analysis dispatcher
│   │   ├── analysis/gridlink/           # 从所附 GridLink 源码重构的分析原语
│   │   ├── io/                          # DSL、PSS/E OUT 与 PSCAD PSOUT 开放适配层
│   │   ├── plotting/
│   │   ├── appendices/
│   │   ├── report_tables/
│   │   └── studyrunners/
│   └── psse_open/                        # 直接调用公开 psspy API 的执行引擎
├── tests/
├── run.py                               # validate/plan/run CLI
└── setup.py
```

两个 master 都会把本项目的 `src` 强制放到 `sys.path[0]`，并在启动时打印 `hbess_open` 的真实来源。因此之前执行过的 `pip install -e C:\...\src` 不会抢占本项目导入。

## PSCAD 本版范围

- `hbess_open.initialisation`：直接按两母线等值方程计算 Vslack 和 TOV shunt，不调用 Pallet/pandapower。
- `USE_VSLACK_CACHE` 与 `CALC_TOV_SHUNT_VAR` 是实际生效的开关；兼容旧 `Ppoc_pu/Qpoc_pu` cache。
- `hbess_open.io.pscad_out`：直接使用官方 `mhi.psout.File` 读取 binary `.psout`；同名 `.pkl/.csv` 会优先作为快速缓存。
- 共用 clause：dP/df、CUO、Vdroop、step disturbance、diq/dV、F/V ride-through、Iq rise/settle/P recovery、S5.2.5.8 P reduction 已可使用 PSCAD 结果。
- PSCAD 专用 clause：ORT、MFRT、phase health、protection trip、maximum fault current 已重构到 `src`。
- `run_analysis_pscad`：master 只提供 job 数据，文件发现、sidecar 分组、handler 校验、输出路径和错误状态在 `src` 内完成。
- `RUN_STUDIES=False` 是有意的；当前 runner 文件只是稳定接口边界，等下一步再接 PSCAD launch/project/volley 策略。

### PSCAD Vslack / TOV 初始化

master 中可先独立准备 SPEC，不启动 PSCAD：

```python
PREPARE_PSCAD_SPEC = True
RUN_STUDIES = False

USE_VSLACK_CACHE = False
CALC_TOV_SHUNT_VAR = True
```

- `USE_VSLACK_CACHE=False`：重新计算全部 Vslack；全部成功后才原子更新 `vslack_cache.csv`。
- `USE_VSLACK_CACHE=True`：使用命中值，只计算缺失工况。
- `CALC_TOV_SHUNT_VAR=True`：优先按 `Calc_TOV=True` 选行；若整列均为 False，则计算所有具有正值 `U_Ov` 的行。
- `CALC_TOV_SHUNT_VAR=False`：不重算 TOV，保留 SPEC 已有值，并在启用 cache 时补入缓存值。

`TOV_MVAr` 沿用旧 pandapower shunt 定义，表示 1.0 pu 电压下的电容组额定 MVAr；目标电压处的实际注入量为 `TOV_MVAr * U_Ov**2`。初始化会生成旧模型需要的四列：`constant_vslack_pu_sig`、展开后的 `Vslack_pu_sig`、`TOV_MVAr`、`TOV_Shunt_C_uF_sig`。它不会保留 `_from_cache`、copy/index 等临时列，也不会打印整张 DataFrame。`PREPARE_PSCAD_SPEC=True` 时只额外写一个 `prepared_pscad_spec.csv`，方便在接 PSCAD runner 前审阅。

PSCAD master 中的 sheet、信号名、特性点、模型路径与 analysis jobs 都有意留空，避免在未确认项目内容前把 Heywood 参数写死。

### PSCAD 结果读取环境

如果目录中只有 binary `.psout`，在执行 PSCAD analysis 的 Python 中安装 MHI 官方 reader：

```bat
python -m pip install -r requirements-pscad.txt
```

请安装包名 `mhi.psout`，不要安装无关的 `mhi` 包。如果结果旁已有同名 `.pkl` 或 `.csv`，则不需要 `mhi.psout`。

## 已完成的五段流程

- `RUN_STUDIES`：SPEC → 公开 `psspy` → `.out/.csv/.json` → Heywood PNG/PDF。
- `RUN_ANALYSIS`：dP/df、CUO、Vdroop、Vgrid/Vref/Qref/PFref step、diq/dV、F/V ride-through、Iq rise/settle/P recovery、S5.2.5.8 P reduction。
- `REPLOT_PSSE`：按文件 stem 配对结果和 JSON；优先读取相邻 CSV，旧 OUT-only 目录才调用 `dyntools`。
- `CREATE_APPENDIX`：按 CSR/DMAT、充电/放电及 SPEC 的标题/报告号生成附录 PDF。
- `CREATE_REPORT_TABLES`：根据 CSR/DMAT column mapping 输出报告 CSV 表格。

## PSS/E dispatched-case cache

PSS/E runner 现在先汇总全部 selected SPEC，再按有效初始工况生成 Dispatch Key。Key 固定包含初始 P/Q/V、fault level、X/R 和 infinite-grid 状态；可能影响初始潮流的 inverter count、temperature、tap setting、control mode 字段会自动加入，也可通过 `DISPATCH_KEY_COLUMNS` 明确指定。

```text
selected SPEC rows
  -> unique Dispatch Keys
  -> each missing key: load base SAV + dispatch once + save dispatched SAV
  -> each dynamic scenario: load its dispatched SAV + initialise dynamics + run commands
```

例如 235 个动态场景只有 12 个唯一初始工况时，只执行 12 次 P/Q/V dispatch。第一批运行生成缺失 dispatched SAV 后立即复用；后续批次在模型未变化时直接 cache hit。这个过程仍是单进程顺序运行，不会额外占用并发 PSS/E licence。

cache 位于 master 的 `DISPATCH_CACHE_DIR`。namespace 会根据 source SAV、savdef/initdef/chandef、有效静态配置和 `project_hooks.py` 自动生成 fingerprint；模型发生变化时不会误用旧 SAV。通常保持：

```python
USE_DISPATCH_CACHE = True
REBUILD_DISPATCH_CACHE = False
VERIFY_DISPATCH_CACHE_HASHES = False
DISPATCH_KEY_COLUMNS = []
AUTO_DISPATCH_KEY_COLUMNS = True
```

如果 `before_dispatch` 或 `after_dispatch` 使用了额外 SPEC 字段，必须把字段名加入 `DISPATCH_KEY_COLUMNS`。只在需要强制重做相同模型 namespace 中的 dispatched SAV 时，临时设置 `REBUILD_DISPATCH_CACHE = True`。

## Plain-text run progress

master 默认 `RUN_PROGRESS_LEVEL = "commands"`，不使用颜色或 ANSI 字符。终端依次输出 `[BATCH]`、`[SPEC]`、`[DISPATCH]`、`[LOAD]`、`[COMMAND]`、`[OK]`、`[FAILED]`，包括：

- selected SPEC 数量与 category 分布；
- 完整 Dispatch Plan、每个 key 的初始 P/Q/V/grid 参数和复用数量；
- 每个 case 的关键 SPEC；
- `LOAD SAV`、`DYNAMIC INIT`、`RUN t1 -> t2`；
- 每个 fault apply/clear、grid change、model change、transformer/load/TOV command；
- study/plot 状态与 elapsed time。

`RUN_PROGRESS_LEVEL = "cases"` 只显示 case 级进度；`"quiet"` 静默。将 `SPEC_FIELDS_TO_PRINT = ["*"]` 可输出每行全部非空 SPEC 字段。

`PSSE_OUTPUT_MODE = "console"` 默认同时保留 PSS/E 自己的原生 PowerShell 输出，包括 FNSL mismatch/iteration、tap 与 machine data 改动、initial-condition check、channel 建立及动态 RUN 进度。设为 `"files"` 时会分别写入 `_report.log`、`_progress.log`、`_alert.log` 和 `_prompt.log`；设为 `"quiet"` 才会静默这些原生流。这个开关只改变可见性，不改变 dispatch 或动态仿真数值。

默认情况下，Study runner 会为每个案例保留下列结果：

```text
<Category>/<File_Name>.out
<Category>/<File_Name>.json
<Category>/<File_Name>.png
<Category>/<File_Name>.pdf
```

每个案例完成后会立刻转换数据并生成 PNG/PDF，再开始下一个案例。dispatched SAV cache 不改变这一顺序。绘图用 CSV 默认是临时文件，成功画图后删除；若画图失败则保留 CSV 便于检查 chandef。Analysis、Replot、Appendix 仍共享 OUT、JSON 和同一目录结构。

模型 SAV、DYR、DLL、TXT、CFG 只复制到一个共享临时运行目录一次，整个批次结束后清理，不再生成 `_work/<File_Name>`。master 中的精简输出开关为：

```python
KEEP_CSV_RESULTS = False
SAVE_RUN_MANIFESTS = False
KEEP_RUNTIME_FILES = False
KEEP_PSSE_LOGS = False
PSSE_OUTPUT_MODE = "console"
```

需要排查问题时可单独打开相应开关；正常批量运行保持 `False` 可以显著减少磁盘文件和重复复制。

## 安装与运行

使用与 PSS/E 匹配的 Python。你的环境是 PSS/E 34 / Python 3.9 32-bit，建议直接使用该解释器：

```bat
cd /d C:\Grid\heywood_psse_native
python -m pip install -r requirements.txt
python -m unittest discover -v
python "001 smib studies\4_run_psse_master_native.py"
```

PSCAD 后处理框架入口为：

```bat
python "001 smib studies\2_run_pscad_master_native.py"
```

新 PSCAD master 的五个开关默认全部为 `False`；先填写 sheet、analysis job 和 channel mapping，再单独打开需要的阶段。

不需要 `pip install -e .`。如希望安装 CLI，也可以选择执行：

```bat
python -m pip install -e .
```

在 master 中修改：

- `SPEC_OPTIONS` 中的工作簿、sheet 选择和场景筛选；
- `MODEL_DIR`、`RESULTS_ROOT` 和 slack bus；
- 五个运行开关；
- Analysis 特性点、Appendix 标题/日期/版本等项目参数。

## SPEC options

master 只使用一个 `SPEC_OPTIONS` 配置块。`sources` 中可启用/停用工作簿，并设置它参与 `studies`、`appendix`、`tables` 中的哪些流程。空 sheet 列表会跳过该工作簿，不要求文件存在。

```python
"sheets": ["5255_*", "!5255_*_OLD"],
"filters": {"Test No": {"<=": 12}, "Batch": {"==": 2}},
"include_categories": ["*Fault*"],
"exclude_file_names": ["*_OLD"],
"text_filter": None,
"limit": None,
"duplicate_policy": "error",
```

sheet 和文件名支持 `*`、`?` 通配符；sheet 前加 `!` 表示排除。行筛选支持 `==`、`!=`、`>`、`>=`、`<`、`<=`、`in`、`not in` 和 `between`，也可简写成 `"Batch": "== 2"`。`enabled_only` 会稳健识别布尔值、`1/0`、`yes/no` 和 `on/off`。加载结果包含 `Spec_Source`、`Spec_Path`、`Sheet_Name`、`Spec_Row`，因此缺失 sheet、错误筛选列或重复 `File_Name` 都会给出可定位的信息。

`PLOT_RESULTS = True` 时，每个成功案例会立即在 `RESULTS_DIR/<Category>/` 下形成同名 DYR、JSON、OUT、PNG、PDF 和 `_initialised.sav` 文件组，然后才运行下一个案例。`_initialised.sav` 在 DYR、动态参数和 channels 装载完成后、`STRT` 前保存；它与内部 `_dispatch_cache` 的静态 dispatched SAV 分开。终端会显示 SPEC、Dispatch Key、时间推进、command、`STUDY OK/FAILED` 与 `PLOT OK/FAILED`；完整路径、cache 状态、elapsed time 和错误写入结果根目录的 `run_status.json`。若缺少 chandef channel，错误会直接给出缺失 channel 名，而不是静默跳过。

`MODEL_DIR` 应包含 SAV、DYR、`.savdef`、`.initdef`、`.chandef` 以及 OEM 模型所需 DLL/TXT/CFG。存在多份版本时，将 `open_psse_config.example.json` 复制为该目录下的 `open_psse_config.json` 并指定文件名。

PSS/E 34 的标准目录会自动检测：

```text
C:\Program Files (x86)\PTI\PSSE34\PSSPY39
C:\Program Files (x86)\PTI\PSSE34\PSSBIN
```

非标准安装位置可在 `open_psse_config.json` 中设置 `psse.python_path` 和 `psse.bin_path`。

## Appendix 额外要求

附录继续采用原项目的 `grid-link-appendix-template.cls` 和品牌 assets。Windows 上需安装 MiKTeX 或 TeX Live，并确保 `xelatex.exe` 在 PATH 中。生成器使用独立临时目录，不会重命名或删除原 plots。

## 离线检查

以下命令不导入 PSS/E：

```bat
python run.py validate --spec HY_Spec_CSR_300.xlsx --sheets 5255_BalFaults
python run.py plan --spec HY_Spec_CSR_300.xlsx --sheets 5255_BalFaults --output study_plan.json
```

Linux 工作区无法执行带许可证和 OEM DLL 的真实 PSS/E 动态仿真；发布项目前仍应在目标 Windows/PSS/E 机器上抽取 flatrun、一个 fault、一个 V/f playback 和一个 reference step，与原 runner 对比电气结果和通道。
