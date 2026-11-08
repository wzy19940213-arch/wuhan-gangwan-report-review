# 武汉港湾专用报告审核工具

面向中国工程检测报告的 AI 辅助审核 skill，重点用于水运、码头、桥梁、道路与桩基报告。它把审核组织为“证据核验 → 计算复核 → 单问题台账 → 原位批注 → 回读与版式验证”。

**一个问题一条批注，原文件不改。** 支持 Word（DOCX；DOC需本地兼容工具）和 PDF 的审核工作流，以及改稿后的复审。

## 能做什么

- 核对标准名称、编号、版本、适用对象、方法和判定条款，不照抄模板规范。
- 审查检测范围、抽样、设备精度/模式、检校证据、检测批次和原始记录。
- 复算代表值、合格率、极值、日期/速率、权重和评分，追踪到结论。
- 区分已确认、条件性和待核实意见，不把缺资料等同不合格。
- 按用户模板或约定格式基准检查版式、引用、签章及附件，逐处批注并验证副本。

## 安装和调用

这是一个标准 `SKILL.md` 技能包，不需要API密钥或后台服务。它提供审核流程与台账质检脚本，**不是一个自动读取并标注所有报告的一键程序**。实际批注需运行环境具备Word/PDF处理能力；规范核验需合法标准资料或官方查询能力。

在支持技能安装器的 Codex 中，可提出：

```text
请使用 skill-installer，从 https://github.com/wzy19940213-arch/wuhan-gangwan-report-review 安装 skills/wuhan-gangwan-report-review。
```

也可把`skills/wuhan-gangwan-report-review`整个目录复制到运行环境支持的skills目录。当前Codex官方文档列出的用户目录为`~/.agents/skills`；具体客户端如使用其他目录，以其配置为准。不要在多个发现路径重复安装同名技能。参考：[官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

调用示例：

```text
使用 $wuhan-gangwan-report-review 审核这份检测报告。
按所附模板检查格式，核实中国规范、设备和计算。
每处问题单独批注，保留原文件，将审核副本保存到我指定的目录。
```

复审示例：

```text
这是修改后的版本。使用 $wuhan-gangwan-report-review 逐条核对旧意见，
区分已解决、未解决和新增问题，继续在问题原位单独批注。
```

## 文件结构

```text
skills/wuhan-gangwan-report-review/
  SKILL.md                       # 主流程与边界
  agents/openai.yaml             # 中文显示名称与调用提示
  references/                    # 技术、格式、批注质检与台账规则
  scripts/validate_findings.py    # 纯标准库台账结构校验
examples/findings.synthetic.json # 完全虚构的结构示例
tests/                          # 自动化测试
evals/                          # 行为评估案例
```

## 本地测试

Python 3.9或以上，无第三方依赖：

```bash
python -m unittest discover -s tests -v
python skills/wuhan-gangwan-report-review/scripts/validate_findings.py examples/findings.synthetic.json --json
```

校验器仅验证数据结构，**不证明规范、计算、批注锚点或工程结论正确**。`calculation.expression`只作为文本存储，不执行其中表达式。

## 隐私、使用边界和许可证

仓库只包含通用流程、脚本和虚构案例，不含真实项目报告、检测数据、证书、签章或标准全文。工具不自动上传文件，也不绑定任何收费服务。对外提交issue或示例前，请自行移除项目、客户和个人信息。

本工具名称按使用者需求命名，不构成任何机构的官方认证、检测资质或专业签发。AI审核意见需由具备相应专业能力的人员结合原始记录、设计和现行适用规范复核；不能作为单独的工程安全或验收合格证明。

代码与原创说明采用 [MIT许可证](LICENSE)。项目材料和第三方标准不在此许可证授权范围内。
