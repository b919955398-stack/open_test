# Heywood BESS Native PSS/E Automation

版本：1.5.0

这是按原 Heywood 项目整体章法整理的开放版：外层保留 master、报告映射、示例和说明；所有被调用的运行逻辑统一放在 `src`。运行时不再依赖私有 `Pallet`、已安装的 `gridlink`，也不会导入旧的 `heywoodbess` editable package。

## 目录结构

```text
heywood_psse_native/
├── 001 smib studies/
│   └── 4_run_psse_master_native.py   # 唯一项目 master
├── 002 report tables/
│   ├── column_mapping_CSR.csv
│   └── column_mapping_DMAT.csv
├── examples/definitions/               # HBESS savdef/initdef/chandef
├── src/
│   ├── hbess_open/                       # Heywood 编排、分析、绘图、附录、表格
│   │   ├── analysis/clause_analysis/
│   │   ├── analysis/gridlink/           # 从所附 GridLink 源码重构的分析原语
│   │   ├── io/                          # Pallet DSL/Out 的开放替代
│   │   ├── plotting/
│   │   ├── appendices/
│   │   ├── report_tables/
│   │   └── studyrunners/
│   └── psse_open/                        # 直接调用公开 psspy API 的执行引擎
├── tests/
├── run.py                               # validate/plan/run CLI
└── setup.py
```

master 会把本项目的 `src` 强制放到 `sys.path[0]`，并在启动时打印 `hbess_open` 和 `psse_open` 的真实来源。因此之前执行过的 `pip install -e C:\...\src` 不会抢占本项目导入。

## 已完成的五段流程

- `RUN_STUDIES`：SPEC → 公开 `psspy` → `.out/.csv/.json` → Heywood PNG/PDF。
- `RUN_ANALYSIS`：dP/df、CUO、Vdroop、Vgrid/Vref/Qref/PFref step、diq/dV、F/V ride-through、Iq rise/settle/P recovery、S5.2.5.8 P reduction。
- `REPLOT_PSSE`：按文件 stem 配对结果和 JSON；优先读取相邻 CSV，旧 OUT-only 目录才调用 `dyntools`。
- `CREATE_APPENDIX`：按 CSR/DMAT、充电/放电及 SPEC 的标题/报告号生成附录 PDF。
- `CREATE_REPORT_TABLES`：根据 CSR/DMAT column mapping 输出报告 CSV 表格。

默认情况下，Study runner 会为每个案例保留下列结果：

```text
<Category>/<File_Name>.out
<Category>/<File_Name>.json
<Category>/<File_Name>.png
<Category>/<File_Name>.pdf
```

每个案例完成后会立刻转换数据并生成 PNG/PDF，再开始下一个案例。绘图用 CSV 默认是临时文件，成功画图后删除；若画图失败则保留 CSV 便于检查 chandef。Analysis、Replot、Appendix 仍共享 OUT、JSON 和同一目录结构。

模型 SAV、DYR、DLL、TXT、CFG 只复制到一个共享临时运行目录一次，整个批次结束后清理，不再生成 `_work/<File_Name>`。master 中的精简输出开关为：

```python
KEEP_CSV_RESULTS = False
SAVE_RUN_MANIFESTS = False
KEEP_RUNTIME_FILES = False
KEEP_PSSE_LOGS = False
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

`PLOT_RESULTS = True` 时，每个成功案例会立即在 `RESULTS_DIR/<Category>/` 下生成同名 PNG 和 PDF，然后才运行下一个案例。终端会逐案例显示 `STUDY OK/FAILED` 与 `PLOT OK/FAILED`；完整路径和错误写入结果根目录的 `run_status.json`。若缺少 chandef channel，错误会直接给出缺失 channel 名，而不是静默跳过。

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
