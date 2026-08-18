param(
    [string]$Voice = "zh-CN-YunyangNeural"
)

$ErrorActionPreference = "Stop"

$outputRoot = "D:\dma\day2\zhiwei-os-video\public\audio\voiceover"
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$segments = @(
    @{
        Id = "01-opening"
        Rate = "+12%"
        Text = "当人工智能从一次性问答，走向长期参与组织运营，新的问题正在出现。智能体会遗忘，决策过程难以追踪，工具调用存在风险，分散的数据与系统，也难以形成真正的组织智能。"
    },
    @{
        Id = "02-positioning"
        Rate = "+2%"
        Text = "知维 O S，是面向组织的 A I 认知操作系统与智能体开放平台。它将记忆、推理、执行、治理与可观测能力整合在统一架构中，为企业级智能体提供持续运行的认知基础设施。"
    },
    @{
        Id = "03-memory"
        Rate = "+0%"
        Text = "知维 O S 为智能体建立分层长期记忆体系。对话、任务、事件和知识，不再随着会话结束而消失，而是逐步沉淀为可检索、可关联、可反思的组织记忆。智能体可以理解历史、延续上下文，并在长期协作中不断积累经验。"
    },
    @{
        Id = "04-causal"
        Rate = "+3%"
        Text = "面对复杂业务，智能体不仅要给出答案，更需要解释答案从何而来。知维 O S 通过因果内核记录任务中的关键事件、推理关系和执行路径，把不可见的决策过程转化为清晰的因果链路。每一次判断、每一次工具调用和每一个结果，都能够被追踪、审计与复盘。"
    },
    @{
        Id = "05-security"
        Rate = "+0%"
        Text = "当智能体开始调用工具、操作数据和执行任务，安全就不能依赖事后补救。知维 O S 提供运行时安全治理，通过模拟运行、默认拒绝、策略校验、隔离策略与审计追踪，为智能体建立明确边界。当前能力聚焦安全控制面与模拟运行，并持续向生产级执行环境演进。"
    },
    @{
        Id = "06-management"
        Rate = "+15%"
        Text = "知维 O S 不只是单个智能体的运行工具，更是一套面向组织的管理平台。管理者可以统一管理组织、用户、策略、审计与部署状态，在同一控制平面中完成权限配置、资源管理和运行治理。让智能体真正进入企业流程，而不是成为彼此孤立的应用。"
    },
    @{
        Id = "07-platform"
        Rate = "+3%"
        Text = "通过开放 A P I、S D K 与开发者工具，企业可以将记忆引擎、因果内核和安全控制能力快速接入现有业务系统。开发者无需重复搭建底层认知基础设施，即可创建具备长期记忆、可控执行和持续进化能力的智能体应用。"
    },
    @{
        Id = "08-scenarios"
        Rate = "+18%"
        Text = "从企业知识助手、智能客服，到运营分析、研发协作和组织决策，知维 O S 可以支撑不同类型的智能体持续学习和协同工作。组织中的经验不再散落于文档、系统和个人记忆中，而是逐步形成能够被智能体理解和使用的认知资产。"
    },
    @{
        Id = "09-closing"
        Rate = "+10%"
        Text = "我们相信，未来的组织不仅需要更多智能体，更需要一个能够承载记忆、治理行动、理解因果并持续进化的数字大脑。知维 O S，A I 认知操作系统与智能体开放平台。让每一个组织，拥有不会遗忘的大脑。"
    }
)

foreach ($segment in $segments) {
    $media = Join-Path $outputRoot "$($segment.Id).mp3"
    $subtitles = Join-Path $outputRoot "$($segment.Id).vtt"

    & uvx --python 3.11 edge-tts `
        --voice $Voice `
        --rate="$($segment.Rate)" `
        --pitch="-2Hz" `
        --text $segment.Text `
        --write-media $media `
        --write-subtitles $subtitles

    if ($LASTEXITCODE -ne 0) {
        throw "Voice generation failed for $($segment.Id)."
    }

    Write-Output "Generated $($segment.Id)"
}
